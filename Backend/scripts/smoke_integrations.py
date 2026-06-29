from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import anthropic
import httpx
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import AIReportProvider, Settings, VapiCallMode
from app.db.engine import connect_database, create_engine, dispose_database
from app.exceptions import EmailDeliveryError
from app.services.email_service import send_admin_alert_email


@dataclass(frozen=True)
class SmokeResult:
    name: str
    ok: bool
    detail: str


async def check_database(settings: Settings) -> SmokeResult:
    engine = create_engine(settings)
    try:
        await connect_database(engine)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return SmokeResult("database", True, "connected")
    except SQLAlchemyError as exc:
        return SmokeResult("database", False, f"{type(exc).__name__}: {exc}")
    finally:
        await dispose_database(engine)


async def check_vapi(settings: Settings) -> SmokeResult:
    if settings.vapi_call_mode == VapiCallMode.PHONE:
        url = f"{settings.vapi_api_url.rstrip('/')}/phone-number/{settings.vapi_phone_number_id}"
        success_detail = f"phone_number_id={settings.vapi_phone_number_id}"
    else:
        url = f"{settings.vapi_api_url.rstrip('/')}/assistant"
        success_detail = "api_key_valid_for_assistant_access"
    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        return SmokeResult("vapi", True, success_detail)
    except httpx.HTTPStatusError as exc:
        return SmokeResult(
            "vapi",
            False,
            f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
        )
    except httpx.RequestError as exc:
        return SmokeResult("vapi", False, f"{type(exc).__name__}: {exc}")


async def check_anthropic(settings: Settings) -> SmokeResult:
    if settings.anthropic_api_key is None:
        return SmokeResult("anthropic", False, "ANTHROPIC_API_KEY missing")
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model=settings.anthropic_smoke_model,
            max_tokens=8,
            temperature=0,
            system="Return exactly the word OK.",
            messages=[{"role": "user", "content": "Health check."}],
        )
        text_parts = [getattr(block, "text", "") for block in response.content]
        text = "".join(part for part in text_parts if isinstance(part, str)).strip()
        if text.upper() != "OK":
            return SmokeResult("anthropic", False, f"unexpected_response={text[:100]}")
        return SmokeResult(
            "anthropic",
            True,
            f"model={response.model} input_tokens={response.usage.input_tokens} output_tokens={response.usage.output_tokens}",
        )
    except anthropic.RateLimitError as exc:
        return SmokeResult("anthropic", False, f"rate_limited: {exc}")
    except anthropic.APIConnectionError as exc:
        return SmokeResult("anthropic", False, f"connection_error: {exc}")
    except anthropic.APIStatusError as exc:
        return SmokeResult("anthropic", False, f"status_error:{exc.status_code}: {exc}")
    except anthropic.APIError as exc:
        return SmokeResult("anthropic", False, f"api_error: {exc}")


async def check_azure_openai(settings: Settings) -> SmokeResult:
    if settings.azure_openai_endpoint is None:
        return SmokeResult("azure_openai", False, "AZURE_OPENAI_ENDPOINT missing")
    if settings.azure_openai_api_key is None:
        return SmokeResult("azure_openai", False, "AZURE_OPENAI_API_KEY missing")
    if settings.azure_openai_api_version is None:
        return SmokeResult("azure_openai", False, "AZURE_OPENAI_API_VERSION missing")
    if settings.azure_chat_deployment is None:
        return SmokeResult("azure_openai", False, "AZURE_CHAT_DEPLOYMENT missing")

    url = (
        f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
        f"{settings.azure_chat_deployment}/chat/completions"
    )
    headers = {"api-key": settings.azure_openai_api_key, "Content-Type": "application/json"}
    params = {"api-version": settings.azure_openai_api_version}
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "Return exactly the word OK."},
        {"role": "user", "content": "Health check."},
    ]
    use_max_completion_tokens = True
    include_temperature = True
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                payload: dict[str, object] = {"messages": messages}
                if include_temperature:
                    payload["temperature"] = 0
                if use_max_completion_tokens:
                    payload["max_completion_tokens"] = 64
                else:
                    payload["max_tokens"] = 64
                response = await client.post(url, headers=headers, params=params, json=payload)
                try:
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 400:
                        raise
                    response_text = exc.response.text.lower()
                    if "max_completion_tokens" in response_text and use_max_completion_tokens:
                        use_max_completion_tokens = False
                        continue
                    if "max_tokens" in response_text and not use_max_completion_tokens:
                        use_max_completion_tokens = True
                        continue
                    if "temperature" in response_text and include_temperature:
                        include_temperature = False
                        continue
                    raise
        decoded: object = response.json()
        if not isinstance(decoded, dict):
            return SmokeResult("azure_openai", False, "unexpected_response_shape")
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices:
            return SmokeResult("azure_openai", False, "missing_choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return SmokeResult("azure_openai", False, "invalid_choice")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            return SmokeResult("azure_openai", False, "missing_message")
        content = message.get("content")
        if not isinstance(content, str) or content.strip().upper() != "OK":
            return SmokeResult("azure_openai", False, f"unexpected_response={str(content)[:100]}")
        model = decoded.get("model")
        usage = decoded.get("usage")
        usage_detail = ""
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            usage_detail = f" prompt_tokens={prompt_tokens} completion_tokens={completion_tokens}"
        return SmokeResult(
            "azure_openai",
            True,
            f"deployment={settings.azure_chat_deployment} model={model}{usage_detail}",
        )
    except httpx.HTTPStatusError as exc:
        return SmokeResult(
            "azure_openai",
            False,
            f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
        )
    except httpx.RequestError as exc:
        return SmokeResult("azure_openai", False, f"{type(exc).__name__}: {exc}")
    except ValueError as exc:
        return SmokeResult("azure_openai", False, f"invalid_json: {exc}")


async def check_resend(settings: Settings) -> SmokeResult:
    try:
        await send_admin_alert_email(
            subject="Voice Assessment smoke test",
            body="Resend smoke test from the Voice Assessment backend completed successfully.",
            settings=settings,
        )
        return SmokeResult("resend", True, f"sent_to={settings.admin_email}")
    except EmailDeliveryError as exc:
        return SmokeResult("resend", False, f"{exc.code}: {exc.message}")


async def run_smoke_checks(send_email: bool) -> list[SmokeResult]:
    settings = Settings()
    ai_result = (
        await check_azure_openai(settings)
        if settings.ai_report_provider == AIReportProvider.AZURE_OPENAI
        else await check_anthropic(settings)
    )
    results = [
        await check_database(settings),
        await check_vapi(settings),
        ai_result,
    ]
    if send_email:
        results.append(await check_resend(settings))
    else:
        results.append(SmokeResult("resend", True, "skipped; pass --send-email to send admin alert"))
    return results


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Run live integration smoke checks.")
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send a real Resend admin alert email as part of the smoke test.",
    )
    args = parser.parse_args()

    try:
        results = asyncio.run(run_smoke_checks(send_email=bool(args.send_email)))
    except ValidationError as exc:
        print(f"settings invalid: {exc}")
        raise SystemExit(2) from exc

    for result in results:
        status = "ok" if result.ok else "failed"
        print(f"{result.name}: {status}: {result.detail}")

    if all(result.ok for result in results):
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
