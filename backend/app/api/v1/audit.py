"""
Audit trail endpoints — FEAT-037.

GET /api/v1/audit                   — List audit events (paginated)
GET /api/v1/audit/{correlation_id}  — Audit trail for a specific request

Audit events are immutable — no write endpoints.
"""

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.recovery import AuditEvent

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/audit", summary="List audit events")
async def list_audit_events(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if event_type:
        q = q.where(AuditEvent.event_type == event_type.upper())

    result = await db.execute(q)
    events = result.scalars().all()
    return [_format_event(e) for e in events]


@router.get(
    "/audit/correlation/{correlation_id}",
    summary="Get full audit trail for a request",
)
async def get_audit_trail(
    correlation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.correlation_id == correlation_id)
        .order_by(AuditEvent.created_at.asc())
    )
    events = result.scalars().all()
    return {
        "correlation_id": str(correlation_id),
        "event_count": len(events),
        "events": [_format_event(e) for e in events],
    }


def _format_event(e: AuditEvent) -> dict:
    return {
        "id": str(e.id),
        "event_type": e.event_type,
        "correlation_id": str(e.correlation_id),
        "candidate_id": str(e.candidate_id) if e.candidate_id else None,
        "recovery_case_id": str(e.recovery_case_id) if e.recovery_case_id else None,
        "policy_decision": e.policy_decision,
        "safety_decision": e.safety_decision,
        "detail": e.detail,
        "created_at": e.created_at.isoformat(),
    }
