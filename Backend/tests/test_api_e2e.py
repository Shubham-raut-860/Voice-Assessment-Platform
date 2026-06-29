from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

E2E_BASE_URL = os.environ.get("VOICE_E2E_BASE_URL")
E2E_DATABASE_URL = os.environ.get("VOICE_E2E_DATABASE_URL")
E2E_WEBHOOK_SECRET = os.environ.get("VAPI_WEBHOOK_SECRET", "x" * 40)
E2E_PASSWORD = "StrongPass123!"

pytestmark = pytest.mark.skipif(
    not E2E_BASE_URL or not E2E_DATABASE_URL,
    reason="Set VOICE_E2E_BASE_URL and VOICE_E2E_DATABASE_URL to run API E2E tests.",
)


@pytest_asyncio.fixture()
async def e2e_client() -> AsyncIterator[httpx.AsyncClient]:
    if E2E_BASE_URL is None:
        raise RuntimeError("VOICE_E2E_BASE_URL is required")

    async with httpx.AsyncClient(base_url=E2E_BASE_URL, timeout=20.0) as client:
        yield client


@pytest_asyncio.fixture()
async def e2e_engine() -> AsyncIterator[AsyncEngine]:
    if E2E_DATABASE_URL is None:
        raise RuntimeError("VOICE_E2E_DATABASE_URL is required")

    engine = create_async_engine(E2E_DATABASE_URL, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_assessment_session_report_and_vapi_webhook_flow(
    e2e_client: httpx.AsyncClient,
    e2e_engine: AsyncEngine,
) -> None:
    suffix = uuid4().hex
    admin_email = f"e2e.admin.{suffix}@voicee2e.dev"
    candidate_email = f"e2e.candidate.{suffix}@voicee2e.dev"

    health_response = await e2e_client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["db"] == "connected"

    ready_response = await e2e_client.get("/ready")
    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"

    admin_id = await _register_user(e2e_client, admin_email, "E2E Admin")
    await _promote_user_to_admin(e2e_engine, admin_id)
    admin_token = await _login(e2e_client, admin_email)

    me_response = await e2e_client.get(
        "/api/v1/auth/me",
        headers=_authorization(admin_token),
    )
    assert me_response.status_code == 200
    assert me_response.json()["role"] == "admin"

    candidate_id = await _register_user(e2e_client, candidate_email, "E2E Candidate")
    assessment_id = await _create_assessment(e2e_client, admin_token)
    session_id = await _create_session(e2e_client, admin_token, assessment_id, candidate_id)

    missing_report_response = await e2e_client.get(
        f"/api/v1/sessions/{session_id}/report",
        headers=_authorization(admin_token),
    )
    assert missing_report_response.status_code == 404
    assert missing_report_response.json()["detail"]["code"] == "report_not_found"

    call_id = f"e2e-call-{suffix}"
    await _set_session_call_id(e2e_engine, session_id, call_id)
    await _send_vapi_event(
        e2e_client,
        {
            "event_id": f"e2e-started-{suffix}",
            "type": "call.started",
            "call_id": call_id,
            "assistant_id": str(uuid4()),
            "started_at": datetime.now(UTC).isoformat(),
        },
    )
    await _send_vapi_event(
        e2e_client,
        {
            "event_id": f"e2e-transcript-{suffix}",
            "type": "transcript.update",
            "call_id": call_id,
            "transcript": [
                {
                    "role": "assistant",
                    "content": "Describe a production incident you handled.",
                    "timestamp": 1.0,
                },
                {
                    "role": "user",
                    "content": "I isolated the failing dependency and communicated status.",
                    "timestamp": 2.0,
                },
            ],
        },
    )
    await _send_vapi_event(
        e2e_client,
        {
            "event_id": f"e2e-ended-{suffix}",
            "type": "call.ended",
            "call_id": call_id,
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_seconds": 120,
            "end_reason": "assistant_ended",
        },
    )
    duplicate_response = await _send_vapi_event(
        e2e_client,
        {
            "event_id": f"e2e-ended-{suffix}",
            "type": "call.ended",
            "call_id": call_id,
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_seconds": 120,
            "end_reason": "assistant_ended",
        },
    )
    assert duplicate_response.status_code == 200

    session_response = await e2e_client.get(
        f"/api/v1/sessions/{session_id}",
        headers=_authorization(admin_token),
    )
    assert session_response.status_code == 200
    session_payload = session_response.json()
    assert session_payload["status"] == "completed"
    assert session_payload["duration_seconds"] == 120
    assert "failing dependency" in session_payload["raw_transcript"]

    await _insert_pending_report(e2e_engine, session_id)
    pending_report_response = await e2e_client.get(
        f"/api/v1/sessions/{session_id}/report",
        headers=_authorization(admin_token),
    )
    assert pending_report_response.status_code == 200
    assert pending_report_response.json()["status"] == "pending"

    stats_response = await e2e_client.get("/api/v1/admin/stats", headers=_authorization(admin_token))
    assert stats_response.status_code == 200
    assert stats_response.json()["total_sessions"] >= 1


async def _register_user(client: httpx.AsyncClient, email: str, full_name: str) -> UUID:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": E2E_PASSWORD,
            "full_name": full_name,
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _login(client: httpx.AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": E2E_PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert isinstance(token, str)
    return token


async def _promote_user_to_admin(engine: AsyncEngine, user_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("update users set role = 'admin' where id = :user_id"),
            {"user_id": user_id},
        )


async def _create_assessment(client: httpx.AsyncClient, token: str) -> UUID:
    response = await client.post(
        "/api/v1/assessments",
        headers=_authorization(token),
        json={
            "title": "E2E Voice Assessment",
            "description": "Automated end-to-end API assessment.",
            "status": "active",
            "vapi_assistant_id": str(uuid4()),
            "passing_score": str(Decimal("75.00")),
            "time_limit_minutes": 30,
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _create_session(
    client: httpx.AsyncClient,
    token: str,
    assessment_id: UUID,
    candidate_id: UUID,
) -> UUID:
    response = await client.post(
        "/api/v1/sessions",
        headers=_authorization(token),
        json={
            "assessment_id": str(assessment_id),
            "candidate_id": str(candidate_id),
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _set_session_call_id(engine: AsyncEngine, session_id: UUID, call_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("update assessment_sessions set vapi_call_id = :call_id where id = :session_id"),
            {"call_id": call_id, "session_id": session_id},
        )


async def _insert_pending_report(engine: AsyncEngine, session_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                insert into assessment_reports (
                    session_id,
                    version,
                    overall_score,
                    pass_fail,
                    strengths,
                    weaknesses,
                    detailed_analysis,
                    recommendations,
                    anthropic_model_used,
                    anthropic_prompt_tokens,
                    anthropic_completion_tokens,
                    generation_status
                )
                values (
                    :session_id,
                    1,
                    null,
                    'inconclusive',
                    '[]'::jsonb,
                    '[]'::jsonb,
                    'Report generation is pending.',
                    'Report generation is pending.',
                    'e2e-pending',
                    0,
                    0,
                    'pending'
                )
                """
            ),
            {"session_id": session_id},
        )


async def _send_vapi_event(
    client: httpx.AsyncClient,
    payload: dict[str, object],
) -> httpx.Response:
    raw_body = _json_bytes(payload)
    response = await client.post(
        "/api/v1/webhooks/vapi",
        headers={
            "Content-Type": "application/json",
            "X-Vapi-Signature": _signature(raw_body),
        },
        content=raw_body,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"received": True}
    return response


def _json_bytes(payload: dict[str, object]) -> bytes:
    import json

    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _signature(body: bytes) -> str:
    timestamp = str(int(datetime.now(UTC).timestamp()))
    digest = hmac.new(
        E2E_WEBHOOK_SECRET.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
