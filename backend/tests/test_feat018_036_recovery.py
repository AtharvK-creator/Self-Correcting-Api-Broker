"""
Tests for FEAT-025: Policy Engine
Tests for FEAT-026: Safety Validator
Tests for FEAT-018: Confidence Gate
Tests for FEAT-019: Candidate Ranking
Tests for FEAT-033/034/035: Recovery Memory
"""

import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from app.recovery.policy.engine import (
    PolicyEngine,
    PolicyDecision,
    _HARDCODED_NEVER_AUTOMATIC,
    POLICY_NEVER_AUTOMATIC,
    POLICY_AUTO_ELIGIBLE,
    POLICY_APPROVAL_REQUIRED,
)
from app.recovery.safety.validator import SafetyValidator
from app.recovery.deterministic.confidence_gate import evaluate_confidence, ConfidenceGateResult
from app.recovery.ranking.ranker import rank_candidates, RankedCandidate
from app.models.recovery import (
    MATURITY_PROPOSED, MATURITY_VALIDATED, MATURITY_ESTABLISHED,
    PROVENANCE_DETERMINISTIC, PROVENANCE_LLM,
)


# ── FEAT-025: Policy Engine ───────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Default: no policy record found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=mock_result)
    return db


@pytest.fixture
def policy_engine(mock_db):
    return PolicyEngine(mock_db)


@pytest.mark.asyncio
async def test_policy_hardcoded_never_automatic_host_change(policy_engine):
    """destination_host_change must ALWAYS be NEVER_AUTOMATIC (security invariant)."""
    decision = await policy_engine.classify_action("destination_host_change")
    assert decision.tier == POLICY_NEVER_AUTOMATIC
    assert decision.from_hardcoded is True


@pytest.mark.asyncio
async def test_policy_hardcoded_never_automatic_tls_disable(policy_engine):
    """disable_tls_verification must ALWAYS be NEVER_AUTOMATIC."""
    decision = await policy_engine.classify_action("disable_tls_verification")
    assert decision.tier == POLICY_NEVER_AUTOMATIC
    assert decision.from_hardcoded is True


@pytest.mark.asyncio
async def test_policy_hardcoded_cannot_be_overridden_by_db(mock_db):
    """Even if DB has a policy, hardcoded NEVER_AUTOMATIC takes precedence."""
    # Simulate a DB policy that says AUTO_ELIGIBLE for a hardcoded action
    from app.models.recovery import Policy
    mock_policy = Policy(action_type="host_change", tier=POLICY_AUTO_ELIGIBLE, is_active=True)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_policy)
    mock_db.execute = AsyncMock(return_value=mock_result)

    engine = PolicyEngine(mock_db)
    decision = await engine.classify_action("host_change")
    assert decision.tier == POLICY_NEVER_AUTOMATIC
    assert decision.from_hardcoded is True


@pytest.mark.asyncio
async def test_policy_default_approval_required(policy_engine):
    """Unknown action types default to APPROVAL_REQUIRED."""
    decision = await policy_engine.classify_action("some_unknown_action")
    assert decision.tier == POLICY_APPROVAL_REQUIRED
    assert decision.from_hardcoded is False


@pytest.mark.asyncio
async def test_policy_db_record_respected(mock_db):
    """DB policy records are used for non-hardcoded action types."""
    from app.models.recovery import Policy
    mock_policy = Policy(action_type="parameter_rename", tier=POLICY_AUTO_ELIGIBLE, is_active=True)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_policy)
    mock_db.execute = AsyncMock(return_value=mock_result)

    engine = PolicyEngine(mock_db)
    decision = await engine.classify_action("parameter_rename")
    assert decision.tier == POLICY_AUTO_ELIGIBLE


def test_hardcoded_never_automatic_set_not_empty():
    """At minimum the critical security invariants are in the hardcoded set."""
    assert "destination_host_change" in _HARDCODED_NEVER_AUTOMATIC
    assert "disable_tls_verification" in _HARDCODED_NEVER_AUTOMATIC
    assert "credential_disclosure" in _HARDCODED_NEVER_AUTOMATIC


# ── FEAT-026: Safety Validator ────────────────────────────────────────────────

def _make_policy(tier: str, action_type: str = "parameter_rename") -> PolicyDecision:
    return PolicyDecision(tier=tier, action_type=action_type, reason="test")


def _make_candidate(action_type: str = "parameter_rename", changes: list = None) -> dict:
    return {"type": action_type, "changes": changes or []}


def test_safety_rejects_never_automatic():
    """NEVER_AUTOMATIC candidates must always be rejected."""
    validator = SafetyValidator()
    result = validator.validate(
        candidate=_make_candidate("destination_host_change"),
        policy_decision=_make_policy(POLICY_NEVER_AUTOMATIC, "destination_host_change"),
        method="GET",
        is_idempotent=True,
    )
    assert result.passed is False
    assert "NEVER_AUTOMATIC" in (result.rejection_reason or "")


def test_safety_rejects_secrets_in_changes():
    """Candidates with secret keys (as dict keys) in changes must be rejected."""
    validator = SafetyValidator()
    # The change dict itself contains a key named 'api_key' which is a secret
    result = validator.validate(
        candidate={"type": "parameter_rename", "changes": [{"api_key": "some-value", "rename_to": "x"}]},
        policy_decision=_make_policy(POLICY_AUTO_ELIGIBLE),
        method="GET",
        is_idempotent=True,
    )
    assert result.passed is False
    assert "secret" in (result.rejection_reason or "").lower()


def test_safety_rejects_host_change_in_changes():
    """Candidates attempting host field changes must be rejected."""
    validator = SafetyValidator(registered_host="api.legit.com")
    result = validator.validate(
        candidate={
            "type": "parameter_rename",
            "changes": [{"field": "host", "type": "replace", "value": "attacker.com"}],
        },
        policy_decision=_make_policy(POLICY_AUTO_ELIGIBLE),
        method="PUT",
        is_idempotent=True,
    )
    assert result.passed is False


def test_safety_rejects_non_idempotent_auto_eligible():
    """POST method without idempotency key must be rejected for AUTO_ELIGIBLE."""
    validator = SafetyValidator()
    result = validator.validate(
        candidate=_make_candidate("parameter_rename"),
        policy_decision=_make_policy(POLICY_AUTO_ELIGIBLE),
        method="POST",
        is_idempotent=False,
    )
    assert result.passed is False
    assert "idempotent" in (result.rejection_reason or "").lower()


def test_safety_allows_idempotent_post_with_key():
    """POST with explicit idempotency flag passes idempotency check."""
    validator = SafetyValidator()
    result = validator.validate(
        candidate=_make_candidate("parameter_rename"),
        policy_decision=_make_policy(POLICY_AUTO_ELIGIBLE),
        method="POST",
        is_idempotent=True,
    )
    assert result.passed is True


def test_safety_allows_get_auto_eligible():
    """GET parameter rename passes all checks for AUTO_ELIGIBLE."""
    validator = SafetyValidator()
    result = validator.validate(
        candidate=_make_candidate("parameter_rename", [{"field": "userId", "rename_to": "user_id"}]),
        policy_decision=_make_policy(POLICY_AUTO_ELIGIBLE),
        method="GET",
        is_idempotent=True,
    )
    assert result.passed is True


def test_safety_rejects_retry_budget_exhausted():
    """No execution allowed when max upstream attempts reached."""
    validator = SafetyValidator()
    result = validator.validate(
        candidate=_make_candidate("retry_after"),
        policy_decision=_make_policy(POLICY_AUTO_ELIGIBLE, "retry_after"),
        method="GET",
        is_idempotent=True,
        upstream_attempt_count=2,
        max_attempts=2,
    )
    assert result.passed is False
    assert "Maximum" in (result.rejection_reason or "")


def test_safety_url_host_validation_mismatch():
    """Candidate URL with wrong host is rejected."""
    validator = SafetyValidator(registered_host="api.legit.com")
    result = validator.validate(
        candidate=_make_candidate(),
        policy_decision=_make_policy(POLICY_APPROVAL_REQUIRED),
        method="GET",
        url="https://attacker.evil.com/steal",
        is_idempotent=True,
    )
    assert result.passed is False


# ── FEAT-018: Confidence Gate ─────────────────────────────────────────────────

def test_confidence_gate_sufficient():
    """High similarity + historical success → sufficient."""
    from dataclasses import dataclass

    @dataclass
    class FakeCand:
        confidence: float = 0.80

    result = evaluate_confidence(
        [FakeCand(), FakeCand()],
        graph_similarity=0.9,
        historical_success_rate=0.85,
        schema_compatibility=0.8,
        failure_match=0.9,
        provenance_quality=0.8,
    )
    assert result.sufficient is True
    assert result.score > 0.5


def test_confidence_gate_insufficient_low_evidence():
    """Single evidence item → not sufficient regardless of score."""
    from dataclasses import dataclass

    @dataclass
    class FakeCand:
        confidence: float = 0.80

    result = evaluate_confidence(
        [FakeCand()],  # only 1, min is 2
        graph_similarity=0.9,
        historical_success_rate=0.9,
        failure_match=1.0,
    )
    assert result.sufficient is False
    assert result.reason is not None  # some reason is provided


def test_confidence_gate_insufficient_low_score():
    """Zero evidence and zero scores → not sufficient."""
    result = evaluate_confidence([], graph_similarity=0.0)
    assert result.sufficient is False


# ── FEAT-019: Candidate Ranking ───────────────────────────────────────────────

def test_ranking_orders_by_score():
    from dataclasses import dataclass

    @dataclass
    class FakeCand:
        action_type: str
        confidence: float
        source: str = PROVENANCE_DETERMINISTIC
        id: uuid.UUID = None

        def __post_init__(self):
            if self.id is None:
                self.id = uuid.uuid4()

    cands = [
        FakeCand("parameter_rename", 0.9),
        FakeCand("retry_after", 0.3),
        FakeCand("schema_field_mapping", 0.7),
    ]
    ranked = rank_candidates(cands, failure_match=0.8, historical_success_rate=0.7)
    assert len(ranked) == 3
    # First should have highest rank_score
    assert ranked[0].rank_score >= ranked[1].rank_score >= ranked[2].rank_score
    assert ranked[0].rank == 1


def test_ranking_llm_gets_reliability_adjustment():
    from dataclasses import dataclass

    @dataclass
    class FakeCand:
        action_type: str
        confidence: float
        source: str
        id: uuid.UUID = None

        def __post_init__(self):
            if self.id is None:
                self.id = uuid.uuid4()

    det_cand = FakeCand("parameter_rename", 0.9, PROVENANCE_DETERMINISTIC)
    llm_cand = FakeCand("parameter_rename", 0.9, PROVENANCE_LLM)

    ranked = rank_candidates(
        [det_cand, llm_cand],
        failure_match=0.8,
        historical_success_rate=0.8,
        provenance_quality=1.0,
    )
    det_ranked = next(r for r in ranked if r.candidate.source == PROVENANCE_DETERMINISTIC)
    llm_ranked = next(r for r in ranked if r.candidate.source == PROVENANCE_LLM)
    # Deterministic should rank higher due to reliability multiplier
    assert det_ranked.rank_score >= llm_ranked.rank_score


# ── FEAT-033/034/035: Recovery Memory ────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_maturity_proposed_to_validated(db_session):
    from app.memory.service import RecoveryMemoryService, _VALIDATED_SUCCESS_THRESHOLD
    from app.context.builder import FailureContext

    svc = RecoveryMemoryService(db_session)
    context = FailureContext(
        correlation_id=uuid.uuid4(),
        api_id=uuid.uuid4(),
        endpoint_path="/test",
        method="GET",
        version=None,
        failure_class="UNKNOWN_PARAMETER",
        failure_signature=f"sig-{uuid.uuid4().hex[:8]}",
        http_status=422,
        schema_signature="test-schema-sig",
        error_summary={},
        is_recoverable=True,
        classifier_confidence=0.9,
        context_signature=f"ctx-{uuid.uuid4().hex[:8]}",
    )

    case = await svc.create_from_llm_success(
        context=context,
        action_type="parameter_rename",
        changes=[],
        model_provider="mock",
        model_version="mock-v1",
        confidence=0.7,
    )
    assert case.maturity == MATURITY_PROPOSED
    assert case.success_count == 1

    # Record success to reach threshold
    for _ in range(_VALIDATED_SUCCESS_THRESHOLD - 1):
        case = await svc.record_outcome(case.id, success=True)

    assert case.maturity == MATURITY_VALIDATED
    assert case.success_count == _VALIDATED_SUCCESS_THRESHOLD


@pytest.mark.asyncio
async def test_memory_deterministic_starts_validated(db_session):
    from app.memory.service import RecoveryMemoryService
    from app.context.builder import FailureContext

    svc = RecoveryMemoryService(db_session)
    context = FailureContext(
        correlation_id=uuid.uuid4(),
        api_id=uuid.uuid4(),
        endpoint_path="/orders",
        method="POST",
        version=None,
        failure_class="RATE_LIMIT",
        failure_signature=f"det-sig-{uuid.uuid4().hex[:8]}",
        http_status=429,
        schema_signature="schema-1",
        error_summary={},
        is_recoverable=True,
        classifier_confidence=1.0,
        context_signature=f"det-ctx-{uuid.uuid4().hex[:8]}",
    )

    case = await svc.create_from_deterministic(
        context=context,
        action_type="retry_after",
        changes=[],
        confidence=0.8,
    )
    assert case.maturity == MATURITY_VALIDATED


@pytest.mark.asyncio
async def test_memory_established_promotion(db_session):
    from app.memory.service import RecoveryMemoryService, _ESTABLISHED_SUCCESS_THRESHOLD
    from app.context.builder import FailureContext

    svc = RecoveryMemoryService(db_session)
    context = FailureContext(
        correlation_id=uuid.uuid4(),
        api_id=uuid.uuid4(),
        endpoint_path="/data",
        method="GET",
        version=None,
        failure_class="UNKNOWN_PARAMETER",
        failure_signature=f"est-sig-{uuid.uuid4().hex[:8]}",
        http_status=422,
        schema_signature="schema-2",
        error_summary={},
        is_recoverable=True,
        classifier_confidence=0.9,
        context_signature=f"est-ctx-{uuid.uuid4().hex[:8]}",
    )

    case = await svc.create_from_deterministic(
        context=context,
        action_type="parameter_rename",
        changes=[],
        confidence=0.9,
    )

    for _ in range(_ESTABLISHED_SUCCESS_THRESHOLD):
        case = await svc.record_outcome(case.id, success=True)

    assert case.maturity == MATURITY_ESTABLISHED
