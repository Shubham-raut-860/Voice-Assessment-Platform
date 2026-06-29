from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn
from uuid import UUID

import structlog
from fastapi import HTTPException
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
from app.services.session_service import initiate_vapi_call

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class StartDemoCallConfig:
    session_id: UUID
    customer_number: str | None


@dataclass(frozen=True)
class StartDemoCallResult:
    session_id: UUID
    call_id: str
    web_call_url: str | None


async def start_demo_call(db: AsyncSession, settings: Settings, config: StartDemoCallConfig) -> StartDemoCallResult:
    try:
        session = await _load_session(db, config.session_id)
        started = await initiate_vapi_call(db, session, settings, config.customer_number)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("demo_start_call_database_failed", session_id=str(config.session_id), error=str(exc))
        raise

    logger.info(
        "demo_vapi_call_started",
        session_id=str(config.session_id),
        call_id=started.call_id,
        has_web_call_url=started.web_call_url is not None,
    )
    return StartDemoCallResult(
        session_id=config.session_id,
        call_id=started.call_id,
        web_call_url=started.web_call_url,
    )


async def _load_session(db: AsyncSession, session_id: UUID) -> AssessmentSession:
    query: Select[tuple[AssessmentSession]] = (
        select(AssessmentSession)
        .options(
            selectinload(AssessmentSession.assessment),
            selectinload(AssessmentSession.candidate),
            selectinload(AssessmentSession.assessor),
        )
        .where(
            AssessmentSession.id == session_id,
            AssessmentSession.deleted_at.is_(None),
        )
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if session is None:
        raise SessionNotFoundError(f"session_not_found:{session_id}")
    return session


async def run_start_call(config: StartDemoCallConfig) -> StartDemoCallResult:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)
    try:
        await connect_database(engine)
        async with session_factory() as db:
            return await start_demo_call(db, settings, config)
    finally:
        await dispose_database(engine)


def parse_args(argv: list[str] | None = None) -> StartDemoCallConfig:
    parser = argparse.ArgumentParser(description="Start a real Vapi outbound call for a demo session.")
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--customer-number",
        required=False,
        help="Candidate phone number in E.164 format, for example +15551234567.",
    )
    args = parser.parse_args(argv)
    customer_number = None if args.customer_number is None else str(args.customer_number).strip()
    if customer_number is not None and (not customer_number.startswith("+") or len(customer_number) < 8):
        parser.error("--customer-number must be in E.164 format, for example +15551234567.")
    return StartDemoCallConfig(
        session_id=_parse_uuid(str(args.session_id), "session-id"),
        customer_number=customer_number,
    )


def _parse_uuid(value: str, argument_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{argument_name} must be a UUID") from exc


def main() -> NoReturn:
    try:
        config = parse_args()
        result = asyncio.run(run_start_call(config))
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc
    except SessionNotFoundError as exc:
        print(f"demo_start_call: failed: {exc.message}")
        raise SystemExit(1) from exc
    except HTTPException as exc:
        print(f"demo_start_call: failed: {exc.detail}")
        raise SystemExit(1) from exc
    except SQLAlchemyError as exc:
        print(f"demo_start_call: failed: {exc}")
        raise SystemExit(1) from exc

    print("demo_start_call: ok")
    print(f"session_id={result.session_id}")
    print(f"call_id={result.call_id}")
    print(f"web_call_url={result.web_call_url or ''}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
