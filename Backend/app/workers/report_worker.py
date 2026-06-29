from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import Select, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.engine import connect_database, create_engine, create_sessionmaker, dispose_database
from app.logging_config import configure_logging
from app.models.assessment_report import AssessmentReport
from app.schemas.enums import ReportStatus
from app.services.anthropic_service import trigger_report_generation

logger = structlog.get_logger(__name__)
DEFAULT_BATCH_SIZE = 5
DEFAULT_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_STALE_AFTER_SECONDS = 900


async def claim_report_sessions(
    db: AsyncSession,
    batch_size: int = DEFAULT_BATCH_SIZE,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> list[UUID]:
    stale_before = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    try:
        query: Select[tuple[AssessmentReport]] = (
            select(AssessmentReport)
            .where(
                AssessmentReport.deleted_at.is_(None),
                or_(
                    AssessmentReport.generation_status == ReportStatus.PENDING,
                    (
                        (AssessmentReport.generation_status == ReportStatus.GENERATING)
                        & (AssessmentReport.updated_at < stale_before)
                    ),
                ),
            )
            .order_by(AssessmentReport.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(query)
        reports = list(result.scalars().all())

        for report in reports:
            report.generation_status = ReportStatus.GENERATING
            report.generation_error = None

        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("report_worker_claim_failed", error=str(exc))
        raise

    session_ids = [report.session_id for report in reports]
    if session_ids:
        logger.info("report_worker_claimed_reports", count=len(session_ids))
    return session_ids


async def run_worker_once(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    batch_size: int = DEFAULT_BATCH_SIZE,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> int:
    async with session_factory() as claim_session:
        session_ids = await claim_report_sessions(
            claim_session,
            batch_size=batch_size,
            stale_after_seconds=stale_after_seconds,
        )

    for session_id in session_ids:
        async with session_factory() as generation_session:
            await trigger_report_generation(session_id, generation_session, settings, claimed=True)

    return len(session_ids)


async def run_worker_forever(
    settings: Settings,
    batch_size: int = DEFAULT_BATCH_SIZE,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> None:
    configure_logging(settings)
    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)

    await connect_database(engine)
    logger.info(
        "report_worker_started",
        batch_size=batch_size,
        poll_interval_seconds=poll_interval_seconds,
        stale_after_seconds=stale_after_seconds,
    )
    try:
        while True:
            processed = await run_worker_once(
                session_factory,
                settings,
                batch_size=batch_size,
                stale_after_seconds=stale_after_seconds,
            )
            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)
    finally:
        logger.info("report_worker_stopping")
        await dispose_database(engine)


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    batch_size = _read_int_arg(args, "--batch-size", DEFAULT_BATCH_SIZE)
    poll_interval_seconds = float(_read_int_arg(args, "--poll-seconds", int(DEFAULT_POLL_INTERVAL_SECONDS)))
    stale_after_seconds = _read_int_arg(args, "--stale-after-seconds", DEFAULT_STALE_AFTER_SECONDS)
    settings = Settings()
    asyncio.run(
        run_worker_forever(
            settings,
            batch_size=batch_size,
            poll_interval_seconds=poll_interval_seconds,
            stale_after_seconds=stale_after_seconds,
        )
    )


def _read_int_arg(args: list[str], name: str, default: int) -> int:
    if name not in args:
        return default
    index = args.index(name)
    value_index = index + 1
    if value_index >= len(args):
        raise ValueError(f"{name} requires an integer value")
    return int(args[value_index])


if __name__ == "__main__":
    main()
