from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter

import structlog
from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = perf_counter()
        status_code = 500
        response: Response | None = None

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            request_id = getattr(request.state, "request_id", None)
            user_id = _extract_user_id(request)
            log_method = logger.info
            if status_code >= 500:
                log_method = logger.error
            elif status_code >= 400:
                log_method = logger.warning

            log_method(
                "http_request_completed",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                user_id=user_id,
            )


def _extract_user_id(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None

    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or token.strip() == "":
        return None

    try:
        claims = jwt.get_unverified_claims(token)
    except JWTError:
        return None

    subject = claims.get("sub")
    if isinstance(subject, str) and subject.strip() != "":
        return subject
    return None
