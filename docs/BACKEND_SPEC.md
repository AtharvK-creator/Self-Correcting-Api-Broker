# Backend Specification

## 1. Stack

- Python
- FastAPI
- Pydantic
- HTTPX
- SQLAlchemy
- Alembic
- PostgreSQL
- pgvector
- NetworkX for graph analysis
- Node2Vec baseline
- GraphSAGE research model
- Gemini/Groq provider adapters

## 2. Modules

```text
app/
├── api/
├── auth/
├── broker/
├── registry/
├── failures/
├── context/
├── graph/
├── embeddings/
├── recovery/
│   ├── deterministic/
│   ├── llm/
│   ├── ranking/
│   ├── policy/
│   └── safety/
├── memory/
├── models/
├── repositories/
├── observability/
└── evaluation/
```

## 3. Core endpoints

```text
POST /api/v1/broker/execute
GET  /api/v1/requests/{request_id}
GET  /api/v1/recovery/{recovery_id}
GET  /api/v1/recovery/{recovery_id}/candidates

GET  /api/v1/recovery-memory
GET  /api/v1/recovery-memory/{case_id}

GET  /api/v1/graph/nodes/{node_id}
GET  /api/v1/graph/search

GET  /api/v1/apis
POST /api/v1/apis
GET  /api/v1/apis/{api_id}
PATCH /api/v1/apis/{api_id}

GET  /api/v1/analytics/summary

POST /api/v1/evaluation/runs
GET  /api/v1/evaluation/runs/{run_id}
```

## 4. Execute flow

```text
POST /broker/execute
→ normalize
→ pre-policy
→ attempt original
→ success OR failure
→ recovery pipeline
```

## 5. Recovery pipeline

```text
failure
→ classify
→ context build
→ graph retrieval
→ deterministic candidate generation
→ confidence gate
→ optional LLM
→ candidate pool
→ ranking
→ policy
→ safety
→ corrected attempt
→ outcome
→ memory update
```

## 6. Deterministic candidate sources

Priority:
1. established recovery memory,
2. validated recovery memory,
3. configured provider rules,
4. schema transformations,
5. safe transient retry.

Each candidate includes:
- action type,
- changes,
- evidence IDs,
- confidence,
- source.

## 7. Confidence gate

Output:

```json
{
  "sufficient": true,
  "score": 0.91,
  "candidate_ids": ["cand_123"],
  "evidence_count": 8
}
```

If insufficient:

```json
{
  "sufficient": false,
  "score": 0.48,
  "reason": "No candidate exceeds evidence threshold"
}
```

## 8. LLM provider interface

```python
class LLMProvider:
    def generate_candidates(self, context) -> list:
        ...
```

Implement:
- GeminiProvider
- GroqProvider
- MockProvider

LLM provider failure returns control to deterministic/final-failure handling; it must not crash the broker.

## 9. Candidate schema

```json
{
  "type": "parameter_rename",
  "changes": [
    {"from": "customerId", "to": "customer_id"}
  ],
  "reason": "Contextual evidence suggests schema rename",
  "confidence": 0.88
}
```

## 10. Candidate ranking

Starting score:

```text
0.30 graph similarity
0.25 historical success
0.20 schema compatibility
0.15 failure match
0.10 provenance quality
- risk penalty
```

Treat weights as configurable experimental parameters.

## 11. Policy

```text
AUTO_ELIGIBLE
APPROVAL_REQUIRED
NEVER_AUTOMATIC
```

## 12. Safety validator

Functions:

```text
validate_action_type()
validate_host()
validate_method()
validate_auth_invariants()
validate_schema()
validate_parameter_types()
validate_idempotency()
validate_policy()
validate_evidence()
validate_retry_budget()
```

## 13. Candidate fallback

If safety rejects candidate:
- persist rejection,
- move to next ranked candidate,
- do not execute,
- do not increment upstream attempt count.

## 14. Corrected attempt

Only one corrected upstream execution is permitted in MVP.

If it succeeds:
- create/update recovery memory,
- update graph,
- record success.

If it fails:
- record second failure,
- do not execute a third upstream request,
- return terminal failure.

## 15. Recovery memory schema

Conceptual fields:

```text
case_id
api_id
endpoint_id
version_id
failure_signature
context_signature
candidate_id
correction
source
model_provider
model_version
validation_status
outcome
confidence
maturity
success_count
failure_count
created_at
last_used_at
```

## 16. Memory promotion

```text
PROPOSED
→ successful validated execution
→ VALIDATED
→ repeated successful reuse
→ ESTABLISHED
```

Negative evidence:
- increments failure count,
- can lower confidence,
- can deprecate a case.

## 17. GraphSAGE

Training inputs should use graph neighborhoods and node/case features.

Initial features may include:
- node type,
- endpoint identity,
- error category,
- parameter metadata,
- schema compatibility,
- outcome statistics.

Never use secret values.

GraphSAGE is an experimental model, not a prerequisite for MVP execution.

## 18. Evaluation API

Evaluation runs should store:
- scenario set,
- baseline,
- model version,
- graph version,
- threshold,
- ranking weights,
- results.

## 19. Testing

### Unit
- classifier,
- candidate generation,
- confidence gate,
- ranking,
- policy,
- safety,
- memory promotion.

### Integration
- broker,
- database,
- graph retrieval,
- embeddings,
- LLM adapter.

### E2E
- controlled API failures,
- successful recovery,
- rejected candidate fallback,
- LLM escalation,
- recovery-memory reuse.

### Security
- SSRF,
- prompt injection,
- secret leakage,
- unsafe actions,
- poisoned memory.

## 20. Required invariants

- LLM output cannot directly execute.
- Maximum two upstream executions.
- Successful normal requests skip recovery.
- LLM fallback is conditional.
- Recovery memory has provenance.
- Secrets never enter graph/vector storage.
