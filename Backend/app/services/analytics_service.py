from __future__ import annotations

from typing import cast
from uuid import UUID

import structlog
from sqlalchemy import Select, case, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import AssessmentNotFoundError, SessionNotFoundError
from app.models.assessment import Assessment
from app.models.assessment_report import AssessmentReport
from app.models.assessment_session import AssessmentSession
from app.models.user import User
from app.schemas.analytics import AssessmentPerformanceStats, PlatformStats, ScoreBucket, WeaknessAggregate
from app.schemas.enums import PassFail, ReportStatus, SessionStatus

logger = structlog.get_logger(__name__)


async def get_platform_stats(db: AsyncSession) -> PlatformStats:
    status_counts = (
        select(
            AssessmentSession.status.label("status"),
            func.count(AssessmentSession.id).label("count"),
        )
        .where(AssessmentSession.deleted_at.is_(None))
        .group_by(AssessmentSession.status)
        .subquery()
    )

    sessions_by_status_subquery = (
        select(
            func.coalesce(
                func.jsonb_object_agg(status_counts.c.status, status_counts.c.count),
                text("'{}'::jsonb"),
            )
        )
        .select_from(status_counts)
        .scalar_subquery()
    )

    completed_reports_filter = (
        AssessmentReport.deleted_at.is_(None),
        AssessmentReport.generation_status == ReportStatus.COMPLETED,
    )
    today_start = func.date_trunc("day", func.now())

    query = select(
        select(func.count(User.id)).where(User.deleted_at.is_(None)).scalar_subquery().label("total_users"),
        select(func.count(Assessment.id))
        .where(Assessment.deleted_at.is_(None))
        .scalar_subquery()
        .label("total_assessments"),
        select(func.count(AssessmentSession.id))
        .where(AssessmentSession.deleted_at.is_(None))
        .scalar_subquery()
        .label("total_sessions"),
        sessions_by_status_subquery.label("sessions_by_status"),
        select(
            func.coalesce(
                func.avg(case((AssessmentReport.pass_fail == PassFail.PASS, 1.0), else_=0.0)),
                0.0,
            )
        )
        .where(*completed_reports_filter)
        .scalar_subquery()
        .label("pass_rate"),
        select(func.coalesce(func.avg(AssessmentReport.overall_score), 0.0))
        .where(*completed_reports_filter, AssessmentReport.overall_score.is_not(None))
        .scalar_subquery()
        .label("avg_score"),
        select(func.count(AssessmentReport.id))
        .where(
            AssessmentReport.deleted_at.is_(None),
            AssessmentReport.generated_at >= today_start,
        )
        .scalar_subquery()
        .label("reports_generated_today"),
        select(func.count(AssessmentReport.id))
        .where(
            AssessmentReport.deleted_at.is_(None),
            AssessmentReport.email_sent_at >= today_start,
        )
        .scalar_subquery()
        .label("emails_sent_today"),
    )

    try:
        row = (await db.execute(query)).one()
    except SQLAlchemyError as exc:
        logger.exception("platform_stats_query_failed", error=str(exc))
        raise

    sessions_by_status_raw = cast(dict[str, int] | None, row.sessions_by_status)
    sessions_by_status = {
        SessionStatus(status): int(count)
        for status, count in (sessions_by_status_raw or {}).items()
    }

    return PlatformStats(
        total_users=int(row.total_users),
        total_assessments=int(row.total_assessments),
        total_sessions=int(row.total_sessions),
        sessions_by_status=sessions_by_status,
        pass_rate=float(row.pass_rate),
        avg_score=float(row.avg_score),
        reports_generated_today=int(row.reports_generated_today),
        emails_sent_today=int(row.emails_sent_today),
    )


async def get_assessment_performance(
    db: AsyncSession,
    assessment_id: UUID,
) -> AssessmentPerformanceStats:
    await _ensure_assessment_exists(db, assessment_id)

    try:
        summary_result = await db.execute(
            text(
                """
                SELECT
                    COUNT(s.id)::int AS attempt_count,
                    COALESCE(AVG(ar.overall_score), 0)::float AS avg_score,
                    COALESCE(AVG(CASE WHEN ar.pass_fail = 'pass' THEN 1.0 ELSE 0.0 END), 0)::float AS pass_rate
                FROM assessment_sessions s
                LEFT JOIN assessment_reports ar
                    ON ar.session_id = s.id
                    AND ar.deleted_at IS NULL
                    AND ar.generation_status = 'completed'
                WHERE s.assessment_id = :assessment_id
                    AND s.deleted_at IS NULL
                """
            ),
            {"assessment_id": assessment_id},
        )
        summary = summary_result.one()

        distribution_result = await db.execute(
            text(
                """
                WITH buckets AS (
                    SELECT generate_series(1, 10) AS bucket
                ),
                scored AS (
                    SELECT
                        LEAST(GREATEST(width_bucket(ar.overall_score, 0, 100, 10), 1), 10) AS bucket,
                        COUNT(*)::int AS count
                    FROM assessment_sessions s
                    JOIN assessment_reports ar
                        ON ar.session_id = s.id
                        AND ar.deleted_at IS NULL
                        AND ar.generation_status = 'completed'
                        AND ar.overall_score IS NOT NULL
                    WHERE s.assessment_id = :assessment_id
                        AND s.deleted_at IS NULL
                    GROUP BY bucket
                )
                SELECT
                    b.bucket::int AS bucket,
                    ((b.bucket - 1) * 10)::float AS min_score,
                    CASE WHEN b.bucket = 10 THEN 100::float ELSE (b.bucket * 10)::float END AS max_score,
                    COALESCE(scored.count, 0)::int AS count
                FROM buckets b
                LEFT JOIN scored ON scored.bucket = b.bucket
                ORDER BY b.bucket
                """
            ),
            {"assessment_id": assessment_id},
        )
        distribution_rows = distribution_result.mappings().all()

        weakness_result = await db.execute(
            text(
                """
                SELECT
                    weakness->>'area' AS area,
                    COUNT(*)::int AS count,
                    COALESCE(AVG((weakness->>'score')::numeric), 0)::float AS avg_score
                FROM assessment_sessions s
                JOIN assessment_reports ar
                    ON ar.session_id = s.id
                    AND ar.deleted_at IS NULL
                    AND ar.generation_status = 'completed'
                CROSS JOIN LATERAL jsonb_array_elements(ar.weaknesses) AS weakness
                WHERE s.assessment_id = :assessment_id
                    AND s.deleted_at IS NULL
                    AND weakness ? 'area'
                    AND weakness ? 'score'
                GROUP BY weakness->>'area'
                ORDER BY count DESC, avg_score ASC
                LIMIT 5
                """
            ),
            {"assessment_id": assessment_id},
        )
        weakness_rows = weakness_result.mappings().all()
    except SQLAlchemyError as exc:
        logger.exception("assessment_performance_query_failed", assessment_id=str(assessment_id), error=str(exc))
        raise

    score_distribution = [
        ScoreBucket(
            bucket=int(row["bucket"]),
            min_score=float(row["min_score"]),
            max_score=float(row["max_score"]),
            count=int(row["count"]),
        )
        for row in distribution_rows
    ]
    top_weaknesses = [
        WeaknessAggregate(
            area=str(row["area"]),
            count=int(row["count"]),
            avg_score=float(row["avg_score"]),
        )
        for row in weakness_rows
    ]

    return AssessmentPerformanceStats(
        assessment_id=assessment_id,
        avg_score=float(summary.avg_score),
        pass_rate=float(summary.pass_rate),
        attempt_count=int(summary.attempt_count),
        score_distribution=score_distribution,
        top_weaknesses=top_weaknesses,
    )


async def list_failed_sessions(
    db: AsyncSession,
    page: int,
    page_size: int,
) -> tuple[list[AssessmentSession], int]:
    filters = (
        AssessmentSession.deleted_at.is_(None),
        AssessmentSession.status == SessionStatus.FAILED,
    )
    try:
        total = int(
            (
                await db.execute(
                    select(func.count(AssessmentSession.id)).where(*filters)
                )
            ).scalar_one()
        )
        query: Select[tuple[AssessmentSession]] = (
            select(AssessmentSession)
            .options(
                selectinload(AssessmentSession.assessment),
                selectinload(AssessmentSession.candidate),
                selectinload(AssessmentSession.assessor),
                selectinload(AssessmentSession.report),
            )
            .where(*filters)
            .order_by(AssessmentSession.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)
        sessions = list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.exception("failed_sessions_query_failed", error=str(exc))
        raise

    return sessions, total


async def retry_report_generation(
    db: AsyncSession,
    session_id: UUID,
) -> None:
    try:
        query: Select[tuple[AssessmentSession]] = (
            select(AssessmentSession)
            .options(selectinload(AssessmentSession.report))
            .where(
                AssessmentSession.id == session_id,
                AssessmentSession.deleted_at.is_(None),
            )
        )
        result = await db.execute(query)
        session = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("retry_report_session_lookup_failed", session_id=str(session_id), error=str(exc))
        raise

    if session is None:
        raise SessionNotFoundError(f"session_not_found:{session_id}")

    if session.report is not None:
        session.report.generation_status = ReportStatus.PENDING
        session.report.generation_error = None
        session.report.generated_at = None

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("retry_report_reset_failed", session_id=str(session_id), error=str(exc))
        raise

    logger.info(
        "report_generation_retry_reset",
        session_id=str(session_id),
    )


async def _ensure_assessment_exists(db: AsyncSession, assessment_id: UUID) -> None:
    try:
        query = select(Assessment.id).where(
            Assessment.id == assessment_id,
            Assessment.deleted_at.is_(None),
        )
        exists = (await db.execute(query)).scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("assessment_exists_query_failed", assessment_id=str(assessment_id), error=str(exc))
        raise

    if exists is None:
        raise AssessmentNotFoundError(f"assessment_not_found:{assessment_id}")
