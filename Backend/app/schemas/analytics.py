from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.enums import SessionStatus


class PlatformStats(BaseModel):
    total_users: int = Field(ge=0)
    total_assessments: int = Field(ge=0)
    total_sessions: int = Field(ge=0)
    sessions_by_status: dict[SessionStatus, int]
    pass_rate: float = Field(ge=0.0, le=1.0)
    avg_score: float = Field(ge=0.0, le=100.0)
    reports_generated_today: int = Field(ge=0)
    emails_sent_today: int = Field(ge=0)


class ScoreBucket(BaseModel):
    bucket: int = Field(ge=1, le=10)
    min_score: float = Field(ge=0.0, le=100.0)
    max_score: float = Field(ge=0.0, le=100.0)
    count: int = Field(ge=0)


class WeaknessAggregate(BaseModel):
    area: str = Field(min_length=1)
    count: int = Field(ge=0)
    avg_score: float = Field(ge=0.0, le=100.0)


class AssessmentPerformanceStats(BaseModel):
    assessment_id: UUID
    avg_score: float = Field(ge=0.0, le=100.0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    attempt_count: int = Field(ge=0)
    score_distribution: list[ScoreBucket]
    top_weaknesses: list[WeaknessAggregate]
