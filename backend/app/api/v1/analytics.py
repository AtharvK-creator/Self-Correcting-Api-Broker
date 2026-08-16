"""
Analytics summary endpoint.

GET /api/v1/analytics/summary
"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.events import RequestEvent, FailureEvent
from app.models.recovery import RecoveryAttempt

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/analytics/summary", summary="Get analytics summary")
async def analytics_summary(db: AsyncSession = Depends(get_db)):
    # Total requests
    total_requests_result = await db.execute(select(func.count(RequestEvent.id)))
    total_requests = total_requests_result.scalar() or 0

    # Successful requests
    success_result = await db.execute(
        select(func.count(RequestEvent.id)).where(RequestEvent.is_success == True)
    )
    total_success = success_result.scalar() or 0

    # Total failures
    total_failures_result = await db.execute(select(func.count(FailureEvent.id)))
    total_failures = total_failures_result.scalar() or 0

    # Recovery attempts
    recovery_result = await db.execute(select(func.count(RecoveryAttempt.id)))
    total_recoveries = recovery_result.scalar() or 0

    # Successful recoveries
    recovered_result = await db.execute(
        select(func.count(RecoveryAttempt.id)).where(RecoveryAttempt.outcome == "SUCCESS")
    )
    total_recovered = recovered_result.scalar() or 0

    # LLM invocations
    llm_result = await db.execute(
        select(func.count(RecoveryAttempt.id)).where(RecoveryAttempt.llm_invoked == True)
    )
    total_llm = llm_result.scalar() or 0

    return {
        "total_requests": total_requests,
        "total_success": total_success,
        "total_failures": total_failures,
        "success_rate": round(total_success / total_requests, 4) if total_requests > 0 else None,
        "total_recovery_attempts": total_recoveries,
        "total_recovered": total_recovered,
        "recovery_rate": round(total_recovered / total_failures, 4) if total_failures > 0 else None,
        "llm_invocations": total_llm,
        "llm_escalation_rate": round(total_llm / total_failures, 4) if total_failures > 0 else None,
    }
