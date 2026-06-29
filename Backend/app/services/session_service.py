from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx
import structlog
from fastapi import HTTPException, status as http_status
from sqlalchemy import Select, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, VapiCallMode
from app.exceptions import AssessmentNotFoundError, SessionNotFoundError
from app.models.assessment import Assessment
from app.models.assessment_session import AssessmentSession
from app.models.user import User
from app.schemas.enums import AssessmentStatus, SessionStatus, UserRole
from app.schemas.session import SessionCreate, SessionUpdate, StartCallResponse

logger = structlog.get_logger(__name__)


async def create_session(
    db: AsyncSession,
    data: SessionCreate,
    requester: User,
) -> AssessmentSession:
    _ensure_session_writer(requester)
    assessment = await _get_active_assessment(db, data.assessment_id)

    session = AssessmentSession(
        assessment_id=assessment.id,
        candidate_id=data.candidate_id,
        assessor_id=data.assessor_id,
        vapi_call_id=None,
        status=SessionStatus.SCHEDULED,
        scheduled_at=data.scheduled_at,
    )

    try:
        db.add(session)
        await db.commit()
        return await get_session(db, session.id, requester)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception(
            "session_create_failed",
            assessment_id=str(data.assessment_id),
            requester_id=str(requester.id),
            error=str(exc),
        )
        raise


async def get_session(db: AsyncSession, id: UUID, requester: User) -> AssessmentSession:
    try:
        query: Select[tuple[AssessmentSession]] = (
            select(AssessmentSession)
            .options(
                selectinload(AssessmentSession.assessment),
                selectinload(AssessmentSession.candidate),
                selectinload(AssessmentSession.assessor),
                selectinload(AssessmentSession.report),
            )
            .where(
                AssessmentSession.id == id,
                AssessmentSession.deleted_at.is_(None),
            )
        )
        result = await db.execute(query)
        session = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("session_get_failed", session_id=str(id), requester_id=str(requester.id), error=str(exc))
        raise

    if session is None:
        raise SessionNotFoundError(f"session_not_found:{id}")

    _ensure_session_read_allowed(session, requester)
    return session


async def list_sessions(
    db: AsyncSession,
    page: int,
    page_size: int,
    candidate_id: UUID | None,
    assessment_id: UUID | None,
    status: SessionStatus | None,
    requester: User,
) -> tuple[list[AssessmentSession], int]:
    filters = [AssessmentSession.deleted_at.is_(None)]
    if candidate_id is not None:
        filters.append(AssessmentSession.candidate_id == candidate_id)
    if assessment_id is not None:
        filters.append(AssessmentSession.assessment_id == assessment_id)
    if status is not None:
        filters.append(AssessmentSession.status == status)
    if requester.role == UserRole.CANDIDATE:
        filters.append(AssessmentSession.candidate_id == requester.id)
    elif requester.role not in {UserRole.ADMIN, UserRole.ASSESSOR}:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="requires_role:admin,assessor")

    try:
        total_query = select(func.count()).select_from(AssessmentSession).where(*filters)
        total = int((await db.execute(total_query)).scalar_one())

        query: Select[tuple[AssessmentSession]] = (
            select(AssessmentSession)
            .options(
                selectinload(AssessmentSession.assessment),
                selectinload(AssessmentSession.candidate),
                selectinload(AssessmentSession.assessor),
                selectinload(AssessmentSession.report),
            )
            .where(*filters)
            .order_by(AssessmentSession.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)
        sessions = list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.exception("session_list_failed", requester_id=str(requester.id), error=str(exc))
        raise

    return sessions, total


async def update_session(
    db: AsyncSession,
    id: UUID,
    data: SessionUpdate,
    requester: User,
) -> AssessmentSession:
    _ensure_session_writer(requester)
    session = await get_session(db, id, requester)
    update_data = data.model_dump(exclude_unset=True)

    for field_name, value in update_data.items():
        setattr(session, field_name, value)

    try:
        await db.commit()
        return await get_session(db, id, requester)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("session_update_failed", session_id=str(id), requester_id=str(requester.id), error=str(exc))
        raise


async def archive_session(db: AsyncSession, id: UUID, requester: User) -> None:
    _ensure_admin(requester)
    session = await get_session(db, id, requester)
    session.deleted_at = datetime.now(UTC)

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("session_archive_failed", session_id=str(id), requester_id=str(requester.id), error=str(exc))
        raise

    logger.info("session_archived", session_id=str(id), requester_id=str(requester.id))


async def initiate_vapi_call(
    db: AsyncSession,
    session: AssessmentSession,
    settings: Settings,
    customer_number: str | None,
) -> StartCallResponse:
    if session.status == SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="session_already_completed",
        )
    if session.vapi_call_id is not None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="session_call_already_bound",
        )

    payload = build_vapi_call_payload(session, settings, customer_number)
    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }
    url = settings.vapi_api_url.rstrip("/") + "/call"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            response_payload = response.json()
    except httpx.HTTPStatusError as exc:
        error_detail = _map_vapi_call_creation_error(exc.response)
        logger.exception(
            "vapi_call_creation_status_failed",
            session_id=str(session.id),
            call_mode=settings.vapi_call_mode,
            status_code=exc.response.status_code,
            response_text=exc.response.text,
        )
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=error_detail,
        ) from exc
    except httpx.RequestError as exc:
        logger.exception("vapi_call_creation_request_failed", session_id=str(session.id), error=str(exc))
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="vapi_call_creation_failed",
        ) from exc

    call_id = _extract_vapi_call_id(response_payload)
    web_call_url = _extract_vapi_web_call_url(response_payload)
    session.vapi_call_id = call_id
    session.status = SessionStatus.IN_PROGRESS
    if session.started_at is None:
        session.started_at = datetime.now(UTC)

    try:
        await db.commit()
        await db.refresh(session)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("vapi_call_id_store_failed", session_id=str(session.id), call_id=call_id, error=str(exc))
        raise

    logger.info(
        "vapi_call_created",
        session_id=str(session.id),
        call_id=call_id,
        call_mode=settings.vapi_call_mode,
        has_web_call_url=web_call_url is not None,
    )
    return StartCallResponse(call_id=call_id, web_call_url=web_call_url)


def build_vapi_call_payload(
    session: AssessmentSession,
    settings: Settings,
    customer_number: str | None,
) -> dict[str, object]:
    if settings.vapi_call_mode == VapiCallMode.PHONE:
        if customer_number is None:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="customer_number_required_for_phone_call_mode",
            )
        return build_vapi_phone_call_payload(session, settings, customer_number)
    if customer_number is not None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="phone_call_mode_not_enabled",
        )
    return build_vapi_web_call_payload(session)


def build_vapi_web_call_payload(session: AssessmentSession) -> dict[str, object]:
    return {
        "type": "webCall",
        "assistantId": str(session.assessment.vapi_assistant_id),
        "metadata": {
            "session_id": str(session.id),
            "assessment_id": str(session.assessment_id),
            "candidate_id": str(session.candidate_id),
        },
    }


def build_vapi_phone_call_payload(
    session: AssessmentSession,
    settings: Settings,
    customer_number: str,
) -> dict[str, object]:
    return {
        "type": "outboundPhoneCall",
        "assistantId": str(session.assessment.vapi_assistant_id),
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {
            "number": customer_number,
        },
        "metadata": {
            "session_id": str(session.id),
            "assessment_id": str(session.assessment_id),
            "candidate_id": str(session.candidate_id),
        },
    }


async def _get_active_assessment(db: AsyncSession, assessment_id: UUID) -> Assessment:
    try:
        query: Select[tuple[Assessment]] = select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.deleted_at.is_(None),
            Assessment.status == AssessmentStatus.ACTIVE,
        )
        result = await db.execute(query)
        assessment = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("active_assessment_lookup_failed", assessment_id=str(assessment_id), error=str(exc))
        raise

    if assessment is None:
        raise AssessmentNotFoundError(f"assessment_not_found:{assessment_id}")
    return assessment


def _extract_vapi_call_id(payload: object) -> str:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="vapi_call_creation_failed",
        )
    for key in ("id", "call_id", "callId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip() != "":
            return value
    raise HTTPException(
        status_code=http_status.HTTP_502_BAD_GATEWAY,
        detail="vapi_call_creation_failed",
    )


def _map_vapi_call_creation_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "vapi_call_creation_failed"

    message = ""
    if isinstance(payload, dict):
        raw_message = payload.get("message")
        if isinstance(raw_message, str):
            message = raw_message

    normalized = message.lower()
    if "free vapi numbers do not support international calls" in normalized:
        return "vapi_international_calls_require_twilio_or_paid_number"
    if "phone number" in normalized and "not" in normalized:
        return "vapi_phone_number_not_ready_or_not_accessible"
    if message.strip():
        return f"vapi_call_creation_failed:{message.strip()[:180]}"
    return "vapi_call_creation_failed"


def _extract_vapi_web_call_url(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("webCallUrl", "web_call_url", "url"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip() != "":
            return value
    return None


def _ensure_session_writer(user: User) -> None:
    if user.role not in {UserRole.ADMIN, UserRole.ASSESSOR}:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="requires_role:admin,assessor")


def _ensure_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="requires_role:admin")


def _ensure_session_read_allowed(session: AssessmentSession, requester: User) -> None:
    if requester.role in {UserRole.ADMIN, UserRole.ASSESSOR}:
        return
    if requester.role == UserRole.CANDIDATE and session.candidate_id == requester.id:
        return
    raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="session_access_denied")
