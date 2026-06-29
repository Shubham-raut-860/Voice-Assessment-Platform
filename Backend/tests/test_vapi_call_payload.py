from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings, VapiCallMode
from app.models.assessment import Assessment
from app.models.assessment_session import AssessmentSession
from app.schemas.enums import AssessmentStatus, SessionStatus
from app.schemas.session import StartCallRequest
from app.services.session_service import build_vapi_call_payload, build_vapi_phone_call_payload, build_vapi_web_call_payload


def test_start_call_request_accepts_empty_body_for_web_call_mode() -> None:
    assert StartCallRequest().customer_number is None
    assert StartCallRequest(customer_number="+15551234567").customer_number == "+15551234567"

    with pytest.raises(ValidationError):
        StartCallRequest(customer_number="5551234567")


def test_build_vapi_phone_call_payload_matches_outbound_contract() -> None:
    assessment_id = uuid4()
    candidate_id = uuid4()
    assistant_id = uuid4()
    creator_id = uuid4()
    session_id = uuid4()
    assessment = Assessment(
        id=assessment_id,
        title="Backend Engineer Screen",
        description="Assess backend production judgment.",
        status=AssessmentStatus.ACTIVE,
        vapi_assistant_id=assistant_id,
        passing_score=Decimal("75.00"),
        time_limit_minutes=30,
        created_by_id=creator_id,
    )
    session = AssessmentSession(
        id=session_id,
        assessment_id=assessment_id,
        candidate_id=candidate_id,
        assessor_id=None,
        vapi_call_id=None,
        status=SessionStatus.SCHEDULED,
        assessment=assessment,
    )
    settings = Settings().model_copy(update={"vapi_call_mode": VapiCallMode.WEB})

    payload = build_vapi_phone_call_payload(session, settings, "+15551234567")

    assert payload["type"] == "outboundPhoneCall"
    assert payload["assistantId"] == str(assistant_id)
    assert payload["phoneNumberId"] == settings.vapi_phone_number_id
    assert payload["customer"] == {"number": "+15551234567"}
    assert payload["metadata"] == {
        "session_id": str(session_id),
        "assessment_id": str(assessment_id),
        "candidate_id": str(candidate_id),
    }


def test_build_vapi_web_call_payload_omits_phone_fields() -> None:
    assessment_id = uuid4()
    candidate_id = uuid4()
    assistant_id = uuid4()
    creator_id = uuid4()
    session_id = uuid4()
    assessment = Assessment(
        id=assessment_id,
        title="Backend Engineer Screen",
        description="Assess backend production judgment.",
        status=AssessmentStatus.ACTIVE,
        vapi_assistant_id=assistant_id,
        passing_score=Decimal("75.00"),
        time_limit_minutes=30,
        created_by_id=creator_id,
    )
    session = AssessmentSession(
        id=session_id,
        assessment_id=assessment_id,
        candidate_id=candidate_id,
        assessor_id=None,
        vapi_call_id=None,
        status=SessionStatus.SCHEDULED,
        assessment=assessment,
    )

    payload = build_vapi_web_call_payload(session)

    assert payload["type"] == "webCall"
    assert payload["assistantId"] == str(assistant_id)
    assert "phoneNumberId" not in payload
    assert "customer" not in payload
    assert payload["metadata"] == {
        "session_id": str(session_id),
        "assessment_id": str(assessment_id),
        "candidate_id": str(candidate_id),
    }


def test_build_vapi_call_payload_defaults_to_web_mode() -> None:
    assessment_id = uuid4()
    candidate_id = uuid4()
    assistant_id = uuid4()
    creator_id = uuid4()
    session_id = uuid4()
    assessment = Assessment(
        id=assessment_id,
        title="Backend Engineer Screen",
        description="Assess backend production judgment.",
        status=AssessmentStatus.ACTIVE,
        vapi_assistant_id=assistant_id,
        passing_score=Decimal("75.00"),
        time_limit_minutes=30,
        created_by_id=creator_id,
    )
    session = AssessmentSession(
        id=session_id,
        assessment_id=assessment_id,
        candidate_id=candidate_id,
        assessor_id=None,
        vapi_call_id=None,
        status=SessionStatus.SCHEDULED,
        assessment=assessment,
    )
    settings = Settings().model_copy(update={"vapi_call_mode": VapiCallMode.WEB})

    payload = build_vapi_call_payload(session, settings, None)

    assert payload["type"] == "webCall"


def test_build_vapi_call_payload_rejects_phone_number_when_phone_mode_disabled() -> None:
    assessment_id = uuid4()
    candidate_id = uuid4()
    assistant_id = uuid4()
    creator_id = uuid4()
    session_id = uuid4()
    assessment = Assessment(
        id=assessment_id,
        title="Backend Engineer Screen",
        description="Assess backend production judgment.",
        status=AssessmentStatus.ACTIVE,
        vapi_assistant_id=assistant_id,
        passing_score=Decimal("75.00"),
        time_limit_minutes=30,
        created_by_id=creator_id,
    )
    session = AssessmentSession(
        id=session_id,
        assessment_id=assessment_id,
        candidate_id=candidate_id,
        assessor_id=None,
        vapi_call_id=None,
        status=SessionStatus.SCHEDULED,
        assessment=assessment,
    )
    settings = Settings().model_copy(update={"vapi_call_mode": VapiCallMode.WEB})

    with pytest.raises(HTTPException) as exc_info:
        build_vapi_call_payload(session, settings, "+15551234567")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "phone_call_mode_not_enabled"
