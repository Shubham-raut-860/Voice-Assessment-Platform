from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.schemas.enums import PassFail, ReportStatus, enum_values

if TYPE_CHECKING:
    from app.models.assessment_session import AssessmentSession


class AssessmentReport(Base):
    __tablename__: str = "assessment_reports"
    __table_args__: tuple[Index, ...] = (
        Index("ix_assessment_reports_session_id", "session_id", unique=True),
        Index("ix_assessment_reports_generation_status", "generation_status"),
        Index("ix_assessment_reports_deleted_at", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "assessment_sessions.id",
            name="fk_assessment_reports_session_id_assessment_sessions",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    pass_fail: Mapped[PassFail] = mapped_column(
        SqlEnum(
            PassFail,
            name="assessment_report_pass_fail",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    strengths: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    weaknesses: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    detailed_analysis: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations: Mapped[str] = mapped_column(Text, nullable=False)
    anthropic_model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    anthropic_prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    anthropic_completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_status: Mapped[ReportStatus] = mapped_column(
        SqlEnum(
            ReportStatus,
            name="assessment_report_generation_status",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[AssessmentSession] = relationship(
        "AssessmentSession",
        back_populates="report",
        foreign_keys=[session_id],
        lazy="selectin",
        uselist=False,
    )
