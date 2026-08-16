"""
Graph inspection endpoints.

GET /api/v1/graph/nodes/{node_id}
GET /api/v1/graph/search
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.graph import GraphNode, GraphEdge

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/graph/nodes/{node_id}", summary="Get graph node by ID")
async def get_graph_node(node_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    node = await db.get(GraphNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Graph node not found")

    # Fetch edges
    out_edges_result = await db.execute(
        select(GraphEdge).where(GraphEdge.source_node_id == node_id)
    )
    out_edges = out_edges_result.scalars().all()

    return {
        "id": str(node.id),
        "node_type": node.node_type,
        "external_id": node.external_id,
        "label": node.label,
        "attributes": node.attributes,
        "outgoing_edges": [
            {
                "id": str(e.id),
                "target_node_id": str(e.target_node_id),
                "edge_type": e.edge_type,
                "weight": e.weight,
            }
            for e in out_edges
        ],
        "created_at": node.created_at.isoformat(),
    }


@router.get("/graph/search", summary="Search graph nodes")
async def search_graph_nodes(
    node_type: str | None = Query(None),
    external_id: str | None = Query(None),
    label: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    q = select(GraphNode).limit(limit)
    if node_type:
        q = q.where(GraphNode.node_type == node_type.upper())
    if external_id:
        q = q.where(GraphNode.external_id == external_id)
    if label:
        q = q.where(GraphNode.label.ilike(f"%{label}%"))

    result = await db.execute(q)
    nodes = result.scalars().all()
    return [
        {
            "id": str(n.id),
            "node_type": n.node_type,
            "external_id": n.external_id,
            "label": n.label,
            "created_at": n.created_at.isoformat(),
        }
        for n in nodes
    ]
