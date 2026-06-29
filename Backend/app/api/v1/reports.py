from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.exceptions import SessionNotFoundError
from app.models.assessment_report import AssessmentReport
from app.models.user import User
from app.schemas.enums import ReportStatus
from app.schemas.report import ReportGenerationStatus, ReportResponse
from app.services.session_service import get_session

router = APIRouter(tags=["reports"])


@router.get("/sessions/{session_id}/report", response_model=ReportResponse | ReportGenerationStatus)
async def get_session_report_route(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssessmentReport | ReportGenerationStatus:
    try:
        session = await get_session(db, session_id, current_user)
    except SessionNotFoundError as exc:
        raise _session_not_found(session_id) from exc

    if session.report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "id": str(session_id)},
        )

    if session.report.generation_status != ReportStatus.COMPLETED:
        return ReportGenerationStatus(
            session_id=session.id,
            status=session.report.generation_status,
            generated_at=session.report.generated_at,
        )

    return session.report


def _session_not_found(session_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "session_not_found", "id": str(session_id)},
    )
