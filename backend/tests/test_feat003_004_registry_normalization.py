"""
Tests for FEAT-003: API Registry and FEAT-004: Request Normalization.
"""

import uuid
import pytest

from app.broker.normalization import (
    normalize_request,
    redact_headers,
    redact_params,
    _schema_signature,
    NormalizedRequest,
)


# ── FEAT-003: Registry tests (via API endpoints) ──────────────────────────────

def test_list_apis_empty(client):
    response = client.get("/api/v1/apis")
    assert response.status_code == 200
    assert response.json() == []


def test_create_api(client):
    response = client.post("/api/v1/apis", json={
        "name": "test-service",
        "base_url": "https://api.test.com",
        "registered_host": "api.test.com",
        "description": "Test service",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "test-service"
    assert body["registered_host"] == "api.test.com"
    assert "id" in body


def test_create_api_duplicate_name(client):
    client.post("/api/v1/apis", json={
        "name": "duplicate-api",
        "base_url": "https://api1.test.com",
        "registered_host": "api1.test.com",
    })
    response = client.post("/api/v1/apis", json={
        "name": "duplicate-api",
        "base_url": "https://api2.test.com",
        "registered_host": "api2.test.com",
    })
    assert response.status_code == 409


def test_get_api_not_found(client):
    response = client.get(f"/api/v1/apis/{uuid.uuid4()}")
    assert response.status_code == 404


def test_patch_api(client):
    create_resp = client.post("/api/v1/apis", json={
        "name": "patch-test-api",
        "base_url": "https://patch.test.com",
        "registered_host": "patch.test.com",
    })
    api_id = create_resp.json()["id"]
    patch_resp = client.patch(f"/api/v1/apis/{api_id}", json={"description": "Updated description"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "Updated description"


# ── FEAT-004: Request normalization tests ─────────────────────────────────────

def test_normalize_request_basic():
    req = normalize_request(
        correlation_id=uuid.uuid4(),
        api_id=uuid.uuid4(),
        endpoint_path="/users",
        method="post",
        headers={"Content-Type": "application/json"},
        query_params={"page": 1},
        body={"name": "Alice"},
    )
    assert req.method == "POST"  # normalized to uppercase
    assert req.endpoint_path == "/users"
    assert req.schema_signature != ""


def test_redact_secret_headers():
    headers = {
        "Authorization": "Bearer secret-token-123",
        "X-Api-Key": "my-api-key",
        "Content-Type": "application/json",
        "User-Agent": "test-client",
    }
    redacted = redact_headers(headers)
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["X-Api-Key"] == "[REDACTED]"
    assert redacted["Content-Type"] == "application/json"
    assert redacted["User-Agent"] == "test-client"


def test_redact_secret_params():
    params = {
        "api_key": "secret-key-value",
        "token": "my-token",
        "user_id": "12345",
        "name": "Alice",
    }
    redacted = redact_params(params)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["user_id"] == "12345"
    assert redacted["name"] == "Alice"


def test_schema_signature_stable():
    params = {"name": "Alice", "age": 30}
    sig1 = _schema_signature(params)
    sig2 = _schema_signature({"age": 30, "name": "Alice"})  # different order
    assert sig1 == sig2  # order-independent


def test_schema_signature_differs_on_different_keys():
    sig1 = _schema_signature({"customerId": "123"})
    sig2 = _schema_signature({"customer_id": "123"})
    assert sig1 != sig2


def test_normalize_request_strips_auth_header():
    """SEC-003: Secrets must never be stored in normalized context."""
    req = normalize_request(
        correlation_id=uuid.uuid4(),
        api_id=uuid.uuid4(),
        endpoint_path="/orders",
        method="GET",
        headers={
            "Authorization": "Bearer tok123",
            "Cookie": "session=abc",
            "Accept": "application/json",
        },
        query_params={},
        body=None,
    )
    # Authorization must be redacted
    assert req.headers.get("Authorization") == "[REDACTED]"
    assert req.headers.get("Cookie") == "[REDACTED]"
    # Non-secret headers preserved
    assert req.headers.get("Accept") == "application/json"


def test_normalize_request_extracts_idempotency_key():
    req = normalize_request(
        correlation_id=uuid.uuid4(),
        api_id=uuid.uuid4(),
        endpoint_path="/payments",
        method="POST",
        headers={"Idempotency-Key": "idem-key-001"},
        query_params={},
        body=None,
    )
    assert req.idempotency_key == "idem-key-001"


def test_normalized_request_is_safe_to_store():
    """Verify that no secret value appears in the NormalizedRequest object."""
    secret_value = "super-secret-api-key-12345"
    req = normalize_request(
        correlation_id=uuid.uuid4(),
        api_id=uuid.uuid4(),
        endpoint_path="/data",
        method="GET",
        headers={"Authorization": f"Bearer {secret_value}", "Content-Type": "application/json"},
        query_params={"api_key": secret_value},
        body={"password": secret_value, "name": "Alice"},
    )
    # Serialize to dict and check that secret value doesn't appear anywhere
    as_dict = req.model_dump()
    as_str = str(as_dict)
    assert secret_value not in as_str, "Secret value found in normalized request!"
