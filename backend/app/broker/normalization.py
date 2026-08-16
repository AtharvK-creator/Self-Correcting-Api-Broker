"""
Request normalization — FEAT-004.

Produces a canonical NormalizedRequest context from an incoming broker execute
payload. Strips secrets from all stored fields before persistence.

FR-002: Normalize request context.
NFR-004: Secrets excluded from graph/vector records.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from pydantic import BaseModel

# Headers whose values must never be stored (SEC-003, SECURITY_ACCESS §11)
_SECRET_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "api-key",
        "x-secret",
        "x-password",
    }
)

# Query/body parameter names that are likely secrets
_SECRET_PARAM_PATTERNS: list[re.Pattern] = [
    re.compile(r"(^|_)(api[_-]?key|secret|password|token|credential|auth)(s)?$", re.I),
]


def _is_secret_param(name: str) -> bool:
    return any(pat.search(name) for pat in _SECRET_PARAM_PATTERNS)


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return headers with secret values replaced by [REDACTED]."""
    return {
        k: "[REDACTED]" if k.lower() in _SECRET_HEADERS else v
        for k, v in headers.items()
    }


def redact_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return params with secret-like keys replaced by [REDACTED]."""
    return {
        k: "[REDACTED]" if _is_secret_param(k) else v
        for k, v in params.items()
    }


def _schema_signature(params: dict[str, Any] | None) -> str:
    """
    Stable hash of the parameter *names* (not values) and types.
    Used for schema-level matching in the recovery pipeline.
    """
    if not params:
        return hashlib.sha256(b"empty").hexdigest()[:16]
    keys = sorted(f"{k}:{type(v).__name__}" for k, v in params.items())
    raw = "|".join(keys).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


class NormalizedRequest(BaseModel):
    """
    Canonical request context produced by the normalizer.

    This is the internal representation used by all pipeline stages.
    Secrets are redacted before this object is created and it is
    safe to persist to graph/vector/audit storage.
    """
    correlation_id: uuid.UUID
    api_id: uuid.UUID
    endpoint_path: str
    method: str
    version: str | None = None
    # Redacted headers — no secret values
    headers: dict[str, str]
    # Redacted query parameters
    query_params: dict[str, Any]
    # Redacted body (or None)
    body: dict[str, Any] | None
    # Stable hash of parameter names+types for schema matching
    schema_signature: str
    # Idempotency metadata
    idempotency_key: str | None = None
    is_idempotent: bool = False
    recovery_mode: str = "auto"  # auto | manual | disabled


def normalize_request(
    *,
    correlation_id: uuid.UUID,
    api_id: uuid.UUID,
    endpoint_path: str,
    method: str,
    headers: dict[str, str],
    query_params: dict[str, Any],
    body: dict[str, Any] | None,
    recovery_mode: str = "auto",
    version: str | None = None,
    is_idempotent: bool = False,
) -> NormalizedRequest:
    """
    Normalize and sanitize an incoming broker request.

    Redacts secrets from headers and parameters.
    Computes a schema signature from parameter names/types.
    """
    clean_headers = redact_headers(headers)
    clean_params = redact_params(query_params)
    clean_body = redact_params(body) if body else None

    # Combine params+body for schema signature
    all_params: dict[str, Any] = {**query_params}
    if body:
        all_params.update(body)
    sig = _schema_signature(all_params)

    # Extract idempotency key from headers
    idempotency_key = headers.get("Idempotency-Key") or headers.get("X-Idempotency-Key")

    return NormalizedRequest(
        correlation_id=correlation_id,
        api_id=api_id,
        endpoint_path=endpoint_path,
        method=method.upper(),
        version=version,
        headers=clean_headers,
        query_params=clean_params,
        body=clean_body,
        schema_signature=sig,
        idempotency_key=idempotency_key,
        is_idempotent=is_idempotent,
        recovery_mode=recovery_mode,
    )
