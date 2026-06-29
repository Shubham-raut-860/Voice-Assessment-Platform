from __future__ import annotations

import hashlib
import hmac
from time import time

import pytest
from fastapi import HTTPException

from app.services.vapi_service import validate_vapi_signature, validate_vapi_webhook_auth


def test_validate_vapi_signature_accepts_valid_signature() -> None:
    payload = b'{"type":"call.started"}'
    secret = "super-secret"
    timestamp = str(int(time()))
    digest = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + payload,
        hashlib.sha256,
    ).hexdigest()

    validate_vapi_signature(payload, f"t={timestamp},v1={digest}", secret)


def test_validate_vapi_signature_rejects_invalid_signature() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_vapi_signature(b"{}", "t=123,v1=bad", "super-secret")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid_signature"


def test_validate_vapi_signature_rejects_stale_signature() -> None:
    payload = b"{}"
    secret = "super-secret"
    timestamp = str(int(time()) - 600)
    digest = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + payload,
        hashlib.sha256,
    ).hexdigest()

    with pytest.raises(HTTPException) as exc_info:
        validate_vapi_signature(payload, f"t={timestamp},v1={digest}", secret)

    assert exc_info.value.status_code == 401


def test_validate_vapi_webhook_auth_accepts_static_secret_header() -> None:
    validate_vapi_webhook_auth(
        payload=b"{}",
        signature_header="",
        shared_secret_header="super-secret",
        secret="super-secret",
    )


def test_validate_vapi_webhook_auth_rejects_invalid_static_secret_header() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_vapi_webhook_auth(
            payload=b"{}",
            signature_header="",
            shared_secret_header="wrong-secret",
            secret="super-secret",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid_signature"


def test_validate_vapi_webhook_auth_prefers_signature_when_present() -> None:
    payload = b'{"type":"call.started"}'
    secret = "super-secret"
    timestamp = str(int(time()))
    digest = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + payload,
        hashlib.sha256,
    ).hexdigest()

    validate_vapi_webhook_auth(
        payload=payload,
        signature_header=f"t={timestamp},v1={digest}",
        shared_secret_header="wrong-secret",
        secret=secret,
    )
