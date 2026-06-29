from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.exceptions import AssessmentNotFoundError
from app.models.assessment import Assessment
from app.models.user import User
from app.schemas.assessment import (
    AssessmentCreate,
    AssessmentListResponse,
    AssessmentResponse,
    AssessmentUpdate,
)
from app.schemas.enums import AssessmentStatus, UserRole
from app.services.assessment_service import (
    archive_assessment,
    create_assessment,
    get_assessment,
    list_assessments,
    update_assessment,
)

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assessment_route(
    data: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.ASSESSOR)),
) -> Assessment:
    return await create_assessment(db, data, current_user)


@router.get("", response_model=AssessmentListResponse)
async def list_assessments_route(
    page: int = 1,
    page_size: int = Query(default=20, le=100),
    assessment_status: AssessmentStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.ASSESSOR)),
) -> AssessmentListResponse:
    _ = current_user
    assessments, total = await list_assessments(db, page, page_size, assessment_status)
    return AssessmentListResponse(items=assessments, total=total, page=page, page_size=page_size)


@router.get("/{assessment_id}", response_model=AssessmentResponse)
async def get_assessment_route(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.ASSESSOR)),
) -> Assessment:
    _ = current_user
    try:
        return await get_assessment(db, assessment_id)
    except AssessmentNotFoundError as exc:
        raise _assessment_not_found(assessment_id) from exc


@router.patch("/{assessment_id}", response_model=AssessmentResponse)
async def update_assessment_route(
    assessment_id: UUID,
    data: AssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> Assessment:
    try:
        return await update_assessment(db, assessment_id, data, current_user)
    except AssessmentNotFoundError as exc:
        raise _assessment_not_found(assessment_id) from exc


@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_assessment_route(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    try:
        await archive_assessment(db, assessment_id, current_user)
    except AssessmentNotFoundError as exc:
        raise _assessment_not_found(assessment_id) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _assessment_not_found(assessment_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "assessment_not_found", "id": str(assessment_id)},
    )
