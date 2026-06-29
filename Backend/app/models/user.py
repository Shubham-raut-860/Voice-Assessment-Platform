from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, String, Text, func, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.schemas.enums import UserRole, enum_values

if TYPE_CHECKING:
    from app.models.assessment import Assessment
    from app.models.assessment_session import AssessmentSession


class User(Base):
    __tablename__: str = "users"
    __table_args__: tuple[Index, ...] = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_role", "role"),
        Index("ix_users_deleted_at", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole, name="user_role", values_callable=enum_values),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
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

    candidate_assessment_sessions: Mapped[list[AssessmentSession]] = relationship(
        "AssessmentSession",
        back_populates="candidate",
        foreign_keys="AssessmentSession.candidate_id",
        lazy="selectin",
    )
    assessor_assessment_sessions: Mapped[list[AssessmentSession]] = relationship(
        "AssessmentSession",
        back_populates="assessor",
        foreign_keys="AssessmentSession.assessor_id",
        lazy="selectin",
    )
    created_assessments: Mapped[list[Assessment]] = relationship(
        "Assessment",
        back_populates="creator",
        foreign_keys="Assessment.created_by_id",
        lazy="selectin",
    )
