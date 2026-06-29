from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

import httpx
import structlog

logger = structlog.get_logger(__name__)

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


@dataclass(frozen=True)
class RevocationProbeConfig:
    base_url: str
    email: str
    password: str
    full_name: str


@dataclass(frozen=True)
class RevocationProbeResult:
    registered: bool
    login_status_code: int
    logout_status_code: int
    revoked_me_status_code: int


async def run_revocation_probe(config: RevocationProbeConfig) -> RevocationProbeResult:
    async with httpx.AsyncClient(base_url=config.base_url, timeout=20.0) as client:
        registered = await _register_user(client, config)
        token = await _login_user(client, config)
        await _assert_current_user(client, token, expected_status_code=200)
        logout_status_code = await _logout(client, token)
        revoked_me_status_code = await _assert_current_user(
            client,
            token,
            expected_status_code=401,
        )

    return RevocationProbeResult(
        registered=registered,
        login_status_code=200,
        logout_status_code=logout_status_code,
        revoked_me_status_code=revoked_me_status_code,
    )


async def _register_user(client: httpx.AsyncClient, config: RevocationProbeConfig) -> bool:
    payload: JsonObject = {
        "email": config.email,
        "password": config.password,
        "full_name": config.full_name,
    }
    try:
        response = await client.post("/api/v1/auth/register", json=payload)
    except httpx.HTTPError as exc:
        logger.exception("redis_revocation_register_request_failed", error=str(exc))
        raise

    if response.status_code == 201:
        return True

    if response.status_code == 400 and "email_already_registered" in response.text:
        return False

    raise RuntimeError(
        f"register_failed: status={response.status_code} body={response.text[:500]}"
    )


async def _login_user(client: httpx.AsyncClient, config: RevocationProbeConfig) -> str:
    payload: JsonObject = {
        "email": config.email,
        "password": config.password,
    }
    try:
        response = await client.post("/api/v1/auth/login", json=payload)
    except httpx.HTTPError as exc:
        logger.exception("redis_revocation_login_request_failed", error=str(exc))
        raise

    if response.status_code != 200:
        raise RuntimeError(f"login_failed: status={response.status_code} body={response.text[:500]}")

    data = _response_json_object(response)
    token = data.get("access_token")
    if not isinstance(token, str) or token.strip() == "":
        raise RuntimeError("login_failed: access_token missing from response")
    return token


async def _logout(client: httpx.AsyncClient, token: str) -> int:
    try:
        response = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        logger.exception("redis_revocation_logout_request_failed", error=str(exc))
        raise

    if response.status_code != 200:
        raise RuntimeError(f"logout_failed: status={response.status_code} body={response.text[:500]}")

    data = _response_json_object(response)
    status = data.get("status")
    if status != "revoked":
        raise RuntimeError(
            "redis_not_active: logout did not revoke token. "
            "Set REDIS_URL and restart the API before using this in pre-production."
        )
    return response.status_code


async def _assert_current_user(
    client: httpx.AsyncClient,
    token: str,
    expected_status_code: int,
) -> int:
    try:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        logger.exception("redis_revocation_me_request_failed", error=str(exc))
        raise

    if response.status_code != expected_status_code:
        raise RuntimeError(
            "unexpected_me_status: "
            f"expected={expected_status_code} actual={response.status_code} body={response.text[:500]}"
        )
    return response.status_code


def _response_json_object(response: httpx.Response) -> JsonObject:
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("response_json_not_object")
    return data


def _default_email() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"redis.revocation.{timestamp}@example.com"


def parse_args() -> RevocationProbeConfig:
    parser = argparse.ArgumentParser(
        description="Verify that logout revokes JWTs through the configured Redis store.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default=_default_email())
    parser.add_argument("--password", default="RedisProbe123!")
    parser.add_argument("--full-name", default="Redis Revocation Probe")
    args = parser.parse_args()
    return RevocationProbeConfig(
        base_url=str(args.base_url).rstrip("/"),
        email=str(args.email),
        password=str(args.password),
        full_name=str(args.full_name),
    )


def main() -> NoReturn:
    config = parse_args()
    try:
        result = asyncio.run(run_revocation_probe(config))
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"redis_revocation: failed: {exc}")
        raise SystemExit(1) from exc

    print("redis_revocation: ok")
    print(f"registered={result.registered}")
    print(f"login_status_code={result.login_status_code}")
    print(f"logout_status_code={result.logout_status_code}")
    print(f"revoked_me_status_code={result.revoked_me_status_code}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
