from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from app.schemas.enums import VapiCallEndReason, VapiTranscriptRole


class VapiTranscriptMessage(BaseModel):
    role: VapiTranscriptRole
    content: str = Field(min_length=1)
    timestamp: float = Field(ge=0)


class VapiCallStartedEvent(BaseModel):
    type: Literal["call.started"]
    call_id: str = Field(min_length=1, max_length=255)
    assistant_id: str = Field(min_length=1, max_length=255)
    started_at: datetime


class VapiCallEndedEvent(BaseModel):
    type: Literal["call.ended"]
    call_id: str = Field(min_length=1, max_length=255)
    ended_at: datetime
    duration_seconds: int = Field(ge=0)
    end_reason: VapiCallEndReason = VapiCallEndReason.UNKNOWN

    @field_validator("end_reason", mode="before")
    @classmethod
    def coerce_unknown_end_reason(cls, value: object) -> object:
        if isinstance(value, str) and value not in VapiCallEndReason._value2member_map_:
            return VapiCallEndReason.UNKNOWN
        return value


class VapiTranscriptUpdateEvent(BaseModel):
    type: Literal["transcript.update"]
    call_id: str = Field(min_length=1, max_length=255)
    transcript: list[VapiTranscriptMessage] = Field(min_length=1)


class VapiAnalysisDoneEvent(BaseModel):
    type: Literal["analysis.done"]
    call_id: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1)
    structured_data: dict[str, object]


class VapiUnknownEvent(BaseModel):
    type: str = Field(min_length=1)
    raw_payload: dict[str, object]

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def preserve_raw_payload(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload: dict[str, object] = dict(data)
        event_type_raw: object = payload.get("type", "unknown")
        event_type = event_type_raw if isinstance(event_type_raw, str) and event_type_raw else "unknown"
        return {"type": event_type, "raw_payload": payload}


KnownVapiWebhookEvent = Annotated[
    VapiCallStartedEvent
    | VapiCallEndedEvent
    | VapiTranscriptUpdateEvent
    | VapiAnalysisDoneEvent,
    Field(discriminator="type"),
]
VapiWebhookEvent = KnownVapiWebhookEvent | VapiUnknownEvent


class VapiWebhookPayload(RootModel[VapiWebhookEvent]):
    root: VapiWebhookEvent

    @model_validator(mode="before")
    @classmethod
    def route_unknown_events(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        event_type: object = data.get("type")
        known_event_types: set[str] = {
            "call.started",
            "call.ended",
            "transcript.update",
            "analysis.done",
        }
        if event_type in known_event_types:
            return data
        return VapiUnknownEvent.model_validate(data)


VapiCallStarted: TypeAlias = VapiCallStartedEvent
VapiCallEnded: TypeAlias = VapiCallEndedEvent
VapiTranscriptUpdate: TypeAlias = VapiTranscriptUpdateEvent
VapiAnalysisDone: TypeAlias = VapiAnalysisDoneEvent
