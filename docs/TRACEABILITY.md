# Requirement Traceability

| Requirement | Architecture | Ticket | Test |
|---|---|---|---|
| FR-001 Request | Broker API | FEAT-003/005 | Integration |
| FR-002 Normalize | Normalizer | FEAT-004 | Unit |
| FR-003 Execute | Execution Engine | FEAT-005 | Integration |
| FR-004 Failure event | Failure Classifier | FEAT-006 | Unit |
| FR-005 Classification | Failure Classifier | FEAT-006 | Unit |
| FR-006 Graph | Contextual Graph | FEAT-007-011 | Graph tests |
| FR-007 Embeddings | Embedding Service | FEAT-012/013 | Retrieval |
| FR-008 Retrieval | Context Retrieval | FEAT-011/013 | Recall@K |
| FR-009 Deterministic candidates | Recovery Engine | FEAT-016/017 | Unit |
| FR-010 Confidence | Confidence Gate | FEAT-018 | Unit |
| FR-011 LLM fallback | LLM subsystem | FEAT-020-024 | Integration |
| FR-012 Structured LLM candidates | Candidate Generator | FEAT-023 | Schema tests |
| FR-013 Provenance | Recovery Memory | FEAT-015/034 | Persistence |
| FR-014 Ranking | Candidate Ranker | FEAT-019 | Ranking tests |
| FR-015 Policy | Policy Engine | FEAT-025 | Policy tests |
| FR-016 Safety | Safety Validator | FEAT-026-029 | Security tests |
| FR-017 Candidate fallback | Recovery Engine | FEAT-030 | Integration |
| FR-018 Max two executions | Recovery Engine | FEAT-032 | E2E |
| FR-019 Outcome | Outcome Store | FEAT-033 | Persistence |
| FR-020 Recovery memory | Memory subsystem | FEAT-034/035 | E2E |
| FR-021 Reuse memory | Retrieval | FEAT-017/036 | E2E |
| FR-022 Maturity | Memory | FEAT-035 | Unit |
| FR-023 Trace UI | Frontend | FEAT-038/039 | UI |
| FR-024 Graph UI | Graph | FEAT-041 | UI |
| FR-025 Evaluation | Evaluation | FEAT-043-053 | Experiment |

## Core research trace

```text
Contextual graph
→ Node2Vec baseline
→ GraphSAGE experiment
→ retrieval
→ candidate ranking
→ recovery outcome
```

## Learning trace

```text
Unknown failure
→ deterministic insufficient
→ LLM proposal
→ safety
→ successful execution
→ recovery memory
→ graph update
→ later retrieval
→ deterministic reuse
```
