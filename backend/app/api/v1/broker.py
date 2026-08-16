"""
Broker execute endpoint — FEAT-005 / FR-001 / FR-003.

POST /api/v1/broker/execute

Full pipeline:
1. Normalize request (FEAT-004)
2. SSRF-validate target URL
3. Execute upstream (FEAT-005)
4. On success → return immediately (NFR-001)
5. On failure → run recovery orchestrator (FEAT-036)
6. Return result with full audit trail correlation
"""

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.normalization import normalize_request
from app.broker.upstream import SSRFError, UpstreamExecutionError, execute_upstream
from app.database import get_db
from app.models.registry import Api

router = APIRouter()
logger = structlog.get_logger(__name__)


class BrokerExecuteRequest(BaseModel):
    api_id: uuid.UUID
    endpoint_path: str
    method: str = "GET"
    headers: dict[str, str] = {}
    query_params: dict[str, Any] = {}
    body: dict[str, Any] | None = None
    recovery_mode: str = "auto"  # auto | manual | disabled


class BrokerExecuteResponse(BaseModel):
    correlation_id: uuid.UUID
    status: str  # success | failure | recovered | recovery_failed
    http_status: int | None = None
    response_body: Any = None
    recovery_id: uuid.UUID | None = None
    attempt_count: int = 1
    llm_invoked: bool = False
    message: str | None = None


@router.post(
    "/broker/execute",
    response_model=BrokerExecuteResponse,
    summary="Execute a request through the broker",
)
async def broker_execute(
    payload: BrokerExecuteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute an upstream API request through the broker.

    On success: returns the upstream response immediately.
    On failure: routes through the recovery pipeline (max 2 upstream attempts).
    """
    correlation_id = uuid.UUID(request.state.correlation_id)

    # ── 1. Resolve API record ─────────────────────────────────────────────────
    api = await db.get(Api, payload.api_id)
    if not api:
        raise HTTPException(status_code=404, detail=f"API {payload.api_id} not found in registry")
    if not api.is_active:
        raise HTTPException(status_code=409, detail=f"API {api.name} is not active")

    # ── 2. Normalize request ──────────────────────────────────────────────────
    normalized = normalize_request(
        correlation_id=correlation_id,
        api_id=payload.api_id,
        endpoint_path=payload.endpoint_path,
        method=payload.method,
        headers=payload.headers,
        query_params=payload.query_params,
        body=payload.body,
        recovery_mode=payload.recovery_mode,
    )

    full_url = f"{api.base_url.rstrip('/')}{payload.endpoint_path}"

    # ── 3. Execute upstream ───────────────────────────────────────────────────
    upstream_error: UpstreamExecutionError | None = None
    upstream_resp = None

    try:
        upstream_resp = await execute_upstream(
            url=full_url,
            method=normalized.method,
            headers=normalized.headers,
            query_params=normalized.query_params,
            body=normalized.body,
            correlation_id=correlation_id,
            registered_host=api.registered_host,
        )
    except SSRFError as exc:
        logger.error(
            "ssrf_violation",
            url=full_url,
            registered_host=api.registered_host,
            correlation_id=str(correlation_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=403,
            detail={
                "message": "SSRF protection: request destination not allowed",
                "correlation_id": str(correlation_id),
            },
        )
    except UpstreamExecutionError as exc:
        upstream_error = exc

    # ── 4. Return on success ──────────────────────────────────────────────────
    if upstream_resp and upstream_resp.is_success:
        return BrokerExecuteResponse(
            correlation_id=correlation_id,
            status="success",
            http_status=upstream_resp.status_code,
            response_body=upstream_resp.body,
            attempt_count=1,
        )

    # ── 5. Recovery pipeline ──────────────────────────────────────────────────
    if payload.recovery_mode == "disabled":
        http_status = upstream_resp.status_code if upstream_resp else None
        return BrokerExecuteResponse(
            correlation_id=correlation_id,
            status="failure",
            http_status=http_status,
            response_body=upstream_resp.body if upstream_resp else None,
            attempt_count=1,
            message="Recovery disabled by caller",
        )

    from app.recovery.orchestrator import RecoveryOrchestrator, RecoveryOutcome

    orchestrator = RecoveryOrchestrator(db)
    recovery_result = await orchestrator.run(
        request=normalized,
        original_http_status=upstream_resp.status_code if upstream_resp else None,
        original_response_body=upstream_resp.body if upstream_resp else None,
        upstream_error=upstream_error,
        registered_host=api.registered_host,
        is_idempotent=normalized.is_idempotent,
    )

    if recovery_result.is_success:
        return BrokerExecuteResponse(
            correlation_id=correlation_id,
            status="recovered",
            http_status=recovery_result.http_status,
            response_body=recovery_result.response_body,
            recovery_id=recovery_result.recovery_attempt_id,
            attempt_count=recovery_result.upstream_attempt_count,
            llm_invoked=recovery_result.llm_invoked,
        )
    else:
        return BrokerExecuteResponse(
            correlation_id=correlation_id,
            status="recovery_failed",
            http_status=recovery_result.http_status,
            response_body=None,
            recovery_id=recovery_result.recovery_attempt_id,
            attempt_count=recovery_result.upstream_attempt_count,
            llm_invoked=recovery_result.llm_invoked,
            message=recovery_result.rejection_reason,
        )
