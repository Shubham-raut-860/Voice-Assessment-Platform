from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

import structlog
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.api import v1_router
from app.config import Settings
from app.db.engine import connect_database, create_engine, create_sessionmaker, dispose_database
from app.dependencies import get_db, get_settings
from app.logging_config import configure_logging
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.token_revocation_service import RedisClient, close_redis_client, create_redis_client

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = cast(Settings, app.state.settings)
    configure_logging(settings)

    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis_client = None

    logger.info("application_starting", environment=settings.environment)
    await connect_database(engine)
    if settings.redis_url is not None and settings.redis_url.strip() != "":
        app.state.redis_client = await create_redis_client(settings.redis_url)
    logger.info("application_started", environment=settings.environment)

    try:
        yield
    finally:
        logger.info("application_stopping", environment=settings.environment)
        await close_redis_client(cast(RedisClient | None, app.state.redis_client))
        await dispose_database(engine)
        logger.info("application_stopped", environment=settings.environment)


def create_app() -> FastAPI:
    bootstrap_settings = Settings()
    configure_logging(bootstrap_settings)

    app = FastAPI(
        title="Voice Assessment API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = bootstrap_settings
    app.state.redis_client = None
    app.state.limiter = limiter

    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=bootstrap_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=bootstrap_settings)
    app.add_middleware(RequestLoggingMiddleware)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id: str = str(uuid4())
        request.state.request_id = request_id
        clear_contextvars()
        bind_contextvars(request_id=request_id)

        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            clear_contextvars()

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = cast(str | None, getattr(request.state, "request_id", None))
        logger.exception(
            "unhandled_exception",
            request_id=request_id,
            error=str(exc),
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "internal_server_error",
                "request_id": request_id,
            },
        )

    @app.get("/health")
    async def health_check(
        session: AsyncSession = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> JSONResponse:
        try:
            await session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            logger.warning("health_database_check_failed", error=str(exc))
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unhealthy",
                    "environment": settings.environment.value,
                    "db": "disconnected",
                },
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ok",
                "environment": settings.environment.value,
                "db": "connected",
            },
        )

    @app.get("/ready")
    async def readiness_check(
        session: AsyncSession = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> JSONResponse:
        try:
            await session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            logger.warning("readiness_database_check_failed", error=str(exc))
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "environment": settings.environment.value,
                    "db": "disconnected",
                },
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ready",
                "environment": settings.environment.value,
                "db": "connected",
            },
        )

    app.include_router(v1_router)
    return app


app = create_app()
