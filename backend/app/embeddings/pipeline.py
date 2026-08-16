"""
Node2Vec embedding pipeline — FEAT-012, FEAT-013.

Architecture (TAD §16, FINAL_DECISIONS #12, #13):
- NetworkX DiGraph built from PostgreSQL graph nodes/edges
- node2vec generates 128-dim embeddings
- Embeddings stored in PostgreSQL via pgvector (EmbeddingRecord table)
- This module runs INSIDE the Docker container (Python 3.11 + gcc)
  where numpy/scikit-learn build correctly.

NFR-004: Secrets never enter embeddings.
FINAL_DECISIONS #12: NetworkX is in-process/analytical only.
FINAL_DECISIONS #13: pgvector is the authoritative vector store.
"""

from __future__ import annotations

import uuid
from typing import Any

import networkx as nx
import numpy as np
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph import EmbeddingRecord, GraphEdge, GraphNode

logger = structlog.get_logger(__name__)

# Embedding dimensionality (locked: TAD §16)
EMBEDDING_DIM = 128

# node2vec hyperparameters (configurable in future via settings)
_N2V_WALK_LENGTH = 30
_N2V_NUM_WALKS = 200
_N2V_P = 1.0   # return parameter
_N2V_Q = 1.0   # in-out parameter
_N2V_WINDOW = 10
_N2V_WORKERS = 1  # deterministic single-thread

EMBEDDING_STRATEGY = "node2vec"


def _build_networkx_graph(nodes: list[GraphNode], edges: list[GraphEdge]) -> nx.DiGraph:
    """
    Build a NetworkX DiGraph from ORM node/edge lists.

    Attributes are structural metadata only — no secret values
    ever reach this layer (enforced by context builder).
    """
    G = nx.DiGraph()
    for node in nodes:
        G.add_node(
            str(node.id),
            node_type=node.node_type,
            label=node.label,
        )
    for edge in edges:
        G.add_edge(
            str(edge.source_node_id),
            str(edge.target_node_id),
            edge_type=edge.edge_type,
            weight=float(edge.weight or 1.0),
        )
    return G


def _run_node2vec(G: nx.DiGraph) -> dict[str, np.ndarray]:
    """
    Run node2vec on a NetworkX graph.

    Returns a mapping of node_id (str) → 128-dim embedding vector.
    Falls back to random embeddings if the graph is too small.
    """
    from node2vec import Node2Vec

    if G.number_of_nodes() < 2:
        logger.warning("node2vec_graph_too_small", nodes=G.number_of_nodes())
        return {
            node: np.random.default_rng(42).standard_normal(EMBEDDING_DIM).astype(np.float32)
            for node in G.nodes()
        }

    # node2vec requires an undirected graph for random walks
    G_undirected = G.to_undirected()

    n2v = Node2Vec(
        G_undirected,
        dimensions=EMBEDDING_DIM,
        walk_length=_N2V_WALK_LENGTH,
        num_walks=_N2V_NUM_WALKS,
        p=_N2V_P,
        q=_N2V_Q,
        workers=_N2V_WORKERS,
        quiet=True,
    )
    model = n2v.fit(window=_N2V_WINDOW, min_count=1, batch_words=4)

    embeddings = {}
    for node_id in G.nodes():
        if node_id in model.wv:
            vec = model.wv[node_id].astype(np.float32)
        else:
            # Node not in vocabulary (isolated) — use zero vector
            vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        embeddings[node_id] = vec

    logger.info(
        "node2vec_complete",
        nodes=G.number_of_nodes(),
        embedded=len(embeddings),
    )
    return embeddings


class EmbeddingPipeline:
    """
    Full embedding pipeline: load graph → build NX graph → node2vec → store in pgvector.

    Must be run inside Docker (Python 3.11 + numpy available).
    Safe to call incrementally: upserts embeddings rather than bulk-replacing.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_full_pipeline(self) -> dict[str, int]:
        """
        Load all nodes and edges from PostgreSQL, run node2vec, store embeddings.

        Returns stats: {"nodes_loaded", "embeddings_stored", "embeddings_updated"}
        """
        # Load nodes
        nodes_result = await self.db.execute(select(GraphNode))
        nodes: list[GraphNode] = nodes_result.scalars().all()

        # Load edges
        edges_result = await self.db.execute(select(GraphEdge))
        edges: list[GraphEdge] = edges_result.scalars().all()

        if not nodes:
            logger.info("embedding_pipeline_no_nodes")
            return {"nodes_loaded": 0, "embeddings_stored": 0, "embeddings_updated": 0}

        G = _build_networkx_graph(nodes, edges)

        logger.info(
            "embedding_pipeline_start",
            nodes=G.number_of_nodes(),
            edges=G.number_of_edges(),
        )

        embeddings = _run_node2vec(G)

        stored = updated = 0
        node_id_map = {str(n.id): n for n in nodes}

        for node_id_str, vector in embeddings.items():
            node = node_id_map.get(node_id_str)
            if not node:
                continue

            await self._upsert_embedding(
                graph_node_id=node.id,
                vector=vector,
            )
            stored += 1

        await self.db.flush()

        logger.info(
            "embedding_pipeline_complete",
            nodes_loaded=len(nodes),
            embeddings_stored=stored,
        )
        return {
            "nodes_loaded": len(nodes),
            "embeddings_stored": stored,
            "embeddings_updated": updated,
        }

    async def run_incremental(self, node_ids: list[uuid.UUID]) -> int:
        """
        Run embedding update for a specific set of nodes and their neighbors.

        Used after graph construction for a single request to update affected embeddings.
        Pulls the 2-hop neighborhood of each node and re-embeds the subgraph.
        """
        if not node_ids:
            return 0

        # Load the k-hop subgraph
        all_node_ids: set[uuid.UUID] = set(node_ids)
        for node_id in node_ids:
            hop_result = await self.db.execute(
                select(GraphEdge).where(
                    (GraphEdge.source_node_id == node_id) |
                    (GraphEdge.target_node_id == node_id)
                )
            )
            for edge in hop_result.scalars().all():
                all_node_ids.add(edge.source_node_id)
                all_node_ids.add(edge.target_node_id)

        nodes_result = await self.db.execute(
            select(GraphNode).where(GraphNode.id.in_(list(all_node_ids)))
        )
        nodes = nodes_result.scalars().all()

        edges_result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.source_node_id.in_(list(all_node_ids))
            )
        )
        edges = edges_result.scalars().all()

        if len(nodes) < 2:
            return 0

        G = _build_networkx_graph(nodes, edges)
        embeddings = _run_node2vec(G)

        count = 0
        node_id_map = {str(n.id): n for n in nodes}
        for node_id_str, vector in embeddings.items():
            node = node_id_map.get(node_id_str)
            if node and node.id in all_node_ids:
                await self._upsert_embedding(node.id, vector)
                count += 1

        await self.db.flush()
        return count

    async def _upsert_embedding(
        self,
        graph_node_id: uuid.UUID,
        vector: np.ndarray,
    ) -> None:
        """Upsert a single embedding record via raw SQL for pgvector compatibility."""
        vector_str = f"[{','.join(str(float(v)) for v in vector)}]"
        rec_id = uuid.uuid4()
        await self.db.execute(
            select(EmbeddingRecord).where(
                EmbeddingRecord.graph_node_id == graph_node_id,
                EmbeddingRecord.model_name == EMBEDDING_STRATEGY,
                EmbeddingRecord.model_version == "v1.0",
            )
        )
        # Use raw SQL to handle vector type seamlessly across dialects
        await self.db.execute(
            text("""
                INSERT INTO embedding_records (id, graph_node_id, model_name, model_version, dimension, embedding)
                VALUES (:id, :graph_node_id, :model_name, :model_version, :dimension, CAST(:embedding AS vector))
                ON CONFLICT (graph_node_id, model_name, model_version)
                DO UPDATE SET embedding = EXCLUDED.embedding
            """),
            {
                "id": rec_id,
                "graph_node_id": graph_node_id,
                "model_name": EMBEDDING_STRATEGY,
                "model_version": "v1.0",
                "dimension": EMBEDDING_DIM,
                "embedding": vector_str,
            },
        )
