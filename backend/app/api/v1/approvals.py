"""
Approval workflow endpoints — FEAT-030, FEAT-031.
Policy management CRUD — FEAT-032.

POST   /api/v1/approvals                 — Submit for approval
GET    /api/v1/approvals                 — List pending approvals
POST   /api/v1/approvals/{id}/approve   — Approve (REVIEWER role)
POST   /api/v1/approvals/{id}/reject    — Reject (REVIEWER role)

GET    /api/v1/policies                  — List policies
POST   /api/v1/policies                  — Create policy
PATCH  /api/v1/policies/{id}             — Update policy
DELETE /api/v1/policies/{id}             — Deactivate policy
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.recovery import (
    ApprovalRequest,
    CorrectionCandidate,
    Policy,
    POLICY_AUTO_ELIGIBLE,
    POLICY_APPROVAL_REQUIRED,
    POLICY_NEVER_AUTOMATIC,
)

router = APIRouter()
logger = structlog.get_logger(__name__)

# ── Schemas ───────────────────────────────────────────────────────────────────

class ApprovalSubmitRequest(BaseModel):
    candidate_id: uuid.UUID
    justification: str = ""


class ApprovalActionRequest(BaseModel):
    reviewer_note: str = ""


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    status: str
    justification: str
    reviewer_id: uuid.UUID | None
    reviewer_note: str | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class PolicyCreate(BaseModel):
    action_type: str
    tier: str
    description: str = ""
    is_active: bool = True

    def validate_tier(self) -> "PolicyCreate":
        allowed = {POLICY_AUTO_ELIGIBLE, POLICY_APPROVAL_REQUIRED, POLICY_NEVER_AUTOMATIC}
        if self.tier not in allowed:
            raise ValueError(f"tier must be one of {allowed}")
        return self


class PolicyPatch(BaseModel):
    tier: str | None = None
    description: str | None = None
    is_active: bool | None = None


class PolicyResponse(BaseModel):
    id: uuid.UUID
    action_type: str
    tier: str
    description: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Approval Workflow ─────────────────────────────────────────────────────────

@router.post(
    "/approvals",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a correction candidate for manual approval",
)
async def submit_for_approval(
    payload: ApprovalSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    candidate = await db.get(CorrectionCandidate, payload.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Check if already submitted
    existing = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.candidate_id == payload.candidate_id,
            ApprovalRequest.status == "PENDING",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Candidate already has a pending approval request")

    approval = ApprovalRequest(
        candidate_id=payload.candidate_id,
        justification=payload.justification,
        status="PENDING",
    )
    db.add(approval)
    await db.flush()
    await db.refresh(approval)
    logger.info("approval_submitted", approval_id=str(approval.id), candidate_id=str(payload.candidate_id))
    return approval


@router.get(
    "/approvals",
    response_model=list[ApprovalResponse],
    summary="List approval requests",
)
async def list_approvals(
    status_filter: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    q = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).limit(limit)
    if status_filter:
        q = q.where(ApprovalRequest.status == status_filter.upper())
    result = await db.execute(q)
    return result.scalars().all()


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve a correction candidate (REVIEWER role)",
)
async def approve_candidate(
    approval_id: uuid.UUID,
    payload: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
):
    approval = await db.get(ApprovalRequest, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Approval is already {approval.status}")

    approval.status = "APPROVED"
    approval.reviewer_note = payload.reviewer_note
    approval.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info("approval_approved", approval_id=str(approval_id))
    return approval


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=ApprovalResponse,
    summary="Reject a correction candidate (REVIEWER role)",
)
async def reject_candidate(
    approval_id: uuid.UUID,
    payload: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
):
    approval = await db.get(ApprovalRequest, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Approval is already {approval.status}")

    approval.status = "REJECTED"
    approval.reviewer_note = payload.reviewer_note
    approval.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info("approval_rejected", approval_id=str(approval_id))
    return approval


# ── Policy Management (FEAT-032) ──────────────────────────────────────────────

@router.get(
    "/policies",
    response_model=list[PolicyResponse],
    summary="List policies",
)
async def list_policies(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    q = select(Policy).order_by(Policy.action_type)
    if active_only:
        q = q.where(Policy.is_active == True)
    result = await db.execute(q)
    return result.scalars().all()


@router.post(
    "/policies",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a policy rule",
)
async def create_policy(
    payload: PolicyCreate,
    db: AsyncSession = Depends(get_db),
):
    allowed_tiers = {POLICY_AUTO_ELIGIBLE, POLICY_APPROVAL_REQUIRED, POLICY_NEVER_AUTOMATIC}
    if payload.tier not in allowed_tiers:
        raise HTTPException(status_code=422, detail=f"tier must be one of {allowed_tiers}")

    existing = await db.execute(
        select(Policy).where(Policy.action_type == payload.action_type, Policy.is_active == True)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Active policy for '{payload.action_type}' already exists")

    policy = Policy(
        action_type=payload.action_type,
        tier=payload.tier,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(policy)
    await db.flush()
    await db.refresh(policy)
    logger.info("policy_created", action_type=payload.action_type, tier=payload.tier)
    return policy


@router.patch(
    "/policies/{policy_id}",
    response_model=PolicyResponse,
    summary="Update a policy rule",
)
async def update_policy(
    policy_id: uuid.UUID,
    payload: PolicyPatch,
    db: AsyncSession = Depends(get_db),
):
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    if payload.tier is not None:
        allowed_tiers = {POLICY_AUTO_ELIGIBLE, POLICY_APPROVAL_REQUIRED, POLICY_NEVER_AUTOMATIC}
        if payload.tier not in allowed_tiers:
            raise HTTPException(status_code=422, detail=f"tier must be one of {allowed_tiers}")
        policy.tier = payload.tier

    if payload.description is not None:
        policy.description = payload.description
    if payload.is_active is not None:
        policy.is_active = payload.is_active

    await db.flush()
    return policy


@router.delete(
    "/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate a policy rule",
)
async def deactivate_policy(
    policy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.is_active = False
    await db.flush()
    logger.info("policy_deactivated", policy_id=str(policy_id))
