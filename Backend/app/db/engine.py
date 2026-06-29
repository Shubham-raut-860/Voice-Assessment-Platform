from __future__ import annotations

from collections.abc import AsyncIterator

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

logger = structlog.get_logger(__name__)


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def connect_database(engine: AsyncEngine) -> None:
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("database_pool_connected")
    except SQLAlchemyError as exc:
        logger.exception("database_pool_connect_failed", error=str(exc))
        raise


async def dispose_database(engine: AsyncEngine) -> None:
    try:
        await engine.dispose()
        logger.info("database_pool_disposed")
    except SQLAlchemyError as exc:
        logger.exception("database_pool_dispose_failed", error=str(exc))
        raise


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.exception("database_session_failed", error=str(exc))
            raise
        finally:
            await session.close()
