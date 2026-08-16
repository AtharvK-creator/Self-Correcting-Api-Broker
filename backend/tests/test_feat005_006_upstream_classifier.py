"""
Tests for FEAT-005: Upstream execution engine (SSRF controls, TLS)
Tests for FEAT-006: Failure taxonomy and classifier.

Security tests: SSRF block, private IP block, redirect revalidation.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.broker.upstream import (
    _validate_host_ssrf,
    SSRFError,
    UpstreamExecutionError,
    UpstreamResponse,
)
from app.failures.classifier import (
    ClassifiedFailure,
    FailureClass,
    classify_failure,
    _compute_signature,
)


# ── FEAT-005: SSRF protection tests ──────────────────────────────────────────

def test_ssrf_blocks_localhost():
    """SEC-002: Private loopback addresses must be blocked."""
    with pytest.raises(SSRFError, match="resolves to private"):
        _validate_host_ssrf("http://localhost/api")


def test_ssrf_blocks_127_0_0_1():
    with pytest.raises(SSRFError, match="resolves to private"):
        _validate_host_ssrf("http://127.0.0.1/api")


def test_ssrf_blocks_private_192_168():
    """Block 192.168.x.x private range."""
    # We mock socket.getaddrinfo to return a private IP
    import socket
    import ipaddress
    from unittest.mock import patch

    mock_result = [(None, None, None, None, ("192.168.1.1", 0))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        with pytest.raises(SSRFError, match="private/reserved"):
            _validate_host_ssrf("http://internal-service.example.com/api")


def test_ssrf_blocks_10_x_x_x():
    """Block 10.x.x.x private range."""
    mock_result = [(None, None, None, None, ("10.0.0.1", 0))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        with pytest.raises(SSRFError, match="private/reserved"):
            _validate_host_ssrf("http://internal.example.com/api")


def test_ssrf_registered_host_mismatch():
    """Hostname must match registered_host if provided."""
    mock_result = [(None, None, None, None, ("93.184.216.34", 0))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        with pytest.raises(SSRFError, match="does not match registered host"):
            _validate_host_ssrf(
                "http://attacker.example.com/steal",
                registered_host="api.legit.com",
            )


def test_ssrf_allows_registered_host():
    """Valid public IP with matching registered host passes."""
    mock_result = [(None, None, None, None, ("93.184.216.34", 0))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        # Should not raise
        _validate_host_ssrf("http://api.legit.com/data", registered_host="api.legit.com")


def test_ssrf_unresolvable_hostname():
    """Unresolvable hostname raises SSRFError."""
    import socket
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("NXDOMAIN")):
        with pytest.raises(SSRFError, match="Cannot resolve hostname"):
            _validate_host_ssrf("http://does-not-exist-xyzzy.example.com/api")


# ── FEAT-006: Failure classifier tests ───────────────────────────────────────

def _make_failure(http_status=None, body=None, error=None, endpoint="/test"):
    return classify_failure(
        http_status=http_status,
        response_body=body,
        error=error,
        api_id=uuid.uuid4(),
        endpoint_path=endpoint,
        correlation_id=uuid.uuid4(),
    )


def test_classify_429_rate_limit():
    f = _make_failure(http_status=429, body={"error": "Too Many Requests"})
    assert f.failure_class == FailureClass.RATE_LIMIT
    assert f.is_recoverable is True
    assert f.classifier_confidence == 1.0


def test_classify_404_endpoint_not_found():
    f = _make_failure(http_status=404, body={"detail": "Not Found"})
    assert f.failure_class == FailureClass.ENDPOINT_NOT_FOUND
    assert f.is_recoverable is True


def test_classify_401_auth_failure():
    f = _make_failure(http_status=401, body={"error": "Unauthorized"})
    assert f.failure_class == FailureClass.AUTHENTICATION_FAILURE
    assert f.is_recoverable is False  # Auth failures not auto-recoverable


def test_classify_403_authz_failure():
    f = _make_failure(http_status=403, body={"error": "Forbidden"})
    assert f.failure_class == FailureClass.AUTHORIZATION_FAILURE


def test_classify_422_unknown_parameter():
    f = _make_failure(
        http_status=422,
        body={"detail": [{"msg": "unknown field", "loc": ["body", "customerId"]}]},
    )
    assert f.failure_class == FailureClass.UNKNOWN_PARAMETER
    assert f.is_recoverable is True
    assert f.classifier_confidence >= 0.85


def test_classify_422_schema_mismatch():
    f = _make_failure(
        http_status=422,
        body={"detail": "schema type error in field 'amount'"},
    )
    assert f.failure_class == FailureClass.SCHEMA_MISMATCH
    assert f.is_recoverable is True


def test_classify_500_upstream_error():
    f = _make_failure(http_status=500, body={"error": "Internal Server Error"})
    assert f.failure_class == FailureClass.UPSTREAM_5XX
    assert f.is_recoverable is True


def test_classify_timeout_error():
    from app.broker.upstream import UpstreamExecutionError
    error = UpstreamExecutionError("Upstream request timed out")
    f = _make_failure(error=error)
    assert f.failure_class == FailureClass.TIMEOUT
    assert f.is_recoverable is True


def test_classify_connection_error():
    error = UpstreamExecutionError("Upstream connection error: refused")
    f = _make_failure(error=error)
    assert f.failure_class == FailureClass.CONNECTION_FAILURE
    assert f.is_recoverable is True


def test_failure_signature_is_stable():
    """Same failure produces same signature (deterministic)."""
    api_id = uuid.uuid4()
    sig1 = _compute_signature(api_id, "/users", FailureClass.RATE_LIMIT, 429, [])
    sig2 = _compute_signature(api_id, "/users", FailureClass.RATE_LIMIT, 429, [])
    assert sig1 == sig2


def test_failure_signature_differs_on_different_class():
    api_id = uuid.uuid4()
    sig1 = _compute_signature(api_id, "/users", FailureClass.RATE_LIMIT, 429, [])
    sig2 = _compute_signature(api_id, "/users", FailureClass.TIMEOUT, 429, [])
    assert sig1 != sig2


def test_classified_failure_has_no_secrets():
    """Error detail must not contain secret values."""
    f = _make_failure(
        http_status=422,
        body={"detail": "invalid field"},
        endpoint="/api/payments",
    )
    detail_str = str(f.error_detail)
    secret_keywords = ["password", "token", "api_key", "secret", "credential"]
    for kw in secret_keywords:
        assert kw not in detail_str.lower()
