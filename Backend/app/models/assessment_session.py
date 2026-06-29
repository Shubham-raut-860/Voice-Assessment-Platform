from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.schemas.enums import SessionStatus, enum_values

if TYPE_CHECKING:
    from app.models.assessment import Assessment
    from app.models.assessment_report import AssessmentReport
    from app.models.user import User


class AssessmentSession(Base):
    __tablename__: str = "assessment_sessions"
    __table_args__: tuple[Index, ...] = (
        Index("ix_assessment_sessions_assessment_id", "assessment_id"),
        Index("ix_assessment_sessions_candidate_id", "candidate_id"),
        Index("ix_assessment_sessions_assessor_id", "assessor_id"),
        Index("ix_assessment_sessions_vapi_call_id", "vapi_call_id", unique=True),
        Index("ix_assessment_sessions_status", "status"),
        Index("ix_assessment_sessions_deleted_at", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    assessment_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "assessments.id",
            name="fk_assessment_sessions_assessment_id_assessments",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_assessment_sessions_candidate_id_users", ondelete="RESTRICT"),
        nullable=False,
    )
    assessor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_assessment_sessions_assessor_id_users", ondelete="SET NULL"),
        nullable=True,
    )
    vapi_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        SqlEnum(
            SessionStatus,
            name="assessment_session_status",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    vapi_analysis: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
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

    assessment: Mapped[Assessment] = relationship(
        "Assessment",
        back_populates="sessions",
        foreign_keys=[assessment_id],
        lazy="selectin",
    )
    candidate: Mapped[User] = relationship(
        "User",
        back_populates="candidate_assessment_sessions",
        foreign_keys=[candidate_id],
        lazy="selectin",
    )
    assessor: Mapped[User | None] = relationship(
        "User",
        back_populates="assessor_assessment_sessions",
        foreign_keys=[assessor_id],
        lazy="selectin",
    )
    report: Mapped[AssessmentReport | None] = relationship(
        "AssessmentReport",
        back_populates="session",
        foreign_keys="AssessmentReport.session_id",
        lazy="selectin",
        uselist=False,
    )
