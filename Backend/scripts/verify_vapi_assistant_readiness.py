from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, cast

import httpx
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings
from scripts.provision_vapi_assistant import (
    DEFAULT_ASSESSMENT_CONTEXT,
    DEFAULT_ASSISTANT_NAME,
    DEFAULT_MAX_DURATION_SECONDS,
    DEFAULT_QUESTION_COUNT,
    DEFAULT_RESPONSE_DELAY_SECONDS,
    DEFAULT_ROLE_TITLE,
    DEFAULT_SERVER_MESSAGES,
    DEFAULT_SILENCE_TIMEOUT_SECONDS,
    build_assessment_interviewer_prompt,
)


REQUIRED_PROMPT_MARKERS: tuple[str, ...] = (
    "ask exactly one question at a time",
    "do not ask about protected-class",
    "collect a transcript with enough concrete evidence",
    "never output json",
)
PASS_FAIL_GUARDRAIL_MARKERS: tuple[str, ...] = (
    "do not reveal pass/fail",
    "do not say they passed",
    "do not say the candidate passed",
    "do not disclose pass/fail",
)
REQUIRED_FIRST_MESSAGE_MARKERS: tuple[str, ...] = (
    "riley",
    "recorded",
    "one question at a time",
    "ready to begin",
)
REQUIRED_END_MESSAGE_MARKERS: tuple[str, ...] = (
    "assessment is complete",
    "report will be generated",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


async def fetch_vapi_assistant(settings: Settings, assistant_id: str) -> dict[str, object]:
    url = settings.vapi_api_url.rstrip("/") + f"/assistant/{assistant_id}"
    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"vapi_assistant_fetch_failed:{exc.response.status_code}:{exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"vapi_assistant_fetch_request_failed:{exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("vapi_assistant_fetch_invalid_response")
    return cast(dict[str, object], payload)


def build_expected_profile(
    server_url: str,
    role_title: str,
    assessment_context: str,
    question_count: int,
) -> dict[str, object]:
    webhook_url = server_url.rstrip("/") + "/api/v1/webhooks/vapi"
    return {
        "name": DEFAULT_ASSISTANT_NAME,
        "server_url": webhook_url,
        "server_messages": DEFAULT_SERVER_MESSAGES,
        "max_duration_seconds": DEFAULT_MAX_DURATION_SECONDS,
        "silence_timeout_seconds": DEFAULT_SILENCE_TIMEOUT_SECONDS,
        "response_delay_seconds": DEFAULT_RESPONSE_DELAY_SECONDS,
        "model_provider": "openai",
        "model": "gpt-4o-mini",
        "transcriber_provider": "deepgram",
        "transcriber_model": "nova-3",
        "transcriber_language": "en",
        "prompt": build_assessment_interviewer_prompt(
            role_title=role_title,
            assessment_context=assessment_context,
            question_count=question_count,
        ),
    }


def run_assistant_checks(
    assistant: dict[str, object],
    expected: dict[str, object],
    webhook_secret: str,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    checks.append(_check_string("name", assistant.get("name"), cast(str, expected["name"])))
    checks.append(_check_contains("firstMessage", assistant.get("firstMessage"), REQUIRED_FIRST_MESSAGE_MARKERS))
    checks.append(_check_contains("endCallMessage", assistant.get("endCallMessage"), REQUIRED_END_MESSAGE_MARKERS))
    checks.append(
        _check_number_range(
            "maxDurationSeconds",
            assistant.get("maxDurationSeconds"),
            minimum=600,
            maximum=1800,
            ideal=cast(int, expected["max_duration_seconds"]),
        )
    )
    checks.append(
        _check_number_range(
            "silenceTimeoutSeconds",
            assistant.get("silenceTimeoutSeconds"),
            minimum=25,
            maximum=60,
            ideal=cast(int, expected["silence_timeout_seconds"]),
        )
    )
    checks.append(
        _check_number_range(
            "responseDelaySeconds",
            assistant.get("responseDelaySeconds"),
            minimum=0.2,
            maximum=1.0,
            ideal=cast(float, expected["response_delay_seconds"]),
        )
    )

    server = assistant.get("server")
    if isinstance(server, dict):
        checks.append(_check_string("server.url", server.get("url"), cast(str, expected["server_url"])))
        headers = server.get("headers")
        if isinstance(headers, dict):
            checks.append(_check_secret_header(headers.get("X-Vapi-Secret"), webhook_secret))
        else:
            checks.append(CheckResult("server.headers.X-Vapi-Secret", False, "missing"))
    else:
        checks.append(CheckResult("server", False, "missing"))

    checks.append(_check_string_list("serverMessages", assistant.get("serverMessages"), DEFAULT_SERVER_MESSAGES))

    model = assistant.get("model")
    if isinstance(model, dict):
        checks.append(_check_string("model.provider", model.get("provider"), cast(str, expected["model_provider"])))
        checks.append(_check_string("model.model", model.get("model"), cast(str, expected["model"])))
        checks.append(_check_model_prompt(model.get("messages")))
    else:
        checks.append(CheckResult("model", False, "missing"))

    transcriber = assistant.get("transcriber")
    if isinstance(transcriber, dict):
        checks.append(
            _check_string("transcriber.provider", transcriber.get("provider"), cast(str, expected["transcriber_provider"]))
        )
        checks.append(_check_string("transcriber.model", transcriber.get("model"), cast(str, expected["transcriber_model"])))
        checks.append(
            _check_string("transcriber.language", transcriber.get("language"), cast(str, expected["transcriber_language"]))
        )
    else:
        checks.append(CheckResult("transcriber", False, "missing"))

    analysis_plan = assistant.get("analysisPlan")
    if isinstance(analysis_plan, dict):
        checks.append(_check_contains("analysisPlan.summaryPrompt", analysis_plan.get("summaryPrompt"), ("evidence", "inference")))
        checks.append(
            _check_contains(
                "analysisPlan.structuredDataPrompt",
                analysis_plan.get("structuredDataPrompt"),
                ("topics_discussed", "evidence_by_competency", "transcript_quality_notes"),
            )
        )
    else:
        checks.append(CheckResult("analysisPlan", False, "missing"))

    return checks


def _check_string(name: str, actual: object, expected: str) -> CheckResult:
    if not isinstance(actual, str) or actual.strip() == "":
        return CheckResult(name, False, "missing")
    if actual.strip() != expected:
        return CheckResult(name, False, f"expected={expected!r} actual={actual!r}")
    return CheckResult(name, True, "ok")


def _check_secret_header(actual: object, expected_secret: str) -> CheckResult:
    if not isinstance(actual, str) or actual.strip() == "":
        return CheckResult("server.headers.X-Vapi-Secret", False, "missing")
    if actual != expected_secret:
        return CheckResult("server.headers.X-Vapi-Secret", False, "configured_but_does_not_match_backend_secret")
    return CheckResult("server.headers.X-Vapi-Secret", True, "matches_backend_secret")


def _check_contains(name: str, actual: object, required_markers: tuple[str, ...]) -> CheckResult:
    if not isinstance(actual, str) or actual.strip() == "":
        return CheckResult(name, False, "missing")
    normalized = actual.lower()
    missing = [marker for marker in required_markers if marker.lower() not in normalized]
    if missing:
        return CheckResult(name, False, f"missing_markers={missing}")
    return CheckResult(name, True, "ok")


def _check_number_range(name: str, actual: object, minimum: float, maximum: float, ideal: float) -> CheckResult:
    if not isinstance(actual, int | float):
        return CheckResult(name, False, "missing_or_not_numeric")
    value = float(actual)
    if value < minimum or value > maximum:
        return CheckResult(name, False, f"outside_range value={value} expected_range={minimum}-{maximum}")
    if abs(value - ideal) > 0.001:
        return CheckResult(name, True, f"acceptable value={value} ideal={ideal}")
    return CheckResult(name, True, "ok")


def _check_string_list(name: str, actual: object, required_values: list[str]) -> CheckResult:
    if not isinstance(actual, list):
        return CheckResult(name, False, "missing_or_not_list")
    values = {item for item in actual if isinstance(item, str)}
    missing = [value for value in required_values if value not in values]
    if missing:
        return CheckResult(name, False, f"missing={missing}")
    return CheckResult(name, True, "ok")


def _check_model_prompt(messages: object) -> CheckResult:
    if not isinstance(messages, list):
        return CheckResult("model.messages", False, "missing_or_not_list")
    prompt_parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            prompt_parts.append(content)
    prompt = "\n".join(prompt_parts).lower()
    missing = [marker for marker in REQUIRED_PROMPT_MARKERS if marker not in prompt]
    if not any(marker in prompt for marker in PASS_FAIL_GUARDRAIL_MARKERS):
        missing.append("pass/fail disclosure guardrail")
    if missing:
        return CheckResult("model.prompt_guardrails", False, f"missing_markers={missing}")
    return CheckResult("model.prompt_guardrails", True, "ok")


def print_checks(checks: list[CheckResult]) -> None:
    for check in checks:
        status = "ok" if check.ok else "failed"
        print(f"{check.name}: {status}: {check.detail}")


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Verify a Vapi assistant is tuned for production voice assessments.")
    parser.add_argument("--assistant-id", required=True, help="Vapi assistant id to verify.")
    parser.add_argument("--server-url", required=True, help="Public API or Worker base URL without the webhook path.")
    parser.add_argument("--role-title", default=DEFAULT_ROLE_TITLE)
    parser.add_argument("--assessment-context", default=DEFAULT_ASSESSMENT_CONTEXT)
    parser.add_argument("--question-count", type=int, default=DEFAULT_QUESTION_COUNT)
    parser.add_argument("--print-profile", action="store_true", help="Print expected profile and exit without calling Vapi.")
    args = parser.parse_args()

    expected = build_expected_profile(
        server_url=str(args.server_url),
        role_title=str(args.role_title),
        assessment_context=str(args.assessment_context),
        question_count=int(args.question_count),
    )
    if bool(args.print_profile):
        print(json.dumps(expected, indent=2, sort_keys=True))
        raise SystemExit(0)

    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"settings invalid: {exc}")
        raise SystemExit(2) from exc

    try:
        assistant = asyncio.run(fetch_vapi_assistant(settings, str(args.assistant_id)))
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1) from exc

    checks = run_assistant_checks(assistant, expected, settings.vapi_webhook_secret)
    print_checks(checks)
    if all(check.ok for check in checks):
        print("vapi_assistant_readiness: ok")
        raise SystemExit(0)

    print("vapi_assistant_readiness: failed")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
