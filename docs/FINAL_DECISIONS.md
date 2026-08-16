# Final Architecture Decisions

This file records decisions that supersede earlier drafts.

1. Deterministic recovery is the default.
2. LLM fallback is automatic only when deterministic evidence is insufficient.
3. LLM output is never executed directly.
4. Recovery memory stores the full situation + solution + provenance + outcome.
5. Successful LLM-discovered cases become VALIDATED knowledge.
6. Repeated successful reuse can promote cases to ESTABLISHED.
7. Candidate rejection happens before execution and may move to the next candidate.
8. Maximum total upstream executions in MVP = 2.
9. A corrected execution failure is terminal in MVP.
10. Three policy tiers are mandatory: AUTO_ELIGIBLE, APPROVAL_REQUIRED, NEVER_AUTOMATIC.
11. PostgreSQL + pgvector is the authoritative MVP data layer.
12. NetworkX is analytical/in-process only.
13. Node2Vec is the initial graph embedding baseline.
14. GraphSAGE is the GNN research extension.
15. CNN is excluded from the core architecture.
16. SDK, CLI, VS Code extension and other productization are future scope.
17. Redis, Kafka, service mesh, Kubernetes and dedicated graph DB are not MVP requirements.
18. All research claims must be experimentally demonstrated.

19. Antigravity should operate autonomously under `MASTER_PROMPT.md`; routine implementation plans do not require human approval.
20. Human review is required only for Level 3 architectural changes, Level 4 research-definition changes, security violations, genuine external blockers, or material ambiguity.
