from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from time import time
from typing import cast

import structlog
from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models.assessment_report import AssessmentReport
from app.models.assessment_session import AssessmentSession
from app.models.webhook_event import WebhookEvent
from app.schemas.enums import PassFail, ReportStatus, SessionStatus, VapiCallEndReason
from app.schemas.webhook import (
    VapiAnalysisDone,
    VapiCallEnded,
    VapiCallStarted,
    VapiTranscriptMessage,
    VapiTranscriptUpdate,
)
from app.services.anthropic_service import trigger_report_generation_background

logger = structlog.get_logger(__name__)
SIGNATURE_TOLERANCE_SECONDS = 300


def validate_vapi_signature(payload: bytes, signature_header: str, secret: str) -> None:
    signature_parts = _parse_signature_header(signature_header)
    timestamp = signature_parts.get("t")
    received_signature = signature_parts.get("v1")

    if timestamp is None or received_signature is None:
        raise _invalid_signature()

    try:
        timestamp_seconds = int(timestamp)
    except ValueError as exc:
        raise _invalid_signature() from exc

    now_seconds = int(time())
    if abs(now_seconds - timestamp_seconds) > SIGNATURE_TOLERANCE_SECONDS:
        raise _invalid_signature()

    signed_payload = timestamp.encode("utf-8") + b"." + payload
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, received_signature):
        raise _invalid_signature()


def validate_vapi_webhook_auth(
    payload: bytes,
    signature_header: str,
    shared_secret_header: str,
    secret: str,
) -> None:
    if signature_header.strip() != "":
        validate_vapi_signature(payload, signature_header, secret)
        return

    if shared_secret_header.strip() == "":
        raise _invalid_signature()

    if not hmac.compare_digest(shared_secret_header, secret):
        raise _invalid_signature()


async def handle_call_started(db: AsyncSession, event: VapiCallStarted) -> None:
    session = await _get_session_by_call_id(db, event.call_id)
    session.status = SessionStatus.IN_PROGRESS
    session.started_at = event.started_at
    logger.info(
        "vapi_call_started_processed",
        session_id=str(session.id),
        call_id=event.call_id,
        assistant_id=event.assistant_id,
    )


async def handle_call_ended(db: AsyncSession, event: VapiCallEnded) -> None:
    session = await _get_session_by_call_id(db, event.call_id)
    session.status = _session_status_for_end_reason(event.end_reason)
    session.ended_at = event.ended_at
    session.duration_seconds = event.duration_seconds
    logger.info(
        "vapi_call_ended_processed",
        session_id=str(session.id),
        call_id=event.call_id,
        end_reason=event.end_reason.value,
        status=session.status.value,
    )


async def handle_transcript_update(db: AsyncSession, event: VapiTranscriptUpdate) -> None:
    session = await _get_session_by_call_id(db, event.call_id)
    existing_transcript = _load_transcript(session.raw_transcript)
    incoming_transcript = [_transcript_message_to_dict(message) for message in event.transcript]
    merged_transcript = _merge_transcript(existing_transcript, incoming_transcript)
    session.raw_transcript = json.dumps(merged_transcript, ensure_ascii=False, separators=(",", ":"))
    logger.info(
        "vapi_transcript_update_processed",
        session_id=str(session.id),
        call_id=event.call_id,
        transcript_items=len(merged_transcript),
    )


async def handle_analysis_done(
    db: AsyncSession,
    event: VapiAnalysisDone,
    background_tasks: BackgroundTasks,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session = await _get_session_by_call_id(db, event.call_id)
    session.vapi_analysis = {
        "summary": event.summary,
        "structured_data": event.structured_data,
        "received_at": datetime.now(UTC).isoformat(),
    }
    await _ensure_pending_report(db, session)
    background_tasks.add_task(
        trigger_report_generation_background,
        session.id,
        session_factory,
        settings,
    )
    logger.info(
        "vapi_analysis_done_processed",
        session_id=str(session.id),
        call_id=event.call_id,
    )


async def handle_vapi_server_message(
    db: AsyncSession,
    payload: dict[str, object],
    background_tasks: BackgroundTasks,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("vapi_server_message_missing")

    message_type = message.get("type")
    if message_type == "end-of-call-report":
        await _handle_end_of_call_report(db, message, background_tasks, settings, session_factory)
        return
    if message_type == "status-update":
        await _handle_status_update(db, message, background_tasks, settings, session_factory)
        return
    if message_type == "transcript":
        await _handle_server_transcript(db, message)
        return

    logger.info("vapi_server_message_ignored", message_type=message_type)


async def get_or_create_webhook_event(
    db: AsyncSession,
    event_id: str,
    event_type: str,
    payload: dict[str, object],
) -> tuple[WebhookEvent, bool]:
    try:
        insert_statement = (
            insert(WebhookEvent)
            .values(
                event_type=event_type,
                vapi_event_id=event_id,
                payload=payload,
            )
            .on_conflict_do_nothing(index_elements=[WebhookEvent.vapi_event_id])
            .returning(WebhookEvent.id)
        )
        insert_result = await db.execute(insert_statement)
        inserted_id = insert_result.scalar_one_or_none()

        query: Select[tuple[WebhookEvent]] = (
            select(WebhookEvent)
            .where(
                WebhookEvent.vapi_event_id == event_id,
                WebhookEvent.deleted_at.is_(None),
            )
            .with_for_update()
        )
        select_result = await db.execute(query)
        webhook_event = select_result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception(
            "webhook_event_get_or_create_failed",
            vapi_event_id=event_id,
            event_type=event_type,
            error=str(exc),
        )
        raise

    if webhook_event is None:
        raise LookupError(f"webhook_event_not_found:{event_id}")

    return webhook_event, inserted_id is not None


async def _ensure_pending_report(db: AsyncSession, session: AssessmentSession) -> None:
    try:
        query: Select[tuple[AssessmentReport]] = (
            select(AssessmentReport)
            .where(
                AssessmentReport.session_id == session.id,
                AssessmentReport.deleted_at.is_(None),
            )
            .with_for_update()
        )
        result = await db.execute(query)
        report = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("vapi_pending_report_lookup_failed", session_id=str(session.id), error=str(exc))
        raise

    if report is not None:
        if report.generation_status in {ReportStatus.FAILED, ReportStatus.PENDING}:
            report.generation_status = ReportStatus.PENDING
            report.generation_error = None
        return

    db.add(
        AssessmentReport(
            session_id=session.id,
            version=1,
            overall_score=None,
            pass_fail=PassFail.INCONCLUSIVE,
            strengths=[],
            weaknesses=[],
            detailed_analysis="Report generation has not completed.",
            recommendations="Report generation has not completed.",
            anthropic_model_used="pending",
            anthropic_prompt_tokens=0,
            anthropic_completion_tokens=0,
            generation_status=ReportStatus.PENDING,
        )
    )


async def _handle_end_of_call_report(
    db: AsyncSession,
    message: dict[str, object],
    background_tasks: BackgroundTasks,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    call_id = _extract_server_call_id(message)
    session = await _get_session_by_call_id(db, call_id)
    session.status = _session_status_for_server_ended_reason(_extract_server_ended_reason(message))
    session.ended_at = _parse_datetime_field(message.get("endedAt"))
    session.raw_transcript = _extract_server_transcript(message)
    session.vapi_analysis = {
        "summary": _extract_server_summary(message),
        "structured_data": _extract_server_structured_data(message),
        "received_at": datetime.now(UTC).isoformat(),
        "source": "vapi_end_of_call_report",
    }
    await _ensure_pending_report(db, session)
    background_tasks.add_task(trigger_report_generation_background, session.id, session_factory, settings)
    logger.info("vapi_end_of_call_report_processed", session_id=str(session.id), call_id=call_id)


async def _handle_status_update(
    db: AsyncSession,
    message: dict[str, object],
    background_tasks: BackgroundTasks,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    call_id = _extract_server_call_id(message)
    session = await _get_session_by_call_id(db, call_id)
    status_value = message.get("status")
    call = message.get("call")
    if status_value is None and isinstance(call, dict):
        status_value = call.get("status")
    if status_value == "in-progress":
        session.status = SessionStatus.IN_PROGRESS
    elif status_value == "ended":
        session.status = SessionStatus.COMPLETED
        session.ended_at = _parse_datetime_field(message.get("endedAt")) or session.ended_at
        if _has_transcript_content(session.raw_transcript):
            await _ensure_pending_report(db, session)
            background_tasks.add_task(trigger_report_generation_background, session.id, session_factory, settings)
            logger.info("vapi_status_update_report_generation_queued", session_id=str(session.id), call_id=call_id)
    logger.info("vapi_status_update_processed", session_id=str(session.id), call_id=call_id, status=status_value)


async def _handle_server_transcript(db: AsyncSession, message: dict[str, object]) -> None:
    call_id = _extract_server_call_id(message)
    session = await _get_session_by_call_id(db, call_id)
    transcript = _extract_server_transcript(message)
    if transcript.strip() != "":
        session.raw_transcript = _merge_plain_transcript(session.raw_transcript, transcript)
    logger.info("vapi_server_transcript_processed", session_id=str(session.id), call_id=call_id)


def _has_transcript_content(raw_transcript: str | None) -> bool:
    return raw_transcript is not None and raw_transcript.strip() != ""


def _merge_plain_transcript(existing: str | None, incoming: str) -> str:
    normalized_incoming = incoming.strip()
    if existing is None or existing.strip() == "":
        return normalized_incoming

    normalized_existing = existing.strip()
    if normalized_incoming in normalized_existing:
        return normalized_existing
    if normalized_existing in normalized_incoming:
        return normalized_incoming
    return f"{normalized_existing}\n{normalized_incoming}"


def _extract_server_call_id(message: dict[str, object]) -> str:
    call = message.get("call")
    if isinstance(call, dict):
        call_id = call.get("id")
        if isinstance(call_id, str) and call_id.strip() != "":
            return call_id
    call_id = message.get("callId")
    if isinstance(call_id, str) and call_id.strip() != "":
        return call_id
    raise ValueError("vapi_server_call_id_missing")


def _extract_server_transcript(message: dict[str, object]) -> str:
    transcript = message.get("transcript")
    if isinstance(transcript, str):
        return transcript
    artifact = message.get("artifact")
    if isinstance(artifact, dict):
        artifact_transcript = artifact.get("transcript")
        if isinstance(artifact_transcript, str):
            return artifact_transcript
        messages = artifact.get("messages")
        if isinstance(messages, list):
            return _format_vapi_messages(messages)
    messages = message.get("messages")
    if isinstance(messages, list):
        return _format_vapi_messages(messages)
    return ""


def _format_vapi_messages(messages: list[object]) -> str:
    lines: list[str] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("message")
        if not isinstance(content, str) or content.strip() == "":
            continue
        label = "Assistant" if role in {"bot", "assistant"} else "Candidate" if role in {"user", "customer"} else str(role)
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def _extract_server_summary(message: dict[str, object]) -> str:
    summary = message.get("summary")
    if isinstance(summary, str) and summary.strip() != "":
        return summary
    analysis = message.get("analysis")
    if isinstance(analysis, dict):
        analysis_summary = analysis.get("summary")
        if isinstance(analysis_summary, str) and analysis_summary.strip() != "":
            return analysis_summary
    return "No Vapi summary was provided."


def _extract_server_structured_data(message: dict[str, object]) -> dict[str, object]:
    analysis = message.get("analysis")
    if isinstance(analysis, dict):
        structured_data = analysis.get("structuredData")
        if isinstance(structured_data, dict):
            return cast(dict[str, object], structured_data)
    return {}


def _server_message_indicates_failure(message: dict[str, object]) -> bool:
    ended_reason = _extract_server_ended_reason(message)
    return isinstance(ended_reason, str) and "error" in ended_reason.lower()


def _extract_server_ended_reason(message: dict[str, object]) -> str | None:
    ended_reason = message.get("endedReason")
    if isinstance(ended_reason, str) and ended_reason.strip() != "":
        return ended_reason
    call = message.get("call")
    if isinstance(call, dict):
        call_ended_reason = call.get("endedReason")
        if isinstance(call_ended_reason, str) and call_ended_reason.strip() != "":
            return call_ended_reason
    return None


def _session_status_for_end_reason(end_reason: VapiCallEndReason) -> SessionStatus:
    failed_reasons: set[VapiCallEndReason] = {
        VapiCallEndReason.ERROR,
        VapiCallEndReason.PIPELINE_ERROR,
        VapiCallEndReason.ASSISTANT_ERROR,
    }
    abandoned_reasons: set[VapiCallEndReason] = {
        VapiCallEndReason.TIME_LIMIT,
        VapiCallEndReason.EXCEEDED_MAX_DURATION,
        VapiCallEndReason.NO_ANSWER,
        VapiCallEndReason.VOICEMAIL,
        VapiCallEndReason.CUSTOMER_DID_NOT_GIVE_MICROPHONE_PERMISSION,
    }
    if end_reason in failed_reasons:
        return SessionStatus.FAILED
    if end_reason in abandoned_reasons:
        return SessionStatus.ABANDONED
    return SessionStatus.COMPLETED


def _session_status_for_server_ended_reason(ended_reason: str | None) -> SessionStatus:
    if ended_reason is None:
        return SessionStatus.COMPLETED
    normalized = ended_reason.strip().lower()
    if normalized in {"error", "pipeline-error", "assistant-error"} or "error" in normalized:
        return SessionStatus.FAILED
    if normalized in {
        "time_limit",
        "time-limit",
        "exceeded-max-duration",
        "no-answer",
        "voicemail",
        "customer-did-not-give-microphone-permission",
    }:
        return SessionStatus.ABANDONED
    return SessionStatus.COMPLETED


def _parse_datetime_field(value: object) -> datetime | None:
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_signature_header(signature_header: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in signature_header.split(","):
        key, separator, value = part.strip().partition("=")
        if separator == "=" and key and value:
            parsed[key] = value
    return parsed


def _invalid_signature() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid_signature",
    )


async def _get_session_by_call_id(db: AsyncSession, call_id: str) -> AssessmentSession:
    try:
        query: Select[tuple[AssessmentSession]] = (
            select(AssessmentSession)
            .where(
                AssessmentSession.vapi_call_id == call_id,
                AssessmentSession.deleted_at.is_(None),
            )
            .with_for_update()
        )
        result = await db.execute(query)
        session = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("vapi_session_lookup_failed", call_id=call_id, error=str(exc))
        raise

    if session is None:
        raise LookupError(f"assessment_session_not_found_for_call:{call_id}")
    return session


def _load_transcript(raw_transcript: str | None) -> list[dict[str, object]]:
    if raw_transcript is None or raw_transcript.strip() == "":
        return []

    decoded = json.loads(raw_transcript)
    if not isinstance(decoded, list):
        raise ValueError("raw_transcript_must_be_json_array")

    transcript: list[dict[str, object]] = []
    for item in decoded:
        if not isinstance(item, dict):
            raise ValueError("raw_transcript_item_must_be_object")
        transcript.append(cast(dict[str, object], item))
    return transcript


def _transcript_message_to_dict(message: VapiTranscriptMessage) -> dict[str, object]:
    dumped = message.model_dump(mode="json")
    return cast(dict[str, object], dumped)


def _merge_transcript(
    existing: list[dict[str, object]],
    incoming: list[dict[str, object]],
) -> list[dict[str, object]]:
    merged_by_key: dict[tuple[str, str, float], dict[str, object]] = {}
    for item in [*existing, *incoming]:
        role = item.get("role")
        content = item.get("content")
        timestamp = item.get("timestamp")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ValueError("transcript_item_role_and_content_must_be_strings")
        if not isinstance(timestamp, int | float):
            raise ValueError("transcript_item_timestamp_must_be_number")
        merged_by_key[(role, content, float(timestamp))] = {
            "role": role,
            "content": content,
            "timestamp": float(timestamp),
        }
    return sorted(merged_by_key.values(), key=lambda item: cast(float, item["timestamp"]))
