"""
Three-tier policy engine — FEAT-025.

Assigns policy tiers to correction candidates:
- AUTO_ELIGIBLE: safe, bounded, evidence-backed
- APPROVAL_REQUIRED: consequential, needs human approval
- NEVER_AUTOMATIC: always reject (security invariant)

PRD §10, SECURITY_ACCESS §9, FINAL_DECISIONS #10.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recovery import (
    POLICY_AUTO_ELIGIBLE,
    POLICY_APPROVAL_REQUIRED,
    POLICY_NEVER_AUTOMATIC,
    Policy,
)

logger = structlog.get_logger(__name__)

# ── Hard-coded NEVER_AUTOMATIC actions (security invariant) ──────────────────
# These cannot be overridden by database policy records.
# SECURITY_ACCESS §9, FINAL_DECISIONS #10.
_HARDCODED_NEVER_AUTOMATIC: frozenset[str] = frozenset(
    {
        "destination_host_change",
        "disable_tls_verification",
        "credential_disclosure",
        "authorization_scope_expansion",
        "arbitrary_code_execution",
        "unregistered_endpoint_redirect",
        # Also block these even if worded differently
        "host_change",
        "tls_bypass",
        "credential_leak",
        "scope_expansion",
        "code_execution",
    }
)


class PolicyDecision:
    def __init__(
        self,
        *,
        tier: str,
        action_type: str,
        reason: str,
        from_hardcoded: bool = False,
    ):
        self.tier = tier
        self.action_type = action_type
        self.reason = reason
        self.from_hardcoded = from_hardcoded

    @property
    def is_auto_eligible(self) -> bool:
        return self.tier == POLICY_AUTO_ELIGIBLE

    @property
    def is_never_automatic(self) -> bool:
        return self.tier == POLICY_NEVER_AUTOMATIC

    @property
    def requires_approval(self) -> bool:
        return self.tier == POLICY_APPROVAL_REQUIRED

    def __repr__(self) -> str:
        return f"<PolicyDecision action={self.action_type!r} tier={self.tier!r}>"


class PolicyEngine:
    """
    Assigns policy tiers to action types.

    Lookup order:
    1. Hardcoded NEVER_AUTOMATIC list (cannot be overridden).
    2. Database policy record.
    3. Default: APPROVAL_REQUIRED (fail safe).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def classify_action(self, action_type: str) -> PolicyDecision:
        """
        Classify an action type and return the appropriate policy tier.

        NEVER_AUTOMATIC is a hard security invariant — it cannot be
        overridden by database records.
        """
        normalized = action_type.lower().strip()

        # 1. Hard security invariant — always NEVER_AUTOMATIC
        if normalized in _HARDCODED_NEVER_AUTOMATIC:
            logger.warning(
                "policy_never_automatic_hardcoded",
                action_type=action_type,
            )
            return PolicyDecision(
                tier=POLICY_NEVER_AUTOMATIC,
                action_type=action_type,
                reason=f"Action type '{action_type}' is hardcoded as NEVER_AUTOMATIC",
                from_hardcoded=True,
            )

        # 2. Look up database policy
        result = await self.db.execute(
            select(Policy).where(
                Policy.action_type == action_type,
                Policy.is_active == True,
            )
        )
        policy = result.scalar_one_or_none()

        if policy:
            # Extra safety: even if a DB record says NEVER_AUTOMATIC,
            # double-check against the hardcoded list
            if policy.tier == POLICY_NEVER_AUTOMATIC:
                return PolicyDecision(
                    tier=POLICY_NEVER_AUTOMATIC,
                    action_type=action_type,
                    reason=policy.description or "Configured as NEVER_AUTOMATIC",
                )
            return PolicyDecision(
                tier=policy.tier,
                action_type=action_type,
                reason=policy.description or f"Configured tier: {policy.tier}",
            )

        # 3. Default: APPROVAL_REQUIRED (fail-safe)
        logger.info(
            "policy_default_approval_required",
            action_type=action_type,
        )
        return PolicyDecision(
            tier=POLICY_APPROVAL_REQUIRED,
            action_type=action_type,
            reason="No specific policy configured; defaulting to APPROVAL_REQUIRED",
        )
