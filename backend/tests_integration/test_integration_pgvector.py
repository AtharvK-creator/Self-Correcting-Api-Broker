"""
Integration tests — run against real PostgreSQL + pgvector.

These tests require a live DB and are excluded from the unit test run.
They are executed by docker-compose.test.yml via the backend_test service.

Marker: @pytest.mark.integration
Run with: pytest tests_integration/ -m integration -v
"""
import os
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Skip all integration tests if DB not available
DATABASE_URL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.integration

if not DATABASE_URL or "sqlite" in DATABASE_URL:
    pytest.skip("Integration tests require a real PostgreSQL DATABASE_URL", allow_module_level=True)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="function")
async def engine():
    eng = create_async_engine(DATABASE_URL, echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(engine):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


# ── pgvector extension test ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pgvector_extension_installed(db):
    """pgvector extension must be available."""
    result = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    row = result.fetchone()
    assert row is not None, "pgvector extension is not installed"


@pytest.mark.asyncio
async def test_vector_type_operations(db):
    """pgvector cosine distance must work."""
    result = await db.execute(text(
        "SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector AS cosine_dist"
    ))
    row = result.fetchone()
    assert row is not None
    dist = float(row[0])
    # Cosine distance between orthogonal vectors = 1.0
    assert abs(dist - 1.0) < 1e-4


# ── Alembic migration test ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_tables_exist(db):
    """All ORM tables must exist after alembic upgrade head."""
    expected_tables = [
        "users", "apis", "api_endpoints", "api_versions", "api_parameters",
        "request_events", "failure_events",
        "graph_nodes", "graph_edges", "embedding_records",
        "recovery_cases", "correction_candidates", "recovery_attempts",
        "policies", "approval_requests", "audit_events", "model_runs", "evaluation_runs",
    ]
    result = await db.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
    """))
    existing = {row[0] for row in result.fetchall()}

    missing = set(expected_tables) - existing
    assert not missing, f"Missing tables after migration: {missing}"


@pytest.mark.asyncio
async def test_embedding_records_vector_column(db):
    """embedding_records.embedding must be of type vector(128)."""
    result = await db.execute(text("""
        SELECT data_type, udt_name
        FROM information_schema.columns
        WHERE table_name = 'embedding_records' AND column_name = 'embedding'
    """))
    row = result.fetchone()
    assert row is not None, "embedding column not found in embedding_records"
    # pgvector columns appear as USER-DEFINED or vector type
    assert row[1] == "vector" or row[0] == "USER-DEFINED"


# ── Node2Vec + pgvector pipeline test ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_graph_node_insert_and_embedding(db):
    """Insert a graph node and verify embedding pipeline stores a vector."""
    from app.models.graph import GraphNode
    from app.embeddings.pipeline import EmbeddingPipeline, EMBEDDING_DIM

    # Insert test nodes
    node_ids = []
    for i in range(5):
        node = GraphNode(
            node_type="REQUEST_CONTEXT",
            external_id=f"integration-test-node-{i}-{uuid.uuid4().hex[:6]}",
            label=f"test-node-{i}",
            attributes={"test": True},
        )
        db.add(node)
        await db.flush()
        node_ids.append(node.id)

    # Insert edges between nodes
    from app.models.graph import GraphEdge
    for i in range(len(node_ids) - 1):
        edge = GraphEdge(
            source_node_id=node_ids[i],
            target_node_id=node_ids[i + 1],
            edge_type="PRODUCES_ERROR",
            weight=1.0,
        )
        db.add(edge)
    await db.flush()

    # Run embedding pipeline
    pipeline = EmbeddingPipeline(db)
    stats = await pipeline.run_full_pipeline()
    assert stats["nodes_loaded"] >= 5
    assert stats["embeddings_stored"] >= 5

    # Verify vector dimension
    result = await db.execute(text(
        f"SELECT vector_dims(CAST(embedding AS vector)) FROM embedding_records "
        f"WHERE graph_node_id = '{node_ids[0]}'"
    ))
    row = result.fetchone()
    assert row is not None
    assert int(row[0]) == EMBEDDING_DIM

    await db.rollback()  # Clean up test data


@pytest.mark.asyncio
async def test_vector_similarity_search(db):
    """pgvector similarity search must return results after embeddings are stored."""
    from app.embeddings.search import SimilaritySearchService
    from app.embeddings.pipeline import EMBEDDING_DIM
    import numpy as np

    # Insert a test embedding directly
    test_node_id = uuid.uuid4()
    test_vector = np.random.default_rng(42).standard_normal(EMBEDDING_DIM).tolist()
    vector_str = f"[{','.join(str(float(v)) for v in test_vector)}]"

    await db.execute(text(f"""
        INSERT INTO graph_nodes (id, node_type, external_id, label, attributes)
        VALUES ('{test_node_id}', 'REQUEST_CONTEXT', 'search-test-{uuid.uuid4().hex[:6]}',
                'search-test', '{{}}')
        ON CONFLICT DO NOTHING
    """))
    await db.execute(text(f"""
        INSERT INTO embedding_records (id, graph_node_id, model_name, model_version, dimension, embedding)
        VALUES ('{uuid.uuid4()}', '{test_node_id}', 'node2vec', 'v1.0', {EMBEDDING_DIM},
                '{vector_str}')
        ON CONFLICT (graph_node_id, model_name, model_version) DO NOTHING
    """))
    await db.flush()

    svc = SimilaritySearchService(db)
    results = await svc.search_by_vector(
        test_vector,
        node_type="REQUEST_CONTEXT",
        limit=5,
        min_similarity=0.0,  # accept any match
    )
    assert len(results) >= 1
    # Self-similarity should be ~1.0
    self_match = next((r for r in results if r.node_id == test_node_id), None)
    if self_match:
        assert self_match.cosine_similarity >= 0.99

    await db.rollback()
