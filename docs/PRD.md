# Product Requirements Document

## 1. Product

**Self-Correcting API Broker via Contextual Graph Learning**

## 2. Product vision

Build a reliability layer that can recover selected external API failures using contextual knowledge while remaining bounded, auditable and safe.

## 3. Problem

External APIs fail or evolve because of:
- parameter changes,
- schema changes,
- endpoint/version changes,
- transient failures,
- throttling,
- unexpected response formats,
- integration drift.

Traditional clients commonly use static retry logic and manually maintained mappings. These approaches do not accumulate structured recovery knowledge.

## 4. Target users

- backend developers,
- API integration engineers,
- platform/reliability engineers,
- researchers studying resilient tool/API execution.

## 5. Goals

- execute normal API requests with minimal added latency,
- classify failures,
- construct contextual graph evidence,
- retrieve similar recovery situations,
- attempt deterministic recovery first,
- invoke an LLM only when deterministic evidence is insufficient,
- rank and safety-check all candidates,
- execute at most one corrected upstream attempt in MVP,
- persist successful recovery cases,
- reuse validated historical cases,
- measure whether graph context improves recovery.

## 6. Non-goals

- full enterprise API management,
- unrestricted autonomous agents,
- arbitrary code execution,
- arbitrary host discovery,
- unlimited retries,
- replacing provider documentation,
- SDK/extension productization in MVP,
- CNN-based modeling without evidence of value.

## 7. Users and core stories

### US-001
As a developer, I can send a request through the broker to a registered API.

### US-002
As a developer, I can inspect why a request failed.

### US-003
As a developer, I can see whether deterministic recovery or LLM fallback was used.

### US-004
As a developer, I can inspect the context and evidence behind a correction.

### US-005
As a developer, I can configure recovery policy.

### US-006
As a researcher, I can reproduce failures and compare recovery strategies.

### US-007
As an evaluator, I can see whether an LLM-discovered correction becomes reusable historical knowledge.

## 8. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-001 | Accept authenticated requests for registered APIs | P0 |
| FR-002 | Normalize request context | P0 |
| FR-003 | Execute upstream request | P0 |
| FR-004 | Capture structured failure event | P0 |
| FR-005 | Classify failure | P0 |
| FR-006 | Build/update contextual graph | P0 |
| FR-007 | Generate graph embeddings | P0 |
| FR-008 | Retrieve similar contextual cases | P0 |
| FR-009 | Generate deterministic candidates | P0 |
| FR-010 | Calculate evidence/confidence | P0 |
| FR-011 | Escalate to LLM when deterministic evidence is insufficient | P0 |
| FR-012 | Generate structured LLM candidates | P0 |
| FR-013 | Track candidate provenance | P0 |
| FR-014 | Rank candidate pool | P0 |
| FR-015 | Apply three-tier recovery policy | P0 |
| FR-016 | Apply deterministic safety validation | P0 |
| FR-017 | Try next ranked candidate after pre-execution rejection | P0 |
| FR-018 | Execute maximum one corrected upstream attempt in MVP | P0 |
| FR-019 | Record final outcome and audit event | P0 |
| FR-020 | Store successful novel recovery as recovery memory | P0 |
| FR-021 | Reuse validated recovery memory in future deterministic retrieval | P0 |
| FR-022 | Track recovery knowledge maturity/confidence | P1 |
| FR-023 | Provide request/recovery trace UI | P1 |
| FR-024 | Provide graph/context inspection | P1 |
| FR-025 | Provide evaluation dashboard | P1 |

## 9. Failure taxonomy

Initial classes:
- UNKNOWN_PARAMETER
- INVALID_PARAMETER
- SCHEMA_MISMATCH
- ENDPOINT_NOT_FOUND
- VERSION_MISMATCH
- RATE_LIMIT
- TIMEOUT
- CONNECTION_FAILURE
- MALFORMED_RESPONSE
- UPSTREAM_5XX
- AUTHENTICATION_FAILURE
- AUTHORIZATION_FAILURE
- POLICY_REJECTION
- UNKNOWN

## 10. Recovery policy

### AUTO_ELIGIBLE
Safe, bounded, evidence-backed changes such as:
- known parameter rename,
- removal of optional unsupported field,
- provider-approved retry-after,
- known schema-compatible field mapping.

### APPROVAL_REQUIRED
Potentially valid but consequential:
- credential refresh,
- endpoint migration,
- non-trivial semantic payload transformation,
- other explicitly configured risky operations.

### NEVER_AUTOMATIC
Always reject automatically:
- destination host change,
- disabling TLS verification,
- credential disclosure,
- authorization scope expansion,
- arbitrary code execution,
- unregistered endpoint redirection.

## 11. Confidence gate

The deterministic engine must output:
- candidate(s),
- evidence score,
- provenance,
- compatibility checks.

If at least one candidate meets configured minimum thresholds, the LLM is not invoked.

If no candidate meets the threshold but the failure/context is valid and eligible for reasoning, the broker may invoke the configured LLM fallback.

If the context itself is invalid/unsafe, do not invoke the LLM merely to guess.

## 12. LLM fallback requirements

- structured JSON output,
- provider abstraction,
- timeout,
- token/cost budget,
- no arbitrary tool execution,
- candidate provenance marked `LLM`,
- model/version recorded,
- all candidates go through the same ranking and safety gates.

## 13. Recovery memory

On successful LLM-assisted recovery, store:
- normalized API identity,
- endpoint/version,
- failure signature,
- contextual graph identifiers,
- request/schema signature,
- candidate transformation,
- evidence,
- source,
- model/provider if applicable,
- safety results,
- outcome,
- timestamps,
- reuse count,
- failure count.

Do not store secrets.

## 14. Knowledge maturity

Suggested states:

```text
PROPOSED
VALIDATED
ESTABLISHED
DEPRECATED
```

A candidate becomes `VALIDATED` only after successful execution and validation.

`ESTABLISHED` requires repeated successful reuse or a configured evidence threshold.

## 15. MVP execution rule

Total upstream executions per request: maximum 2.

Candidate rejection before execution does not consume an attempt.

If the corrected execution fails, the MVP terminates recovery for that request and records the new failure.

## 16. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-001 | Successful requests bypass recovery pipeline |
| NFR-002 | Recovery attempts are bounded |
| NFR-003 | No autonomous action bypasses safety validation |
| NFR-004 | Secrets are excluded from graph/vector records |
| NFR-005 | Every recovery decision is auditable |
| NFR-006 | LLM can be disabled without disabling deterministic recovery |
| NFR-007 | LLM failure degrades gracefully |
| NFR-008 | Recovery knowledge has provenance |
| NFR-009 | Experiments are reproducible |
| NFR-010 | Core recovery path is automated-testable |

## 17. Success criteria

MVP must demonstrate at least one controlled failure where:
1. original request fails,
2. deterministic retrieval either succeeds or is shown insufficient,
3. LLM fallback can be invoked when appropriate,
4. a candidate is safely validated,
5. corrected attempt produces a measurable outcome,
6. successful novel recovery becomes reusable memory,
7. a later similar failure can use that memory deterministically.

## 18. Research contribution

Do not claim that API self-correction, graph embeddings, or LLM reasoning are individually novel.

Evaluate the combined architecture:
- contextual graph representation,
- graph learning,
- recovery memory,
- confidence-gated LLM fallback,
- deterministic safety,
- bounded execution.
