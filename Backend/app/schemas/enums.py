from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

EnumValue = TypeVar("EnumValue", bound=StrEnum)


def enum_values(enum_class: type[EnumValue]) -> list[str]:
    return [member.value for member in enum_class]


class UserRole(StrEnum):
    ADMIN = "admin"
    ASSESSOR = "assessor"
    CANDIDATE = "candidate"


class AssessmentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class SessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class ReportStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class PassFail(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class VapiCallEndReason(StrEnum):
    ASSISTANT_ENDED = "assistant_ended"
    CUSTOMER_ENDED = "customer_ended"
    TIME_LIMIT = "time_limit"
    ERROR = "error"
    PIPELINE_ERROR = "pipeline-error"
    NO_ANSWER = "no-answer"
    VOICEMAIL = "voicemail"
    MACHINE_END_CALL = "machine-end-call"
    EXCEEDED_MAX_DURATION = "exceeded-max-duration"
    ASSISTANT_ERROR = "assistant-error"
    CUSTOMER_DID_NOT_GIVE_MICROPHONE_PERMISSION = "customer-did-not-give-microphone-permission"
    UNKNOWN = "unknown"


class VapiTranscriptRole(StrEnum):
    ASSISTANT = "assistant"
    USER = "user"
