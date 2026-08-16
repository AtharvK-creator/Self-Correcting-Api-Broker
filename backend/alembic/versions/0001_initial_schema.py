"""Initial schema — all MVP tables + pgvector extension.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension (requires pgvector to be installed on the DB server)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="DEVELOPER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    # ── apis ─────────────────────────────────────────────────────────────────
    op.create_table(
        "apis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("registered_host", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_apis_name", "apis", ["name"])
    op.create_index("ix_apis_registered_host", "apis", ["registered_host"])

    # ── api_endpoints ────────────────────────────────────────────────────────
    op.create_table(
        "api_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("api_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("apis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_idempotent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_api_endpoints_api_id", "api_endpoints", ["api_id"])

    # ── api_versions ─────────────────────────────────────────────────────────
    op.create_table(
        "api_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_string", sa.String(64), nullable=False),
        sa.Column("schema_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_api_versions_endpoint_id", "api_versions", ["endpoint_id"])

    # ── api_parameters ───────────────────────────────────────────────────────
    op.create_table(
        "api_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("location", sa.String(32), nullable=False),
        sa.Column("data_type", sa.String(64), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("known_aliases", postgresql.JSONB(), nullable=True, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("version_introduced", sa.String(64), nullable=True),
        sa.Column("version_deprecated", sa.String(64), nullable=True),
    )
    op.create_index("ix_api_parameters_endpoint_id", "api_parameters", ["endpoint_id"])

    # ── request_events ───────────────────────────────────────────────────────
    op.create_table(
        "request_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("apis.id", ondelete="SET NULL"), nullable=True),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_endpoints.id", ondelete="SET NULL"), nullable=True),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("request_context", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_summary", postgresql.JSONB(), nullable=True),
        sa.Column("upstream_latency_ms", sa.Float(), nullable=True),
        sa.Column("is_success", sa.Boolean(), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_request_events_correlation_id", "request_events", ["correlation_id"])
    op.create_index("ix_request_events_api_id", "request_events", ["api_id"])
    op.create_index("ix_request_events_created_at", "request_events", ["created_at"])

    # ── failure_events ───────────────────────────────────────────────────────
    op.create_table(
        "failure_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("request_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("request_events.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("failure_class", sa.String(64), nullable=False),
        sa.Column("failure_signature", sa.String(128), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("classifier_confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_recoverable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_failure_events_request_event_id", "failure_events", ["request_event_id"])
    op.create_index("ix_failure_events_correlation_id", "failure_events", ["correlation_id"])
    op.create_index("ix_failure_events_failure_class", "failure_events", ["failure_class"])
    op.create_index("ix_failure_events_failure_signature", "failure_events", ["failure_signature"])

    # ── graph_nodes ──────────────────────────────────────────────────────────
    op.create_table(
        "graph_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("node_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("node_type", "external_id", name="uq_graph_node_type_external_id"),
    )
    op.create_index("ix_graph_nodes_node_type", "graph_nodes", ["node_type"])
    op.create_index("ix_graph_nodes_external_id", "graph_nodes", ["external_id"])

    # ── graph_edges ──────────────────────────────────────────────────────────
    op.create_table(
        "graph_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edge_type", sa.String(32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source_node_id", "target_node_id", "edge_type", name="uq_graph_edge_src_tgt_type"),
    )
    op.create_index("ix_graph_edges_source_node_id", "graph_edges", ["source_node_id"])
    op.create_index("ix_graph_edges_target_node_id", "graph_edges", ["target_node_id"])
    op.create_index("ix_graph_edges_edge_type", "graph_edges", ["edge_type"])

    # ── embedding_records (with pgvector column) ──────────────────────────────
    op.create_table(
        "embedding_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("graph_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("graph_node_id", "model_name", "model_version", name="uq_embedding_node_model"),
    )
    op.create_index("ix_embedding_records_graph_node_id", "embedding_records", ["graph_node_id"])
    # Add the actual pgvector column using raw SQL (pgvector type not in SA natively)
    op.execute("ALTER TABLE embedding_records ADD COLUMN embedding vector(128)")
    op.execute("CREATE INDEX ON embedding_records USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)")

    # ── recovery_cases ───────────────────────────────────────────────────────
    op.create_table(
        "recovery_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("api_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("apis.id", ondelete="SET NULL"), nullable=True),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_endpoints.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("failure_signature", sa.String(128), nullable=False),
        sa.Column("context_signature", sa.String(128), nullable=False),
        sa.Column("graph_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("correction", postgresql.JSONB(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("model_provider", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("maturity", sa.String(32), nullable=False, server_default="PROPOSED"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reuse_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_recovery_cases_failure_signature", "recovery_cases", ["failure_signature"])
    op.create_index("ix_recovery_cases_context_signature", "recovery_cases", ["context_signature"])
    op.create_index("ix_recovery_cases_maturity", "recovery_cases", ["maturity"])
    op.create_index("ix_recovery_cases_api_id", "recovery_cases", ["api_id"])

    # ── correction_candidates ────────────────────────────────────────────────
    op.create_table(
        "correction_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recovery_cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("provenance", sa.String(32), nullable=False),
        sa.Column("source_detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("rank_score", sa.Float(), nullable=True),
        sa.Column("policy_tier", sa.String(32), nullable=True),
        sa.Column("safety_passed", sa.Boolean(), nullable=True),
        sa.Column("safety_detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("was_executed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("was_rejected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_correction_candidates_correlation_id", "correction_candidates", ["correlation_id"])

    # ── recovery_attempts ────────────────────────────────────────────────────
    op.create_table(
        "recovery_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("original_request_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("request_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("corrected_request_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("request_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("upstream_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("failure_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("selected_candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("correction_candidates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recovery_cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deterministic_sufficient", sa.Boolean(), nullable=True),
        sa.Column("llm_invoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recovery_attempts_correlation_id", "recovery_attempts", ["correlation_id"])

    # ── policies ─────────────────────────────────────────────────────────────
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("action_type", sa.String(64), nullable=False, unique=True),
        sa.Column("tier", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_policies_action_type", "policies", ["action_type"])

    # ── approval_requests ────────────────────────────────────────────────────
    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("correction_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approval_requests_candidate_id", "approval_requests", ["candidate_id"])
    op.create_index("ix_approval_requests_correlation_id", "approval_requests", ["correlation_id"])

    # ── audit_events ─────────────────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("policy_decision", sa.String(32), nullable=True),
        sa.Column("safety_decision", sa.String(32), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    # ── model_runs ───────────────────────────────────────────────────────────
    op.create_table(
        "model_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("was_successful", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_model_runs_correlation_id", "model_runs", ["correlation_id"])

    # ── evaluation_runs ──────────────────────────────────────────────────────
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("baseline", sa.String(64), nullable=False),
        sa.Column("scenario_set", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("graph_version", sa.String(64), nullable=True),
        sa.Column("confidence_threshold", sa.Float(), nullable=True),
        sa.Column("ranking_weights", postgresql.JSONB(), nullable=True),
        sa.Column("results", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Seed default policies (locked NEVER_AUTOMATIC actions) ───────────────
    op.execute("""
    INSERT INTO policies (id, action_type, tier, description) VALUES
      (uuid_generate_v4(), 'destination_host_change', 'NEVER_AUTOMATIC', 'Changing the destination host is never automatic'),
      (uuid_generate_v4(), 'disable_tls_verification', 'NEVER_AUTOMATIC', 'Disabling TLS verification is never automatic'),
      (uuid_generate_v4(), 'credential_disclosure', 'NEVER_AUTOMATIC', 'Credential disclosure is never automatic'),
      (uuid_generate_v4(), 'authorization_scope_expansion', 'NEVER_AUTOMATIC', 'Authorization scope expansion is never automatic'),
      (uuid_generate_v4(), 'arbitrary_code_execution', 'NEVER_AUTOMATIC', 'Arbitrary code execution is never automatic'),
      (uuid_generate_v4(), 'unregistered_endpoint_redirect', 'NEVER_AUTOMATIC', 'Redirecting to unregistered endpoint is never automatic'),
      (uuid_generate_v4(), 'parameter_rename', 'AUTO_ELIGIBLE', 'Known parameter rename is auto-eligible'),
      (uuid_generate_v4(), 'remove_optional_field', 'AUTO_ELIGIBLE', 'Removing optional unsupported field is auto-eligible'),
      (uuid_generate_v4(), 'retry_after', 'AUTO_ELIGIBLE', 'Provider-approved retry-after is auto-eligible'),
      (uuid_generate_v4(), 'schema_field_mapping', 'AUTO_ELIGIBLE', 'Known schema-compatible field mapping is auto-eligible'),
      (uuid_generate_v4(), 'credential_refresh', 'APPROVAL_REQUIRED', 'Credential refresh requires approval'),
      (uuid_generate_v4(), 'endpoint_migration', 'APPROVAL_REQUIRED', 'Endpoint migration requires approval'),
      (uuid_generate_v4(), 'payload_transformation', 'APPROVAL_REQUIRED', 'Non-trivial payload transformation requires approval')
    ON CONFLICT (action_type) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("evaluation_runs")
    op.drop_table("model_runs")
    op.drop_table("audit_events")
    op.drop_table("approval_requests")
    op.drop_table("policies")
    op.drop_table("recovery_attempts")
    op.drop_table("correction_candidates")
    op.drop_table("recovery_cases")
    op.drop_table("embedding_records")
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")
    op.drop_table("failure_events")
    op.drop_table("request_events")
    op.drop_table("api_parameters")
    op.drop_table("api_versions")
    op.drop_table("api_endpoints")
    op.drop_table("apis")
    op.drop_table("users")
