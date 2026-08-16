"""
Evaluation endpoints — FEAT-043+.

POST /api/v1/evaluation/runs
GET  /api/v1/evaluation/runs/{run_id}
"""

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.recovery import EvaluationRun

router = APIRouter()
logger = structlog.get_logger(__name__)


class EvaluationRunCreate(BaseModel):
    name: str
    baseline: str  # B0 | B1 | B2 | B3 | P1
    scenario_set: str
    model_version: str | None = None
    graph_version: str | None = None
    confidence_threshold: float | None = None
    ranking_weights: dict | None = None


@router.post(
    "/evaluation/runs",
    status_code=status.HTTP_201_CREATED,
    summary="Create an evaluation run",
)
async def create_evaluation_run(
    payload: EvaluationRunCreate, db: AsyncSession = Depends(get_db)
):
    run = EvaluationRun(**payload.model_dump())
    db.add(run)
    await db.flush()
    await db.refresh(run)
    logger.info("evaluation_run_created", run_id=str(run.id), name=run.name)
    return {
        "id": str(run.id),
        "name": run.name,
        "baseline": run.baseline,
        "scenario_set": run.scenario_set,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
    }


@router.get("/evaluation/runs/{run_id}", summary="Get evaluation run")
async def get_evaluation_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(EvaluationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return {
        "id": str(run.id),
        "name": run.name,
        "baseline": run.baseline,
        "scenario_set": run.scenario_set,
        "model_version": run.model_version,
        "graph_version": run.graph_version,
        "confidence_threshold": run.confidence_threshold,
        "ranking_weights": run.ranking_weights,
        "results": run.results,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.post("/evaluation/runs/{run_id}/execute", summary="Execute evaluation run")
async def execute_run_endpoint(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.evaluation.runner import EvaluationRunner
    runner = EvaluationRunner(db)
    try:
        run = await runner.execute_run(run_id)
        return {
            "id": str(run.id),
            "status": run.status,
            "results": run.results,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
