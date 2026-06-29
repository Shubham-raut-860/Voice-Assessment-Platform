from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.assessment_report import AssessmentReport
from app.models.assessment_session import AssessmentSession
from app.schemas.enums import PassFail, ReportStatus, SessionStatus
from scripts.check_demo_session import parse_args as parse_check_args
from scripts.prepare_live_vapi_demo import _assert_live_vapi_settings, _local_urls_match
from scripts.run_presentation_demo import parse_args as parse_presentation_args
from scripts.seed_demo_data import parse_args as parse_seed_args
from scripts.start_demo_vapi_call import parse_args as parse_start_args
from scripts.verify_live_e2e import evaluate_live_e2e_status, parse_args as parse_live_e2e_args


def test_seed_demo_parse_args_accepts_required_assistant_id() -> None:
    config = parse_seed_args(
        [
            "--vapi-assistant-id",
            "11111111-1111-4111-8111-111111111111",
            "--passing-score",
            "82.50",
            "--time-limit-minutes",
            "45",
        ]
    )

    assert config.vapi_assistant_id == UUID("11111111-1111-4111-8111-111111111111")
    assert config.passing_score == Decimal("82.50")
    assert config.time_limit_minutes == 45


def test_seed_demo_parse_args_rejects_missing_assistant_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_VAPI_ASSISTANT_ID", raising=False)

    with pytest.raises(SystemExit):
        parse_seed_args([])


def test_start_demo_call_parse_args_validates_phone_number() -> None:
    config = parse_start_args(
        [
            "--session-id",
            "22222222-2222-4222-8222-222222222222",
            "--customer-number",
            "+15551234567",
        ]
    )

    assert config.session_id == UUID("22222222-2222-4222-8222-222222222222")
    assert config.customer_number == "+15551234567"


def test_start_demo_call_parse_args_rejects_non_e164_phone_number() -> None:
    with pytest.raises(SystemExit):
        parse_start_args(
            [
                "--session-id",
                "22222222-2222-4222-8222-222222222222",
                "--customer-number",
                "5551234567",
            ]
        )


def test_check_demo_session_parse_args_accepts_session_uuid() -> None:
    session_id = parse_check_args(["--session-id", "33333333-3333-4333-8333-333333333333"])

    assert session_id == UUID("33333333-3333-4333-8333-333333333333")


def test_presentation_demo_defaults_to_simulated_vapi_mode() -> None:
    config = parse_presentation_args([])

    assert config.mode == "simulated-vapi"
    assert config.customer_number is None
    assert config.vapi_assistant_id == UUID("11111111-1111-4111-8111-111111111111")


def test_presentation_demo_accepts_live_vapi_mode() -> None:
    config = parse_presentation_args(
        [
            "--mode",
            "live-vapi",
            "--vapi-assistant-id",
            "44444444-4444-4444-8444-444444444444",
            "--customer-number",
            "+15551234567",
        ]
    )

    assert config.mode == "live-vapi"
    assert config.vapi_assistant_id == UUID("44444444-4444-4444-8444-444444444444")
    assert config.customer_number == "+15551234567"


def test_live_vapi_ngrok_tunnel_match_accepts_localhost_equivalents() -> None:
    assert _local_urls_match("http://localhost:8000", "http://127.0.0.1:8000")
    assert _local_urls_match("http://127.0.0.1:8000", "http://localhost:8000")


def test_live_vapi_ngrok_tunnel_match_rejects_wrong_port() -> None:
    assert not _local_urls_match("http://127.0.0.1:5173", "http://127.0.0.1:8000")


def test_live_vapi_settings_guard_rejects_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("VAPI_API_KEY", "replace-with-vapi-api-key")
    monkeypatch.setenv("VAPI_WEBHOOK_SECRET", "replace-with-vapi-webhook-secret")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "replace-with-vapi-phone-number-id")
    monkeypatch.setenv("VAPI_API_URL", "https://api.vapi.ai")

    with pytest.raises(RuntimeError, match="live_vapi_settings_not_ready"):
        _assert_live_vapi_settings(Settings())


def test_live_e2e_parse_args_defaults_to_full_chain() -> None:
    config = parse_live_e2e_args(["--session-id", "55555555-5555-4555-8555-555555555555"])

    assert config.session_id == UUID("55555555-5555-4555-8555-555555555555")
    assert config.require_transcript
    assert config.require_report
    assert config.require_email


def test_live_e2e_status_passes_when_full_chain_is_complete() -> None:
    session_id = UUID("66666666-6666-4666-8666-666666666666")
    session = AssessmentSession(
        id=session_id,
        assessment_id=UUID("77777777-7777-4777-8777-777777777777"),
        candidate_id=UUID("88888888-8888-4888-8888-888888888888"),
        assessor_id=None,
        vapi_call_id="call_live_123",
        status=SessionStatus.COMPLETED,
        scheduled_at=None,
        started_at=None,
        ended_at=None,
        duration_seconds=120,
        raw_transcript='[{"role":"user","content":"I solved the incident.","timestamp":1.0}]',
        vapi_analysis={"summary": "completed"},
    )
    session.report = AssessmentReport(
        id=UUID("99999999-9999-4999-8999-999999999999"),
        session_id=session_id,
        version=1,
        overall_score=Decimal("86.00"),
        pass_fail=PassFail.PASS,
        strengths=[],
        weaknesses=[],
        detailed_analysis="Strong evidence.",
        recommendations="Keep improving.",
        anthropic_model_used="azure",
        anthropic_prompt_tokens=100,
        anthropic_completion_tokens=50,
        generation_status=ReportStatus.COMPLETED,
        generation_error=None,
        generated_at=datetime.now(UTC),
        email_sent_at=datetime.now(UTC),
    )

    status = evaluate_live_e2e_status(
        session,
        parse_live_e2e_args(["--session-id", str(session_id)]),
    )

    assert status.passed
    assert status.missing == []


def test_live_e2e_status_reports_missing_email() -> None:
    session_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    session = AssessmentSession(
        id=session_id,
        assessment_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        candidate_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        assessor_id=None,
        vapi_call_id="call_live_456",
        status=SessionStatus.COMPLETED,
        scheduled_at=None,
        started_at=None,
        ended_at=None,
        duration_seconds=120,
        raw_transcript='[{"role":"user","content":"Evidence.","timestamp":1.0}]',
        vapi_analysis=None,
    )
    session.report = AssessmentReport(
        id=UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
        session_id=session_id,
        version=1,
        overall_score=Decimal("86.00"),
        pass_fail=PassFail.PASS,
        strengths=[],
        weaknesses=[],
        detailed_analysis="Strong evidence.",
        recommendations="Keep improving.",
        anthropic_model_used="azure",
        anthropic_prompt_tokens=100,
        anthropic_completion_tokens=50,
        generation_status=ReportStatus.COMPLETED,
        generation_error=None,
        generated_at=datetime.now(UTC),
        email_sent_at=None,
    )

    status = evaluate_live_e2e_status(
        session,
        parse_live_e2e_args(["--session-id", str(session_id)]),
    )

    assert not status.passed
    assert status.missing == ["email_sent_at"]
