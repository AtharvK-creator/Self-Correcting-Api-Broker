"""
Context builder — FEAT-009.

Builds a normalized failure context without secrets.
The context is used for graph node creation and retrieval.

FR-006: Build/update contextual graph.
NFR-004: Secrets excluded from graph/vector records.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from pydantic import BaseModel

from app.broker.normalization import NormalizedRequest
from app.failures.classifier import ClassifiedFailure


class FailureContext(BaseModel):
    """
    Normalized failure context — safe to persist to graph and vector storage.

    All values are structural metadata, never secret values.
    """
    correlation_id: uuid.UUID
    api_id: uuid.UUID
    endpoint_path: str
    method: str
    version: str | None
    failure_class: str
    failure_signature: str
    http_status: int | None
    schema_signature: str
    # Structural summary of the error (no secrets)
    error_summary: dict[str, Any]
    is_recoverable: bool
    classifier_confidence: float
    # Stable context fingerprint for deduplication
    context_signature: str


def build_failure_context(
    request: NormalizedRequest,
    failure: ClassifiedFailure,
) -> FailureContext:
    """
    Combine a normalized request with a classified failure into a
    FailureContext for graph construction and retrieval.

    No secrets flow through this function — the NormalizedRequest
    already has secrets redacted, and the ClassifiedFailure contains
    only structural metadata.
    """
    # Build a sanitized error summary — no secrets
    error_summary = _sanitize_error_detail(failure.error_detail)

    # Context signature = stable hash of (api, endpoint, failure_class, schema)
    context_signature = _compute_context_signature(
        api_id=request.api_id,
        endpoint_path=request.endpoint_path,
        failure_class=failure.failure_class,
        schema_signature=request.schema_signature,
    )

    return FailureContext(
        correlation_id=request.correlation_id,
        api_id=request.api_id,
        endpoint_path=request.endpoint_path,
        method=request.method,
        version=request.version,
        failure_class=failure.failure_class,
        failure_signature=failure.failure_signature,
        http_status=failure.http_status,
        schema_signature=request.schema_signature,
        error_summary=error_summary,
        is_recoverable=failure.is_recoverable,
        classifier_confidence=failure.classifier_confidence,
        context_signature=context_signature,
    )


def _compute_context_signature(
    api_id: uuid.UUID,
    endpoint_path: str,
    failure_class: str,
    schema_signature: str,
) -> str:
    """Stable context fingerprint for deduplication and retrieval."""
    raw = f"{api_id}::{endpoint_path}::{failure_class}::{schema_signature}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


# Keys that should never appear in error summaries
_FORBIDDEN_KEYS = frozenset({
    "authorization", "password", "token", "api_key", "secret",
    "credential", "cookie", "auth", "key",
})


def _sanitize_error_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """
    Remove any potentially secret keys from error detail.

    SEC-003: Secrets never enter embeddings or graph storage.
    """
    if not isinstance(detail, dict):
        return {}
    return {
        k: ("[REDACTED]" if k.lower() in _FORBIDDEN_KEYS else v)
        for k, v in detail.items()
        if isinstance(k, str)
    }
