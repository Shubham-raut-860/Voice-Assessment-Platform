from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import NoReturn, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from pydantic import ValidationError

from app.config import Settings

DEFAULT_ASSISTANT_NAME = "Riley - Voice Assessment Interviewer"
DEFAULT_MAX_DURATION_SECONDS = 900
DEFAULT_SILENCE_TIMEOUT_SECONDS = 35
DEFAULT_RESPONSE_DELAY_SECONDS = 0.35
DEFAULT_QUESTION_COUNT = 6
DEFAULT_ROLE_TITLE = "professional competency assessment"
DEFAULT_ASSESSMENT_CONTEXT = (
    "Evaluate communication clarity, structured thinking, judgment, problem solving, "
    "ownership, and ability to give evidence-backed examples."
)
DEFAULT_SERVER_MESSAGES: list[str] = ["status-update", "transcript", "end-of-call-report"]

def build_assessment_interviewer_prompt(
    role_title: str,
    assessment_context: str,
    question_count: int,
) -> str:
    bounded_question_count = min(max(question_count, 4), 8)
    return f"""
You are Riley, a calm, professional AI voice assessor for Vocalis.ai.

Assessment target:
- Role or theme: {role_title}
- What to evaluate: {assessment_context}
- Target depth: ask about {bounded_question_count} primary questions, plus brief follow-ups only when needed.

Primary objective:
Conduct a fair, consistent, evidence-seeking assessment conversation. Your job is not to score the
candidate live. Your job is to collect a transcript with enough concrete evidence for the backend
report engine to evaluate the candidate after the call.

Voice and pacing:
- Speak naturally, clearly, and briefly.
- Ask exactly one question at a time.
- Keep most turns under two short sentences.
- Pause after each question and let the candidate answer.
- Do not stack multiple prompts in one turn.
- Do not over-explain the platform.

Opening:
1. Greet the candidate by saying this is their AI voice assessment.
2. State that the session may be recorded and analyzed to generate an assessment report.
3. Ask if they are ready to begin.
4. If they say no, ask one practical readiness question. If they are still not ready, close politely.

Question ladder:
1. Ask for a concise background summary relevant to the role or theme.
2. Ask for a concrete example of prior work, responsibility, or project ownership.
3. Ask a scenario question that requires structured reasoning.
4. Ask a prioritization or tradeoff question.
5. Ask a communication question about explaining complexity, conflict, feedback, or alignment.
6. Ask a self-reflection question about a mistake, gap, or improvement area.
7. Ask a final open question: "Is there anything important about your experience that we did not cover?"

Follow-up behavior:
- If an answer is vague, ask for one specific example.
- If an answer lacks outcome, ask what changed or what result followed.
- If an answer lacks reasoning, ask what tradeoff they considered.
- If an answer is too short, ask one gentle clarifying follow-up.
- If the candidate rambles, summarize briefly and move to the next question.
- Do not interrogate. One follow-up per weak answer is usually enough.

Fairness and safety:
- Do not ask about protected-class status, age, family status, health, disability, religion,
  nationality, government identifiers, financial account details, passwords, or secrets.
- Do not provide legal, medical, or financial advice.
- Do not coach the candidate toward an ideal answer.
- Do not reveal scoring thresholds, internal rubric weights, or pass/fail decisions.
- If asked how scoring works, say: "The transcript is reviewed against the configured criteria after
  the call, and the final report is generated separately."

Closing:
- Once the evidence is sufficient or the time limit is near, stop asking new questions.
- Thank the candidate.
- Say the assessment is complete and the report will be generated after processing.
- Do not say they passed, failed, did well, or did poorly.

Output behavior:
- Speak only conversational text.
- Never output JSON, markdown, bullet lists, XML, or code during the call.
- Never invent candidate experience or facts.
""".strip()


def build_assistant_payload(
    server_url: str,
    name: str = DEFAULT_ASSISTANT_NAME,
    max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS,
    silence_timeout_seconds: int = DEFAULT_SILENCE_TIMEOUT_SECONDS,
    response_delay_seconds: float = DEFAULT_RESPONSE_DELAY_SECONDS,
    role_title: str = DEFAULT_ROLE_TITLE,
    assessment_context: str = DEFAULT_ASSESSMENT_CONTEXT,
    question_count: int = DEFAULT_QUESTION_COUNT,
    voice_id: str = "Elliot",
    webhook_secret: str | None = None,
) -> dict[str, object]:
    webhook_url = server_url.rstrip("/") + "/api/v1/webhooks/vapi"
    server: dict[str, object] = {"url": webhook_url}
    if webhook_secret is not None and webhook_secret.strip() != "":
        server["headers"] = {"X-Vapi-Secret": webhook_secret}

    return {
        "name": name,
        "firstMessage": (
            "Hello, I am Riley, your AI voice assessor. This session may be recorded and analyzed "
            "to generate your assessment report. I will ask one question at a time. Are you ready to begin?"
        ),
        "firstMessageMode": "assistant-speaks-first",
        "endCallMessage": (
            "Thank you. Your assessment is complete, and your report will be generated after processing."
        ),
        "silenceTimeoutSeconds": silence_timeout_seconds,
        "responseDelaySeconds": response_delay_seconds,
        "server": server,
        "serverMessages": DEFAULT_SERVER_MESSAGES,
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": build_assessment_interviewer_prompt(
                        role_title=role_title,
                        assessment_context=assessment_context,
                        question_count=question_count,
                    ),
                }
            ],
        },
        "voice": {
            "provider": "vapi",
            "voiceId": voice_id,
        },
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "en",
        },
        "maxDurationSeconds": max_duration_seconds,
        "backgroundSound": "off",
        "modelOutputInMessagesEnabled": False,
        "analysisPlan": {
            "summaryPrompt": (
                "Summarize the assessment conversation for evaluator review. Cite concrete transcript evidence. "
                "Separate observed evidence from inference. Do not assign a final pass/fail decision."
            ),
            "structuredDataPrompt": (
                "Return a compact JSON object with these keys: topics_discussed, evidence_by_competency, "
                "notable_strengths, notable_concerns, unanswered_questions, transcript_quality_notes, "
                "candidate_participation_level. Use only transcript evidence."
            ),
        },
    }


async def create_vapi_assistant(
    settings: Settings,
    payload: dict[str, object],
) -> dict[str, object]:
    url = settings.vapi_api_url.rstrip("/") + "/assistant"
    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            decoded = response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"vapi_assistant_create_failed:{exc.response.status_code}:{exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"vapi_assistant_create_request_failed:{exc}") from exc

    if not isinstance(decoded, dict):
        raise RuntimeError("vapi_assistant_create_invalid_response")
    return cast(dict[str, object], decoded)


async def update_vapi_assistant(
    settings: Settings,
    assistant_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    url = settings.vapi_api_url.rstrip("/") + f"/assistant/{assistant_id}"
    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(url, headers=headers, json=payload)
            response.raise_for_status()
            decoded = response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"vapi_assistant_update_failed:{exc.response.status_code}:{exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"vapi_assistant_update_request_failed:{exc}") from exc

    if not isinstance(decoded, dict):
        raise RuntimeError("vapi_assistant_update_invalid_response")
    return cast(dict[str, object], decoded)


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Provision the Vapi assessment assistant.")
    parser.add_argument(
        "--server-url",
        default=None,
        help="Public base URL for this backend or Cloudflare Worker, without a trailing path.",
    )
    parser.add_argument("--assistant-id", default=None, help="Existing Vapi assistant ID to update instead of creating one.")
    parser.add_argument("--name", default=DEFAULT_ASSISTANT_NAME)
    parser.add_argument("--max-duration-seconds", type=int, default=DEFAULT_MAX_DURATION_SECONDS)
    parser.add_argument("--silence-timeout-seconds", type=int, default=DEFAULT_SILENCE_TIMEOUT_SECONDS)
    parser.add_argument("--response-delay-seconds", type=float, default=DEFAULT_RESPONSE_DELAY_SECONDS)
    parser.add_argument("--role-title", default=DEFAULT_ROLE_TITLE)
    parser.add_argument("--assessment-context", default=DEFAULT_ASSESSMENT_CONTEXT)
    parser.add_argument("--question-count", type=int, default=DEFAULT_QUESTION_COUNT)
    parser.add_argument("--voice-id", default="Elliot")
    parser.add_argument("--include-secret-header", action="store_true")
    parser.add_argument(
        "--preserve-server-url",
        action="store_true",
        help="When updating an assistant, leave the existing Vapi server URL and headers unchanged.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the assistant payload without calling Vapi.")
    args = parser.parse_args()

    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"settings invalid: {exc}")
        raise SystemExit(2) from exc

    assistant_id_arg = str(args.assistant_id).strip() if args.assistant_id is not None else ""
    preserve_server_url = bool(args.preserve_server_url)
    server_url = str(args.server_url).strip() if args.server_url is not None else ""
    if not preserve_server_url and server_url == "":
        print("server-url is required unless --preserve-server-url is used")
        raise SystemExit(2)
    if preserve_server_url and assistant_id_arg == "":
        print("assistant-id is required when --preserve-server-url is used")
        raise SystemExit(2)

    payload = build_assistant_payload(
        server_url=server_url or "https://example.invalid",
        name=str(args.name),
        max_duration_seconds=int(args.max_duration_seconds),
        silence_timeout_seconds=int(args.silence_timeout_seconds),
        response_delay_seconds=float(args.response_delay_seconds),
        role_title=str(args.role_title),
        assessment_context=str(args.assessment_context),
        question_count=int(args.question_count),
        voice_id=str(args.voice_id),
        webhook_secret=settings.vapi_webhook_secret if bool(args.include_secret_header) else None,
    )
    if preserve_server_url:
        payload.pop("server", None)

    if bool(args.dry_run):
        print(json.dumps(payload, indent=2, sort_keys=True))
        raise SystemExit(0)

    try:
        if assistant_id_arg:
            saved = asyncio.run(update_vapi_assistant(settings, assistant_id_arg, payload))
            assistant_id = saved.get("id", assistant_id_arg)
            print(f"assistant_updated id={assistant_id}")
            raise SystemExit(0)
        created = asyncio.run(create_vapi_assistant(settings, payload))
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1) from exc

    assistant_id = created.get("id")
    print(f"assistant_created id={assistant_id}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
