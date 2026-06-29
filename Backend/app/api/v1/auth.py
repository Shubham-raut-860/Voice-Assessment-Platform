from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, TypeAlias, cast

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies import get_current_user, get_db, get_redis_client, get_settings, oauth2_scheme
from app.middleware.rate_limit import AUTH_RATE_LIMIT, limiter
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.auth_service import (
    authenticate_header,
    authenticate_user,
    create_access_token,
    decode_access_token,
    register_user,
)
from app.services.token_revocation_service import RedisClient, revoke_access_token

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class OAuth2PasswordLoginRequest(BaseModel):
    username: EmailStr
    password: str = Field(min_length=1, max_length=72)
    grant_type: str | None = None
    scope: str = ""
    client_id: str | None = None
    client_secret: str | None = None


LoginPayload: TypeAlias = LoginRequest | OAuth2PasswordLoginRequest


async def parse_login_payload(
    request: Request,
    json_payload: Annotated[LoginPayload | None, Body()] = None,
) -> LoginRequest:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/x-www-form-urlencoded") or content_type.startswith(
        "multipart/form-data"
    ):
        form = await request.form()
        form_payload: dict[str, object] = {
            "username": form.get("username"),
            "password": form.get("password"),
            "grant_type": form.get("grant_type"),
            "scope": form.get("scope", ""),
            "client_id": form.get("client_id"),
            "client_secret": form.get("client_secret"),
        }
        try:
            oauth_payload = OAuth2PasswordLoginRequest.model_validate(form_payload)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.errors(),
            ) from exc
        return LoginRequest(email=oauth_payload.username, password=oauth_payload.password)

    if json_payload is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="login_payload_required",
        )

    if isinstance(json_payload, OAuth2PasswordLoginRequest):
        return LoginRequest(email=json_payload.username, password=json_payload.password)
    return json_payload


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(AUTH_RATE_LIMIT)
async def register(
    request: Request,
    response: Response,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    _ = request
    _ = response
    return await register_user(db, data, settings)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest = Depends(parse_login_payload),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    _ = request
    _ = response
    user = await authenticate_user(db, str(payload.email), payload.password, settings)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
            headers=authenticate_header(),
        )

    token = create_access_token(user, settings)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/logout", status_code=status.HTTP_202_ACCEPTED)
async def logout(
    response: Response,
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    redis_client: RedisClient | None = Depends(get_redis_client),
) -> dict[str, str]:
    _ = response
    claims = decode_access_token(token, settings)
    jti = claims.get("jti")
    expires_at = _expiration_from_claim(claims.get("exp"))

    if redis_client is None:
        logger.info("user_logout_requested_without_redis", user_id=str(current_user.id))
        return {"status": "accepted", "note": "token_remains_valid_until_expiry"}

    if not isinstance(jti, str) or jti.strip() == "" or expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token_revocation_claims",
            headers=authenticate_header(),
        )

    await revoke_access_token(redis_client, jti, expires_at)
    logger.info("user_logout_revoked_token", user_id=str(current_user.id), jti=jti)
    return {"status": "revoked", "note": "token_revoked_until_expiry"}


def _expiration_from_claim(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), tz=UTC)
    return None
