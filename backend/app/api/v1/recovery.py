"""
Recovery inspection endpoints.

GET /api/v1/requests/{request_id}
GET /api/v1/recovery/{recovery_id}
GET /api/v1/recovery/{recovery_id}/candidates
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.events import RequestEvent, FailureEvent
from app.models.recovery import RecoveryAttempt, CorrectionCandidate

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/requests/{request_id}", summary="Get request event")
async def get_request(request_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    event = await db.get(RequestEvent, request_id)
    if not event:
        raise HTTPException(status_code=404, detail="Request event not found")
    return {
        "id": str(event.id),
        "correlation_id": str(event.correlation_id),
        "method": event.method,
        "url": event.url,
        "attempt_number": event.attempt_number,
        "http_status": event.http_status,
        "is_success": event.is_success,
        "upstream_latency_ms": event.upstream_latency_ms,
        "created_at": event.created_at.isoformat(),
    }


@router.get("/recovery/{recovery_id}", summary="Get recovery attempt")
async def get_recovery(recovery_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    attempt = await db.get(RecoveryAttempt, recovery_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Recovery attempt not found")
    return {
        "id": str(attempt.id),
        "correlation_id": str(attempt.correlation_id),
        "upstream_attempt_count": attempt.upstream_attempt_count,
        "deterministic_sufficient": attempt.deterministic_sufficient,
        "llm_invoked": attempt.llm_invoked,
        "outcome": attempt.outcome,
        "created_at": attempt.created_at.isoformat(),
        "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
    }


@router.get("/recovery/{recovery_id}/candidates", summary="List candidates for a recovery")
async def get_recovery_candidates(recovery_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    attempt = await db.get(RecoveryAttempt, recovery_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Recovery attempt not found")

    result = await db.execute(
        select(CorrectionCandidate).where(
            CorrectionCandidate.correlation_id == attempt.correlation_id
        ).order_by(CorrectionCandidate.rank_score.desc())
    )
    candidates = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "action_type": c.action_type,
            "provenance": c.provenance,
            "confidence": c.confidence,
            "rank_score": c.rank_score,
            "policy_tier": c.policy_tier,
            "safety_passed": c.safety_passed,
            "was_executed": c.was_executed,
            "was_rejected": c.was_rejected,
            "rejection_reason": c.rejection_reason,
        }
        for c in candidates
    ]
