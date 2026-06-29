from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import Select, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings
from app.db.engine import connect_database, create_engine, create_sessionmaker, dispose_database
from app.models.assessment import Assessment
from app.models.assessment_session import AssessmentSession
from app.models.user import User
from app.schemas.enums import AssessmentStatus, SessionStatus, UserRole
from app.services.auth_service import hash_password

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DemoSeedConfig:
    admin_email: str
    admin_password: str
    assessor_email: str
    assessor_password: str
    candidate_email: str
    candidate_password: str
    vapi_assistant_id: UUID
    assessment_title: str
    assessment_description: str
    passing_score: Decimal
    time_limit_minutes: int
    reset_passwords: bool


@dataclass(frozen=True)
class DemoSeedResult:
    admin_id: UUID
    assessor_id: UUID
    candidate_id: UUID
    assessment_id: UUID
    session_id: UUID


async def seed_demo_data(db: AsyncSession, config: DemoSeedConfig) -> DemoSeedResult:
    try:
        async with db.begin():
            admin = await _upsert_user(
                db=db,
                email=config.admin_email,
                password=config.admin_password,
                full_name="Demo Admin",
                role=UserRole.ADMIN,
                reset_password=config.reset_passwords,
            )
            assessor = await _upsert_user(
                db=db,
                email=config.assessor_email,
                password=config.assessor_password,
                full_name="Demo Assessor",
                role=UserRole.ASSESSOR,
                reset_password=config.reset_passwords,
            )
            candidate = await _upsert_user(
                db=db,
                email=config.candidate_email,
                password=config.candidate_password,
                full_name="Demo Candidate",
                role=UserRole.CANDIDATE,
                reset_password=config.reset_passwords,
            )
            assessment = await _upsert_assessment(db, config, admin)
            session = await _get_or_create_session(db, assessment, candidate, assessor)
        logger.info(
            "demo_seed_completed",
            admin_id=str(admin.id),
            assessor_id=str(assessor.id),
            candidate_id=str(candidate.id),
            assessment_id=str(assessment.id),
            session_id=str(session.id),
        )
        return DemoSeedResult(
            admin_id=admin.id,
            assessor_id=assessor.id,
            candidate_id=candidate.id,
            assessment_id=assessment.id,
            session_id=session.id,
        )
    except SQLAlchemyError as exc:
        logger.exception("demo_seed_database_failed", error=str(exc))
        raise


async def _upsert_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
    reset_password: bool,
) -> User:
    normalized_email = email.strip().lower()
    query: Select[tuple[User]] = select(User).where(
        func.lower(User.email) == normalized_email,
        User.deleted_at.is_(None),
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=normalized_email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.flush()
        return user

    user.full_name = full_name
    user.role = role
    user.is_active = True
    user.is_verified = True
    if reset_password:
        user.hashed_password = hash_password(password)
    await db.flush()
    return user


async def _upsert_assessment(
    db: AsyncSession,
    config: DemoSeedConfig,
    creator: User,
) -> Assessment:
    query: Select[tuple[Assessment]] = select(Assessment).where(
        Assessment.title == config.assessment_title,
        Assessment.created_by_id == creator.id,
        Assessment.deleted_at.is_(None),
    )
    result = await db.execute(query)
    assessment = result.scalar_one_or_none()

    if assessment is None:
        assessment = Assessment(
            title=config.assessment_title,
            description=config.assessment_description,
            status=AssessmentStatus.ACTIVE,
            vapi_assistant_id=config.vapi_assistant_id,
            passing_score=config.passing_score,
            time_limit_minutes=config.time_limit_minutes,
            created_by_id=creator.id,
        )
        db.add(assessment)
        await db.flush()
        return assessment

    assessment.description = config.assessment_description
    assessment.status = AssessmentStatus.ACTIVE
    assessment.vapi_assistant_id = config.vapi_assistant_id
    assessment.passing_score = config.passing_score
    assessment.time_limit_minutes = config.time_limit_minutes
    await db.flush()
    return assessment


async def _get_or_create_session(
    db: AsyncSession,
    assessment: Assessment,
    candidate: User,
    assessor: User,
) -> AssessmentSession:
    query: Select[tuple[AssessmentSession]] = select(AssessmentSession).where(
        AssessmentSession.assessment_id == assessment.id,
        AssessmentSession.candidate_id == candidate.id,
        AssessmentSession.deleted_at.is_(None),
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if session is not None:
        session.assessor_id = assessor.id
        if session.status in {SessionStatus.FAILED, SessionStatus.ABANDONED}:
            session.status = SessionStatus.SCHEDULED
        await db.flush()
        return session

    session = AssessmentSession(
        assessment_id=assessment.id,
        candidate_id=candidate.id,
        assessor_id=assessor.id,
        status=SessionStatus.SCHEDULED,
        vapi_call_id=None,
    )
    db.add(session)
    await db.flush()
    return session


async def run_seed(config: DemoSeedConfig) -> DemoSeedResult:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)
    try:
        await connect_database(engine)
        async with session_factory() as db:
            return await seed_demo_data(db, config)
    finally:
        await dispose_database(engine)


def parse_args(argv: list[str] | None = None) -> DemoSeedConfig:
    parser = argparse.ArgumentParser(description="Seed a repeatable alpha demo workspace.")
    parser.add_argument("--admin-email", default="[email-redacted]")
    parser.add_argument("--admin-password", default="DemoAdmin123!")
    parser.add_argument("--assessor-email", default="[email-redacted]")
    parser.add_argument("--assessor-password", default="DemoAssessor123!")
    parser.add_argument("--candidate-email", default="[email-redacted]")
    parser.add_argument("--candidate-password", default="DemoCandidate123!")
    parser.add_argument("--vapi-assistant-id", default=os.environ.get("DEMO_VAPI_ASSISTANT_ID"))
    parser.add_argument("--assessment-title", default="Alpha Demo Voice Assessment")
    parser.add_argument(
        "--assessment-description",
        default=(
            "A live alpha assessment used to validate the Vapi call, webhook, transcript, "
            "AI report, and email delivery workflow."
        ),
    )
    parser.add_argument("--passing-score", default="75.00")
    parser.add_argument("--time-limit-minutes", type=int, default=30)
    parser.add_argument("--reset-passwords", action="store_true")
    args = parser.parse_args(argv)

    if args.vapi_assistant_id is None or str(args.vapi_assistant_id).strip() == "":
        parser.error("Provide --vapi-assistant-id or set DEMO_VAPI_ASSISTANT_ID.")

    return DemoSeedConfig(
        admin_email=str(args.admin_email),
        admin_password=str(args.admin_password),
        assessor_email=str(args.assessor_email),
        assessor_password=str(args.assessor_password),
        candidate_email=str(args.candidate_email),
        candidate_password=str(args.candidate_password),
        vapi_assistant_id=_parse_uuid(str(args.vapi_assistant_id), "vapi-assistant-id"),
        assessment_title=str(args.assessment_title),
        assessment_description=str(args.assessment_description),
        passing_score=_parse_decimal(str(args.passing_score), "passing-score"),
        time_limit_minutes=_parse_positive_int(int(args.time_limit_minutes), "time-limit-minutes"),
        reset_passwords=bool(args.reset_passwords),
    )


def _parse_uuid(value: str, argument_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{argument_name} must be a UUID") from exc


def _parse_decimal(value: str, argument_name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"{argument_name} must be a decimal") from exc
    if parsed < Decimal("0.00") or parsed > Decimal("100.00"):
        raise argparse.ArgumentTypeError(f"{argument_name} must be between 0 and 100")
    return parsed.quantize(Decimal("0.01"))


def _parse_positive_int(value: int, argument_name: str) -> int:
    if value <= 0:
        raise argparse.ArgumentTypeError(f"{argument_name} must be positive")
    return value


def main() -> NoReturn:
    try:
        config = parse_args()
        result = asyncio.run(run_seed(config))
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc
    except (SQLAlchemyError, argparse.ArgumentTypeError) as exc:
        print(f"demo_seed: failed: {exc}")
        raise SystemExit(1) from exc

    print("demo_seed: ok")
    print(f"admin_id={result.admin_id}")
    print(f"assessor_id={result.assessor_id}")
    print(f"candidate_id={result.candidate_id}")
    print(f"assessment_id={result.assessment_id}")
    print(f"session_id={result.session_id}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
