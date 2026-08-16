"""
Failure taxonomy and classifier — FEAT-006.

Produces normalized FailureEvent records from upstream responses/errors.
Uses deterministic rule-based classification first.

FR-004: Capture structured failure event.
FR-005: Classify failure.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import structlog

from app.broker.upstream import UpstreamExecutionError

logger = structlog.get_logger(__name__)

# ── Failure classes (PRD §9) ──────────────────────────────────────────────────

class FailureClass:
    UNKNOWN_PARAMETER = "UNKNOWN_PARAMETER"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    ENDPOINT_NOT_FOUND = "ENDPOINT_NOT_FOUND"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    UPSTREAM_5XX = "UPSTREAM_5XX"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    POLICY_REJECTION = "POLICY_REJECTION"
    UNKNOWN = "UNKNOWN"


# Failure classes that are generally recoverable
_RECOVERABLE_CLASSES = {
    FailureClass.UNKNOWN_PARAMETER,
    FailureClass.INVALID_PARAMETER,
    FailureClass.SCHEMA_MISMATCH,
    FailureClass.ENDPOINT_NOT_FOUND,
    FailureClass.VERSION_MISMATCH,
    FailureClass.RATE_LIMIT,
    FailureClass.TIMEOUT,
    FailureClass.CONNECTION_FAILURE,
    FailureClass.UPSTREAM_5XX,
    FailureClass.MALFORMED_RESPONSE,
}


class ClassifiedFailure:
    """Normalized failure event ready for graph construction and recovery."""

    def __init__(
        self,
        *,
        failure_class: str,
        failure_signature: str,
        http_status: int | None,
        error_detail: dict,
        classifier_confidence: float,
        is_recoverable: bool,
        correlation_id: uuid.UUID,
    ):
        self.failure_class = failure_class
        self.failure_signature = failure_signature
        self.http_status = http_status
        self.error_detail = error_detail
        self.classifier_confidence = classifier_confidence
        self.is_recoverable = is_recoverable
        self.correlation_id = correlation_id

    def __repr__(self) -> str:
        return (
            f"<ClassifiedFailure class={self.failure_class!r} "
            f"sig={self.failure_signature!r} recoverable={self.is_recoverable}>"
        )


def _compute_signature(
    api_id: uuid.UUID | None,
    endpoint_path: str,
    failure_class: str,
    http_status: int | None,
    error_keys: list[str],
) -> str:
    """
    Compute a stable failure signature for indexing and retrieval.

    The signature captures the structural identity of the failure without
    encoding variable data like correlation IDs or timestamps.
    """
    parts = [
        str(api_id) if api_id else "unknown_api",
        endpoint_path,
        failure_class,
        str(http_status) if http_status else "no_status",
        "|".join(sorted(error_keys)),
    ]
    raw = "::".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def classify_failure(
    *,
    http_status: int | None,
    response_body: Any,
    error: UpstreamExecutionError | Exception | None,
    api_id: uuid.UUID | None,
    endpoint_path: str,
    correlation_id: uuid.UUID,
) -> ClassifiedFailure:
    """
    Classify a failure deterministically from HTTP status, response body,
    and transport-level errors.

    Confidence is 1.0 for deterministic rule matches, lower for heuristics.
    """
    failure_class = FailureClass.UNKNOWN
    confidence = 1.0
    error_detail: dict = {}
    error_keys: list[str] = []

    # ── Transport-level errors ────────────────────────────────────────────────
    if isinstance(error, UpstreamExecutionError):
        msg = str(error).lower()
        if "timed out" in msg or "timeout" in msg:
            failure_class = FailureClass.TIMEOUT
        else:
            failure_class = FailureClass.CONNECTION_FAILURE
        error_detail = {"message": str(error), "type": type(error).__name__}
        error_keys = ["transport_error"]

    elif http_status is not None:
        # ── HTTP status-based classification ──────────────────────────────────
        body_str = str(response_body).lower() if response_body else ""
        body_keys = _extract_body_keys(response_body)
        error_keys = body_keys

        if http_status == 429:
            failure_class = FailureClass.RATE_LIMIT
            error_detail = {"http_status": http_status, "body": response_body}

        elif http_status == 401:
            failure_class = FailureClass.AUTHENTICATION_FAILURE
            error_detail = {"http_status": http_status, "body": response_body}

        elif http_status == 403:
            failure_class = FailureClass.AUTHORIZATION_FAILURE
            error_detail = {"http_status": http_status, "body": response_body}

        elif http_status == 404:
            failure_class = FailureClass.ENDPOINT_NOT_FOUND
            error_detail = {"http_status": http_status, "body": response_body}

        elif http_status == 422 or http_status == 400:
            # Heuristic sub-classification
            if any(kw in body_str for kw in ("unknown field", "unexpected key", "extra field")):
                failure_class = FailureClass.UNKNOWN_PARAMETER
                confidence = 0.9
            elif any(kw in body_str for kw in ("invalid", "validation error", "value error")):
                failure_class = FailureClass.INVALID_PARAMETER
                confidence = 0.9
            elif any(kw in body_str for kw in ("schema", "type error", "format")):
                failure_class = FailureClass.SCHEMA_MISMATCH
                confidence = 0.85
            else:
                failure_class = FailureClass.INVALID_PARAMETER
                confidence = 0.75
            error_detail = {"http_status": http_status, "body": response_body}

        elif http_status >= 500:
            failure_class = FailureClass.UPSTREAM_5XX
            error_detail = {"http_status": http_status, "body": response_body}

        else:
            failure_class = FailureClass.UNKNOWN
            confidence = 0.5
            error_detail = {"http_status": http_status, "body": response_body}

    else:
        # Response body malformed or no status
        failure_class = FailureClass.MALFORMED_RESPONSE
        error_detail = {"message": "No HTTP status available", "error": str(error) if error else None}
        error_keys = ["no_status"]

    is_recoverable = failure_class in _RECOVERABLE_CLASSES
    signature = _compute_signature(api_id, endpoint_path, failure_class, http_status, error_keys)

    logger.info(
        "failure_classified",
        failure_class=failure_class,
        http_status=http_status,
        confidence=confidence,
        is_recoverable=is_recoverable,
        correlation_id=str(correlation_id),
    )

    return ClassifiedFailure(
        failure_class=failure_class,
        failure_signature=signature,
        http_status=http_status,
        error_detail=error_detail,
        classifier_confidence=confidence,
        is_recoverable=is_recoverable,
        correlation_id=correlation_id,
    )


def _extract_body_keys(body: Any) -> list[str]:
    """Extract top-level keys from a dict response body for signature calculation."""
    if isinstance(body, dict):
        return list(body.keys())
    return []
