from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AssessmentNotFoundError
from app.models.assessment import Assessment
from app.models.user import User
from app.schemas.assessment import AssessmentCreate, AssessmentUpdate
from app.schemas.enums import AssessmentStatus, UserRole

logger = structlog.get_logger(__name__)


async def create_assessment(
    db: AsyncSession,
    data: AssessmentCreate,
    creator: User,
) -> Assessment:
    _ensure_assessment_writer(creator)
    assessment = Assessment(
        title=data.title,
        description=data.description,
        status=data.status,
        vapi_assistant_id=data.vapi_assistant_id,
        passing_score=data.passing_score,
        time_limit_minutes=data.time_limit_minutes,
        created_by_id=creator.id,
    )
    try:
        db.add(assessment)
        await db.commit()
        await db.refresh(assessment)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("assessment_create_failed", creator_id=str(creator.id), error=str(exc))
        raise

    logger.info("assessment_created", assessment_id=str(assessment.id), creator_id=str(creator.id))
    return assessment


async def get_assessment(db: AsyncSession, id: UUID) -> Assessment:
    try:
        query: Select[tuple[Assessment]] = select(Assessment).where(
            Assessment.id == id,
            Assessment.deleted_at.is_(None),
        )
        result = await db.execute(query)
        assessment = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("assessment_get_failed", assessment_id=str(id), error=str(exc))
        raise

    if assessment is None:
        raise AssessmentNotFoundError(f"assessment_not_found:{id}")
    return assessment


async def list_assessments(
    db: AsyncSession,
    page: int,
    page_size: int,
    status: AssessmentStatus | None,
) -> tuple[list[Assessment], int]:
    filters = [Assessment.deleted_at.is_(None)]
    if status is not None:
        filters.append(Assessment.status == status)

    try:
        total_query = select(func.count()).select_from(Assessment).where(*filters)
        total = int((await db.execute(total_query)).scalar_one())

        query: Select[tuple[Assessment]] = (
            select(Assessment)
            .where(*filters)
            .order_by(Assessment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)
        assessments = list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.exception("assessment_list_failed", status=status, error=str(exc))
        raise

    return assessments, total


async def update_assessment(
    db: AsyncSession,
    id: UUID,
    data: AssessmentUpdate,
    requester: User,
) -> Assessment:
    _ensure_admin(requester)
    assessment = await get_assessment(db, id)
    update_data = data.model_dump(exclude_unset=True)

    for field_name, value in update_data.items():
        setattr(assessment, field_name, value)

    try:
        await db.commit()
        await db.refresh(assessment)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception(
            "assessment_update_failed",
            assessment_id=str(id),
            requester_id=str(requester.id),
            error=str(exc),
        )
        raise

    logger.info("assessment_updated", assessment_id=str(id), requester_id=str(requester.id))
    return assessment


async def archive_assessment(db: AsyncSession, id: UUID, requester: User) -> None:
    _ensure_admin(requester)
    assessment = await get_assessment(db, id)
    assessment.status = AssessmentStatus.ARCHIVED
    assessment.deleted_at = datetime.now(UTC)

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception(
            "assessment_archive_failed",
            assessment_id=str(id),
            requester_id=str(requester.id),
            error=str(exc),
        )
        raise

    logger.info("assessment_archived", assessment_id=str(id), requester_id=str(requester.id))


def _ensure_assessment_writer(user: User) -> None:
    if user.role not in {UserRole.ADMIN, UserRole.ASSESSOR}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires_role:admin,assessor",
        )


def _ensure_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires_role:admin",
        )
