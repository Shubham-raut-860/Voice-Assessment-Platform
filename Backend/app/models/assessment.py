from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.schemas.enums import AssessmentStatus, enum_values

if TYPE_CHECKING:
    from app.models.assessment_session import AssessmentSession
    from app.models.user import User


class Assessment(Base):
    __tablename__: str = "assessments"
    __table_args__: tuple[Index, ...] = (
        Index("ix_assessments_created_by_id", "created_by_id"),
        Index("ix_assessments_status", "status"),
        Index("ix_assessments_deleted_at", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AssessmentStatus] = mapped_column(
        SqlEnum(AssessmentStatus, name="assessment_status", values_callable=enum_values),
        nullable=False,
    )
    vapi_assistant_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    passing_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    time_limit_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_assessments_created_by_id_users", ondelete="RESTRICT"),
        nullable=False,
    )
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

    creator: Mapped[User] = relationship(
        "User",
        back_populates="created_assessments",
        foreign_keys=[created_by_id],
        lazy="selectin",
    )
    sessions: Mapped[list[AssessmentSession]] = relationship(
        "AssessmentSession",
        back_populates="assessment",
        foreign_keys="AssessmentSession.assessment_id",
        lazy="selectin",
    )
