from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.dependencies import get_db, get_session_factory, get_settings, require_role
from app.exceptions import AssessmentNotFoundError, SessionNotFoundError
from app.models.user import User
from app.schemas.analytics import AssessmentPerformanceStats, PlatformStats
from app.schemas.enums import UserRole
from app.schemas.session import SessionListResponse
from app.schemas.user import UserCreate, UserListResponse, UserResponse
from app.services.analytics_service import (
    get_assessment_performance,
    get_platform_stats,
    list_failed_sessions,
    retry_report_generation,
)
from app.services.anthropic_service import trigger_report_generation_background
from app.services.auth_service import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


@router.get(
    "/stats",
    response_model=PlatformStats,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def get_admin_stats_route(db: AsyncSession = Depends(get_db)) -> PlatformStats:
    return await get_platform_stats(db)


@router.get(
    "/assessments/{assessment_id}/performance",
    response_model=AssessmentPerformanceStats,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def get_assessment_performance_route(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AssessmentPerformanceStats:
    try:
        return await get_assessment_performance(db, assessment_id)
    except AssessmentNotFoundError as exc:
        raise _assessment_not_found(assessment_id) from exc


@router.get(
    "/sessions/failed",
    response_model=SessionListResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def list_failed_sessions_route(
    page: int = 1,
    page_size: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    sessions, total = await list_failed_sessions(db, page, page_size)
    return SessionListResponse(items=sessions, total=total, page=page, page_size=page_size)


@router.post(
    "/sessions/{session_id}/retry-report",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def retry_report_generation_route(
    session_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> dict[str, bool]:
    try:
        await retry_report_generation(db, session_id)
    except SessionNotFoundError as exc:
        raise _session_not_found(session_id) from exc
    background_tasks.add_task(trigger_report_generation_background, session_id, session_factory, settings)
    return {"accepted": True}


@router.get(
    "/users",
    response_model=UserListResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def list_admin_users_route(
    page: int = 1,
    page_size: int = Query(default=20, le=100),
    role: UserRole | None = None,
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    users, total = await _list_users(db, page, page_size, role)
    return UserListResponse(items=users, total=total, page=page, page_size=page_size)


@router.get(
    "/users/lookup",
    response_model=UserResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def lookup_admin_user_route(
    email: EmailStr,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _get_user_by_email(db, str(email).lower())
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found", "email": str(email).lower()},
        )
    return user


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def create_admin_user_route(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    normalized_email = str(data.email).lower()
    existing = await _get_user_by_email(db, normalized_email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email_already_registered",
        )

    user = User(
        email=normalized_email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        is_active=True,
        is_verified=True,
    )

    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email_already_registered",
        ) from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "user_create_failed", "email": normalized_email},
        ) from exc
    return user


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def update_admin_user_route(
    user_id: UUID,
    data: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _get_user(db, user_id)
    update_data = data.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(user, field_name, value)

    try:
        await db.commit()
        await db.refresh(user)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "user_update_failed", "id": str(user_id)},
        ) from exc
    return user


async def _list_users(
    db: AsyncSession,
    page: int,
    page_size: int,
    role: UserRole | None,
) -> tuple[list[User], int]:
    filters = [User.deleted_at.is_(None)]
    if role is not None:
        filters.append(User.role == role)

    total = int((await db.execute(select(func.count(User.id)).where(*filters))).scalar_one())
    query: Select[tuple[User]] = (
        select(User)
        .where(*filters)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def _get_user(db: AsyncSession, user_id: UUID) -> User:
    query: Select[tuple[User]] = select(User).where(
        User.id == user_id,
        User.deleted_at.is_(None),
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found", "id": str(user_id)},
        )
    return user


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    query: Select[tuple[User]] = select(User).where(
        func.lower(User.email) == email,
        User.deleted_at.is_(None),
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


def _session_not_found(session_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "session_not_found", "id": str(session_id)},
    )


def _assessment_not_found(assessment_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "assessment_not_found", "id": str(assessment_id)},
    )
