"""
Recovery memory endpoints.

GET /api/v1/recovery-memory
GET /api/v1/recovery-memory/{case_id}
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.recovery import RecoveryCase

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/recovery-memory", summary="List recovery memory cases")
async def list_recovery_memory(
    maturity: str | None = Query(None, description="Filter by maturity: PROPOSED, VALIDATED, ESTABLISHED"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(RecoveryCase).order_by(RecoveryCase.confidence.desc()).limit(limit).offset(offset)
    if maturity:
        q = q.where(RecoveryCase.maturity == maturity.upper())
    result = await db.execute(q)
    cases = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "failure_signature": c.failure_signature,
            "source": c.source,
            "model_provider": c.model_provider,
            "maturity": c.maturity,
            "confidence": c.confidence,
            "success_count": c.success_count,
            "failure_count": c.failure_count,
            "reuse_count": c.reuse_count,
            "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in cases
    ]


@router.get("/recovery-memory/{case_id}", summary="Get recovery memory case detail")
async def get_recovery_case(case_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    case = await db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Recovery case not found")
    return {
        "id": str(case.id),
        "api_id": str(case.api_id) if case.api_id else None,
        "endpoint_id": str(case.endpoint_id) if case.endpoint_id else None,
        "failure_signature": case.failure_signature,
        "context_signature": case.context_signature,
        "correction": case.correction,
        "source": case.source,
        "model_provider": case.model_provider,
        "model_version": case.model_version,
        "maturity": case.maturity,
        "confidence": case.confidence,
        "success_count": case.success_count,
        "failure_count": case.failure_count,
        "reuse_count": case.reuse_count,
        "last_used_at": case.last_used_at.isoformat() if case.last_used_at else None,
        "created_at": case.created_at.isoformat(),
    }
