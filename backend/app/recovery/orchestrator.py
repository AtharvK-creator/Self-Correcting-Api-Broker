"""
Recovery orchestrator — FEAT-036.

Implements the full recovery pipeline per TAD §8, PRD §11, BACKEND_SPEC §6-10.

Pipeline stages:
  1. Failure classification (FEAT-006)
  2. Context building (FEAT-009)
  3. Graph construction (FEAT-010)
  4. Memory retrieval (FEAT-033)
  5. Deterministic candidate generation (FEAT-016)
  6. Confidence gate (FEAT-018) — skips LLM if sufficient
  7. LLM escalation (FEAT-020/023/024) — candidate generator only
  8. Policy classification (FEAT-025)
  9. Safety validation (FEAT-026)
  10. Candidate ranking (FEAT-019)
  11. Execution decision (FEAT-036)
  12. Memory update (FEAT-034/035)

Invariants enforced:
  - Maximum 2 upstream executions per correlation ID (TAD §14)
  - LLM never executes requests (TAD §10)
  - NEVER_AUTOMATIC candidates always rejected (SEC invariant)
  - Fail-closed on any safety validation failure
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.normalization import NormalizedRequest
from app.broker.upstream import UpstreamExecutionError, execute_upstream
from app.context.builder import FailureContext, build_failure_context
from app.embeddings.search import SimilaritySearchService
from app.failures.classifier import ClassifiedFailure, classify_failure
from app.graph.service import GraphService
from app.memory.service import RecoveryMemoryService
from app.models.events import FailureEvent, RequestEvent
from app.models.recovery import (
    AuditEvent,
    CorrectionCandidate,
    ModelRun,
    POLICY_NEVER_AUTOMATIC,
    PROVENANCE_DETERMINISTIC,
    PROVENANCE_LLM,
    RecoveryAttempt,
)
from app.recovery.deterministic.confidence_gate import evaluate_confidence
from app.recovery.deterministic.templates import (
    DeterministicCandidate,
    generate_from_recovery_case,
    generate_retry_candidate,
)
from app.recovery.llm.providers import get_llm_provider
from app.recovery.policy.engine import PolicyEngine
from app.recovery.ranking.ranker import rank_candidates
from app.recovery.safety.validator import SafetyValidator

logger = structlog.get_logger(__name__)

MAX_UPSTREAM_ATTEMPTS = 2  # TAD §14: immutable invariant


class RecoveryOutcome:
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


class RecoveryResult:
    def __init__(
        self,
        *,
        outcome: str,
        http_status: int | None = None,
        response_body: Any = None,
        recovery_attempt_id: uuid.UUID | None = None,
        selected_candidate_id: uuid.UUID | None = None,
        upstream_attempt_count: int = 1,
        llm_invoked: bool = False,
        rejection_reason: str | None = None,
    ):
        self.outcome = outcome
        self.http_status = http_status
        self.response_body = response_body
        self.recovery_attempt_id = recovery_attempt_id
        self.selected_candidate_id = selected_candidate_id
        self.upstream_attempt_count = upstream_attempt_count
        self.llm_invoked = llm_invoked
        self.rejection_reason = rejection_reason

    @property
    def is_success(self) -> bool:
        return self.outcome == RecoveryOutcome.SUCCESS


class RecoveryOrchestrator:
    """
    Full recovery pipeline orchestrator.

    Thread-safety: use one instance per request (holds a DB session).
    The orchestrator owns the recovery attempt lifecycle.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._graph = GraphService(db)
        self._memory = RecoveryMemoryService(db)
        self._policy = PolicyEngine(db)
        self._vector_search = SimilaritySearchService(db)

    async def run(
        self,
        *,
        request: NormalizedRequest,
        original_http_status: int | None,
        original_response_body: Any,
        upstream_error: UpstreamExecutionError | None,
        registered_host: str | None,
        is_idempotent: bool = False,
    ) -> RecoveryResult:
        """
        Run the full recovery pipeline for a failed request.

        Returns RecoveryResult with outcome and response data.
        """
        correlation_id = request.correlation_id

        # ── 1. Record recovery attempt row ────────────────────────────────────
        attempt = RecoveryAttempt(
            correlation_id=correlation_id,
            upstream_attempt_count=1,  # The original request counts as attempt 1
        )
        self.db.add(attempt)
        await self.db.flush()

        try:
            result = await self._pipeline(
                request=request,
                original_http_status=original_http_status,
                original_response_body=original_response_body,
                upstream_error=upstream_error,
                registered_host=registered_host,
                is_idempotent=is_idempotent,
                attempt=attempt,
            )
        except Exception as exc:
            logger.error(
                "recovery_pipeline_error",
                correlation_id=str(correlation_id),
                error=str(exc),
                exc_info=True,
            )
            attempt.outcome = RecoveryOutcome.TERMINAL_FAILURE
            attempt.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self._audit(
                event_type="PIPELINE_ERROR",
                correlation_id=correlation_id,
                detail={"error": str(exc)},
            )
            return RecoveryResult(
                outcome=RecoveryOutcome.TERMINAL_FAILURE,
                recovery_attempt_id=attempt.id,
                upstream_attempt_count=attempt.upstream_attempt_count,
                rejection_reason=f"Pipeline error: {exc}",
            )

        attempt.outcome = result.outcome
        attempt.completed_at = datetime.now(timezone.utc)
        attempt.llm_invoked = result.llm_invoked
        if result.selected_candidate_id:
            attempt.selected_candidate_id = result.selected_candidate_id
        await self.db.flush()

        return result

    async def _pipeline(
        self,
        *,
        request: NormalizedRequest,
        original_http_status: int | None,
        original_response_body: Any,
        upstream_error: UpstreamExecutionError | None,
        registered_host: str | None,
        is_idempotent: bool,
        attempt: RecoveryAttempt,
    ) -> RecoveryResult:
        correlation_id = request.correlation_id

        # ── 2. Classify failure ───────────────────────────────────────────────
        failure = classify_failure(
            http_status=original_http_status,
            response_body=original_response_body,
            error=upstream_error,
            api_id=request.api_id,
            endpoint_path=request.endpoint_path,
            correlation_id=correlation_id,
        )

        if not failure.is_recoverable:
            logger.info(
                "failure_not_recoverable",
                failure_class=failure.failure_class,
                correlation_id=str(correlation_id),
            )
            await self._audit(
                event_type="FAILURE_NOT_RECOVERABLE",
                correlation_id=correlation_id,
                detail={"failure_class": failure.failure_class},
            )
            return RecoveryResult(
                outcome=RecoveryOutcome.TERMINAL_FAILURE,
                http_status=original_http_status,
                recovery_attempt_id=attempt.id,
                rejection_reason=f"Failure class {failure.failure_class} is not recoverable",
            )

        # Persist failure event
        failure_event = FailureEvent(
            correlation_id=correlation_id,
            failure_class=failure.failure_class,
            failure_signature=failure.failure_signature,
            http_status=failure.http_status,
            error_detail=failure.error_detail,
            classifier_confidence=failure.classifier_confidence,
            is_recoverable=failure.is_recoverable,
        )
        self.db.add(failure_event)
        await self.db.flush()
        attempt.failure_event_id = failure_event.id

        # ── 3. Build context ──────────────────────────────────────────────────
        context = build_failure_context(request, failure)

        # ── 4. Build graph ────────────────────────────────────────────────────
        try:
            node_ids = await self._graph.build_failure_context_graph(context)
        except Exception as exc:
            logger.warning("graph_build_error", error=str(exc), correlation_id=str(correlation_id))
            node_ids = {}

        # ── 5. Retrieve memory ────────────────────────────────────────────────
        memory_cases = await self._memory.find_by_signature(failure.failure_signature)
        context_cases = await self._memory.find_by_context(context)
        all_cases = {c.id: c for c in [*memory_cases, *context_cases]}

        # ── 6. Generate deterministic candidates ──────────────────────────────
        det_candidates: list[DeterministicCandidate] = []
        for case in all_cases.values():
            det_candidates.append(generate_from_recovery_case(context, case))

        retry_cand = generate_retry_candidate(context)
        if retry_cand:
            det_candidates.append(retry_cand)

        # ── 7. Confidence gate ────────────────────────────────────────────────
        gate = evaluate_confidence(
            det_candidates,
            failure_match=failure.classifier_confidence,
            historical_success_rate=max(
                (c.confidence for c in det_candidates), default=0.0
            ),
        )

        # ── 8. LLM escalation (if gate insufficient) ──────────────────────────
        llm_invoked = False
        llm_candidates = []
        if not gate.sufficient and request.recovery_mode != "disabled":
            llm_invoked = True
            provider = get_llm_provider()
            graph_neighborhood = await self._get_neighborhood_summary(
                node_ids.get("context_node_id")
            )
            llm_result = await provider.generate_candidates(
                failure_context=context.model_dump(),
                api_schema=None,
                graph_neighborhood=graph_neighborhood,
                correlation_id=correlation_id,
            )
            # Record model run
            model_run = ModelRun(
                correlation_id=correlation_id,
                provider=llm_result.model_provider,
                model=llm_result.model_version,
                prompt_tokens=llm_result.prompt_tokens,
                completion_tokens=llm_result.completion_tokens,
                latency_ms=llm_result.latency_ms,
                was_successful=llm_result.was_successful,
                error_detail=llm_result.error,
            )
            self.db.add(model_run)
            await self.db.flush()
            llm_candidates = llm_result.candidates

        # ── 9. Policy + safety filter ─────────────────────────────────────────
        validator = SafetyValidator(registered_host=registered_host)
        all_raw_candidates = [*det_candidates, *llm_candidates]

        persisted_candidates: list[CorrectionCandidate] = []
        for raw in all_raw_candidates:
            action_type = getattr(raw, "action_type", "")
            provenance = getattr(raw, "source", None) or getattr(raw, "provenance", PROVENANCE_LLM)
            changes = getattr(raw, "changes", [])
            confidence = getattr(raw, "confidence", 0.5)

            policy_decision = await self._policy.classify_action(action_type)
            safety_result = validator.validate(
                candidate={"type": action_type, "changes": changes},
                policy_decision=policy_decision,
                method=request.method,
                is_idempotent=is_idempotent,
                upstream_attempt_count=attempt.upstream_attempt_count,
                max_attempts=MAX_UPSTREAM_ATTEMPTS,
            )

            cand = CorrectionCandidate(
                correlation_id=correlation_id,
                action_type=action_type,
                changes=changes,
                reason=getattr(raw, "reason", ""),
                provenance=provenance,
                source_detail={},
                confidence=confidence,
                policy_tier=policy_decision.tier,
                safety_passed=safety_result.passed,
                safety_detail={"checks": safety_result.checks},
                was_rejected=not safety_result.passed,
                rejection_reason=safety_result.rejection_reason,
            )
            self.db.add(cand)
            await self.db.flush()
            persisted_candidates.append(cand)

            if not safety_result.passed:
                await self._audit(
                    event_type="CANDIDATE_REJECTED",
                    correlation_id=correlation_id,
                    candidate_id=cand.id,
                    policy_decision=policy_decision.tier,
                    safety_decision="REJECT",
                    detail={"rejection_reason": safety_result.rejection_reason},
                )

        # ── 10. Rank candidates ────────────────────────────────────────────────
        safe_candidates = [c for c in persisted_candidates if c.safety_passed]
        if not safe_candidates:
            logger.warning(
                "no_safe_candidates",
                total=len(persisted_candidates),
                correlation_id=str(correlation_id),
            )
            return RecoveryResult(
                outcome=RecoveryOutcome.TERMINAL_FAILURE,
                http_status=original_http_status,
                recovery_attempt_id=attempt.id,
                upstream_attempt_count=attempt.upstream_attempt_count,
                llm_invoked=llm_invoked,
                rejection_reason="No candidates passed safety validation",
            )

        ranked = rank_candidates(
            safe_candidates,
            failure_match=failure.classifier_confidence,
        )
        for rc in ranked:
            rc.candidate.rank_score = rc.rank_score

        best = ranked[0].candidate

        # ── 11. Execute corrected request ─────────────────────────────────────
        # Enforce MAX 2 upstream attempts
        if attempt.upstream_attempt_count >= MAX_UPSTREAM_ATTEMPTS:
            await self._audit(
                event_type="RETRY_BUDGET_EXHAUSTED",
                correlation_id=correlation_id,
                detail={"attempt_count": attempt.upstream_attempt_count},
            )
            return RecoveryResult(
                outcome=RecoveryOutcome.TERMINAL_FAILURE,
                recovery_attempt_id=attempt.id,
                upstream_attempt_count=attempt.upstream_attempt_count,
                llm_invoked=llm_invoked,
                rejection_reason="Maximum upstream execution count reached",
            )

        # Build corrected request URL/params by applying the candidate
        corrected_params = await self._apply_candidate(request, best)

        attempt.upstream_attempt_count += 1
        attempt.selected_candidate_id = best.id
        await self.db.flush()

        await self._audit(
            event_type="CANDIDATE_SELECTED",
            correlation_id=correlation_id,
            candidate_id=best.id,
            policy_decision=best.policy_tier,
            safety_decision="PASS",
            detail={"action_type": best.action_type, "rank_score": best.rank_score},
        )

        try:
            from app.models.registry import Api
            api = await self.db.get(Api, request.api_id)
            base_url = api.base_url if api else ""
            full_url = f"{base_url.rstrip('/')}{request.endpoint_path}"

            upstream_resp = await execute_upstream(
                url=corrected_params.get("url") or full_url,
                method=request.method,
                headers=corrected_params.get("headers") or request.headers,
                query_params=corrected_params.get("query_params") or request.query_params,
                body=corrected_params.get("body") or request.body,
                correlation_id=correlation_id,
                registered_host=registered_host,
            )
        except UpstreamExecutionError as exc:
            logger.error(
                "corrected_request_failed",
                correlation_id=str(correlation_id),
                error=str(exc),
            )
            best.was_executed = True
            await self.db.flush()
            return RecoveryResult(
                outcome=RecoveryOutcome.FAILURE,
                recovery_attempt_id=attempt.id,
                selected_candidate_id=best.id,
                upstream_attempt_count=attempt.upstream_attempt_count,
                llm_invoked=llm_invoked,
                rejection_reason=f"Corrected request failed: {exc}",
            )

        best.was_executed = True
        await self.db.flush()

        if upstream_resp.is_success:
            # ── 12. Update memory on success ──────────────────────────────────
            if best.provenance == PROVENANCE_LLM:
                try:
                    new_case = await self._memory.create_from_llm_success(
                        context=context,
                        action_type=best.action_type,
                        changes=best.changes,
                        model_provider="",
                        model_version="",
                        confidence=best.confidence,
                        api_id=request.api_id,
                    )
                    best.recovery_case_id = new_case.id
                    await self.db.flush()
                except Exception as exc:
                    logger.warning("memory_update_error", error=str(exc))
            else:
                # Update deterministic case outcome
                if best.recovery_case_id:
                    try:
                        await self._memory.record_outcome(best.recovery_case_id, success=True)
                    except Exception as exc:
                        logger.warning("memory_outcome_error", error=str(exc))

            await self._audit(
                event_type="RECOVERY_SUCCESS",
                correlation_id=correlation_id,
                candidate_id=best.id,
                detail={"http_status": upstream_resp.status_code},
            )
            return RecoveryResult(
                outcome=RecoveryOutcome.SUCCESS,
                http_status=upstream_resp.status_code,
                response_body=upstream_resp.body,
                recovery_attempt_id=attempt.id,
                selected_candidate_id=best.id,
                upstream_attempt_count=attempt.upstream_attempt_count,
                llm_invoked=llm_invoked,
            )
        else:
            # Corrected request also failed
            if best.recovery_case_id:
                try:
                    await self._memory.record_outcome(best.recovery_case_id, success=False)
                except Exception:
                    pass
            await self._audit(
                event_type="RECOVERY_FAILURE",
                correlation_id=correlation_id,
                candidate_id=best.id,
                detail={"http_status": upstream_resp.status_code},
            )
            return RecoveryResult(
                outcome=RecoveryOutcome.FAILURE,
                http_status=upstream_resp.status_code,
                response_body=upstream_resp.body,
                recovery_attempt_id=attempt.id,
                selected_candidate_id=best.id,
                upstream_attempt_count=attempt.upstream_attempt_count,
                llm_invoked=llm_invoked,
                rejection_reason="Corrected request failed with non-2xx status",
            )

    async def _apply_candidate(
        self,
        request: NormalizedRequest,
        candidate: CorrectionCandidate,
    ) -> dict[str, Any]:
        """
        Apply a candidate's changes to the request to produce corrected parameters.

        Returns corrected headers, query_params, body.
        Does not mutate the original request.
        """
        headers = dict(request.headers)
        query_params = dict(request.query_params)
        body = dict(request.body) if request.body else {}

        for change in candidate.changes:
            if not isinstance(change, dict):
                continue
            action = change.get("action") or candidate.action_type
            field = change.get("field", "")
            location = change.get("location", "body")
            rename_to = change.get("rename_to")

            if action == "parameter_rename" and field and rename_to:
                if location == "body" and field in body:
                    body[rename_to] = body.pop(field)
                elif location == "query" and field in query_params:
                    query_params[rename_to] = query_params.pop(field)
                elif location == "header" and field in headers:
                    headers[rename_to] = headers.pop(field)

            elif action == "remove_optional_field":
                for loc, container in [("body", body), ("query", query_params)]:
                    if location == loc and field in container:
                        container.pop(field)

            elif action == "wait_and_retry":
                import asyncio
                wait_secs = change.get("retry_after_seconds", 1)
                await asyncio.sleep(min(wait_secs, 5))  # cap at 5s

        return {"headers": headers, "query_params": query_params, "body": body or None}

    async def _get_neighborhood_summary(
        self, context_node_id: uuid.UUID | None
    ) -> list[dict]:
        if not context_node_id:
            return []
        # 1. Try vector search (pgvector) — richer semantic results
        try:
            similar = await self._vector_search.find_similar_contexts(
                context_node_id, limit=10, min_similarity=0.70
            )
            if similar:
                return [
                    {
                        "id": str(r.node_id),
                        "node_type": r.node_type,
                        "label": r.label,
                        "cosine_similarity": r.cosine_similarity,
                        **r.attributes,
                    }
                    for r in similar
                ]
        except Exception:
            pass  # pgvector not available or no embeddings yet — fall through

        # 2. Fallback: NX graph walk (always available)
        try:
            G = await self._graph.get_neighborhood(context_node_id=context_node_id)
            return [{"id": n, **G.nodes[n]} for n in list(G.nodes)[:10]]
        except Exception:
            return []

    async def _audit(
        self,
        *,
        event_type: str,
        correlation_id: uuid.UUID,
        candidate_id: uuid.UUID | None = None,
        recovery_case_id: uuid.UUID | None = None,
        policy_decision: str | None = None,
        safety_decision: str | None = None,
        detail: dict | None = None,
    ) -> None:
        event = AuditEvent(
            event_type=event_type,
            correlation_id=correlation_id,
            candidate_id=candidate_id,
            recovery_case_id=recovery_case_id,
            policy_decision=policy_decision,
            safety_decision=safety_decision,
            detail=detail or {},
        )
        self.db.add(event)
        await self.db.flush()
