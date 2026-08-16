"""
Confidence gate — FEAT-018.

Decides whether deterministic evidence is sufficient to skip LLM escalation.

TAD §9, BACKEND_SPEC §7, PRD §11.
Score formula (TAD §9, configurable weights):
  confidence = 0.30*graph_similarity + 0.25*historical_success
              + 0.20*schema_compatibility + 0.15*failure_match
              + 0.10*provenance_quality - risk_penalty
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class ConfidenceGateResult:
    sufficient: bool
    score: float
    candidate_ids: list[str] = field(default_factory=list)
    evidence_count: int = 0
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "sufficient": self.sufficient,
            "score": self.score,
            "candidate_ids": self.candidate_ids,
            "evidence_count": self.evidence_count,
            "reason": self.reason,
        }


def evaluate_confidence(
    candidates: list[Any],
    *,
    graph_similarity: float = 0.0,
    historical_success_rate: float = 0.0,
    schema_compatibility: float = 0.0,
    failure_match: float = 0.0,
    provenance_quality: float = 0.0,
    risk_penalty: float = 0.0,
    threshold: float | None = None,
    min_evidence_count: int | None = None,
) -> ConfidenceGateResult:
    """
    Evaluate whether deterministic evidence is sufficient.

    Returns ConfidenceGateResult.sufficient = True if:
    - combined score >= threshold, AND
    - evidence_count >= min_evidence_count

    LLM is NOT invoked when sufficient=True.
    LLM MAY be invoked when sufficient=False (if eligible and within budget).
    """
    settings = get_settings()
    weights = settings.ranking_weights
    threshold = threshold if threshold is not None else settings.confidence_threshold
    min_evidence = min_evidence_count if min_evidence_count is not None else settings.min_evidence_count

    score = (
        weights["graph_similarity"] * graph_similarity
        + weights["historical_success"] * historical_success_rate
        + weights["schema_compatibility"] * schema_compatibility
        + weights["failure_match"] * failure_match
        + weights["provenance_quality"] * provenance_quality
        - risk_penalty
    )
    score = max(0.0, min(score, 1.0))

    # Filter candidates that have meaningful confidence
    high_confidence_candidates = [
        c for c in candidates
        if hasattr(c, "confidence") and c.confidence >= threshold * 0.7
    ]
    evidence_count = len(high_confidence_candidates)

    sufficient = score >= threshold and evidence_count >= min_evidence
    candidate_ids = [
        str(getattr(c, "id", getattr(c, "recovery_case_id", "?")))
        for c in high_confidence_candidates
    ]

    reason = None
    if not sufficient:
        if score < threshold:
            reason = f"Score {score:.3f} below threshold {threshold:.3f}"
        elif evidence_count < min_evidence:
            reason = f"Evidence count {evidence_count} below minimum {min_evidence}"

    logger.info(
        "confidence_gate_evaluated",
        score=score,
        threshold=threshold,
        evidence_count=evidence_count,
        min_evidence=min_evidence,
        sufficient=sufficient,
    )

    return ConfidenceGateResult(
        sufficient=sufficient,
        score=score,
        candidate_ids=candidate_ids,
        evidence_count=evidence_count,
        reason=reason,
    )
