from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import structlog
from fastapi import HTTPException, status

from app.services.auth_service import authenticate_header

logger = structlog.get_logger(__name__)


class RedisClient(Protocol):
    async def set(self, name: str, value: str, ex: int) -> object:
        raise NotImplementedError

    async def get(self, name: str) -> object:
        raise NotImplementedError

    async def aclose(self) -> object:
        raise NotImplementedError


def revocation_key(jti: str) -> str:
    return f"jwt:revoked:{jti}"


async def create_redis_client(redis_url: str) -> RedisClient:
    try:
        from redis.asyncio import Redis
        from redis.exceptions import RedisError
    except ImportError as exc:
        logger.exception("redis_sdk_not_installed")
        raise RuntimeError("redis_sdk_not_installed") from exc

    try:
        client = Redis.from_url(redis_url, decode_responses=True)
        await client.ping()
    except RedisError as exc:
        logger.exception("redis_connection_failed", error=str(exc))
        raise RuntimeError("redis_connection_failed") from exc

    logger.info("redis_connected")
    return client


async def close_redis_client(redis_client: RedisClient | None) -> None:
    if redis_client is None:
        return
    try:
        await redis_client.aclose()
    except Exception as exc:
        logger.warning("redis_close_failed", error=str(exc))


async def revoke_access_token(
    redis_client: RedisClient,
    jti: str,
    expires_at: datetime,
) -> None:
    ttl_seconds = int((expires_at - datetime.now(UTC)).total_seconds())
    if ttl_seconds <= 0:
        logger.info("jwt_revocation_skipped_expired_token", jti=jti)
        return

    try:
        await redis_client.set(revocation_key(jti), "1", ex=ttl_seconds)
    except Exception as exc:
        logger.exception("jwt_revocation_store_failed", jti=jti, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="token_revocation_unavailable",
        ) from exc

    logger.info("jwt_revoked", jti=jti, ttl_seconds=ttl_seconds)


async def ensure_token_not_revoked(redis_client: RedisClient | None, jti: str | None) -> None:
    if redis_client is None:
        return
    if jti is None or jti.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token_jti",
            headers=authenticate_header(),
        )

    try:
        revoked = await redis_client.get(revocation_key(jti))
    except Exception as exc:
        logger.exception("jwt_revocation_lookup_failed", jti=jti, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="token_revocation_unavailable",
        ) from exc

    if revoked is not None:
        logger.info("revoked_jwt_rejected", jti=jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_revoked",
            headers=authenticate_header(),
        )
