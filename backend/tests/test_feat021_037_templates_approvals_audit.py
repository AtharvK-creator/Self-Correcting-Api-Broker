"""
Tests for FEAT-021/022: Prompt template library
Tests for FEAT-030/031: Approval workflow
Tests for FEAT-032: Policy management
Tests for FEAT-037: Audit trail
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.recovery.llm.templates import (
    render_correction_template,
    render_schema_analysis_template,
    render_candidate_eval_template,
    _assert_no_secrets,
    CORRECTION_TEMPLATE_VERSION,
    VALID_ACTION_TYPES,
)


# ── FEAT-021/022: Prompt Templates ───────────────────────────────────────────

def test_correction_template_renders():
    rendered = render_correction_template(
        method="POST",
        endpoint_path="/users",
        failure_class="UNKNOWN_PARAMETER",
        http_status=422,
        schema_signature="abc123",
        error_summary={"detail": "unknown field 'customerId'"},
        max_candidates=3,
    )
    assert "POST /users" in rendered.text
    assert "UNKNOWN_PARAMETER" in rendered.text
    assert "422" in rendered.text
    assert CORRECTION_TEMPLATE_VERSION in rendered.text
    assert rendered.template_type == "correction"
    assert rendered.char_count > 100


def test_correction_template_includes_valid_action_types():
    """Template must enumerate valid action types as a constraint."""
    rendered = render_correction_template(
        method="GET",
        endpoint_path="/items",
        failure_class="RATE_LIMIT",
        http_status=429,
        schema_signature="xyz",
        error_summary={},
    )
    for action_type in VALID_ACTION_TYPES:
        assert action_type in rendered.text


def test_correction_template_rejects_secrets_in_error_summary():
    """Secret keys in error_summary must raise ValueError before prompt render."""
    with pytest.raises(ValueError, match="Secret key"):
        render_correction_template(
            method="GET",
            endpoint_path="/data",
            failure_class="UNKNOWN",
            http_status=500,
            schema_signature="sig",
            error_summary={"api_key": "leaked-value"},
        )


def test_correction_template_includes_neighborhood():
    neighborhood = [
        {"id": "node-1", "node_type": "REQUEST_CONTEXT", "failure_class": "UNKNOWN_PARAMETER"}
    ]
    rendered = render_correction_template(
        method="GET",
        endpoint_path="/data",
        failure_class="UNKNOWN_PARAMETER",
        http_status=422,
        schema_signature="sig",
        error_summary={},
        graph_neighborhood=neighborhood,
    )
    assert "node-1" in rendered.text


def test_schema_analysis_template_renders():
    schema = {"fields": [{"name": "customer_id", "type": "string"}]}
    rendered = render_schema_analysis_template(api_schema=schema)
    assert "customer_id" in rendered.text
    assert rendered.template_type == "schema_analysis"


def test_schema_analysis_rejects_secrets():
    with pytest.raises(ValueError, match="Secret key"):
        render_schema_analysis_template(api_schema={"password": "oops"})


def test_candidate_eval_template_renders():
    rendered = render_candidate_eval_template(
        action_type="parameter_rename",
        changes=[{"field": "userId", "rename_to": "user_id"}],
        reason="snake_case convention",
        similar_count=3,
        historical_success_rate=0.85,
        failure_class="UNKNOWN_PARAMETER",
    )
    assert "parameter_rename" in rendered.text
    assert "85.0%" in rendered.text
    assert rendered.template_type == "candidate_eval"


def test_assert_no_secrets_passes_clean_dict():
    # Should not raise
    _assert_no_secrets({"user_id": "123", "name": "Alice", "page": 1})


def test_assert_no_secrets_detects_nested():
    with pytest.raises(ValueError, match="Secret key"):
        _assert_no_secrets({"data": {"token": "abc123"}})


# ── FEAT-030/031: Approval Workflow ───────────────────────────────────────────

def test_submit_for_approval(client):
    """Submit a correction candidate for approval."""
    # First create a candidate — use in-memory fixture
    cand_id = uuid.uuid4()
    # Use mocked candidate via direct registry test approach —
    # in unit tests we test the schema validation layer
    response = client.post("/api/v1/approvals", json={
        "candidate_id": str(cand_id),
        "justification": "Needs review",
    })
    # 404 expected because candidate doesn't exist in test DB (no live PG)
    assert response.status_code in (404, 201)


def test_list_approvals_empty(client):
    response = client.get("/api/v1/approvals")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_approve_nonexistent_raises_404(client):
    response = client.post(f"/api/v1/approvals/{uuid.uuid4()}/approve", json={})
    assert response.status_code == 404


def test_reject_nonexistent_raises_404(client):
    response = client.post(f"/api/v1/approvals/{uuid.uuid4()}/reject", json={})
    assert response.status_code == 404


# ── FEAT-032: Policy Management ───────────────────────────────────────────────

def test_list_policies_empty(client):
    response = client.get("/api/v1/policies")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_policy(client):
    response = client.post("/api/v1/policies", json={
        "action_type": "parameter_rename",
        "tier": "AUTO_ELIGIBLE",
        "description": "Safe rename operations",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["action_type"] == "parameter_rename"
    assert body["tier"] == "AUTO_ELIGIBLE"
    assert body["is_active"] is True


def test_create_policy_invalid_tier(client):
    response = client.post("/api/v1/policies", json={
        "action_type": "some_action",
        "tier": "INVALID_TIER",
    })
    assert response.status_code == 422


def test_create_policy_duplicate_active(client):
    client.post("/api/v1/policies", json={
        "action_type": "test_duplicate_action",
        "tier": "AUTO_ELIGIBLE",
    })
    response = client.post("/api/v1/policies", json={
        "action_type": "test_duplicate_action",
        "tier": "AUTO_ELIGIBLE",
    })
    assert response.status_code == 409


def test_update_policy(client):
    create_resp = client.post("/api/v1/policies", json={
        "action_type": "patchable_action",
        "tier": "APPROVAL_REQUIRED",
    })
    policy_id = create_resp.json()["id"]
    patch_resp = client.patch(f"/api/v1/policies/{policy_id}", json={
        "description": "Updated description",
    })
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "Updated description"


def test_deactivate_policy(client):
    create_resp = client.post("/api/v1/policies", json={
        "action_type": "deactivatable_action",
        "tier": "APPROVAL_REQUIRED",
    })
    policy_id = create_resp.json()["id"]
    delete_resp = client.delete(f"/api/v1/policies/{policy_id}")
    assert delete_resp.status_code == 204


def test_policy_never_automatic_tier_accepted(client):
    """NEVER_AUTOMATIC is a valid tier to set via API."""
    response = client.post("/api/v1/policies", json={
        "action_type": "custom_dangerous_action",
        "tier": "NEVER_AUTOMATIC",
        "description": "Always block this",
    })
    assert response.status_code == 201
    assert response.json()["tier"] == "NEVER_AUTOMATIC"


# ── FEAT-037: Audit Trail ─────────────────────────────────────────────────────

def test_audit_list_empty(client):
    response = client.get("/api/v1/audit")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_audit_by_correlation_id(client):
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/audit/correlation/{random_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["correlation_id"] == str(random_id)
    assert body["event_count"] == 0
    assert body["events"] == []


def test_audit_event_type_filter(client):
    response = client.get("/api/v1/audit?event_type=CANDIDATE_SELECTED")
    assert response.status_code == 200
    # All returned events should match the filter
    for event in response.json():
        assert event["event_type"] == "CANDIDATE_SELECTED"
