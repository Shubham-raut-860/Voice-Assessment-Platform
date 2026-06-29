from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import cast
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models.user import User
from app.schemas.enums import UserRole
from app.services.auth_service import authenticate_header, decode_access_token
from app.services.token_revocation_service import RedisClient, ensure_token_not_revoked

logger = structlog.get_logger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)


def get_redis_client(request: Request) -> RedisClient | None:
    return cast(RedisClient | None, request.app.state.redis_client)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with session_factory() as session:
        try:
            yield session
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.exception("database_session_error", error=str(exc))
            raise
        finally:
            await session.close()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis_client: RedisClient | None = Depends(get_redis_client),
) -> User:
    claims = decode_access_token(token, settings)
    jti = claims.get("jti")
    await ensure_token_not_revoked(redis_client, jti if isinstance(jti, str) else None)

    subject = claims.get("sub")
    if not isinstance(subject, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token_subject",
            headers=authenticate_header(),
        )

    try:
        user_id = UUID(subject)
    except ValueError as exc:
        logger.warning("jwt_subject_invalid_uuid", subject=subject)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token_subject",
            headers=authenticate_header(),
        ) from exc

    try:
        query: Select[tuple[User]] = select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("current_user_lookup_failed", user_id=str(user_id), error=str(exc))
        raise

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token_user",
            headers=authenticate_header(),
        )

    token_role = claims.get("role")
    if not isinstance(token_role, str) or token_role != user.role.value:
        logger.warning("jwt_role_mismatch", user_id=str(user.id), token_role=token_role)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token_role",
            headers=authenticate_header(),
        )

    return user


def require_role(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    allowed_roles = set(roles)

    async def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            allowed_values = ", ".join(role.value for role in roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires_role:{allowed_values}",
            )
        return current_user

    return role_dependency
