from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError

from app.config import AIReportProvider, Environment, Settings, VapiCallMode


PLACEHOLDER_FRAGMENTS: tuple[str, ...] = (
    "replace-with",
    "local-dev",
    "example.com",
    "example.org",
    "example.net",
    "invalid",
    "your-project",
    "your-domain",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_no_placeholder(name: str, value: str) -> CheckResult:
    normalized = value.strip().lower()
    if normalized == "":
        return CheckResult(name, False, "empty")
    for fragment in PLACEHOLDER_FRAGMENTS:
        if fragment in normalized:
            return CheckResult(name, False, f"placeholder_detected:{fragment}")
    return CheckResult(name, True, "set")


def check_database_url(settings: Settings) -> CheckResult:
    parsed = urlparse(settings.database_url)
    if parsed.scheme != "postgresql+asyncpg":
        return CheckResult("DATABASE_URL", False, "must_use_postgresql+asyncpg")
    if parsed.hostname in {None, "127.0.0.1", "localhost"} and settings.environment != Environment.DEVELOPMENT:
        return CheckResult("DATABASE_URL", False, "non_development_database_must_not_be_localhost")
    if _looks_like_supabase_transaction_pooler(settings.database_url):
        return CheckResult(
            "DATABASE_URL",
            False,
            "supabase_transaction_pooler_requires_prepared_statement_cache_size=0",
        )
    return check_no_placeholder("DATABASE_URL", settings.database_url)


def check_public_https_url(name: str, value: str) -> CheckResult:
    parsed = urlparse(value)
    if parsed.scheme != "https":
        return CheckResult(name, False, "must_use_https")
    if parsed.hostname in {None, "127.0.0.1", "localhost"}:
        return CheckResult(name, False, "must_be_public_hostname")
    return check_no_placeholder(name, value)


def check_origin_list(settings: Settings) -> CheckResult:
    if not settings.cors_origins:
        return CheckResult("CORS_ORIGINS", False, "no_origins_configured")
    if settings.environment == Environment.PRODUCTION and any(origin == "*" for origin in settings.cors_origins):
        return CheckResult("CORS_ORIGINS", False, "wildcard_not_allowed_in_production")
    invalid_origins = [
        origin
        for origin in settings.cors_origins
        if not origin.startswith("https://") and settings.environment == Environment.PRODUCTION
    ]
    if invalid_origins:
        return CheckResult("CORS_ORIGINS", False, f"production_origins_must_use_https:{invalid_origins}")
    return CheckResult("CORS_ORIGINS", True, f"{len(settings.cors_origins)} origin(s)")


def check_ai_provider(settings: Settings) -> list[CheckResult]:
    checks: list[CheckResult] = [
        CheckResult("AI_REPORT_PROVIDER", True, settings.ai_report_provider.value),
    ]
    if settings.ai_report_provider == AIReportProvider.ANTHROPIC:
        if settings.anthropic_api_key is None:
            checks.append(CheckResult("ANTHROPIC_API_KEY", False, "missing"))
        else:
            checks.append(check_no_placeholder("ANTHROPIC_API_KEY", settings.anthropic_api_key))
        checks.extend(
            [
                check_no_placeholder("ANTHROPIC_MODEL", settings.anthropic_model),
                check_no_placeholder("ANTHROPIC_SMOKE_MODEL", settings.anthropic_smoke_model),
            ]
        )
        return checks

    if settings.azure_openai_endpoint is None:
        checks.append(CheckResult("AZURE_OPENAI_ENDPOINT", False, "missing"))
    else:
        checks.append(check_public_https_url("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint))
    if settings.azure_openai_api_key is None:
        checks.append(CheckResult("AZURE_OPENAI_API_KEY", False, "missing"))
    else:
        checks.append(check_no_placeholder("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key))
    if settings.azure_openai_api_version is None:
        checks.append(CheckResult("AZURE_OPENAI_API_VERSION", False, "missing"))
    else:
        checks.append(check_no_placeholder("AZURE_OPENAI_API_VERSION", settings.azure_openai_api_version))
    if settings.azure_chat_deployment is None:
        checks.append(CheckResult("AZURE_CHAT_DEPLOYMENT", False, "missing"))
    else:
        checks.append(check_no_placeholder("AZURE_CHAT_DEPLOYMENT", settings.azure_chat_deployment))
    return checks


def _looks_like_supabase_transaction_pooler(database_url: str) -> bool:
    parsed = urlparse(database_url)
    hostname = parsed.hostname or ""
    query = parsed.query
    is_supabase_pooler = "pooler.supabase.com" in hostname and parsed.port == 6543
    disables_prepared_cache = "prepared_statement_cache_size=0" in query
    return is_supabase_pooler and not disables_prepared_cache


def run_checks(public_api_url: str | None) -> list[CheckResult]:
    settings = Settings()
    checks: list[CheckResult] = [
        check_database_url(settings),
        check_public_https_url("SUPABASE_URL", settings.supabase_url),
        check_no_placeholder("SUPABASE_SERVICE_ROLE_KEY", settings.supabase_service_role_key),
        check_no_placeholder("VAPI_API_KEY", settings.vapi_api_key),
        check_no_placeholder("VAPI_WEBHOOK_SECRET", settings.vapi_webhook_secret),
        check_public_https_url("VAPI_API_URL", settings.vapi_api_url),
        check_no_placeholder("RESEND_API_KEY", settings.resend_api_key),
        check_no_placeholder("RESEND_FROM_EMAIL", settings.resend_from_email),
        check_no_placeholder("ADMIN_EMAIL", settings.admin_email),
        check_no_placeholder("JWT_SECRET", settings.jwt_secret),
        check_origin_list(settings),
    ]
    if settings.vapi_call_mode == VapiCallMode.PHONE:
        checks.append(check_no_placeholder("VAPI_PHONE_NUMBER_ID", settings.vapi_phone_number_id or ""))
    else:
        checks.append(CheckResult("VAPI_PHONE_NUMBER_ID", True, "not_required_for_web_call_mode"))
    checks.extend(check_ai_provider(settings))
    if public_api_url is not None:
        checks.append(check_public_https_url("PUBLIC_API_URL", public_api_url))
        if public_api_url.rstrip("/").endswith("/api/v1/webhooks/vapi"):
            checks.append(CheckResult("PUBLIC_API_URL", False, "provide_base_url_without_webhook_path"))
    return checks


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Validate live integration readiness for the backend.")
    parser.add_argument(
        "--public-api-url",
        help="Public HTTPS base URL for the API or Cloudflare Worker, without a trailing path.",
    )
    args = parser.parse_args()

    try:
        checks = run_checks(public_api_url=args.public_api_url)
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc

    for check in checks:
        status = "ok" if check.ok else "failed"
        print(f"{check.name}: {status}: {check.detail}")

    if all(check.ok for check in checks):
        print("live_readiness: ok")
        raise SystemExit(0)

    print("live_readiness: failed")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
