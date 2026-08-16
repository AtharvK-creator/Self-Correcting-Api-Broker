"""
Graph construction and neighborhood retrieval — FEAT-010, FEAT-011.

Builds/updates contextual graph nodes and edges in PostgreSQL.
Uses NetworkX for in-process graph analysis (TAD §18).
NetworkX is analytical only — PostgreSQL is the authoritative store.

FR-006: Build/update contextual graph.
FR-008: Retrieve similar contextual cases.
FINAL_DECISIONS #12: NetworkX is analytical/in-process only.
"""

from __future__ import annotations

import uuid
from typing import Any

import networkx as nx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.builder import FailureContext
from app.models.graph import EDGE_TYPES, NODE_TYPES, GraphEdge, GraphNode

logger = structlog.get_logger(__name__)


class GraphService:
    """
    Manages contextual graph nodes and edges in PostgreSQL.

    Build order for a new failure event:
    1. Ensure API node exists
    2. Ensure ENDPOINT node exists, linked to API
    3. Ensure ERROR_TYPE node exists
    4. Ensure ERROR_SIGNATURE node exists, linked to ERROR_TYPE
    5. Ensure REQUEST_CONTEXT node exists, linked to ENDPOINT
    6. Link REQUEST_CONTEXT → ERROR_SIGNATURE (PRODUCES_ERROR)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Node upsert ───────────────────────────────────────────────────────────

    async def _get_or_create_node(
        self,
        *,
        node_type: str,
        external_id: str,
        label: str,
        attributes: dict[str, Any] | None = None,
    ) -> GraphNode:
        """Retrieve existing node or create it. Uses external_id as stable key."""
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unknown node type: {node_type!r}")

        result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.node_type == node_type,
                GraphNode.external_id == external_id,
            )
        )
        node = result.scalar_one_or_none()

        if node is None:
            node = GraphNode(
                node_type=node_type,
                external_id=external_id,
                label=label,
                attributes=attributes or {},
            )
            self.db.add(node)
            await self.db.flush()
            logger.debug(
                "graph_node_created",
                node_type=node_type,
                external_id=external_id,
                node_id=str(node.id),
            )

        return node

    async def _get_or_create_edge(
        self,
        *,
        source_node_id: uuid.UUID,
        target_node_id: uuid.UUID,
        edge_type: str,
        weight: float = 1.0,
        attributes: dict[str, Any] | None = None,
    ) -> GraphEdge:
        """Retrieve existing edge or create it."""
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unknown edge type: {edge_type!r}")

        result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.source_node_id == source_node_id,
                GraphEdge.target_node_id == target_node_id,
                GraphEdge.edge_type == edge_type,
            )
        )
        edge = result.scalar_one_or_none()

        if edge is None:
            edge = GraphEdge(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                edge_type=edge_type,
                weight=weight,
                attributes=attributes or {},
            )
            self.db.add(edge)
            await self.db.flush()

        return edge

    # ── Graph construction ────────────────────────────────────────────────────

    async def build_failure_context_graph(
        self,
        context: FailureContext,
    ) -> dict[str, uuid.UUID]:
        """
        Build or update graph nodes and edges for a failure context.

        Returns a mapping of node role → node_id for use in recovery pipeline.
        No secrets flow through this function.
        """
        # API node
        api_node = await self._get_or_create_node(
            node_type="API",
            external_id=str(context.api_id),
            label=f"api:{context.api_id}",
            attributes={"api_id": str(context.api_id)},
        )

        # ENDPOINT node
        endpoint_external_id = f"{context.api_id}::{context.endpoint_path}::{context.method}"
        endpoint_node = await self._get_or_create_node(
            node_type="ENDPOINT",
            external_id=endpoint_external_id,
            label=f"{context.method} {context.endpoint_path}",
            attributes={
                "path": context.endpoint_path,
                "method": context.method,
                "version": context.version,
            },
        )

        # API → ENDPOINT edge
        await self._get_or_create_edge(
            source_node_id=api_node.id,
            target_node_id=endpoint_node.id,
            edge_type="HAS_ENDPOINT",
        )

        # ERROR_TYPE node
        error_type_node = await self._get_or_create_node(
            node_type="ERROR_TYPE",
            external_id=context.failure_class,
            label=context.failure_class,
            attributes={"failure_class": context.failure_class},
        )

        # ERROR_SIGNATURE node
        error_sig_node = await self._get_or_create_node(
            node_type="ERROR_SIGNATURE",
            external_id=context.failure_signature,
            label=f"sig:{context.failure_signature[:12]}",
            attributes={
                "failure_signature": context.failure_signature,
                "http_status": context.http_status,
                # error_summary already sanitized by context builder
                "error_summary": context.error_summary,
            },
        )

        # ERROR_SIGNATURE → ERROR_TYPE edge
        await self._get_or_create_edge(
            source_node_id=error_sig_node.id,
            target_node_id=error_type_node.id,
            edge_type="HAS_SCHEMA_FIELD",  # using closest available edge type
        )

        # REQUEST_CONTEXT node
        ctx_node = await self._get_or_create_node(
            node_type="REQUEST_CONTEXT",
            external_id=context.context_signature,
            label=f"ctx:{context.context_signature[:12]}",
            attributes={
                "context_signature": context.context_signature,
                "schema_signature": context.schema_signature,
                "failure_class": context.failure_class,
                "is_recoverable": context.is_recoverable,
                "classifier_confidence": context.classifier_confidence,
            },
        )

        # ENDPOINT → REQUEST_CONTEXT edge
        await self._get_or_create_edge(
            source_node_id=endpoint_node.id,
            target_node_id=ctx_node.id,
            edge_type="PRODUCES_ERROR",
        )

        # REQUEST_CONTEXT → ERROR_SIGNATURE edge
        await self._get_or_create_edge(
            source_node_id=ctx_node.id,
            target_node_id=error_sig_node.id,
            edge_type="PRODUCES_ERROR",
        )

        logger.info(
            "graph_context_built",
            correlation_id=str(context.correlation_id),
            context_signature=context.context_signature,
            failure_class=context.failure_class,
        )

        return {
            "api_node_id": api_node.id,
            "endpoint_node_id": endpoint_node.id,
            "error_type_node_id": error_type_node.id,
            "error_sig_node_id": error_sig_node.id,
            "context_node_id": ctx_node.id,
        }

    # ── Neighborhood retrieval ────────────────────────────────────────────────

    async def get_neighborhood(
        self,
        *,
        context_node_id: uuid.UUID,
        max_depth: int = 2,
        max_nodes: int = 50,
    ) -> nx.DiGraph:
        """
        Retrieve the graph neighborhood around a context node (FEAT-011).

        Returns a NetworkX DiGraph for in-process analysis.
        NetworkX is analytical only — results are not persisted to NX.
        """
        visited: set[uuid.UUID] = set()
        queue: list[tuple[uuid.UUID, int]] = [(context_node_id, 0)]
        G = nx.DiGraph()

        while queue:
            node_id, depth = queue.pop(0)
            if node_id in visited or depth > max_depth:
                continue
            visited.add(node_id)

            node = await self.db.get(GraphNode, node_id)
            if not node:
                continue

            G.add_node(
                str(node.id),
                node_type=node.node_type,
                label=node.label,
                external_id=node.external_id,
            )

            if len(visited) >= max_nodes:
                break

            # Outgoing edges
            out_result = await self.db.execute(
                select(GraphEdge).where(GraphEdge.source_node_id == node_id)
            )
            for edge in out_result.scalars().all():
                G.add_edge(
                    str(node.id),
                    str(edge.target_node_id),
                    edge_type=edge.edge_type,
                    weight=edge.weight,
                )
                if edge.target_node_id not in visited:
                    queue.append((edge.target_node_id, depth + 1))

        logger.debug(
            "graph_neighborhood_retrieved",
            context_node_id=str(context_node_id),
            nodes=G.number_of_nodes(),
            edges=G.number_of_edges(),
        )
        return G

    async def get_similar_contexts(
        self,
        context: FailureContext,
        limit: int = 10,
    ) -> list[GraphNode]:
        """
        Find REQUEST_CONTEXT nodes with the same failure class or signature.

        Used by the deterministic recovery engine before graph embeddings
        are available (fallback retrieval path).
        """
        # Exact signature match first
        exact_result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.node_type == "REQUEST_CONTEXT",
                GraphNode.external_id == context.context_signature,
            )
        )
        exact = exact_result.scalars().all()

        # Same failure class match
        same_class_result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.node_type == "REQUEST_CONTEXT",
                GraphNode.attributes["failure_class"].as_string() == context.failure_class,
            ).limit(limit)
        )
        same_class = same_class_result.scalars().all()

        # Combine and deduplicate
        seen: set[uuid.UUID] = set()
        results: list[GraphNode] = []
        for node in [*exact, *same_class]:
            if node.id not in seen:
                seen.add(node.id)
                results.append(node)

        return results[:limit]
