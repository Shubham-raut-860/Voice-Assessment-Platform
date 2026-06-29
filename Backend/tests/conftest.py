from __future__ import annotations

from collections.abc import Iterator
from os import environ

import pytest


@pytest.fixture(autouse=True)
def app_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _set_default_env(monkeypatch, "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    _set_default_env(monkeypatch, "SUPABASE_URL", "https://example.supabase.co")
    _set_default_env(monkeypatch, "SUPABASE_SERVICE_ROLE_KEY", "x" * 40)
    _set_default_env(monkeypatch, "ANTHROPIC_API_KEY", "x" * 40)
    _set_default_env(monkeypatch, "VAPI_API_KEY", "x" * 40)
    _set_default_env(monkeypatch, "VAPI_WEBHOOK_SECRET", "x" * 40)
    _set_default_env(monkeypatch, "VAPI_PHONE_NUMBER_ID", "vapi-phone-number-id")
    _set_default_env(monkeypatch, "RESEND_API_KEY", "x" * 40)
    _set_default_env(monkeypatch, "JWT_SECRET", "x" * 40)
    _set_default_env(monkeypatch, "ADMIN_EMAIL", "[email-redacted]")
    _set_default_env(monkeypatch, "ENVIRONMENT", "development")
    _set_default_env(monkeypatch, "CORS_ORIGINS", '["http://localhost:3000"]')
    yield


def _set_default_env(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    if name not in environ:
        monkeypatch.setenv(name, value)
