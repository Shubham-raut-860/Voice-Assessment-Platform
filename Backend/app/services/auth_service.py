from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog
from fastapi import HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.enums import UserRole

logger = structlog.get_logger(__name__)
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.CRITICAL)
password_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
    bcrypt__truncate_error=True,
)
DUMMY_PASSWORD_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeOEmI7qC0fbXQ15ka8Y0m9tyj/mzN9G3G"


def authenticate_header() -> dict[str, str]:
    return {"WWW-Authenticate": "Bearer"}


def hash_password(plain: str) -> str:
    return password_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return password_context.verify(plain, hashed)


def create_access_token(user: User, settings: Settings) -> str:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, object] = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": expires_at,
        "iat": issued_at,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    # python-jose returns heterogenous claim values, so Any is unavoidable at this boundary.
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError as exc:
        logger.warning("jwt_expired", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_expired",
            headers=authenticate_header(),
        ) from exc
    except JWTError as exc:
        logger.warning("jwt_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token",
            headers=authenticate_header(),
        ) from exc

    return claims


async def register_user(db: AsyncSession, data: RegisterRequest, settings: Settings) -> User:
    normalized_email = str(data.email).lower()
    requested_role = data.role
    validate_signup_role(requested_role, data.invite_code, settings)

    try:
        existing_user_query: Select[tuple[User]] = select(User).where(
            func.lower(User.email) == normalized_email,
            User.deleted_at.is_(None),
        )
        existing_user_result = await db.execute(existing_user_query)
        existing_user = existing_user_result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("register_user_email_lookup_failed", email=normalized_email, error=str(exc))
        raise

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email_already_registered",
        )

    user = User(
        email=normalized_email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=requested_role,
        is_verified=not settings.require_email_verification,
    )

    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except IntegrityError as exc:
        await db.rollback()
        logger.warning("register_user_integrity_error", email=normalized_email, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email_already_registered",
        ) from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("register_user_failed", email=normalized_email, error=str(exc))
        raise

    logger.info(
        "user_registered",
        user_id=str(user.id),
        email=normalized_email,
        role=user.role.value,
        is_verified=user.is_verified,
        require_email_verification=settings.require_email_verification,
        environment=settings.environment.value,
    )
    return user


def validate_signup_role(role: UserRole, invite_code: str | None, settings: Settings) -> None:
    if role == UserRole.CANDIDATE:
        return

    if role == UserRole.ADMIN:
        configured_code = settings.admin_signup_invite_code
    else:
        configured_code = settings.staff_signup_invite_code or settings.admin_signup_invite_code

    if configured_code is None:
        logger.warning("staff_signup_disabled", requested_role=role.value)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="staff_signup_disabled",
        )

    if invite_code is None or not hmac.compare_digest(invite_code, configured_code):
        logger.warning("staff_signup_invalid_invite_code", requested_role=role.value)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid_invite_code",
        )


async def authenticate_user(db: AsyncSession, email: str, password: str, settings: Settings) -> User | None:
    normalized_email = email.lower()

    try:
        query: Select[tuple[User]] = select(User).where(
            func.lower(User.email) == normalized_email,
            User.deleted_at.is_(None),
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("authenticate_user_lookup_failed", email=normalized_email, error=str(exc))
        raise

    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if not user.is_active:
        logger.info("inactive_user_login_rejected", user_id=str(user.id), email=normalized_email)
        return None

    if settings.require_email_verification and not user.is_verified:
        logger.info("unverified_user_login_rejected", user_id=str(user.id), email=normalized_email)
        return None

    return user
