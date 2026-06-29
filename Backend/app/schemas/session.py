from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assessment import AssessmentResponse
from app.schemas.enums import SessionStatus
from app.schemas.user import UserResponse


class SessionCreate(BaseModel):
    assessment_id: UUID
    candidate_id: UUID
    assessor_id: UUID | None = None
    scheduled_at: datetime | None = None


class SessionUpdate(BaseModel):
    assessor_id: UUID | None = None
    vapi_call_id: str | None = Field(default=None, min_length=1, max_length=255)
    status: SessionStatus | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    raw_transcript: str | None = None


class StartCallRequest(BaseModel):
    customer_number: str | None = Field(
        default=None,
        min_length=8,
        max_length=16,
        pattern=r"^\+[1-9]\d{7,14}$",
        description="Candidate phone number in E.164 format. Required only when VAPI_CALL_MODE=phone.",
    )


class StartCallResponse(BaseModel):
    call_id: str = Field(min_length=1)
    web_call_url: str | None = None


class BindWebCallRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=255)


class SessionDB(BaseModel):
    id: UUID
    assessment_id: UUID
    candidate_id: UUID
    assessor_id: UUID | None
    vapi_call_id: str | None
    status: SessionStatus
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    raw_transcript: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseModel):
    id: UUID
    assessment_id: UUID
    candidate_id: UUID
    assessor_id: UUID | None
    vapi_call_id: str | None
    status: SessionStatus
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    raw_transcript: str | None
    created_at: datetime
    updated_at: datetime
    assessment: AssessmentResponse
    candidate: UserResponse
    assessor: UserResponse | None

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
