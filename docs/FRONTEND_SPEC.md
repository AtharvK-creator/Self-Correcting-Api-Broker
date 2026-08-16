# Frontend Specification

## 1. Purpose

The frontend is an observability and control interface for the backend recovery engine. It is not the core intelligence layer.

## 2. Routes

```text
/login
/dashboard
/apis
/apis/:id
/broker
/requests
/requests/:id
/recovery/:id
/recovery-memory
/graph
/evaluation
/settings
```

## 3. Dashboard

Show:
- request volume,
- success rate,
- recovery rate,
- deterministic recovery rate,
- LLM escalation rate,
- LLM-assisted recovery rate,
- unsafe/rejected candidates,
- average recovery latency,
- average attempts,
- recovery-memory reuse.

## 4. Broker Console

User selects:
- registered API,
- endpoint,
- method,
- parameters/body,
- recovery mode.

The UI must not expose stored secrets.

## 5. Request trace

Visualize:

```text
Original Request
↓
Upstream Failure
↓
Failure Classification
↓
Context Retrieval
↓
Deterministic Candidates
↓
Confidence Gate
↓
LLM Escalation (if used)
↓
Candidate Ranking
↓
Policy
↓
Safety Validation
↓
Corrected Attempt
↓
Outcome
↓
Recovery Memory Update
```

## 6. Recovery detail

Display:
- failure,
- contextual graph evidence,
- deterministic candidates,
- confidence score,
- LLM escalation reason if applicable,
- model/provider,
- ranked candidates,
- policy tier,
- safety checks,
- rejection reasons,
- execution result.

## 7. Recovery memory

Show:
- situation signature,
- correction,
- source,
- model,
- success/failure count,
- confidence,
- maturity,
- last used,
- provenance.

## 8. Graph explorer

Display relationships among:
- API,
- endpoint,
- version,
- parameter,
- failure,
- correction,
- recovery case,
- outcome.

## 9. Evaluation

Show:
- baseline recovery,
- deterministic recovery,
- LLM fallback,
- proposed graph-learning system,
- recovery rate,
- precision,
- unsafe correction rate,
- LLM escalation rate,
- latency,
- cost.

## 10. States

Every data view needs:
- loading,
- empty,
- error,
- unauthorized,
- stale/degraded data state.

## 11. Accessibility

- keyboard navigation,
- semantic controls,
- focus visibility,
- sufficient contrast,
- status not conveyed by color alone.

## 12. Frontend security

- secure authentication,
- no secrets in browser storage,
- sanitized external content,
- privileged route protection,
- no raw stack traces.

## 13. Acceptance criteria

FE-001: Submit a registered request.

FE-002: View complete recovery trace.

FE-003: Distinguish deterministic and LLM recovery.

FE-004: Inspect graph evidence.

FE-005: Inspect recovery-memory provenance.

FE-006: View evaluation metrics.

FE-007: Never display provider secrets.
