from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
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

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DemoSessionStatus:
    session_id: str
    session_status: str
    vapi_call_id: str | None
    candidate_email: str
    candidate_name: str
    assessment_title: str
    assessment_status: str
    report_status: str | None
    overall_score: str | None
    pass_fail: str | None
    generated_at: str | None
    email_sent_at: str | None


async def get_demo_session_status(db: AsyncSession, session_id: UUID) -> DemoSessionStatus:
    try:
        query: Select[tuple[AssessmentSession]] = (
            select(AssessmentSession)
            .options(
                selectinload(AssessmentSession.assessment),
                selectinload(AssessmentSession.candidate),
                selectinload(AssessmentSession.report),
            )
            .where(
                AssessmentSession.id == session_id,
                AssessmentSession.deleted_at.is_(None),
            )
        )
        result = await db.execute(query)
        session = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("demo_status_database_failed", session_id=str(session_id), error=str(exc))
        raise

    if session is None:
        raise SessionNotFoundError(f"session_not_found:{session_id}")

    report = session.report
    return DemoSessionStatus(
        session_id=str(session.id),
        session_status=session.status.value,
        vapi_call_id=session.vapi_call_id,
        candidate_email=session.candidate.email,
        candidate_name=session.candidate.full_name,
        assessment_title=session.assessment.title,
        assessment_status=session.assessment.status.value,
        report_status=report.generation_status.value if report is not None else None,
        overall_score=_decimal_to_string(report.overall_score) if report is not None else None,
        pass_fail=report.pass_fail.value if report is not None else None,
        generated_at=_datetime_to_string(report.generated_at) if report is not None else None,
        email_sent_at=_datetime_to_string(report.email_sent_at) if report is not None else None,
    )


async def run_check(session_id: UUID) -> DemoSessionStatus:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)
    try:
        await connect_database(engine)
        async with session_factory() as db:
            return await get_demo_session_status(db, session_id)
    finally:
        await dispose_database(engine)


def parse_args(argv: list[str] | None = None) -> UUID:
    parser = argparse.ArgumentParser(description="Inspect the current state of a demo assessment session.")
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args(argv)
    return _parse_uuid(str(args.session_id), "session-id")


def _parse_uuid(value: str, argument_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{argument_name} must be a UUID") from exc


def _datetime_to_string(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _decimal_to_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def main() -> NoReturn:
    try:
        session_id = parse_args()
        result = asyncio.run(run_check(session_id))
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc
    except SessionNotFoundError as exc:
        print(f"demo_status: failed: {exc.message}")
        raise SystemExit(1) from exc
    except SQLAlchemyError as exc:
        print(f"demo_status: failed: {exc}")
        raise SystemExit(1) from exc

    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
