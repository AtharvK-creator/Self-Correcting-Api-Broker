"""
pgvector similarity search — FEAT-014.

Uses cosine similarity via pgvector's <=> operator.
Authoritative vector store: PostgreSQL + pgvector (FINAL_DECISIONS #13).

NFR-004: Secrets never enter embeddings or search queries.
TAD §17: similarity search feeds recovery candidate generation.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.pipeline import EMBEDDING_DIM
from app.models.graph import EmbeddingRecord, GraphNode

logger = structlog.get_logger(__name__)


class VectorSearchResult:
    def __init__(
        self,
        *,
        node_id: uuid.UUID,
        node_type: str,
        label: str,
        external_id: str,
        cosine_similarity: float,
        attributes: dict,
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.label = label
        self.external_id = external_id
        self.cosine_similarity = cosine_similarity
        self.attributes = attributes

    def __repr__(self) -> str:
        return (
            f"<VectorSearchResult node_id={self.node_id} "
            f"type={self.node_type} sim={self.cosine_similarity:.4f}>"
        )


class SimilaritySearchService:
    """
    Cosine-similarity search over node embeddings stored in pgvector.

    This class requires a real PostgreSQL connection with the pgvector
    extension installed. It will not work with SQLite.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_by_vector(
        self,
        query_vector: list[float],
        *,
        node_type: str | None = None,
        limit: int = 10,
        min_similarity: float = 0.70,
    ) -> list[VectorSearchResult]:
        """
        Find the top-k most similar nodes by cosine similarity.

        pgvector's <=> operator computes cosine distance (1 - cosine_similarity).
        We filter to similarity >= min_similarity (distance <= 1 - min_similarity).
        """
        if len(query_vector) != EMBEDDING_DIM:
            raise ValueError(
                f"Query vector dimension {len(query_vector)} != expected {EMBEDDING_DIM}"
            )

        max_distance = 1.0 - min_similarity
        vector_literal = f"[{','.join(str(float(v)) for v in query_vector)}]"

        # Build query with optional node_type filter
        if node_type:
            sql = text("""
                SELECT
                    e.graph_node_id AS node_id,
                    n.node_type,
                    n.label,
                    n.external_id,
                    n.attributes,
                    1 - (e.embedding <=> CAST(:query_vector AS vector)) AS cosine_similarity
                FROM embedding_records e
                JOIN graph_nodes n ON n.id = e.graph_node_id
                WHERE n.node_type = :node_type
                  AND (e.embedding <=> CAST(:query_vector AS vector)) <= :max_distance
                ORDER BY e.embedding <=> CAST(:query_vector AS vector)
                LIMIT :limit
            """)
            result = await self.db.execute(
                sql,
                {
                    "query_vector": vector_literal,
                    "node_type": node_type,
                    "max_distance": max_distance,
                    "limit": limit,
                },
            )
        else:
            sql = text("""
                SELECT
                    e.graph_node_id AS node_id,
                    n.node_type,
                    n.label,
                    n.external_id,
                    n.attributes,
                    1 - (e.embedding <=> CAST(:query_vector AS vector)) AS cosine_similarity
                FROM embedding_records e
                JOIN graph_nodes n ON n.id = e.graph_node_id
                WHERE (e.embedding <=> CAST(:query_vector AS vector)) <= :max_distance
                ORDER BY e.embedding <=> CAST(:query_vector AS vector)
                LIMIT :limit
            """)
            result = await self.db.execute(
                sql,
                {
                    "query_vector": vector_literal,
                    "max_distance": max_distance,
                    "limit": limit,
                },
            )

        rows = result.fetchall()
        results = []
        for row in rows:
            results.append(VectorSearchResult(
                node_id=row.node_id,
                node_type=row.node_type,
                label=row.label,
                external_id=row.external_id,
                cosine_similarity=float(row.cosine_similarity),
                attributes=row.attributes or {},
            ))

        logger.debug(
            "vector_search_complete",
            results=len(results),
            node_type=node_type,
            min_similarity=min_similarity,
        )
        return results

    async def search_by_node_id(
        self,
        node_id: uuid.UUID,
        *,
        node_type: str | None = None,
        limit: int = 10,
        min_similarity: float = 0.70,
    ) -> list[VectorSearchResult]:
        """
        Find nodes similar to a given node by looking up its embedding first.

        Returns similar nodes excluding the query node itself.
        """
        record = await self.db.execute(
            text("SELECT embedding FROM embedding_records WHERE graph_node_id = :node_id"),
            {"node_id": node_id},
        )
        row = record.fetchone()
        if not row:
            logger.warning("vector_search_no_embedding", node_id=str(node_id))
            return []

        raw_vector = row[0]
        # pgvector returns vector as string like '[0.1,0.2,...]' or as list
        if isinstance(raw_vector, str):
            query_vector = [float(x) for x in raw_vector.strip("[]").split(",")]
        else:
            query_vector = list(raw_vector)

        results = await self.search_by_vector(
            query_vector,
            node_type=node_type,
            limit=limit + 1,  # +1 to exclude self
            min_similarity=min_similarity,
        )
        # Exclude the query node itself
        return [r for r in results if r.node_id != node_id][:limit]

    async def find_similar_contexts(
        self,
        context_node_id: uuid.UUID,
        *,
        limit: int = 5,
        min_similarity: float = 0.75,
    ) -> list[VectorSearchResult]:
        """
        Find similar REQUEST_CONTEXT nodes.

        Primary retrieval path for the recovery pipeline after embeddings
        have been computed by the Node2Vec pipeline.
        """
        return await self.search_by_node_id(
            context_node_id,
            node_type="REQUEST_CONTEXT",
            limit=limit,
            min_similarity=min_similarity,
        )

    async def ensure_ivfflat_index(self) -> None:
        """
        Create IVFFlat index on the embedding_records table if it doesn't exist.

        This is idempotent. Should be called once after sufficient data is loaded.
        pgvector recommends IVFFlat with lists = rows/1000, at least 10.
        """
        await self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_embedding_records_vector_cosine
            ON embedding_records
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        await self.db.flush()
        logger.info("ivfflat_index_ensured")
