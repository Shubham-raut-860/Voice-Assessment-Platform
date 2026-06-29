from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import cast
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.dependencies import get_db, get_session_factory, get_settings
from app.middleware.rate_limit import WEBHOOK_RATE_LIMIT, limiter
from app.models.assessment_session import AssessmentSession
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import (
    VapiAnalysisDoneEvent,
    VapiCallEndedEvent,
    VapiCallStartedEvent,
    VapiTranscriptUpdateEvent,
    VapiUnknownEvent,
    VapiWebhookEvent,
    VapiWebhookPayload,
)
from app.services.vapi_service import (
    get_or_create_webhook_event,
    handle_analysis_done,
    handle_call_ended,
    handle_call_started,
    handle_transcript_update,
    handle_vapi_server_message,
    validate_vapi_webhook_auth,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/vapi", status_code=200)
@limiter.limit(WEBHOOK_RATE_LIMIT)
async def receive_vapi_webhook(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> dict[str, bool]:
    _ = response
    raw_body = await request.body()
    signature_header = request.headers.get("X-Vapi-Signature", "")
    shared_secret_header = request.headers.get("X-Vapi-Secret", "")
    validate_vapi_webhook_auth(
        raw_body,
        signature_header,
        shared_secret_header,
        settings.vapi_webhook_secret,
    )

    try:
        payload = _parse_payload(raw_body)
    except ValueError as exc:
        logger.warning("vapi_webhook_invalid_payload", error=str(exc))
        return {"received": True}

    event_id = _extract_event_id(payload, raw_body)
    event_type = _extract_event_type(payload)
    call_id = _extract_call_id(payload)
    session_id: str | None = None

    try:
        async with db.begin():
            webhook_event, is_new = await get_or_create_webhook_event(
                db,
                event_id=event_id,
                event_type=event_type,
                payload=payload,
            )
            if not is_new and webhook_event.processed:
                logger.info(
                    "vapi_webhook_duplicate_ignored",
                    vapi_event_id=event_id,
                    event_type=event_type,
                )
                return {"received": True}

            if call_id is not None:
                session_id = await _lookup_session_id(db, call_id)

            try:
                if _is_vapi_server_message(payload):
                    await handle_vapi_server_message(db, payload, background_tasks, settings, session_factory)
                else:
                    event = VapiWebhookPayload.model_validate(payload).root
                    await _dispatch_event(db, event, background_tasks, settings, session_factory)
                webhook_event.processed = True
                webhook_event.processed_at = datetime.now(UTC)
                webhook_event.error = None
            except (LookupError, ValidationError, ValueError, SQLAlchemyError) as exc:
                _mark_webhook_error(webhook_event, exc)
                logger.exception(
                    "vapi_webhook_processing_failed",
                    vapi_event_id=event_id,
                    event_type=event_type,
                    call_id=call_id,
                    session_id=session_id,
                    error=str(exc),
                )
            except Exception as exc:
                _mark_webhook_error(webhook_event, exc)
                logger.exception(
                    "vapi_webhook_unexpected_processing_failed",
                    vapi_event_id=event_id,
                    event_type=event_type,
                    call_id=call_id,
                    session_id=session_id,
                    error=str(exc),
                )
    except SQLAlchemyError as exc:
        logger.exception(
            "vapi_webhook_transaction_failed",
            vapi_event_id=event_id,
            event_type=event_type,
            call_id=call_id,
            session_id=session_id,
            error=str(exc),
        )
    except Exception as exc:
        logger.exception(
            "vapi_webhook_route_failed",
            vapi_event_id=event_id,
            event_type=event_type,
            call_id=call_id,
            session_id=session_id,
            error=str(exc),
        )

    return {"received": True}


async def _dispatch_event(
    db: AsyncSession,
    event: VapiWebhookEvent,
    background_tasks: BackgroundTasks,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if isinstance(event, VapiCallStartedEvent):
        await handle_call_started(db, event)
        return
    if isinstance(event, VapiCallEndedEvent):
        await handle_call_ended(db, event)
        return
    if isinstance(event, VapiTranscriptUpdateEvent):
        await handle_transcript_update(db, event)
        return
    if isinstance(event, VapiAnalysisDoneEvent):
        await handle_analysis_done(db, event, background_tasks, settings, session_factory)
        return
    if isinstance(event, VapiUnknownEvent):
        logger.info("vapi_unknown_event_ignored", event_type=event.type)
        return
    raise ValueError(f"unsupported_vapi_event:{type(event).__name__}")


def _parse_payload(raw_body: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(raw_body)
    except JSONDecodeError as exc:
        raise ValueError("invalid_json_payload") from exc

    if not isinstance(decoded, dict):
        raise ValueError("payload_must_be_json_object")
    return cast(dict[str, object], decoded)


def _extract_event_id(payload: dict[str, object], raw_body: bytes) -> str:
    for key in ("event_id", "id", "vapi_event_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip() != "":
            return value

    message = payload.get("message")
    if isinstance(message, dict):
        message_id = message.get("id")
        if isinstance(message_id, str) and message_id.strip() != "":
            return message_id
        message_type = message.get("type")
        call = message.get("call")
        call_id = call.get("id") if isinstance(call, dict) else None
        timestamp = message.get("timestamp") or message.get("endedAt") or message.get("startedAt")
        if isinstance(message_type, str) and isinstance(call_id, str):
            return f"{message_type}:{call_id}:{timestamp or hashlib.sha256(raw_body).hexdigest()}"

    fallback_id = hashlib.sha256(raw_body).hexdigest()
    logger.warning("vapi_webhook_missing_event_id", fallback_event_id=fallback_id)
    return fallback_id


def _extract_event_type(payload: dict[str, object]) -> str:
    value = payload.get("type")
    if isinstance(value, str) and value.strip() != "":
        return value
    message = payload.get("message")
    if isinstance(message, dict):
        message_type = message.get("type")
        if isinstance(message_type, str) and message_type.strip() != "":
            return message_type
    return "unknown"


def _extract_call_id(payload: dict[str, object]) -> str | None:
    value = payload.get("call_id")
    if isinstance(value, str) and value.strip() != "":
        return value
    message = payload.get("message")
    if isinstance(message, dict):
        call = message.get("call")
        if isinstance(call, dict):
            call_id = call.get("id")
            if isinstance(call_id, str) and call_id.strip() != "":
                return call_id
    return None


def _is_vapi_server_message(payload: dict[str, object]) -> bool:
    message = payload.get("message")
    return isinstance(message, dict) and isinstance(message.get("type"), str)


async def _lookup_session_id(db: AsyncSession, call_id: str) -> str | None:
    try:
        query: Select[tuple[UUID]] = select(AssessmentSession.id).where(
            AssessmentSession.vapi_call_id == call_id,
            AssessmentSession.deleted_at.is_(None),
        )
        result = await db.execute(query)
        session_id = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("vapi_webhook_session_context_lookup_failed", call_id=call_id, error=str(exc))
        raise

    return None if session_id is None else str(session_id)


def _mark_webhook_error(webhook_event: WebhookEvent, exc: Exception) -> None:
    webhook_event.processed = True
    webhook_event.processed_at = datetime.now(UTC)
    webhook_event.error = f"{type(exc).__name__}: {exc}"
