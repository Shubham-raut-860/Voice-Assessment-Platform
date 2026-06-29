from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260530_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM("admin", "assessor", "candidate", name="user_role", create_type=False)
assessment_status = postgresql.ENUM(
    "draft",
    "active",
    "completed",
    "archived",
    name="assessment_status",
    create_type=False,
)
session_status = postgresql.ENUM(
    "scheduled",
    "in_progress",
    "completed",
    "failed",
    "abandoned",
    name="assessment_session_status",
    create_type=False,
)
report_pass_fail = postgresql.ENUM(
    "pass",
    "fail",
    "inconclusive",
    name="assessment_report_pass_fail",
    create_type=False,
)
report_generation_status = postgresql.ENUM(
    "pending",
    "generating",
    "completed",
    "failed",
    name="assessment_report_generation_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))

    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    assessment_status.create(bind, checkfirst=True)
    session_status.create(bind, checkfirst=True)
    report_pass_fail.create(bind, checkfirst=True)
    report_generation_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    op.create_table(
        "assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", assessment_status, nullable=False),
        sa.Column("vapi_assistant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("passing_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_assessments_created_by_id_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_assessments_created_by_id", "assessments", ["created_by_id"])
    op.create_index("ix_assessments_status", "assessments", ["status"])
    op.create_index("ix_assessments_deleted_at", "assessments", ["deleted_at"])

    op.create_table(
        "assessment_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vapi_call_id", sa.String(length=255), nullable=True),
        sa.Column("status", session_status, nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("raw_transcript", sa.Text(), nullable=True),
        sa.Column("vapi_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name="fk_assessment_sessions_assessment_id_assessments",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["users.id"],
            name="fk_assessment_sessions_candidate_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assessor_id"],
            ["users.id"],
            name="fk_assessment_sessions_assessor_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_assessment_sessions_assessment_id", "assessment_sessions", ["assessment_id"])
    op.create_index("ix_assessment_sessions_candidate_id", "assessment_sessions", ["candidate_id"])
    op.create_index("ix_assessment_sessions_assessor_id", "assessment_sessions", ["assessor_id"])
    op.create_index("ix_assessment_sessions_vapi_call_id", "assessment_sessions", ["vapi_call_id"], unique=True)
    op.create_index("ix_assessment_sessions_status", "assessment_sessions", ["status"])
    op.create_index("ix_assessment_sessions_deleted_at", "assessment_sessions", ["deleted_at"])

    op.create_table(
        "assessment_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("overall_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("pass_fail", report_pass_fail, nullable=False),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("detailed_analysis", sa.Text(), nullable=False),
        sa.Column("recommendations", sa.Text(), nullable=False),
        sa.Column("anthropic_model_used", sa.String(length=100), nullable=False),
        sa.Column("anthropic_prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("anthropic_completion_tokens", sa.Integer(), nullable=False),
        sa.Column("generation_status", report_generation_status, nullable=False),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["assessment_sessions.id"],
            name="fk_assessment_reports_session_id_assessment_sessions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_assessment_reports_session_id", "assessment_reports", ["session_id"], unique=True)
    op.create_index("ix_assessment_reports_generation_status", "assessment_reports", ["generation_status"])
    op.create_index("ix_assessment_reports_deleted_at", "assessment_reports", ["deleted_at"])

    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("vapi_event_id", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webhook_events_event_type", "webhook_events", ["event_type"])
    op.create_index("ix_webhook_events_vapi_event_id", "webhook_events", ["vapi_event_id"], unique=True)
    op.create_index("ix_webhook_events_processed", "webhook_events", ["processed"])
    op.create_index("ix_webhook_events_deleted_at", "webhook_events", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_webhook_events_deleted_at", table_name="webhook_events")
    op.drop_index("ix_webhook_events_processed", table_name="webhook_events")
    op.drop_index("ix_webhook_events_vapi_event_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_event_type", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index("ix_assessment_reports_deleted_at", table_name="assessment_reports")
    op.drop_index("ix_assessment_reports_generation_status", table_name="assessment_reports")
    op.drop_index("ix_assessment_reports_session_id", table_name="assessment_reports")
    op.drop_table("assessment_reports")

    op.drop_index("ix_assessment_sessions_deleted_at", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_status", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_vapi_call_id", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_assessor_id", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_candidate_id", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_assessment_id", table_name="assessment_sessions")
    op.drop_table("assessment_sessions")

    op.drop_index("ix_assessments_deleted_at", table_name="assessments")
    op.drop_index("ix_assessments_status", table_name="assessments")
    op.drop_index("ix_assessments_created_by_id", table_name="assessments")
    op.drop_table("assessments")

    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    report_generation_status.drop(bind, checkfirst=True)
    report_pass_fail.drop(bind, checkfirst=True)
    session_status.drop(bind, checkfirst=True)
    assessment_status.drop(bind, checkfirst=True)
    user_role.drop(bind, checkfirst=True)
