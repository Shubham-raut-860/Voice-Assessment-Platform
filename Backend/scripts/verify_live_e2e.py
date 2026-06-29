from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings
from app.db.engine import connect_database, create_engine, create_sessionmaker, dispose_database
from app.exceptions import SessionNotFoundError
from app.models.assessment_session import AssessmentSession
from app.schemas.enums import ReportStatus, SessionStatus

logger = structlog.get_logger(__name__)
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_POLL_SECONDS = 10


@dataclass(frozen=True)
class LiveE2EConfig:
    session_id: UUID
    timeout_seconds: int
    poll_seconds: int
    require_transcript: bool
    require_report: bool
    require_email: bool


@dataclass(frozen=True)
class LiveE2EStatus:
    session_id: str
    passed: bool
    terminal_failure: bool
    missing: list[str]
    session_status: str | None
    vapi_call_id: str | None
    has_transcript: bool
    has_vapi_analysis: bool
    report_status: str | None
    generated_at: str | None
    email_sent_at: str | None
    failure_reason: str | None


async def wait_for_live_e2e(config: LiveE2EConfig) -> LiveE2EStatus:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)
    deadline = asyncio.get_running_loop().time() + float(config.timeout_seconds)
    last_status: LiveE2EStatus | None = None

    try:
        await connect_database(engine)
        while True:
            async with session_factory() as db:
                last_status = await get_live_e2e_status(db, config)

            if last_status.passed or last_status.terminal_failure:
                return last_status

            if asyncio.get_running_loop().time() >= deadline:
                return last_status

            await asyncio.sleep(float(config.poll_seconds))
    finally:
        await dispose_database(engine)


async def get_live_e2e_status(db: AsyncSession, config: LiveE2EConfig) -> LiveE2EStatus:
    try:
        query: Select[tuple[AssessmentSession]] = (
            select(AssessmentSession)
            .options(selectinload(AssessmentSession.report))
            .where(
                AssessmentSession.id == config.session_id,
                AssessmentSession.deleted_at.is_(None),
            )
        )
        result = await db.execute(query)
        session = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("live_e2e_status_database_failed", session_id=str(config.session_id), error=str(exc))
        raise

    if session is None:
        raise SessionNotFoundError(f"session_not_found:{config.session_id}")

    return evaluate_live_e2e_status(session, config)


def evaluate_live_e2e_status(session: AssessmentSession, config: LiveE2EConfig) -> LiveE2EStatus:
    report = session.report
    missing: list[str] = []
    failure_reason: str | None = None

    if session.status != SessionStatus.COMPLETED:
        missing.append("session_completed")
    if session.vapi_call_id is None or session.vapi_call_id.strip() == "":
        missing.append("vapi_call_id")
    if config.require_transcript and not _has_text(session.raw_transcript):
        missing.append("transcript")
    if config.require_report:
        if report is None:
            missing.append("report")
        elif report.generation_status != ReportStatus.COMPLETED:
            missing.append("report_completed")
        elif report.generated_at is None:
            missing.append("report_generated_at")
    if config.require_email:
        if report is None or report.email_sent_at is None:
            missing.append("email_sent_at")

    terminal_failure = False
    if session.status == SessionStatus.FAILED:
        terminal_failure = True
        failure_reason = "session_failed"
    if report is not None and report.generation_status == ReportStatus.FAILED:
        terminal_failure = True
        failure_reason = f"report_failed:{report.generation_error or 'unknown_error'}"

    return LiveE2EStatus(
        session_id=str(session.id),
        passed=not missing and not terminal_failure,
        terminal_failure=terminal_failure,
        missing=missing,
        session_status=session.status.value,
        vapi_call_id=session.vapi_call_id,
        has_transcript=_has_text(session.raw_transcript),
        has_vapi_analysis=session.vapi_analysis is not None,
        report_status=report.generation_status.value if report is not None else None,
        generated_at=_datetime_to_string(report.generated_at) if report is not None else None,
        email_sent_at=_datetime_to_string(report.email_sent_at) if report is not None else None,
        failure_reason=failure_reason,
    )


def parse_args(argv: list[str] | None = None) -> LiveE2EConfig:
    parser = argparse.ArgumentParser(description="Poll a real Vapi session until the live E2E chain is verified.")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--allow-missing-transcript", action="store_true")
    parser.add_argument("--allow-missing-report", action="store_true")
    parser.add_argument("--allow-missing-email", action="store_true")
    args = parser.parse_args(argv)

    return LiveE2EConfig(
        session_id=_parse_uuid(str(args.session_id), "session-id"),
        timeout_seconds=int(args.timeout_seconds),
        poll_seconds=int(args.poll_seconds),
        require_transcript=not bool(args.allow_missing_transcript),
        require_report=not bool(args.allow_missing_report),
        require_email=not bool(args.allow_missing_email),
    )


def _parse_uuid(value: str, argument_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{argument_name} must be a UUID") from exc


def _has_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def _datetime_to_string(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def main() -> NoReturn:
    try:
        result = asyncio.run(wait_for_live_e2e(parse_args()))
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc
    except SessionNotFoundError as exc:
        print(f"live_e2e: failed: {exc.message}")
        raise SystemExit(1) from exc
    except SQLAlchemyError as exc:
        print(f"live_e2e: failed: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    if result.passed:
        print("live_e2e: ok")
        raise SystemExit(0)

    print("live_e2e: failed")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
