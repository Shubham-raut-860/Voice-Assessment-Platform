from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, VapiCallMode
from app.dependencies import get_current_user, get_db, get_settings, require_role
from app.exceptions import AssessmentNotFoundError, SessionNotFoundError
from app.models.assessment_session import AssessmentSession
from app.models.user import User
from app.schemas.enums import SessionStatus, UserRole
from app.schemas.session import (
    SessionCreate,
    SessionListResponse,
    SessionResponse,
    SessionUpdate,
    StartCallRequest,
    StartCallResponse,
    BindWebCallRequest,
)
from app.services.session_service import (
    archive_session,
    create_session,
    get_session,
    initiate_vapi_call,
    list_sessions,
    update_session,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session_route(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.ASSESSOR)),
) -> AssessmentSession:
    try:
        return await create_session(db, data, current_user)
    except AssessmentNotFoundError as exc:
        raise _assessment_not_found(data.assessment_id) from exc


@router.get("", response_model=SessionListResponse)
async def list_sessions_route(
    page: int = 1,
    page_size: int = Query(default=20, le=100),
    candidate_id: UUID | None = None,
    assessment_id: UUID | None = None,
    session_status: SessionStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionListResponse:
    sessions, total = await list_sessions(
        db,
        page=page,
        page_size=page_size,
        candidate_id=candidate_id,
        assessment_id=assessment_id,
        status=session_status,
        requester=current_user,
    )
    return SessionListResponse(items=sessions, total=total, page=page, page_size=page_size)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_route(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssessmentSession:
    try:
        return await get_session(db, session_id, current_user)
    except SessionNotFoundError as exc:
        raise _session_not_found(session_id) from exc


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session_route(
    session_id: UUID,
    data: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> AssessmentSession:
    try:
        return await update_session(db, session_id, data, current_user)
    except SessionNotFoundError as exc:
        raise _session_not_found(session_id) from exc


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_session_route(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    try:
        await archive_session(db, session_id, current_user)
    except SessionNotFoundError as exc:
        raise _session_not_found(session_id) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/start-call", response_model=StartCallResponse)
async def start_call_route(
    session_id: UUID,
    data: StartCallRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> StartCallResponse:
    try:
        session = await get_session(db, session_id, current_user)
    except SessionNotFoundError as exc:
        raise _session_not_found(session_id) from exc

    if current_user.role == UserRole.CANDIDATE:
        if settings.vapi_call_mode != VapiCallMode.WEB or session.candidate_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="requires_role:admin,assessor",
            )
        return await initiate_vapi_call(db, session, settings, None)

    if current_user.role not in {UserRole.ADMIN, UserRole.ASSESSOR}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires_role:admin,assessor",
        )

    return await initiate_vapi_call(db, session, settings, data.customer_number)


@router.post("/{session_id}/bind-web-call", response_model=SessionResponse)
async def bind_web_call_route(
    session_id: UUID,
    data: BindWebCallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssessmentSession:
    try:
        session = await get_session(db, session_id, current_user)
    except SessionNotFoundError as exc:
        raise _session_not_found(session_id) from exc

    if current_user.role == UserRole.CANDIDATE and session.candidate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="session_access_denied",
        )

    if session.vapi_call_id is not None and session.vapi_call_id != data.call_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="session_call_already_bound",
        )

    session.vapi_call_id = data.call_id
    session.status = SessionStatus.IN_PROGRESS
    if session.started_at is None:
        session.started_at = datetime.now(UTC)

    await db.commit()
    return await get_session(db, session_id, current_user)


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
