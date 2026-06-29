from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from email.utils import parseaddr
from pathlib import Path
from typing import NoReturn, cast

import httpx
import structlog
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings
from app.exceptions import EmailDeliveryError
from app.services.email_service import send_resend_test_email

logger = structlog.get_logger(__name__)
RESEND_API_BASE_URL = "https://api.resend.com"
VERIFIED_DOMAIN_STATUSES: frozenset[str] = frozenset({"verified"})
DEMO_ONLY_SENDERS: frozenset[str] = frozenset({"[email-redacted]"})


@dataclass(frozen=True)
class ResendDomain:
    id: str
    name: str
    status: str
    sending_enabled: bool


@dataclass(frozen=True)
class ResendReadinessResult:
    ready: bool
    sender_email: str
    sender_domain: str
    matched_domain: ResendDomain | None
    blockers: list[str]
    warnings: list[str]
    test_message_id: str | None


async def main_async(send_test_to: str | None) -> int:
    try:
        settings = Settings()
    except ValidationError as exc:
        logger.error("resend_readiness_settings_invalid", error=str(exc))
        print(f"settings invalid: {exc}")
        return 2

    try:
        sender_email = _extract_sender_email(settings.resend_from_email)
        sender_domain = _extract_domain(sender_email)
    except ValueError as exc:
        logger.error("resend_sender_configuration_invalid", error=str(exc))
        print(f"resend sender configuration invalid: {exc}")
        return 2
    blockers: list[str] = []
    warnings: list[str] = []
    test_message_id: str | None = None

    if sender_email.lower() in DEMO_ONLY_SENDERS:
        blockers.append(
            "RESEND_FROM_EMAIL uses Resend's onboarding sender. This is demo-only and cannot send unrestricted production email."
        )

    try:
        domains = await list_resend_domains(settings.resend_api_key)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        logger.exception("resend_domain_list_http_failed", status_code=status_code, error=str(exc))
        if status_code == 401:
            print("resend domain check failed: invalid_or_unauthorized_api_key")
            return 1
        if status_code == 403:
            print("resend domain check failed: api_key_missing_domain_read_permission")
            return 1
        print(f"resend domain check failed: http_status={status_code}")
        return 1
    except httpx.TimeoutException as exc:
        logger.exception("resend_domain_list_timeout", error=str(exc))
        print("resend domain check failed: timeout")
        return 1
    except httpx.RequestError as exc:
        logger.exception("resend_domain_list_request_failed", error=str(exc))
        print(f"resend domain check failed: request_error={exc}")
        return 1
    except ValueError as exc:
        logger.exception("resend_domain_list_parse_failed", error=str(exc))
        print(f"resend domain check failed: invalid_response={exc}")
        return 1

    matched_domain = _find_matching_domain(domains, sender_domain)
    if matched_domain is None:
        blockers.append(f"Sender domain '{sender_domain}' is not present in Resend Domains.")
    else:
        if matched_domain.status.lower() not in VERIFIED_DOMAIN_STATUSES:
            blockers.append(
                f"Sender domain '{matched_domain.name}' is not verified in Resend. Current status: {matched_domain.status}."
            )
        if not matched_domain.sending_enabled:
            blockers.append(f"Sender domain '{matched_domain.name}' does not have sending enabled in Resend.")

    if send_test_to is not None:
        try:
            test_message_id = await send_resend_test_email(to_email=send_test_to, settings=settings)
        except EmailDeliveryError as exc:
            logger.exception("resend_readiness_test_email_failed", code=exc.code, message=exc.message)
            blockers.append(f"Test email failed: {exc.code}: {exc.message}")

    ready = len(blockers) == 0
    result = ResendReadinessResult(
        ready=ready,
        sender_email=sender_email,
        sender_domain=sender_domain,
        matched_domain=matched_domain,
        blockers=blockers,
        warnings=warnings,
        test_message_id=test_message_id,
    )
    _print_result(result)
    logger.info(
        "resend_readiness_completed",
        ready=ready,
        sender_email=sender_email,
        sender_domain=sender_domain,
        matched_domain=matched_domain.name if matched_domain is not None else None,
        blocker_count=len(blockers),
        warning_count=len(warnings),
        test_message_id=test_message_id,
    )
    return 0 if ready else 1


async def list_resend_domains(api_key: str) -> list[ResendDomain]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(base_url=RESEND_API_BASE_URL, timeout=20.0) as client:
        response = await client.get("/domains", headers=headers)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("domains_response_must_be_object")

    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("domains_response_data_must_be_list")

    domains: list[ResendDomain] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        domain_id = item.get("id")
        status = item.get("status")
        capabilities = item.get("capabilities")
        if not isinstance(name, str) or not isinstance(domain_id, str) or not isinstance(status, str):
            continue
        sending_enabled = False
        if isinstance(capabilities, dict):
            sending = capabilities.get("sending")
            sending_enabled = isinstance(sending, str) and sending.lower() == "enabled"
        domains.append(
            ResendDomain(
                id=domain_id,
                name=name.lower(),
                status=status.lower(),
                sending_enabled=sending_enabled,
            )
        )
    return domains


def _extract_sender_email(value: str) -> str:
    _display_name, email_address = parseaddr(value)
    normalized = email_address.strip().lower()
    if normalized == "" or "@" not in normalized:
        raise ValueError("RESEND_FROM_EMAIL must contain a valid email address")
    return normalized


def _extract_domain(email_address: str) -> str:
    _local_part, separator, domain = email_address.partition("@")
    if separator != "@" or domain.strip() == "":
        raise ValueError("sender email must include a domain")
    return domain.strip().lower()


def _find_matching_domain(domains: list[ResendDomain], sender_domain: str) -> ResendDomain | None:
    normalized_sender_domain = sender_domain.lower()
    for domain in domains:
        if normalized_sender_domain == domain.name or normalized_sender_domain.endswith(f".{domain.name}"):
            return domain
    return None


def _print_result(result: ResendReadinessResult) -> None:
    print("== Resend production readiness ==")
    print(f"sender_email={result.sender_email}")
    print(f"sender_domain={result.sender_domain}")
    if result.matched_domain is None:
        print("matched_domain=none")
    else:
        domain = result.matched_domain
        print(
            "matched_domain="
            f"{domain.name} status={domain.status} sending_enabled={str(domain.sending_enabled).lower()}"
        )
    if result.test_message_id is not None:
        print(f"test_message_id={result.test_message_id}")
    if result.warnings:
        print("warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    if result.blockers:
        print("blockers:")
        for blocker in result.blockers:
            print(f"- {blocker}")
    print(f"ready={str(result.ready).lower()}")


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Verify Resend sender/domain readiness for production email.")
    parser.add_argument(
        "--send-test-to",
        default=None,
        help="Optional recipient for a live test email. Use your verified Resend test recipient until a domain is verified.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(send_test_to=cast(str | None, args.send_test_to))))


if __name__ == "__main__":
    main()
