from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import PassFail, ReportStatus

ScoreDecimal = Annotated[Decimal, Field(ge=Decimal("0.00"), le=Decimal("100.00"), max_digits=5, decimal_places=2)]


class ReportFinding(TypedDict):
    area: str
    evidence: str
    score: float


class ReportDB(BaseModel):
    id: UUID
    session_id: UUID
    version: int
    overall_score: Decimal | None
    pass_fail: PassFail
    strengths: list[ReportFinding]
    weaknesses: list[ReportFinding]
    detailed_analysis: str
    recommendations: str
    anthropic_model_used: str
    anthropic_prompt_tokens: int
    anthropic_completion_tokens: int
    generation_status: ReportStatus
    generation_error: str | None
    generated_at: datetime | None
    email_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportResponse(BaseModel):
    id: UUID
    session_id: UUID
    version: int = Field(ge=1)
    overall_score: ScoreDecimal | None
    pass_fail: PassFail
    strengths: list[ReportFinding]
    weaknesses: list[ReportFinding]
    detailed_analysis: str
    recommendations: str
    anthropic_model_used: str = Field(max_length=100)
    anthropic_prompt_tokens: int = Field(ge=0)
    anthropic_completion_tokens: int = Field(ge=0)
    generation_status: ReportStatus
    generation_error: str | None
    generated_at: datetime | None
    email_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportGenerationStatus(BaseModel):
    session_id: UUID
    status: ReportStatus
    generated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
