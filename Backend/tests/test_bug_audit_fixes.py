from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import Response
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.api.v1.auth import logout
from app.models.assessment_report import AssessmentReport
from app.models.assessment_session import AssessmentSession
from app.models.user import User
from app.schemas.enums import ReportStatus, SessionStatus, UserRole, VapiCallEndReason
from app.services import auth_service
from app.services.auth_service import authenticate_user, create_access_token
from app.services.token_revocation_service import ensure_token_not_revoked, revocation_key
from app.schemas.webhook import VapiCallEndedEvent
from app.services import anthropic_service
from app.services.vapi_service import _session_status_for_end_reason


def test_vapi_call_ended_coerces_unknown_end_reason() -> None:
    event = VapiCallEndedEvent.model_validate(
        {
            "type": "call.ended",
            "call_id": "call_123",
            "ended_at": "2026-06-01T10:00:00Z",
            "duration_seconds": 32,
            "end_reason": "new-vapi-reason",
        }
    )

    assert event.end_reason == VapiCallEndReason.UNKNOWN


def test_vapi_end_reason_maps_non_completion_statuses() -> None:
    assert _session_status_for_end_reason(VapiCallEndReason.ERROR) == SessionStatus.FAILED
    assert _session_status_for_end_reason(VapiCallEndReason.PIPELINE_ERROR) == SessionStatus.FAILED
    assert _session_status_for_end_reason(VapiCallEndReason.TIME_LIMIT) == SessionStatus.ABANDONED
    assert _session_status_for_end_reason(VapiCallEndReason.EXCEEDED_MAX_DURATION) == SessionStatus.ABANDONED
    assert _session_status_for_end_reason(VapiCallEndReason.ASSISTANT_ENDED) == SessionStatus.COMPLETED


def test_user_role_has_no_lowercase_alias_members() -> None:
    assert [role.name for role in UserRole] == ["ADMIN", "ASSESSOR", "CANDIDATE"]
    assert not hasattr(UserRole, "admin")


@pytest.mark.asyncio
async def test_trigger_report_generation_backs_off_when_unclaimed_report_is_generating(
    monkeypatch: MonkeyPatch,
) -> None:
    session = AssessmentSession(id=uuid4(), status=SessionStatus.COMPLETED)
    report = AssessmentReport(
        id=uuid4(),
        session_id=session.id,
        version=1,
        generation_status=ReportStatus.GENERATING,
    )
    generate_called = False

    async def fake_load_session(db: AsyncSession, session_id: object) -> AssessmentSession:
        _ = db
        _ = session_id
        return session

    async def fake_get_or_create_report(db: AsyncSession, session_id: object) -> AssessmentReport:
        _ = db
        _ = session_id
        return report

    async def fake_generate_report(session_arg: AssessmentSession, settings_arg: Settings) -> object:
        nonlocal generate_called
        _ = session_arg
        _ = settings_arg
        generate_called = True
        return object()

    monkeypatch.setattr(anthropic_service, "_load_session", fake_load_session)
    monkeypatch.setattr(anthropic_service, "_get_or_create_report", fake_get_or_create_report)
    monkeypatch.setattr(anthropic_service, "generate_report", fake_generate_report)

    await anthropic_service.trigger_report_generation(session.id, _FakeAsyncSession(), Settings())

    assert generate_called is False


class _FakeAsyncSession:
    async def commit(self) -> None:
        raise AssertionError("commit should not be called for unclaimed generating reports")


@pytest.mark.asyncio
async def test_logout_response_discloses_stateless_token_semantics() -> None:
    user = User(
        id=uuid4(),
        email="[email-redacted]",
        hashed_password="hashed",
        full_name="Admin User",
        role=UserRole.ADMIN,
    )

    response = await logout(
        response=Response(),
        token=create_access_token(user, Settings()),
        current_user=user,
        settings=Settings(),
        redis_client=None,
    )

    assert response == {
        "status": "accepted",
        "note": "token_remains_valid_until_expiry",
    }


@pytest.mark.asyncio
async def test_logout_revokes_jwt_when_redis_is_available() -> None:
    user = User(
        id=uuid4(),
        email="[email-redacted]",
        hashed_password="hashed",
        full_name="Admin User",
        role=UserRole.ADMIN,
    )
    settings = Settings()
    token = create_access_token(user, settings)
    redis_client = _FakeRedisClient()

    response = await logout(
        response=Response(),
        token=token,
        current_user=user,
        settings=settings,
        redis_client=redis_client,
    )

    assert response == {"status": "revoked", "note": "token_revoked_until_expiry"}
    assert len(redis_client.values) == 1
    revoked_key = next(iter(redis_client.values))
    assert revoked_key.startswith("jwt:revoked:")


@pytest.mark.asyncio
async def test_revoked_jwt_is_rejected() -> None:
    redis_client = _FakeRedisClient()
    await redis_client.set(revocation_key("jti_123"), "1", ex=60)

    with pytest.raises(Exception) as exc_info:
        await ensure_token_not_revoked(redis_client, "jti_123")

    assert getattr(exc_info.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_unverified_user_can_login_when_email_verification_disabled(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_service, "verify_password", _always_valid_password)
    user = _auth_user(is_verified=False)

    authenticated = await authenticate_user(
        _FakeUserLookupDb(user),
        "[email-redacted]",
        "CorrectPassword123!",
        Settings(),
    )

    assert authenticated is user


@pytest.mark.asyncio
async def test_unverified_user_cannot_login_when_email_verification_required(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    monkeypatch.setattr(auth_service, "verify_password", _always_valid_password)
    user = _auth_user(is_verified=False)

    authenticated = await authenticate_user(
        _FakeUserLookupDb(user),
        "[email-redacted]",
        "CorrectPassword123!",
        Settings(),
    )

    assert authenticated is None


def _auth_user(is_verified: bool) -> User:
    return User(
        id=uuid4(),
        email="[email-redacted]",
        hashed_password="hashed_password",
        full_name="Candidate User",
        role=UserRole.CANDIDATE,
        is_active=True,
        is_verified=is_verified,
    )


class _FakeUserLookupDb:
    def __init__(self, user: User | None) -> None:
        self._user = user

    async def execute(self, statement: object) -> "_FakeUserLookupResult":
        _ = statement
        return _FakeUserLookupResult(self._user)


class _FakeUserLookupResult:
    def __init__(self, user: User | None) -> None:
        self._user = user

    def scalar_one_or_none(self) -> User | None:
        return self._user


def _always_valid_password(plain: str, hashed: str) -> bool:
    _ = plain
    _ = hashed
    return True


class _FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def set(self, name: str, value: str, ex: int) -> object:
        self.values[name] = value
        self.expirations[name] = ex
        return True

    async def get(self, name: str) -> object:
        return self.values.get(name)

    async def aclose(self) -> object:
        return None
