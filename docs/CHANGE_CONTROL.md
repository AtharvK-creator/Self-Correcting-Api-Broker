# Change Control

This document prevents unnecessary approval loops while protecting architecture.

## Change levels

### LEVEL 0 — Implementation detail
Examples:
- variable/class names,
- file organization inside an approved module,
- helper functions,
- test structure,
- UI micro-layout,
- internal refactoring that preserves contracts.

**Action:** Antigravity decides autonomously.

### LEVEL 1 — Local design decision
Examples:
- choosing a library already compatible with the TAD,
- implementation algorithm where the TAD permits alternatives,
- indexing strategy that does not change contracts.

**Action:** Antigravity decides autonomously and documents the choice.

### LEVEL 2 — Cross-module implementation
Examples:
- adding a service required by an existing ticket,
- adding a repository,
- adding an adapter already specified by the architecture.

**Action:** Antigravity proceeds autonomously if all locked invariants remain satisfied.

### LEVEL 3 — Architectural change
Examples:
- changing database authority,
- changing the recovery state machine,
- changing maximum upstream attempts,
- making the LLM mandatory,
- allowing LLM output to execute directly,
- changing the three policy tiers,
- replacing the graph architecture,
- adding a major infrastructure dependency.

**Action:** STOP and request human review.

### LEVEL 4 — Research-definition change
Examples:
- changing the research question,
- changing evaluation methodology,
- changing baselines,
- changing success metrics,
- changing what constitutes evidence for a research claim.

**Action:** STOP and request human review.

## Conflict resolution

If two documents appear to conflict:
1. Do not silently choose.
2. Identify the exact conflict.
3. Prefer `FINAL_DECISIONS.md` for decisions explicitly marked final.
4. If still unresolved, stop only for that conflict.

## Approval-loop rule

Do NOT ask the user "Is this okay?" for routine implementation decisions.

Proceed autonomously unless:
- a Level 3/4 change is required,
- a security invariant would be violated,
- a required external dependency is unavailable/incompatible,
- credentials/permissions are genuinely required from the user,
- the specification is materially ambiguous.

## Reporting

At the end of each autonomous work block, report:
- completed tickets,
- files changed,
- tests run,
- failures/blockers,
- architecture/security deviations,
- next ticket.

Do not request approval merely to continue to the next ticket.
