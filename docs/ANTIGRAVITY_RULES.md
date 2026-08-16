# Antigravity Implementation Rules

## 1. Source of truth

Use:

```text
PRD
TAD
SECURITY_ACCESS
FRONTEND_SPEC
BACKEND_SPEC
FEATURE_TICKETS
TRACEABILITY
EVALUATION
```

Do not redesign the project independently.

## 2. Core architectural invariants

1. Deterministic recovery is attempted first.
2. LLM is an automatic fallback only when deterministic evidence is insufficient.
3. LLM is a candidate generator, never an execution authority.
4. Every candidate passes ranking, policy and safety.
5. Candidate rejection may move to the next candidate.
6. Maximum total upstream executions in MVP is two.
7. A failed corrected execution is terminal in MVP.
8. Successful novel LLM recovery becomes recovery memory with provenance.
9. One successful LLM case does not automatically become an unrestricted permanent rule.
10. Graph learning must materially participate in contextual retrieval/evaluation.
11. CNN is not to be added without an explicit experiment justifying it.
12. SDK/productization is future scope.

## 3. Implementation discipline

Before coding a feature:
1. locate ticket,
2. read dependencies,
3. inspect relevant requirement,
4. inspect architecture,
5. inspect security rules,
6. implement,
7. test,
8. update documentation if architecture changed.

## 4. LLM rule

If deterministic recovery produces a candidate above threshold:
- do not invoke LLM.

If deterministic evidence is insufficient:
- invoke LLM if the failure/context is valid and policy allows reasoning.

If LLM is unavailable:
- continue deterministic path or return controlled failure.

## 5. Recovery memory rule

Store:
- situation,
- context,
- candidate,
- provenance,
- validation,
- outcome,
- model information,
- confidence.

Promote:
```text
PROPOSED → VALIDATED → ESTABLISHED
```

Do not promote a failed candidate.

## 6. Security

Never:
- execute arbitrary model output,
- accept arbitrary host changes,
- disable TLS,
- expose secrets,
- expand authorization,
- execute arbitrary code.

## 7. Research integrity

Do not fabricate:
- recovery rates,
- accuracy,
- benchmark results,
- LLM escalation reduction,
- GraphSAGE improvements.

All claims must come from executed experiments.

## 8. Architecture changes

If a change affects architecture, update:
- TAD,
- affected specification,
- tickets,
- traceability,
- README.

## 9. Final MVP verification

Antigravity must demonstrate:

```text
Original request
→ real failure
→ graph context
→ deterministic attempt
→ confidence gate
→ optional LLM escalation
→ candidate ranking
→ safety
→ corrected attempt
→ outcome
→ recovery memory
→ graph update
→ future deterministic reuse
```
