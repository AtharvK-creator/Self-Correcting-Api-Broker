"""
SQLAlchemy ORM models — request and failure events.

Covers: request_events, failure_events.
Uses sa.JSON (not JSONB) for cross-dialect compatibility;
the migration uses JSONB for PostgreSQL specifically.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RequestEvent(Base):
    """Records every upstream execution attempt (original + corrected)."""
    __tablename__ = "request_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    api_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("apis.id", ondelete="SET NULL"), nullable=True, index=True
    )
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_endpoints.id", ondelete="SET NULL"), nullable=True
    )
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # attempt_number: 1 = original, 2 = corrected.  Max 2 per correlation in MVP.
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    # Normalized request context — secrets stripped before storage
    request_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    upstream_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_success: Mapped[bool | None] = mapped_column(nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    failure_event: Mapped["FailureEvent | None"] = relationship(back_populates="request_event", uselist=False)

    def __repr__(self) -> str:
        return f"<RequestEvent {self.method} attempt={self.attempt_number} status={self.http_status}>"


class FailureEvent(Base):
    """Normalized failure event produced by the failure classifier."""
    __tablename__ = "failure_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("request_events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    failure_class: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # failure_signature is a stable hash of (api, endpoint, failure_class, key error indicators)
    failure_signature: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Classifier confidence (1.0 = deterministic rule matched, <1.0 = heuristic)
    classifier_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")
    is_recoverable: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    request_event: Mapped["RequestEvent"] = relationship(back_populates="failure_event")

    def __repr__(self) -> str:
        return f"<FailureEvent class={self.failure_class!r} sig={self.failure_signature!r}>"
