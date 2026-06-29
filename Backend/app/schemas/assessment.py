from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import AssessmentStatus

ScoreDecimal = Annotated[Decimal, Field(ge=Decimal("0.00"), le=Decimal("100.00"), max_digits=5, decimal_places=2)]


class AssessmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    status: AssessmentStatus = AssessmentStatus.DRAFT
    vapi_assistant_id: UUID
    passing_score: ScoreDecimal
    time_limit_minutes: int = Field(gt=0, le=1440)


class AssessmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    status: AssessmentStatus | None = None
    vapi_assistant_id: UUID | None = None
    passing_score: ScoreDecimal | None = None
    time_limit_minutes: int | None = Field(default=None, gt=0, le=1440)


class AssessmentDB(BaseModel):
    id: UUID
    title: str
    description: str
    status: AssessmentStatus
    vapi_assistant_id: UUID
    passing_score: Decimal
    time_limit_minutes: int
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AssessmentResponse(BaseModel):
    id: UUID
    title: str
    description: str
    status: AssessmentStatus
    vapi_assistant_id: UUID
    passing_score: ScoreDecimal
    time_limit_minutes: int
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssessmentListResponse(BaseModel):
    items: list[AssessmentResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
