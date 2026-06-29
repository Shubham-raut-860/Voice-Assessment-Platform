from __future__ import annotations

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.middleware.rate_limit import AUTH_RATE_LIMIT, DEFAULT_RATE_LIMIT, WEBHOOK_RATE_LIMIT


def test_app_registers_expected_routes() -> None:
    from app.main import app

    routes = {route.path for route in app.routes}

    assert "/health" in routes
    assert "/ready" in routes
    assert "/api/v1/auth/login" in routes
    assert "/api/v1/auth/register" in routes
    assert "/api/v1/assessments" in routes
    assert "/api/v1/sessions" in routes
    assert "/api/v1/sessions/{session_id}/report" in routes
    assert "/api/v1/admin/stats" in routes
    assert "/api/v1/webhooks/vapi" in routes


def test_rate_limit_contracts() -> None:
    assert DEFAULT_RATE_LIMIT == "100/minute"
    assert AUTH_RATE_LIMIT == "10/minute"
    assert WEBHOOK_RATE_LIMIT == "60/minute"


def test_middleware_stack_order() -> None:
    from app.main import app

    middleware_names = [middleware.cls.__name__ for middleware in app.user_middleware]

    assert middleware_names == [
        "BaseHTTPMiddleware",
        "RequestLoggingMiddleware",
        "SecurityHeadersMiddleware",
        "SlowAPIMiddleware",
        "CORSMiddleware",
    ]


@pytest.mark.asyncio
async def test_health_returns_503_when_database_check_fails() -> None:
    from app.main import create_app

    app = create_app()
    health_route = next(route for route in app.routes if route.path == "/health")
    endpoint = health_route.endpoint

    response = await endpoint(_FailingSession(), app.state.settings)

    assert response.status_code == 503
    assert response.body == b'{"status":"unhealthy","environment":"development","db":"disconnected"}'


class _FailingSession:
    async def execute(self, statement: object) -> None:
        _ = statement
        raise SQLAlchemyError("database unavailable")
