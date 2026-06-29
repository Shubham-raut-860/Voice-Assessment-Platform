from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import structlog
from pydantic import ValidationError
from sqlalchemy import Select, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.engine import create_engine, create_sessionmaker, dispose_database
from app.models.assessment_report import AssessmentReport
from app.models.assessment_session import AssessmentSession
from app.models.webhook_event import WebhookEvent
from app.schemas.enums import ReportStatus, SessionStatus
from app.services.email_service import send_admin_alert_email

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ProbeThresholds:
    stale_generating_minutes: int
    failed_report_limit: int
    failed_webhook_limit: int
    failed_session_limit: int
    unsent_email_limit: int


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    value: int
    threshold: int
    detail: str


async def run_probe(settings: Settings, thresholds: ProbeThresholds) -> list[ProbeResult]:
    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)
    stale_before = datetime.now(UTC) - timedelta(minutes=thresholds.stale_generating_minutes)

    try:
        async with session_factory() as db:
            failed_reports = await _count_failed_reports(db)
            stale_generating_reports = await _count_stale_generating_reports(db, stale_before)
            failed_webhooks = await _count_failed_webhooks(db)
            failed_sessions = await _count_failed_sessions(db)
            unsent_completed_reports = await _count_unsent_completed_reports(db)
    finally:
        await dispose_database(engine)

    return [
        ProbeResult(
            name="failed_reports",
            ok=failed_reports <= thresholds.failed_report_limit,
            value=failed_reports,
            threshold=thresholds.failed_report_limit,
            detail="assessment_report_generation_failed backlog",
        ),
        ProbeResult(
            name="stale_generating_reports",
            ok=stale_generating_reports == 0,
            value=stale_generating_reports,
            threshold=0,
            detail=f"generation_status=generating older than {thresholds.stale_generating_minutes} minutes",
        ),
        ProbeResult(
            name="failed_webhooks",
            ok=failed_webhooks <= thresholds.failed_webhook_limit,
            value=failed_webhooks,
            threshold=thresholds.failed_webhook_limit,
            detail="processed webhook_events with error",
        ),
        ProbeResult(
            name="failed_sessions",
            ok=failed_sessions <= thresholds.failed_session_limit,
            value=failed_sessions,
            threshold=thresholds.failed_session_limit,
            detail="assessment_sessions with failed status",
        ),
        ProbeResult(
            name="unsent_completed_reports",
            ok=unsent_completed_reports <= thresholds.unsent_email_limit,
            value=unsent_completed_reports,
            threshold=thresholds.unsent_email_limit,
            detail="completed reports where email_sent_at is null",
        ),
    ]


async def send_probe_failure_alert(settings: Settings, results: list[ProbeResult]) -> None:
    failed_results = [result for result in results if not result.ok]
    if not failed_results:
        return

    lines = [
        "Voice Assessment operational probe failed.",
        "",
        f"Environment: {settings.environment.value}",
        "",
    ]
    for result in failed_results:
        lines.append(
            f"- {result.name}: value={result.value}, threshold={result.threshold}, detail={result.detail}"
        )

    await send_admin_alert_email(
        subject="Voice Assessment operational probe failed",
        body="\n".join(lines),
        settings=settings,
    )


async def _count_failed_reports(db: AsyncSession) -> int:
    query: Select[tuple[int]] = select(func.count()).select_from(AssessmentReport).where(
        AssessmentReport.deleted_at.is_(None),
        AssessmentReport.generation_status == ReportStatus.FAILED,
    )
    return int((await db.execute(query)).scalar_one())


async def _count_stale_generating_reports(db: AsyncSession, stale_before: datetime) -> int:
    query: Select[tuple[int]] = select(func.count()).select_from(AssessmentReport).where(
        AssessmentReport.deleted_at.is_(None),
        AssessmentReport.generation_status == ReportStatus.GENERATING,
        AssessmentReport.updated_at < stale_before,
    )
    return int((await db.execute(query)).scalar_one())


async def _count_failed_webhooks(db: AsyncSession) -> int:
    query: Select[tuple[int]] = select(func.count()).select_from(WebhookEvent).where(
        WebhookEvent.deleted_at.is_(None),
        WebhookEvent.processed.is_(True),
        WebhookEvent.error.is_not(None),
    )
    return int((await db.execute(query)).scalar_one())


async def _count_failed_sessions(db: AsyncSession) -> int:
    query: Select[tuple[int]] = select(func.count()).select_from(AssessmentSession).where(
        AssessmentSession.deleted_at.is_(None),
        AssessmentSession.status == SessionStatus.FAILED,
    )
    return int((await db.execute(query)).scalar_one())


async def _count_unsent_completed_reports(db: AsyncSession) -> int:
    query: Select[tuple[int]] = select(func.count()).select_from(AssessmentReport).where(
        AssessmentReport.deleted_at.is_(None),
        AssessmentReport.generation_status == ReportStatus.COMPLETED,
        AssessmentReport.email_sent_at.is_(None),
    )
    return int((await db.execute(query)).scalar_one())


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Probe operational database signals.")
    parser.add_argument("--stale-generating-minutes", type=int, default=15)
    parser.add_argument("--failed-report-limit", type=int, default=0)
    parser.add_argument("--failed-webhook-limit", type=int, default=0)
    parser.add_argument("--failed-session-limit", type=int, default=0)
    parser.add_argument("--unsent-email-limit", type=int, default=0)
    parser.add_argument("--send-alert-on-failure", action="store_true")
    args = parser.parse_args()

    thresholds = ProbeThresholds(
        stale_generating_minutes=int(args.stale_generating_minutes),
        failed_report_limit=int(args.failed_report_limit),
        failed_webhook_limit=int(args.failed_webhook_limit),
        failed_session_limit=int(args.failed_session_limit),
        unsent_email_limit=int(args.unsent_email_limit),
    )

    try:
        settings = Settings()
        results = asyncio.run(run_probe(settings, thresholds))
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc
    except SQLAlchemyError as exc:
        logger.exception("ops_probe_database_failed", error=str(exc))
        print(f"database: failed: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    for result in results:
        status = "ok" if result.ok else "failed"
        print(
            f"{result.name}: {status}: value={result.value} "
            f"threshold={result.threshold} detail={result.detail}"
        )

    if all(result.ok for result in results):
        print("ops_probe: ok")
        raise SystemExit(0)

    if bool(args.send_alert_on_failure):
        try:
            asyncio.run(send_probe_failure_alert(settings, results))
            print("ops_probe_alert: sent")
        except Exception as exc:
            logger.exception("ops_probe_alert_failed", error=str(exc))
            print(f"ops_probe_alert: failed: {type(exc).__name__}: {exc}")

    print("ops_probe: failed")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
