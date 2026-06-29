from __future__ import annotations

from scripts.provision_vapi_assistant import (
    DEFAULT_RESPONSE_DELAY_SECONDS,
    DEFAULT_SILENCE_TIMEOUT_SECONDS,
    build_assistant_payload,
)


def test_build_assistant_payload_sets_webhook_and_assessment_prompt() -> None:
    payload = build_assistant_payload(
        server_url="https://voice-assessment.example.com/",
        name="Staff Backend Assessment",
        max_duration_seconds=1200,
    )

    assert payload["name"] == "Staff Backend Assessment"
    assert payload["server"] == {
        "url": "https://voice-assessment.example.com/api/v1/webhooks/vapi",
    }
    assert payload["maxDurationSeconds"] == 1200
    assert payload["firstMessageMode"] == "assistant-speaks-first"
    assert payload["silenceTimeoutSeconds"] == DEFAULT_SILENCE_TIMEOUT_SECONDS
    assert payload["responseDelaySeconds"] == DEFAULT_RESPONSE_DELAY_SECONDS
    assert "analysisPlan" in payload

    model = payload["model"]
    assert isinstance(model, dict)
    assert model["provider"] == "openai"
    messages = model["messages"]
    assert isinstance(messages, list)
    first_message = messages[0]
    assert isinstance(first_message, dict)
    assert "professional AI voice assessor" in str(first_message["content"])
    assert "Do not ask about protected-class status" in str(first_message["content"])


def test_build_assistant_payload_can_include_static_secret_header() -> None:
    payload = build_assistant_payload(
        server_url="https://voice-assessment.example.com",
        webhook_secret="shared-secret",
    )

    assert payload["server"] == {
        "url": "https://voice-assessment.example.com/api/v1/webhooks/vapi",
        "headers": {"X-Vapi-Secret": "shared-secret"},
    }
