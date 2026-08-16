# Feature Ticket List

## EPIC-00 — Foundation

### FEAT-001 Repository and development environment
P0
- Docker Compose
- `.env.example`
- backend/frontend structure
- health endpoints

### FEAT-002 PostgreSQL + migrations
P0
- SQLAlchemy
- Alembic
- core tables
- test database

## EPIC-01 — Broker

### FEAT-003 API registry
P0
- APIs/endpoints/versions/schemas

### FEAT-004 Request normalization
P0
- canonical request context

### FEAT-005 Upstream execution engine
P0
- HTTPX
- timeout
- redirect controls
- telemetry

### FEAT-006 Failure taxonomy
P0
- normalized failure events

## EPIC-02 — Contextual Graph

### FEAT-007 Graph node model
P0

### FEAT-008 Graph edge model
P0

### FEAT-009 Context builder
P0

### FEAT-010 Graph construction
P0

### FEAT-011 Graph neighborhood retrieval
P0

## EPIC-03 — Embeddings

### FEAT-012 Node2Vec baseline
P0

### FEAT-013 pgvector storage/retrieval
P0

### FEAT-014 GraphSAGE experiment
P1
- only after Node2Vec baseline is working
- compare retrieval/ranking performance

## EPIC-04 — Deterministic Recovery

### FEAT-015 Recovery-memory schema
P0

### FEAT-016 Deterministic candidate templates
P0

### FEAT-017 Historical candidate retrieval
P0

### FEAT-018 Confidence/evidence gate
P0

### FEAT-019 Candidate ranking
P0

## EPIC-05 — LLM Fallback

### FEAT-020 Provider abstraction
P0

### FEAT-021 Gemini adapter
P1

### FEAT-022 Groq adapter
P1

### FEAT-023 Structured LLM candidate generation
P0

### FEAT-024 LLM escalation policy
P0
- invoke only when deterministic evidence is insufficient

## EPIC-06 — Safety

### FEAT-025 Three-tier policy engine
P0

### FEAT-026 Deterministic safety validator
P0

### FEAT-027 SSRF controls
P0

### FEAT-028 Secret redaction
P0

### FEAT-029 Idempotency checks
P0

### FEAT-030 Candidate rejection fallback
P0

## EPIC-07 — Recovery

### FEAT-031 Recovery execution state machine
P0

### FEAT-032 Maximum-two-attempt enforcement
P0

### FEAT-033 Recovery outcome recorder
P0

### FEAT-034 Recovery-memory promotion
P0

### FEAT-035 Knowledge confidence/maturity
P1

### FEAT-036 Graph update after successful recovery
P0

## EPIC-08 — Frontend

### FEAT-037 Broker console
P1

### FEAT-038 Request trace
P1

### FEAT-039 Recovery detail
P1

### FEAT-040 Recovery-memory explorer
P1

### FEAT-041 Graph explorer
P1

### FEAT-042 Analytics dashboard
P1

## EPIC-09 — Evaluation

### FEAT-043 Controlled failure laboratory
P0

### FEAT-044 Baseline: ordinary client
P0

### FEAT-045 Baseline: static retry
P0

### FEAT-046 Baseline: rule-based recovery
P0

### FEAT-047 LLM-only recovery baseline
P1

### FEAT-048 Proposed graph + deterministic + LLM fallback
P0

### FEAT-049 Retrieval metrics
P0

### FEAT-050 Recovery metrics
P0

### FEAT-051 LLM escalation-rate metric
P0

### FEAT-052 Ablation study
P0

### FEAT-053 Blind holdout evaluation
P0

## EPIC-10 — Hardening

### FEAT-054 Security test suite
P0

### FEAT-055 Failure-injection reproducibility
P0

### FEAT-056 Performance tests
P1

### FEAT-057 Documentation consistency check
P1

## Recommended order

```text
001 → 002 → 003 → 004 → 005 → 006
→ 007 → 008 → 009 → 010 → 011
→ 012 → 013
→ 015 → 016 → 017 → 018 → 019
→ 025 → 026 → 027 → 028 → 029 → 030
→ 031 → 032 → 033 → 034 → 036
→ 020 → 023 → 024
→ 043 → 044 → 045 → 046 → 048
→ 049 → 050 → 051 → 052 → 053
→ 054 → 055
→ 014 (GraphSAGE research extension)
→ frontend tickets
```

## Definition of done

A ticket is complete only when:
- implementation exists,
- acceptance criteria pass,
- tests exist,
- security impact is checked,
- relevant documentation remains consistent.
