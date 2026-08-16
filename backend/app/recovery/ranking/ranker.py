"""
Candidate ranking — FEAT-019.

Ranks all candidates (deterministic + LLM) by combined score.
LLM confidence is evidence, not authority (TAD §11).

Score formula (TAD §11, BACKEND_SPEC §10):
  rank_score = 0.30*graph_similarity + 0.25*historical_success
              + 0.20*schema_compatibility + 0.15*failure_match
              + 0.10*provenance_quality - risk_penalty
              (adjusted for candidate source reliability)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.models.recovery import PROVENANCE_DETERMINISTIC, PROVENANCE_LLM


# Risk penalties for action types
_RISK_PENALTIES = {
    "retry_after": 0.0,
    "parameter_rename": 0.0,
    "remove_optional_field": 0.0,
    "schema_field_mapping": 0.0,
    "add_missing_optional_field": 0.0,
    "credential_refresh": 0.15,
    "endpoint_migration": 0.20,
    "payload_transformation": 0.10,
}

# Provenance reliability multiplier
_PROVENANCE_RELIABILITY = {
    PROVENANCE_DETERMINISTIC: 1.0,
    PROVENANCE_LLM: 0.85,  # LLM is evidence, not authority
}


@dataclass
class RankedCandidate:
    """A candidate with a computed rank score and ordering metadata."""
    candidate: Any
    rank_score: float
    rank: int = 0
    risk_penalty: float = 0.0
    source_reliability: float = 1.0


def rank_candidates(
    candidates: list[Any],
    *,
    graph_similarity: float = 0.0,
    historical_success_rate: float = 0.0,
    schema_compatibility: float = 0.0,
    failure_match: float = 0.0,
    provenance_quality: float = 0.0,
) -> list[RankedCandidate]:
    """
    Rank all candidates by combined score.

    Returns candidates sorted by rank_score descending.
    LLM candidates get a reliability adjustment but not a hard block.
    """
    settings = get_settings()
    weights = settings.ranking_weights

    scored: list[RankedCandidate] = []

    for candidate in candidates:
        action_type = (
            getattr(candidate, "action_type", None)
            or candidate.get("type", "")
            if isinstance(candidate, dict)
            else getattr(candidate, "action_type", "")
        )
        provenance = (
            getattr(candidate, "source", PROVENANCE_DETERMINISTIC)
            if not isinstance(candidate, dict)
            else candidate.get("provenance", PROVENANCE_DETERMINISTIC)
        )
        candidate_confidence = (
            getattr(candidate, "confidence", 0.5)
            if not isinstance(candidate, dict)
            else candidate.get("confidence", 0.5)
        )

        risk_penalty = _RISK_PENALTIES.get(action_type, 0.05)
        source_reliability = _PROVENANCE_RELIABILITY.get(provenance, 0.9)

        # Incorporate candidate's own confidence into provenance_quality
        effective_provenance = provenance_quality * candidate_confidence * source_reliability

        raw_score = (
            weights["graph_similarity"] * graph_similarity
            + weights["historical_success"] * historical_success_rate
            + weights["schema_compatibility"] * schema_compatibility
            + weights["failure_match"] * failure_match
            + weights["provenance_quality"] * effective_provenance
            - risk_penalty
        )
        rank_score = max(0.0, min(raw_score, 1.0))

        scored.append(RankedCandidate(
            candidate=candidate,
            rank_score=rank_score,
            risk_penalty=risk_penalty,
            source_reliability=source_reliability,
        ))

    # Sort by rank_score descending
    scored.sort(key=lambda rc: rc.rank_score, reverse=True)

    # Assign ranks
    for i, rc in enumerate(scored):
        rc.rank = i + 1

    return scored
