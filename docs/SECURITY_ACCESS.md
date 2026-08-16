# Security and Access Specification

## 1. Security principle

**Fail closed for autonomous recovery.**

An AI-generated suggestion is untrusted input.

## 2. Trust boundaries

```text
Client
  ↓ untrusted
Broker API
  ↓ controlled
Recovery Engine
  ↓ controlled
External API / response
  ↓ untrusted
AI provider
  ↓ untrusted output
Safety + Policy Engine
  ↓ trusted execution decision
Upstream API
```

## 3. Assets

- provider API keys,
- OAuth tokens,
- user sessions,
- request/response payloads,
- graph data,
- recovery memory,
- prompts,
- model outputs,
- audit logs.

## 4. Authentication

Use secure token/session authentication.

Provider credentials must be stored using environment/secret management and never hardcoded.

## 5. Authorization

Roles:

| Role | Core access |
|---|---|
| ADMIN | all configuration and security operations |
| DEVELOPER | API registration, execution, recovery inspection |
| VIEWER | read-only history/analytics |

## 6. SSRF

The broker must:
- prefer registered API destinations,
- validate hostnames,
- block private/loopback/link-local destinations by default,
- restrict redirects,
- revalidate redirect destinations,
- prevent arbitrary host selection from model output.

## 7. Prompt injection

External API responses and historical text are untrusted.

Never treat them as system instructions.

LLM prompt sections must clearly separate:
- trusted policy,
- trusted broker metadata,
- untrusted external content,
- untrusted historical content.

## 8. LLM output security

The model cannot:
- execute code,
- select arbitrary host,
- change credentials,
- expand authorization,
- disable TLS,
- bypass policy,
- directly trigger HTTP execution.

Output must conform to a strict candidate schema.

## 9. Candidate policy

### AUTO_ELIGIBLE
Only predefined safe transformation types.

### APPROVAL_REQUIRED
Requires explicit human approval.

### NEVER_AUTOMATIC
Rejected without approval path unless an explicit future policy is defined.

## 10. Idempotency

Automatic corrected execution requires:
- inherently idempotent method, or
- explicit API policy marking operation safe, or
- correctly configured idempotency key.

## 11. Secret handling

Never place secrets in:
- graph nodes,
- graph edges,
- embeddings,
- recovery memory,
- logs,
- prompts.

Redact:
- Authorization,
- cookies,
- tokens,
- API keys,
- passwords,
- obvious PII.

## 12. Graph poisoning

A malicious or incorrect recovery may pollute historical knowledge.

Mitigations:
- provenance,
- source reliability,
- outcome evidence,
- confidence maturity,
- negative outcomes,
- repeated-success requirement for `ESTABLISHED`,
- deprecation support.

## 13. Recovery-memory poisoning

A single LLM success cannot automatically become a high-confidence permanent rule.

Store:
- source,
- model/provider,
- validation,
- outcome,
- reuse count,
- failure count.

## 14. Rate limiting

Apply:
- client rate limit,
- upstream rate limit,
- recovery limit,
- LLM budget,
- request body limits.

## 15. Audit

Record:
- actor,
- request ID,
- recovery ID,
- candidate,
- source,
- evidence IDs,
- policy decision,
- safety decision,
- execution result,
- timestamps.

## 16. Approval workflow

Approval-required candidate:

```text
Candidate
 ↓
Policy = APPROVAL_REQUIRED
 ↓
Create approval request
 ↓
Human approve/deny
 ↓
Safety validation
 ↓
Execution if approved
```

## 17. Security acceptance criteria

SEC-001: AI cannot directly execute requests.

SEC-002: Arbitrary hosts cannot be selected through model output.

SEC-003: Secrets never enter embeddings.

SEC-004: Every executed correction has an audit event.

SEC-005: Rejected candidates are recorded.

SEC-006: Maximum upstream execution count is enforced.

SEC-007: External response content is treated as untrusted.

SEC-008: LLM provider outage does not disable deterministic recovery.

SEC-009: Recovery memory records provenance.

SEC-010: A single LLM success cannot silently create an unrestricted rule.

## 18. Security testing

- SSRF tests,
- prompt injection tests,
- secret redaction tests,
- authorization tests,
- unsafe-candidate tests,
- poisoned-history tests,
- retry abuse tests,
- approval bypass tests.
