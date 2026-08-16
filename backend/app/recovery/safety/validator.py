"""
Deterministic safety validator — FEAT-026, FEAT-027, FEAT-028, FEAT-029.

Fail-closed: any validation failure rejects the candidate.
No unsafe action is automatically executed (TAD §24).

Security invariants preserved:
- SEC-001: AI cannot directly execute requests
- SEC-002: Arbitrary hosts cannot be selected through model output
- SEC-003: Secrets never enter embeddings
- SEC-006: Maximum upstream execution count enforced
- SECURITY_ACCESS §6-11
"""

from __future__ import annotations

import ipaddress
import re
import socket
import uuid
from typing import Any
from urllib.parse import urlparse

import structlog

from app.recovery.policy.engine import PolicyDecision, POLICY_NEVER_AUTOMATIC, POLICY_AUTO_ELIGIBLE

logger = structlog.get_logger(__name__)

# Safe action types for automatic execution
_SAFE_ACTION_TYPES = frozenset(
    {
        "parameter_rename",
        "remove_optional_field",
        "retry_after",
        "schema_field_mapping",
        "add_missing_optional_field",
        "normalize_field_type",
    }
)

# Methods that are inherently idempotent
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})

# Keys that indicate secrets in candidate changes
_SECRET_CHANGE_KEYS = frozenset(
    {"password", "api_key", "token", "secret", "credential", "authorization", "auth"}
)


class SafetyResult:
    def __init__(
        self,
        *,
        passed: bool,
        checks: list[dict],
        rejection_reason: str | None = None,
    ):
        self.passed = passed
        self.checks = checks
        self.rejection_reason = rejection_reason

    def __repr__(self) -> str:
        return f"<SafetyResult passed={self.passed} reason={self.rejection_reason!r}>"


class SafetyValidator:
    """
    Deterministic safety validator.

    Every candidate must pass all checks before execution.
    Safety is fail-closed: any failure rejects the candidate.

    The validator does NOT consult the LLM.
    The LLM cannot bypass this validator.
    """

    def __init__(self, *, registered_host: str | None = None):
        self.registered_host = registered_host

    def validate(
        self,
        *,
        candidate: dict[str, Any],
        policy_decision: PolicyDecision,
        method: str,
        url: str | None = None,
        is_idempotent: bool = False,
        upstream_attempt_count: int = 0,
        max_attempts: int = 2,
    ) -> SafetyResult:
        """
        Run all safety checks and return a SafetyResult.

        Fail-closed: if any check fails, the candidate is rejected.
        """
        checks: list[dict] = []

        # ── Check 1: Policy tier ──────────────────────────────────────────────
        if policy_decision.is_never_automatic:
            checks.append({
                "check": "policy_tier",
                "passed": False,
                "detail": f"NEVER_AUTOMATIC policy for action '{policy_decision.action_type}'",
            })
            return SafetyResult(
                passed=False,
                checks=checks,
                rejection_reason=f"NEVER_AUTOMATIC: {policy_decision.reason}",
            )
        checks.append({"check": "policy_tier", "passed": True})

        # ── Check 2: Action type is recognized and safe ───────────────────────
        action_type = candidate.get("type") or candidate.get("action_type") or ""
        action_safe = action_type in _SAFE_ACTION_TYPES or not policy_decision.is_auto_eligible
        checks.append({
            "check": "action_type_safe",
            "passed": action_safe,
            "action_type": action_type,
        })
        if not action_safe and policy_decision.is_auto_eligible:
            return SafetyResult(
                passed=False,
                checks=checks,
                rejection_reason=f"Action type '{action_type}' is not in the safe action list for AUTO_ELIGIBLE",
            )

        # ── Check 3: No secret values in changes ──────────────────────────────
        changes = candidate.get("changes") or []
        for change in changes:
            if isinstance(change, dict):
                for key, value in change.items():
                    if key.lower() in _SECRET_CHANGE_KEYS:
                        checks.append({
                            "check": "no_secrets_in_changes",
                            "passed": False,
                            "detail": f"Secret-like key '{key}' found in candidate changes",
                        })
                        return SafetyResult(
                            passed=False,
                            checks=checks,
                            rejection_reason=f"Candidate changes contain secret key: '{key}'",
                        )
        checks.append({"check": "no_secrets_in_changes", "passed": True})

        # ── Check 4: No host change in changes ────────────────────────────────
        for change in changes:
            if isinstance(change, dict):
                if "host" in str(change.get("field", "")).lower() or "url" in str(change.get("field", "")).lower():
                    if change.get("type") == "replace" or change.get("action") == "replace":
                        checks.append({
                            "check": "no_host_change",
                            "passed": False,
                            "detail": "Candidate attempts to change host/URL field",
                        })
                        return SafetyResult(
                            passed=False,
                            checks=checks,
                            rejection_reason="Candidate changes contain host/URL modification",
                        )
        checks.append({"check": "no_host_change", "passed": True})

        # ── Check 5: URL host validation (if URL provided) ────────────────────
        if url:
            try:
                self._validate_url_host(url)
                checks.append({"check": "url_host_valid", "passed": True})
            except ValueError as exc:
                checks.append({"check": "url_host_valid", "passed": False, "detail": str(exc)})
                return SafetyResult(
                    passed=False,
                    checks=checks,
                    rejection_reason=f"URL host validation failed: {exc}",
                )

        # ── Check 6: Idempotency for AUTO_ELIGIBLE ────────────────────────────
        if policy_decision.is_auto_eligible:
            method_idempotent = method.upper() in _IDEMPOTENT_METHODS
            if not method_idempotent and not is_idempotent:
                checks.append({
                    "check": "idempotency",
                    "passed": False,
                    "detail": f"Method {method} is not idempotent and endpoint not marked idempotent",
                })
                return SafetyResult(
                    passed=False,
                    checks=checks,
                    rejection_reason=f"AUTO_ELIGIBLE requires idempotent method or explicit idempotency key; {method} is not inherently idempotent",
                )
        checks.append({"check": "idempotency", "passed": True})

        # ── Check 7: Upstream attempt budget ──────────────────────────────────
        if upstream_attempt_count >= max_attempts:
            checks.append({
                "check": "retry_budget",
                "passed": False,
                "detail": f"upstream_attempt_count={upstream_attempt_count} >= max_attempts={max_attempts}",
            })
            return SafetyResult(
                passed=False,
                checks=checks,
                rejection_reason=f"Maximum upstream attempt count ({max_attempts}) already reached",
            )
        checks.append({"check": "retry_budget", "passed": True})

        logger.debug(
            "safety_validation_passed",
            action_type=action_type,
            policy_tier=policy_decision.tier,
        )
        return SafetyResult(passed=True, checks=checks)

    def _validate_url_host(self, url: str) -> None:
        """
        Validate that a URL's host matches the registered host.
        Raises ValueError if host is disallowed.
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError(f"Cannot determine hostname from URL: {url!r}")

        if self.registered_host and hostname.lower() != self.registered_host.lower():
            raise ValueError(
                f"Corrected request hostname '{hostname}' does not match "
                f"registered host '{self.registered_host}'"
            )
