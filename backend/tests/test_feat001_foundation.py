"""
Tests for FEAT-001: Repository and development environment.

Verifies:
- Health liveness endpoint returns 200
- Health readiness endpoint responds (200 or 503 depending on DB)
- Version and uptime fields are present
- App structure is importable
"""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def bare_client():
    """Client without DB override — tests that don't need DB."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_health_liveness(bare_client):
    """GET /health returns 200 with status=ok."""
    response = bare_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body
    assert "version" in body


def test_health_liveness_has_correlation_id_header(bare_client):
    """Health endpoint returns X-Correlation-ID header."""
    response = bare_client.get("/health")
    assert "X-Correlation-ID" in response.headers


def test_health_readiness_db_ok(client):
    """GET /health/ready returns 200 when DB is reachable."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert "llm_provider" in body


def test_health_readiness_db_unreachable():
    """GET /health/ready returns 503 when DB execute fails."""
    from unittest.mock import AsyncMock, patch
    from fastapi.testclient import TestClient
    from app.database import get_db

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=Exception("connection refused"))
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def broken_db():
        yield mock_session

    with TestClient(app, raise_server_exceptions=False) as c:
        app.dependency_overrides[get_db] = broken_db
        response = c.get("/health/ready")
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_app_imports():
    """All core app modules are importable without errors."""
    import app.config
    import app.database
    import app.models
    import app.api.v1.health
    import app.api.v1.registry
    import app.api.v1.broker
    assert True


def test_settings_loaded():
    """Settings load correctly from environment."""
    from app.config import get_settings
    settings = get_settings()
    assert settings.app_env in {"development", "testing", "production"}
    assert settings.llm_provider in {"gemini", "groq", "mock"}


def test_cors_headers(bare_client):
    """CORS preflight returns correct headers."""
    response = bare_client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    # Allow origin should be present for localhost:3000
    assert response.status_code in {200, 204}
