from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace
from decimal import Decimal
from uuid import uuid4

import pytest
from pytest import MonkeyPatch

from app.config import Settings
from app.exceptions import EmailDeliveryError
from app.models.assessment import Assessment
from app.models.assessment_report import AssessmentReport
from app.models.assessment_session import AssessmentSession
from app.models.user import User
from app.schemas.enums import AssessmentStatus, PassFail, ReportStatus, SessionStatus, UserRole
from app.services.anthropic_service import build_assessment_prompt
from app.services import email_service
from app.services.email_service import build_report_email_html, send_report_email, send_resend_test_email


def test_build_report_email_html_contains_report_content() -> None:
    candidate, assessment, report, _session = _objects()

    html = build_report_email_html(report, candidate, assessment)

    assert "Jane Candidate" in html
    assert "Support Assessment" in html
    assert "82.25/100" in html
    assert "Discovery" in html
    assert "<table" in html


def test_send_report_email_rejects_incomplete_report() -> None:
    _candidate, _assessment, report, session = _objects()
    report.generation_status = ReportStatus.FAILED
    settings = Settings()

    with pytest.raises(EmailDeliveryError):
        asyncio.run(send_report_email(report, session, settings))

    assert report.email_sent_at is None


def test_create_resend_client_rejects_sdk_without_async_client(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "resend", SimpleNamespace())

    with pytest.raises(EmailDeliveryError, match="resend_async_client_unavailable"):
        email_service._create_async_resend_client("test_api_key")


@pytest.mark.asyncio
async def test_send_report_email_sets_sent_timestamp_on_success(monkeypatch: MonkeyPatch) -> None:
    _candidate, _assessment, report, session = _objects()
    settings = Settings()

    monkeypatch.setattr(email_service, "_create_async_resend_client", _fake_resend_client_success)

    message_id = await send_report_email(report, session, settings)

    assert message_id == "email_phase4_success"
    assert report.email_sent_at is not None


@pytest.mark.asyncio
async def test_send_report_email_preserves_unsent_state_on_failure(monkeypatch: MonkeyPatch) -> None:
    _candidate, _assessment, report, session = _objects()
    settings = Settings()

    monkeypatch.setattr(email_service, "_create_async_resend_client", _fake_resend_client_failure)

    with pytest.raises(EmailDeliveryError):
        await send_report_email(report, session, settings)

    assert report.email_sent_at is None


@pytest.mark.asyncio
async def test_send_report_email_retries_transient_failure(monkeypatch: MonkeyPatch) -> None:
    _candidate, _assessment, report, session = _objects()
    settings = Settings()

    _FakeEmailsTransientFailureThenSuccess.attempts = 0
    monkeypatch.setattr(email_service, "_create_async_resend_client", _fake_resend_client_transient_then_success)
    monkeypatch.setattr(email_service.asyncio, "sleep", _fake_sleep)

    message_id = await send_report_email(report, session, settings)

    assert message_id == "email_phase4_retry_success"
    assert _FakeEmailsTransientFailureThenSuccess.attempts == 2
    assert report.email_sent_at is not None


@pytest.mark.asyncio
async def test_send_resend_test_email_uses_configured_sender(monkeypatch: MonkeyPatch) -> None:
    settings = Settings()

    monkeypatch.setattr(email_service, "_create_async_resend_client", _fake_resend_client_success)

    message_id = await send_resend_test_email("[email-redacted]", settings)

    assert message_id == "email_phase4_success"
    assert _FakeEmailsSuccess.last_payload == {
        "from": settings.resend_from_email,
        "to": ["[email-redacted]"],
        "subject": "Hello World",
        "html": "<p>Congrats on sending your <strong>first email</strong>!</p>",
    }


def test_build_assessment_prompt_uses_session_data() -> None:
    _candidate, assessment, _report, session = _objects()
    transcript = [
        {
            "role": "user",
            "content": "I would ask clarifying questions before proposing a solution.",
            "timestamp": 1.0,
        }
    ]
    session.raw_transcript = json.dumps(transcript)
    session.assessment = assessment

    prompt = asyncio.run(build_assessment_prompt(session))

    assert "Support Assessment" in prompt
    assert "clarifying questions" in prompt
    assert str(session.id) in prompt


def _objects() -> tuple[User, Assessment, AssessmentReport, AssessmentSession]:
    candidate = User(
        id=uuid4(),
        email="[email-redacted]",
        hashed_password="hashed",
        full_name="Jane Candidate",
        role=UserRole.CANDIDATE,
    )
    assessment = Assessment(
        id=uuid4(),
        title="Support Assessment",
        description="Evaluate support troubleshooting clarity.",
        status=AssessmentStatus.ACTIVE,
        vapi_assistant_id=uuid4(),
        passing_score=Decimal("70.00"),
        time_limit_minutes=30,
        created_by_id=uuid4(),
    )
    session = AssessmentSession(
        id=uuid4(),
        assessment_id=assessment.id,
        candidate_id=candidate.id,
        vapi_call_id="call_123",
        status=SessionStatus.COMPLETED,
    )
    session.candidate = candidate
    session.assessment = assessment
    report = AssessmentReport(
        id=uuid4(),
        session_id=session.id,
        version=1,
        overall_score=Decimal("82.25"),
        pass_fail=PassFail.PASS,
        strengths=[{"area": "Discovery", "evidence": "Asked clarifying questions.", "score": 86.0}],
        weaknesses=[{"area": "Closing", "evidence": "Did not summarize next steps.", "score": 62.0}],
        detailed_analysis="The candidate communicated clearly.",
        recommendations="Practice concise closing summaries.",
        anthropic_model_used="claude-sonnet-4-6",
        anthropic_prompt_tokens=120,
        anthropic_completion_tokens=80,
        generation_status=ReportStatus.COMPLETED,
    )
    session.report = report
    return candidate, assessment, report, session


def _fake_resend_client_success(api_key: str) -> "_FakeResendClientSuccess":
    _ = api_key
    return _FakeResendClientSuccess()


def _fake_resend_client_failure(api_key: str) -> "_FakeResendClientFailure":
    _ = api_key
    return _FakeResendClientFailure()


def _fake_resend_client_transient_then_success(api_key: str) -> "_FakeResendClientTransientFailureThenSuccess":
    _ = api_key
    return _FakeResendClientTransientFailureThenSuccess()


async def _fake_sleep(delay: float) -> None:
    _ = delay


class _FakeResendClientSuccess:
    emails: "_FakeEmailsSuccess"

    def __init__(self) -> None:
        self.emails = _FakeEmailsSuccess()


class _FakeEmailsSuccess:
    last_payload: dict[str, object] | None = None

    async def send(self, payload: dict[str, object]) -> dict[str, str]:
        self.__class__.last_payload = payload
        return {"id": "email_phase4_success"}


class _FakeResendClientFailure:
    emails: "_FakeEmailsFailure"

    def __init__(self) -> None:
        self.emails = _FakeEmailsFailure()


class _FakeEmailsFailure:
    async def send(self, payload: dict[str, object]) -> dict[str, str]:
        _ = payload
        raise RuntimeError("simulated_resend_failure")


class _FakeResendClientTransientFailureThenSuccess:
    emails: "_FakeEmailsTransientFailureThenSuccess"

    def __init__(self) -> None:
        self.emails = _FakeEmailsTransientFailureThenSuccess()


class _FakeEmailsTransientFailureThenSuccess:
    attempts: int = 0

    async def send(self, payload: dict[str, object]) -> dict[str, str]:
        _ = payload
        self.__class__.attempts += 1
        if self.__class__.attempts == 1:
            raise RuntimeError("connection reset by peer")
        return {"id": "email_phase4_retry_success"}
