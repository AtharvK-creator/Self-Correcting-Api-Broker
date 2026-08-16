"""
Health check endpoints — FEAT-001.

GET /health          — liveness probe
GET /health/ready    — readiness probe (checks DB connectivity)
"""

import time

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

router = APIRouter()
logger = structlog.get_logger(__name__)
_start_time = time.time()


@router.get("/health", summary="Liveness probe")
async def health_live():
    """Basic liveness check — returns 200 if the process is running."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "version": "0.1.0",
    }


@router.get("/health/ready", summary="Readiness probe")
async def health_ready(db: AsyncSession = Depends(get_db)):
    """
    Readiness check — verifies database connectivity.
    Returns 503 if the database is unreachable.
    """
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        logger.warning("health_db_unreachable", error=str(exc))
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "database": "unreachable"},
        )

    settings = get_settings()
    return {
        "status": "ready",
        "database": db_status,
        "llm_provider": settings.llm_provider,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }
