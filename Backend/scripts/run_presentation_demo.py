from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from pydantic import ValidationError
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings, VapiCallMode
from app.db.engine import connect_database, create_engine, create_sessionmaker, dispose_database
from app.models.assessment_session import AssessmentSession
from app.schemas.enums import VapiCallEndReason, VapiTranscriptRole
from app.schemas.webhook import (
    VapiAnalysisDoneEvent,
    VapiCallEndedEvent,
    VapiCallStartedEvent,
    VapiTranscriptMessage,
    VapiTranscriptUpdateEvent,
)
from app.services.anthropic_service import trigger_report_generation
from app.services.vapi_service import (
    handle_analysis_done,
    handle_call_ended,
    handle_call_started,
    handle_transcript_update,
)
from scripts.check_demo_session import DemoSessionStatus, get_demo_session_status
from scripts.seed_demo_data import DemoSeedConfig, DemoSeedResult, seed_demo_data
from scripts.start_demo_vapi_call import StartDemoCallConfig, start_demo_call

DEFAULT_DEMO_ASSISTANT_ID = UUID("11111111-1111-4111-8111-111111111111")


@dataclass(frozen=True)
class PresentationDemoConfig:
    mode: str
    vapi_assistant_id: UUID
    customer_number: str | None
    reset_passwords: bool
    skip_report_generation: bool


@dataclass(frozen=True)
class PresentationDemoResult:
    seed: DemoSeedResult
    call_id: str
    web_call_url: str | None
    status: DemoSessionStatus
    email_mode: str


async def run_presentation_demo(config: PresentationDemoConfig) -> PresentationDemoResult:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)
    try:
        await connect_database(engine)
        async with session_factory() as db:
            seed = await seed_demo_data(db, _build_seed_config(config))

        if config.mode == "live-vapi":
            if settings.vapi_call_mode == VapiCallMode.PHONE and config.customer_number is None:
                raise ValueError("--customer-number is required when --mode live-vapi")
            async with session_factory() as db:
                started = await start_demo_call(
                    db,
                    settings,
                    StartDemoCallConfig(
                        session_id=seed.session_id,
                        customer_number=config.customer_number,
                    ),
                )
                await db.commit()
            async with session_factory() as db:
                status = await get_demo_session_status(db, seed.session_id)
            return PresentationDemoResult(
                seed=seed,
                call_id=started.call_id,
                web_call_url=started.web_call_url,
                status=status,
                email_mode="not_attempted",
            )

        call_id = f"demo-call-{uuid4()}"
        async with session_factory() as db:
            await _simulate_vapi_conversation(
                db=db,
                settings=settings,
                session_id=seed.session_id,
                call_id=call_id,
                session_factory=session_factory,
            )
            await db.commit()

        if not config.skip_report_generation:
            async with session_factory() as db:
                await trigger_report_generation(
                    seed.session_id,
                    db,
                    settings,
                    send_email=_looks_like_real_resend_key(settings.resend_api_key),
                )

        async with session_factory() as db:
            status = await get_demo_session_status(db, seed.session_id)
        email_mode = "attempted" if _looks_like_real_resend_key(settings.resend_api_key) else "skipped_invalid_or_placeholder_key"
        return PresentationDemoResult(seed=seed, call_id=call_id, web_call_url=None, status=status, email_mode=email_mode)
    finally:
        await dispose_database(engine)


async def _simulate_vapi_conversation(
    db: AsyncSession,
    settings: Settings,
    session_id: UUID,
    call_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session = await _load_session(db, session_id)
    session.vapi_call_id = call_id
    await db.flush()

    started_at = datetime.now(UTC) - timedelta(minutes=18)
    ended_at = datetime.now(UTC)
    assistant_id = str(session.assessment.vapi_assistant_id)

    await handle_call_started(
        db,
        VapiCallStartedEvent(
            type="call.started",
            call_id=call_id,
            assistant_id=assistant_id,
            started_at=started_at,
        ),
    )
    await handle_transcript_update(
        db,
        VapiTranscriptUpdateEvent(
            type="transcript.update",
            call_id=call_id,
            transcript=_presentation_transcript(),
        ),
    )
    await handle_call_ended(
        db,
        VapiCallEndedEvent(
            type="call.ended",
            call_id=call_id,
            ended_at=ended_at,
            duration_seconds=1080,
            end_reason=VapiCallEndReason.ASSISTANT_ENDED,
        ),
    )
    await handle_analysis_done(
        db,
        VapiAnalysisDoneEvent(
            type="analysis.done",
            call_id=call_id,
            summary=(
                "Candidate gave structured answers on system design, reliability, and incident response. "
                "They explained tradeoffs, monitoring, and rollback strategy with concrete examples."
            ),
            structured_data={
                "communication_clarity": "strong",
                "systems_thinking": "strong",
                "risk_awareness": "strong",
                "follow_up_depth": "moderate",
            },
        ),
        BackgroundTasks(),
        settings,
        session_factory,
    )


async def _load_session(db: AsyncSession, session_id: UUID) -> AssessmentSession:
    query: Select[tuple[AssessmentSession]] = (
        select(AssessmentSession)
        .options(selectinload(AssessmentSession.assessment))
        .where(
            AssessmentSession.id == session_id,
            AssessmentSession.deleted_at.is_(None),
        )
        .with_for_update()
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if session is None:
        raise LookupError(f"session_not_found:{session_id}")
    return session


def _presentation_transcript() -> list[VapiTranscriptMessage]:
    turns: list[tuple[VapiTranscriptRole, str, float]] = [
        (
            VapiTranscriptRole.ASSISTANT,
            "Can you describe a production system you designed and the reliability tradeoffs you made?",
            1.0,
        ),
        (
            VapiTranscriptRole.USER,
            (
                "I designed an assessment API with async workers. The main tradeoff was keeping the request path "
                "fast while moving AI report generation into a durable background process. I used database state "
                "to make retries observable instead of hiding them in memory."
            ),
            14.0,
        ),
        (
            VapiTranscriptRole.ASSISTANT,
            "How would you handle a webhook provider sending duplicate or out-of-order events?",
            92.0,
        ),
        (
            VapiTranscriptRole.USER,
            (
                "I would validate the signature before any database work, store an idempotency key, and process "
                "each event in a transaction. For out-of-order events, the session state machine should tolerate "
                "a transcript arriving after call ended and append it without regressing status."
            ),
            105.0,
        ),
        (
            VapiTranscriptRole.ASSISTANT,
            "What monitoring would you add before launch?",
            186.0,
        ),
        (
            VapiTranscriptRole.USER,
            (
                "I would track webhook failure rate, report generation latency, AI token spend, email delivery "
                "failures, and queue depth. I would also add alerts for stale generating reports and failed Vapi "
                "call creation because those directly affect the customer demo."
            ),
            198.0,
        ),
        (
            VapiTranscriptRole.ASSISTANT,
            "What would you improve if you had another week?",
            282.0,
        ),
        (
            VapiTranscriptRole.USER,
            (
                "I would replace stateless logout with revocation or a refresh-token flow, move rate limiting to "
                "Redis, create a real Vapi browser candidate flow, and add a CI pipeline with live integration gates."
            ),
            296.0,
        ),
    ]
    return [VapiTranscriptMessage(role=role, content=content, timestamp=timestamp) for role, content, timestamp in turns]


def _build_seed_config(config: PresentationDemoConfig) -> DemoSeedConfig:
    return DemoSeedConfig(
        admin_email="[email-redacted]",
        admin_password="DemoAdmin123!",
        assessor_email="[email-redacted]",
        assessor_password="DemoAssessor123!",
        candidate_email="[email-redacted]",
        candidate_password="DemoCandidate123!",
        vapi_assistant_id=config.vapi_assistant_id,
        assessment_title="Company Presentation Voice Assessment",
        assessment_description=(
            "Presentation-ready assessment that demonstrates session creation, transcript capture, "
            "AI scoring, report status, and email delivery state."
        ),
        passing_score=Decimal("75.00"),
        time_limit_minutes=30,
        reset_passwords=config.reset_passwords,
    )


def _looks_like_real_resend_key(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized.startswith("re_"):
        return False
    placeholder_fragments = ("local-dev", "replace-with", "example", "invalid", "your-")
    return not any(fragment in normalized for fragment in placeholder_fragments)


def parse_args(argv: list[str] | None = None) -> PresentationDemoConfig:
    parser = argparse.ArgumentParser(description="Run the company presentation demo workflow.")
    parser.add_argument("--mode", choices=["simulated-vapi", "live-vapi"], default="simulated-vapi")
    parser.add_argument("--vapi-assistant-id", default=str(DEFAULT_DEMO_ASSISTANT_ID))
    parser.add_argument("--customer-number", help="Required for --mode live-vapi. Use E.164, for example +15551234567.")
    parser.add_argument("--reset-passwords", action="store_true")
    parser.add_argument("--skip-report-generation", action="store_true")
    args = parser.parse_args(argv)

    customer_number = None if args.customer_number is None else str(args.customer_number).strip()
    if customer_number is not None and not customer_number.startswith("+"):
        parser.error("--customer-number must use E.164 format, for example +15551234567.")

    return PresentationDemoConfig(
        mode=str(args.mode),
        vapi_assistant_id=_parse_uuid(str(args.vapi_assistant_id), "vapi-assistant-id"),
        customer_number=customer_number,
        reset_passwords=bool(args.reset_passwords),
        skip_report_generation=bool(args.skip_report_generation),
    )


def _parse_uuid(value: str, argument_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{argument_name} must be a UUID") from exc


def main() -> NoReturn:
    try:
        config = parse_args()
        result = asyncio.run(run_presentation_demo(config))
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc
    except OSError as exc:
        print(f"presentation_demo: failed: database_unavailable:{exc}")
        print("start_database_hint=$env:VOICE_ASSESSMENT_POSTGRES_PASSWORD=\"local_voice_password\"; docker-compose up -d postgres migrate")
        raise SystemExit(1) from exc
    except (SQLAlchemyError, ValueError, LookupError) as exc:
        print(f"presentation_demo: failed: {exc}")
        raise SystemExit(1) from exc

    print("presentation_demo: ok")
    print(f"admin_login=[email-redacted]")
    print(f"assessor_login=[email-redacted]")
    print(f"candidate_login=[email-redacted]")
    print(f"password=DemoAdmin123! / DemoAssessor123! / DemoCandidate123!")
    print(f"session_id={result.seed.session_id}")
    print(f"call_id={result.call_id}")
    print(f"web_call_url={result.web_call_url or ''}")
    print(f"session_status={result.status.session_status}")
    print(f"report_status={result.status.report_status}")
    print(f"overall_score={result.status.overall_score}")
    print(f"email_mode={result.email_mode}")
    print(f"email_sent_at={result.status.email_sent_at}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
