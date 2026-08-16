"""
SQLAlchemy ORM models — contextual graph nodes and edges.

Corresponds to FEAT-007 (graph node model) and FEAT-008 (graph edge model).
Node types follow TAD §4.

Uses sa.JSON (not JSONB) for cross-dialect compatibility;
the migration uses JSONB for PostgreSQL specifically.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# ──────────────────────────────────────────────────────────────────────────────
# Valid node types (TAD §4)
# ──────────────────────────────────────────────────────────────────────────────
NODE_TYPES = {
    "API",
    "SERVICE",
    "ENDPOINT",
    "VERSION",
    "PARAMETER",
    "SCHEMA_FIELD",
    "ERROR_TYPE",
    "ERROR_SIGNATURE",
    "REQUEST_CONTEXT",
    "RECOVERY_CASE",
    "CORRECTION",
    "OUTCOME",
    "MODEL_RUN",
}

# Valid edge types (TAD §4)
EDGE_TYPES = {
    "HAS_ENDPOINT",
    "HAS_VERSION",
    "HAS_PARAMETER",
    "HAS_SCHEMA_FIELD",
    "PRODUCES_ERROR",
    "SIMILAR_CONTEXT",
    "PROPOSED_CORRECTION",
    "CORRECTED_BY",
    "SUCCEEDED_WITH",
    "FAILED_WITH",
    "DISCOVERED_BY",
    "VALIDATED_BY",
    "DEPENDS_ON",
}


class GraphNode(Base):
    __tablename__ = "graph_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Stable external identity (e.g., api_id, endpoint_id, failure_signature)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    # Structured attributes — secrets must never be stored here
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    outgoing_edges: Mapped[list["GraphEdge"]] = relationship(
        "GraphEdge",
        foreign_keys="GraphEdge.source_node_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[list["GraphEdge"]] = relationship(
        "GraphEdge",
        foreign_keys="GraphEdge.target_node_id",
        back_populates="target_node",
    )
    embedding_records: Mapped[list["EmbeddingRecord"]] = relationship(
        "EmbeddingRecord", back_populates="graph_node", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("node_type", "external_id", name="uq_graph_node_type_external_id"),
    )

    def __repr__(self) -> str:
        return f"<GraphNode type={self.node_type!r} label={self.label!r}>"


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source_node: Mapped["GraphNode"] = relationship(
        "GraphNode", foreign_keys=[source_node_id], back_populates="outgoing_edges"
    )
    target_node: Mapped["GraphNode"] = relationship(
        "GraphNode", foreign_keys=[target_node_id], back_populates="incoming_edges"
    )

    __table_args__ = (
        UniqueConstraint(
            "source_node_id", "target_node_id", "edge_type", name="uq_graph_edge_src_tgt_type"
        ),
    )

    def __repr__(self) -> str:
        return f"<GraphEdge {self.edge_type!r} {self.source_node_id}→{self.target_node_id}>"


class EmbeddingRecord(Base):
    """
    Stores vector embeddings for graph nodes / recovery cases.
    Uses pgvector — do not store secrets in the vector or metadata.
    The actual 'embedding' column (pgvector type) is added via Alembic migration.
    """
    __tablename__ = "embedding_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    graph_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. node2vec, graphsage
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    graph_node: Mapped["GraphNode"] = relationship(back_populates="embedding_records")

    __table_args__ = (
        UniqueConstraint(
            "graph_node_id", "model_name", "model_version", name="uq_embedding_node_model"
        ),
    )

    def __repr__(self) -> str:
        return f"<EmbeddingRecord node={self.graph_node_id} model={self.model_name!r}>"
