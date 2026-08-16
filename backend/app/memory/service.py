"""
Recovery memory service — FEAT-033, FEAT-034, FEAT-035.

Manages the recovery case lifecycle:
- Retrieval (by signature/context)
- Creation from successful LLM corrections
- Maturity promotion (PROPOSED → VALIDATED → ESTABLISHED)

TAD §15, PRD §14.
Maturity gates:
- PROPOSED   → VALIDATED:   success_count >= 2 after LLM origin
- VALIDATED  → ESTABLISHED: success_count >= 5, failure_count/success_count <= 0.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.builder import FailureContext
from app.models.recovery import (
    MATURITY_ESTABLISHED,
    MATURITY_PROPOSED,
    MATURITY_VALIDATED,
    POLICY_AUTO_ELIGIBLE,
    PROVENANCE_DETERMINISTIC,
    PROVENANCE_LLM,
    RecoveryCase,
)

logger = structlog.get_logger(__name__)

# Maturity promotion thresholds (configurable in future)
_VALIDATED_SUCCESS_THRESHOLD = 2
_ESTABLISHED_SUCCESS_THRESHOLD = 5
_ESTABLISHED_FAILURE_RATE_MAX = 0.20


class RecoveryMemoryService:
    """Manages the recovery case lifecycle and maturity promotion."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def find_by_signature(
        self,
        failure_signature: str,
        *,
        min_maturity: str = MATURITY_VALIDATED,
        limit: int = 5,
    ) -> list[RecoveryCase]:
        """
        Retrieve recovery cases by failure signature.

        Only returns VALIDATED or ESTABLISHED cases by default.
        PROPOSED cases are excluded from automatic recovery paths.
        """
        maturity_order = [MATURITY_ESTABLISHED, MATURITY_VALIDATED, MATURITY_PROPOSED]
        eligible_maturities = maturity_order[: maturity_order.index(min_maturity) + 1]

        result = await self.db.execute(
            select(RecoveryCase)
            .where(
                RecoveryCase.failure_signature == failure_signature,
                RecoveryCase.maturity.in_(eligible_maturities),
            )
            .order_by(RecoveryCase.confidence.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def find_by_context(
        self,
        context: FailureContext,
        *,
        min_maturity: str = MATURITY_VALIDATED,
        limit: int = 5,
    ) -> list[RecoveryCase]:
        """Retrieve recovery cases by context signature."""
        maturity_order = [MATURITY_ESTABLISHED, MATURITY_VALIDATED, MATURITY_PROPOSED]
        eligible_maturities = maturity_order[: maturity_order.index(min_maturity) + 1]

        result = await self.db.execute(
            select(RecoveryCase)
            .where(
                RecoveryCase.context_signature == context.context_signature,
                RecoveryCase.maturity.in_(eligible_maturities),
            )
            .order_by(RecoveryCase.confidence.desc())
            .limit(limit)
        )
        return result.scalars().all()

    # ── Creation ──────────────────────────────────────────────────────────────

    async def create_from_llm_success(
        self,
        *,
        context: FailureContext,
        action_type: str,
        changes: list,
        model_provider: str,
        model_version: str,
        confidence: float,
        api_id: uuid.UUID | None = None,
        endpoint_id: uuid.UUID | None = None,
    ) -> RecoveryCase:
        """
        Create a new PROPOSED recovery case from a successful LLM correction.

        Starts at PROPOSED maturity — promoted by record_outcome.
        """
        # Check if a case with this signature+context already exists
        existing = await self.db.execute(
            select(RecoveryCase).where(
                RecoveryCase.failure_signature == context.failure_signature,
                RecoveryCase.context_signature == context.context_signature,
                RecoveryCase.source == PROVENANCE_LLM,
            )
        )
        case = existing.scalar_one_or_none()

        if case:
            # Update existing case
            case.reuse_count += 1
            case.last_used_at = datetime.now(timezone.utc)
            await self.db.flush()
            return case

        case = RecoveryCase(
            api_id=api_id,
            endpoint_id=endpoint_id,
            failure_signature=context.failure_signature,
            context_signature=context.context_signature,
            correction={
                "type": action_type,
                "changes": changes,
            },
            source=PROVENANCE_LLM,
            model_provider=model_provider,
            model_version=model_version,
            maturity=MATURITY_PROPOSED,
            confidence=confidence,
            success_count=1,
            failure_count=0,
            reuse_count=0,
            last_used_at=datetime.now(timezone.utc),
        )
        self.db.add(case)
        await self.db.flush()

        logger.info(
            "recovery_case_created",
            case_id=str(case.id),
            failure_signature=context.failure_signature,
            source=PROVENANCE_LLM,
        )
        return case

    async def create_from_deterministic(
        self,
        *,
        context: FailureContext,
        action_type: str,
        changes: list,
        confidence: float,
        api_id: uuid.UUID | None = None,
    ) -> RecoveryCase:
        """
        Create a VALIDATED recovery case from a deterministic correction.

        Deterministic cases start at VALIDATED (not PROPOSED) because they
        have inherent structural evidence.
        """
        existing = await self.db.execute(
            select(RecoveryCase).where(
                RecoveryCase.failure_signature == context.failure_signature,
                RecoveryCase.source == PROVENANCE_DETERMINISTIC,
            )
        )
        case = existing.scalar_one_or_none()
        if case:
            case.reuse_count += 1
            case.last_used_at = datetime.now(timezone.utc)
            await self.db.flush()
            return case

        case = RecoveryCase(
            api_id=api_id,
            failure_signature=context.failure_signature,
            context_signature=context.context_signature,
            correction={"type": action_type, "changes": changes},
            source=PROVENANCE_DETERMINISTIC,
            maturity=MATURITY_VALIDATED,
            confidence=confidence,
            success_count=1,
            failure_count=0,
            reuse_count=0,
            last_used_at=datetime.now(timezone.utc),
        )
        self.db.add(case)
        await self.db.flush()
        return case

    # ── Outcome recording and maturity promotion ──────────────────────────────

    async def record_outcome(
        self,
        case_id: uuid.UUID,
        *,
        success: bool,
    ) -> RecoveryCase:
        """
        Record a success/failure outcome and promote maturity if thresholds met.

        PROPOSED → VALIDATED  : success_count >= 2
        VALIDATED → ESTABLISHED: success_count >= 5, failure_rate <= 20%
        """
        case = await self.db.get(RecoveryCase, case_id)
        if not case:
            raise ValueError(f"RecoveryCase {case_id} not found")

        if success:
            case.success_count += 1
            # Recalculate confidence using Laplace smoothing
            total = case.success_count + case.failure_count
            case.confidence = (case.success_count + 1) / (total + 2)
        else:
            case.failure_count += 1
            total = case.success_count + case.failure_count
            case.confidence = (case.success_count + 1) / (total + 2)

        case.last_used_at = datetime.now(timezone.utc)

        # Maturity promotion
        old_maturity = case.maturity
        case.maturity = self._compute_maturity(case)

        if case.maturity != old_maturity:
            logger.info(
                "recovery_case_maturity_promoted",
                case_id=str(case_id),
                from_maturity=old_maturity,
                to_maturity=case.maturity,
                success_count=case.success_count,
                failure_count=case.failure_count,
            )

        await self.db.flush()
        return case

    def _compute_maturity(self, case: RecoveryCase) -> str:
        if case.maturity == MATURITY_PROPOSED:
            if case.success_count >= _VALIDATED_SUCCESS_THRESHOLD:
                return MATURITY_VALIDATED
        elif case.maturity == MATURITY_VALIDATED:
            failure_rate = (
                case.failure_count / case.success_count
                if case.success_count > 0
                else 1.0
            )
            if (
                case.success_count >= _ESTABLISHED_SUCCESS_THRESHOLD
                and failure_rate <= _ESTABLISHED_FAILURE_RATE_MAX
            ):
                return MATURITY_ESTABLISHED
        return case.maturity
