from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import NoReturn, cast
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings, VapiCallMode
from app.db.engine import connect_database, create_engine, create_sessionmaker, dispose_database
from scripts.provision_vapi_assistant import build_assistant_payload, create_vapi_assistant
from scripts.seed_demo_data import DemoSeedConfig, seed_demo_data
from scripts.validate_live_readiness import check_no_placeholder, check_public_https_url

NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class NgrokTunnel:
    public_url: str
    local_url: str


@dataclass(frozen=True)
class LiveVapiDemoConfig:
    backend_url: str
    ngrok_api_url: str
    start_ngrok: bool
    assistant_name: str
    role_title: str
    assessment_context: str
    question_count: int
    max_duration_seconds: int
    reset_passwords: bool


@dataclass(frozen=True)
class LiveVapiDemoResult:
    public_api_url: str
    webhook_url: str
    assistant_id: str
    session_id: str
    candidate_email: str


async def prepare_live_vapi_demo(config: LiveVapiDemoConfig) -> LiveVapiDemoResult:
    settings = Settings()
    _assert_live_vapi_settings(settings)
    await _assert_backend_ready(config.backend_url)

    tunnel = await ensure_ngrok_tunnel(
        backend_url=config.backend_url,
        ngrok_api_url=config.ngrok_api_url,
        start_ngrok=config.start_ngrok,
    )
    public_url_check = check_public_https_url("PUBLIC_API_URL", tunnel.public_url)
    if not public_url_check.ok:
        raise RuntimeError(f"public_api_url_not_ready:{public_url_check.detail}")

    payload = build_assistant_payload(
        server_url=tunnel.public_url,
        name=config.assistant_name,
        max_duration_seconds=config.max_duration_seconds,
        role_title=config.role_title,
        assessment_context=config.assessment_context,
        question_count=config.question_count,
        webhook_secret=settings.vapi_webhook_secret,
    )
    created_assistant = await create_vapi_assistant(settings, payload)
    assistant_id_raw = created_assistant.get("id")
    if not isinstance(assistant_id_raw, str) or assistant_id_raw.strip() == "":
        raise RuntimeError("vapi_assistant_created_without_id")

    engine = create_engine(settings)
    session_factory = create_sessionmaker(engine)
    try:
        await connect_database(engine)
        async with session_factory() as db:
            seed = await seed_demo_data(
                db,
                DemoSeedConfig(
                    admin_email="[email-redacted]",
                    admin_password="DemoAdmin123!",
                    assessor_email="[email-redacted]",
                    assessor_password="DemoAssessor123!",
                    candidate_email=settings.admin_email,
                    candidate_password="DemoCandidate123!",
                    vapi_assistant_id=assistant_id_raw,
                    assessment_title="Live Vapi Company Demo Assessment",
                    assessment_description=(
                        "Live Vapi demo assessment connected to an ngrok public webhook URL. "
                        "Use this session for the pre-production voice-to-report validation."
                    ),
                    passing_score=cast("Decimal", Decimal("75.00")),
                    time_limit_minutes=30,
                    reset_passwords=config.reset_passwords,
                ),
            )
    finally:
        await dispose_database(engine)

    return LiveVapiDemoResult(
        public_api_url=tunnel.public_url,
        webhook_url=tunnel.public_url.rstrip("/") + "/api/v1/webhooks/vapi",
        assistant_id=assistant_id_raw,
        session_id=str(seed.session_id),
        candidate_email=settings.admin_email,
    )


async def _assert_backend_ready(backend_url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(backend_url.rstrip("/") + "/ready")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"backend_not_ready:{backend_url}") from exc


def _assert_live_vapi_settings(settings: Settings) -> None:
    failed_checks = [
        check_no_placeholder("VAPI_API_KEY", settings.vapi_api_key),
        check_no_placeholder("VAPI_WEBHOOK_SECRET", settings.vapi_webhook_secret),
        check_public_https_url("VAPI_API_URL", settings.vapi_api_url),
    ]
    if settings.vapi_call_mode == VapiCallMode.PHONE:
        failed_checks.append(check_no_placeholder("VAPI_PHONE_NUMBER_ID", settings.vapi_phone_number_id or ""))
    failures = [f"{check.name}:{check.detail}" for check in failed_checks if not check.ok]
    if failures:
        raise RuntimeError("live_vapi_settings_not_ready:" + ",".join(failures))


async def ensure_ngrok_tunnel(backend_url: str, ngrok_api_url: str, start_ngrok: bool) -> NgrokTunnel:
    existing = await _get_ngrok_tunnel(ngrok_api_url=ngrok_api_url, backend_url=backend_url)
    if existing is not None:
        return existing

    if not start_ngrok:
        raise RuntimeError("ngrok_tunnel_not_found_for_backend")

    try:
        subprocess.Popen(
            ["ngrok", "http", backend_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ngrok_not_found_install_ngrok_or_start_it_manually") from exc
    except OSError as exc:
        raise RuntimeError(f"ngrok_start_failed:{exc}") from exc

    deadline = asyncio.get_running_loop().time() + 30.0
    while asyncio.get_running_loop().time() < deadline:
        tunnel = await _get_ngrok_tunnel(ngrok_api_url=ngrok_api_url, backend_url=backend_url)
        if tunnel is not None:
            return tunnel
        await asyncio.sleep(1.0)

    raise RuntimeError("ngrok_tunnel_start_timeout_check_ngrok_auth_token_and_local_backend")


async def _get_ngrok_tunnel(ngrok_api_url: str, backend_url: str) -> NgrokTunnel | None:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(ngrok_api_url)
            response.raise_for_status()
            decoded = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not isinstance(decoded, dict):
        return None
    tunnels = decoded.get("tunnels")
    if not isinstance(tunnels, list):
        return None

    for tunnel in tunnels:
        if not isinstance(tunnel, dict):
            continue
        public_url = tunnel.get("public_url")
        config = tunnel.get("config")
        local_url = config.get("addr") if isinstance(config, dict) else None
        if (
            isinstance(public_url, str)
            and public_url.startswith("https://")
            and isinstance(local_url, str)
            and _local_urls_match(local_url=local_url, backend_url=backend_url)
        ):
            return NgrokTunnel(public_url=public_url, local_url=local_url)
    return None


def _local_urls_match(local_url: str, backend_url: str) -> bool:
    parsed_local = urlparse(local_url)
    parsed_backend = urlparse(backend_url)
    local_host = parsed_local.hostname or ""
    backend_host = parsed_backend.hostname or ""
    host_matches = local_host in {backend_host, "localhost", "127.0.0.1"} and backend_host in {
        local_host,
        "localhost",
        "127.0.0.1",
    }
    return host_matches and parsed_local.port == parsed_backend.port


def parse_args(argv: list[str] | None = None) -> LiveVapiDemoConfig:
    parser = argparse.ArgumentParser(description="Prepare a live Vapi demo through an ngrok public webhook URL.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--ngrok-api-url", default=NGROK_API_URL)
    parser.add_argument("--no-start-ngrok", action="store_true")
    parser.add_argument("--assistant-name", default="Voice Assessment Live Demo Interviewer")
    parser.add_argument("--role-title", default="professional competency assessment")
    parser.add_argument(
        "--assessment-context",
        default=(
            "Evaluate communication clarity, structured thinking, judgment, problem solving, "
            "ownership, and ability to give evidence-backed examples."
        ),
    )
    parser.add_argument("--question-count", type=int, default=6)
    parser.add_argument("--max-duration-seconds", type=int, default=1800)
    parser.add_argument("--reset-passwords", action="store_true")
    args = parser.parse_args(argv)

    return LiveVapiDemoConfig(
        backend_url=str(args.backend_url),
        ngrok_api_url=str(args.ngrok_api_url),
        start_ngrok=not bool(args.no_start_ngrok),
        assistant_name=str(args.assistant_name),
        role_title=str(args.role_title),
        assessment_context=str(args.assessment_context),
        question_count=int(args.question_count),
        max_duration_seconds=int(args.max_duration_seconds),
        reset_passwords=bool(args.reset_passwords),
    )


def main() -> NoReturn:
    try:
        result = asyncio.run(prepare_live_vapi_demo(parse_args()))
    except ValidationError as exc:
        print(f"settings: failed: {exc}")
        raise SystemExit(2) from exc
    except (RuntimeError, SQLAlchemyError) as exc:
        print(f"live_vapi_demo_prepare: failed: {exc}")
        raise SystemExit(1) from exc

    print("live_vapi_demo_prepare: ok")
    print(f"public_api_url={result.public_api_url}")
    print(f"webhook_url={result.webhook_url}")
    print(f"assistant_id={result.assistant_id}")
    print(f"session_id={result.session_id}")
    print("candidate_login=" + result.candidate_email)
    print("candidate_password=DemoCandidate123!")
    print("candidate_url=http://127.0.0.1:3000/demo/" + result.session_id)
    print("next_step=sign in as the candidate, open candidate_url, check microphone, then start browser call")
    print("verify_command=python scripts\\verify_live_e2e.py --session-id " + result.session_id)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
