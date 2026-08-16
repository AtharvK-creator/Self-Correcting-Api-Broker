"""
SQLAlchemy ORM models — recovery pipeline.

Covers: recovery_cases, correction_candidates, recovery_attempts,
        policies, approval_requests, audit_events.

Uses sa.JSON (not JSONB) for cross-dialect compatibility;
the migration uses JSONB for PostgreSQL specifically.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Knowledge maturity states (TAD §15, PRD §14)
MATURITY_PROPOSED = "PROPOSED"
MATURITY_VALIDATED = "VALIDATED"
MATURITY_ESTABLISHED = "ESTABLISHED"
MATURITY_DEPRECATED = "DEPRECATED"

# Policy tiers (FINAL_DECISIONS #10, TAD §12)
POLICY_AUTO_ELIGIBLE = "AUTO_ELIGIBLE"
POLICY_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
POLICY_NEVER_AUTOMATIC = "NEVER_AUTOMATIC"

# Candidate provenance sources
PROVENANCE_DETERMINISTIC = "DETERMINISTIC"
PROVENANCE_LLM = "LLM"


class RecoveryCase(Base):
    """
    A recovery case links a failure situation to a correction and its outcome.
    Successful LLM cases become VALIDATED memory (TAD §15).
    Secrets are never stored here.
    """
    __tablename__ = "recovery_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("apis.id", ondelete="SET NULL"), nullable=True, index=True
    )
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_endpoints.id", ondelete="SET NULL"), nullable=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_versions.id", ondelete="SET NULL"), nullable=True
    )
    failure_signature: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    context_signature: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    graph_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("graph_nodes.id", ondelete="SET NULL"), nullable=True
    )
    # Correction stored as structured JSON — secrets stripped
    correction: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # DETERMINISTIC | LLM
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    maturity: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MATURITY_PROPOSED, server_default=MATURITY_PROPOSED, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reuse_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    candidates: Mapped[list["CorrectionCandidate"]] = relationship(
        back_populates="recovery_case", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<RecoveryCase maturity={self.maturity!r} "
            f"sig={self.failure_signature!r} src={self.source!r}>"
        )


class CorrectionCandidate(Base):
    """
    A ranked, policy-checked, safety-validated correction candidate.
    LLM candidates are treated as untrusted input until safety-validated.
    """
    __tablename__ = "correction_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recovery_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recovery_cases.id", ondelete="SET NULL"), nullable=True
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    changes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False)  # DETERMINISTIC | LLM
    source_detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    rank_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    policy_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    safety_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    safety_detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    was_executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    was_rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    recovery_case: Mapped["RecoveryCase | None"] = relationship(back_populates="candidates")

    def __repr__(self) -> str:
        return (
            f"<CorrectionCandidate action={self.action_type!r} "
            f"prov={self.provenance!r} score={self.rank_score}>"
        )


class RecoveryAttempt(Base):
    """
    Tracks the overall recovery attempt for one correlation ID.
    Enforces maximum 2 upstream executions (TAD §14).
    """
    __tablename__ = "recovery_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    original_request_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request_events.id", ondelete="SET NULL"), nullable=True
    )
    corrected_request_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request_events.id", ondelete="SET NULL"), nullable=True
    )
    # Total upstream executions consumed — must never exceed 2 in MVP
    upstream_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failure_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("failure_events.id", ondelete="SET NULL"), nullable=True
    )
    selected_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("correction_candidates.id", ondelete="SET NULL"), nullable=True
    )
    recovery_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recovery_cases.id", ondelete="SET NULL"), nullable=True
    )
    # deterministic_sufficient = True means LLM was NOT invoked
    deterministic_sufficient: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    llm_invoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)  # SUCCESS | FAILURE | TERMINAL_FAILURE
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RecoveryAttempt corr={self.correlation_id} "
            f"attempts={self.upstream_attempt_count} outcome={self.outcome!r}>"
        )


class Policy(Base):
    """Configurable policy rules for action types."""
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_type: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Policy action={self.action_type!r} tier={self.tier!r}>"


class ApprovalRequest(Base):
    """Human approval workflow for APPROVAL_REQUIRED candidates."""
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("correction_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", server_default="PENDING")
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ApprovalRequest candidate={self.candidate_id} status={self.status!r}>"


class AuditEvent(Base):
    """
    Immutable audit trail — every recovery decision is recorded here.
    SEC-004: every executed correction has an audit event.
    """
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recovery_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    policy_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    safety_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<AuditEvent type={self.event_type!r} corr={self.correlation_id}>"


class ModelRun(Base):
    """Tracks LLM provider invocations — model, version, token usage, cost."""
    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    was_successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ModelRun provider={self.provider!r} model={self.model!r}>"


class EvaluationRun(Base):
    """Stores evaluation experiment runs per EVALUATION.md."""
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    baseline: Mapped[str] = mapped_column(String(64), nullable=False)  # B0, B1, B2, B3, P1
    scenario_set: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    graph_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    ranking_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<EvaluationRun name={self.name!r} baseline={self.baseline!r}>"
