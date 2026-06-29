from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

DEFAULT_RATE_LIMIT = "100/minute"
AUTH_RATE_LIMIT = "10/minute"
WEBHOOK_RATE_LIMIT = "60/minute"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[DEFAULT_RATE_LIMIT],
    headers_enabled=True,
)


async def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    _ = request
    retry_after = _extract_retry_after(exc)
    return JSONResponse(
        status_code=429,
        content={
            "detail": "rate_limit_exceeded",
            "retry_after": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


def _extract_retry_after(exc: RateLimitExceeded) -> int:
    headers = getattr(exc, "headers", None)
    if isinstance(headers, dict):
        retry_after_raw = headers.get("Retry-After")
        if isinstance(retry_after_raw, str) and retry_after_raw.isdigit():
            return int(retry_after_raw)
    return 60
