# Evaluation Specification

## 1. Research question

Can contextual graph learning and accumulated recovery memory improve API failure recovery while reducing unnecessary LLM invocation?

## 2. Hypotheses

### H1
Graph-contextual recovery improves recovery rate over static retry and rule-only baselines.

### H2
Graph-based retrieval improves recovery-candidate ranking.

### H3
Validated recovery memory reduces LLM escalation rate on repeated/similar situations.

### H4
GraphSAGE improves contextual retrieval/ranking over the Node2Vec baseline on appropriate test data.

No hypothesis should be treated as proven until experimentally measured.

## 3. Baselines

B0 — ordinary client.

B1 — static retry.

B2 — rule-based recovery.

B3 — LLM-only recovery.

P1 — proposed:
- graph context,
- deterministic recovery,
- confidence gate,
- optional LLM fallback,
- safety,
- recovery memory.

## 4. Scenario laboratory

Controlled services should produce deterministic:
- unknown parameter,
- schema mismatch,
- endpoint/version change,
- timeout,
- 429,
- 5xx,
- malformed response,
- authentication/authorization failure,
- unsafe candidate situations.

Not all failures should be recoverable.

## 5. Core metrics

### Recovery Rate
successful recoveries / recoverable failures

### Correction Precision
correct corrections / executed corrections

### Unsafe Correction Rate
unsafe corrections executed / correction executions

Target: as close to zero as possible.

### LLM Escalation Rate

LLM invocations / eligible failures

### LLM Avoidance Rate

eligible failures solved deterministically / eligible failures

### Recovery Memory Reuse Rate

successful recoveries using previously stored cases / successful recoveries

### Retrieval Recall@K
Whether relevant recovery cases occur in top-K.

### MRR
Mean reciprocal rank of relevant contextual case.

### Latency
Compare:
- normal request,
- deterministic recovery,
- LLM fallback recovery.

### Cost
Measure model calls and token usage where available.

## 6. Critical experiment

Run an initial population of failure scenarios.

Then create a blind holdout containing similar-but-not-identical situations.

Train/build recovery memory only from the development set.

Do not seed the holdout with its answer.

Compare:

```text
Before recovery memory
vs
After recovery memory
```

Measure whether LLM escalation decreases while recovery remains correct.

## 7. Ablation

Compare:

```text
A: no graph
B: graph without embeddings
C: Node2Vec
D: GraphSAGE
E: graph + memory
F: graph + memory + LLM fallback
```

## 8. Recovery-memory experiment

Track a case through:

```text
First occurrence
→ deterministic insufficient
→ LLM
→ successful correction
→ VALIDATED memory

Second similar occurrence
→ retrieval
→ deterministic reuse

Repeated successful uses
→ ESTABLISHED
```

Measure:
- success,
- confidence,
- latency,
- LLM usage.

## 9. GraphSAGE experiment

Use GraphSAGE only after Node2Vec baseline.

Compare:
- retrieval Recall@K,
- MRR,
- candidate ranking accuracy,
- recovery rate.

If GraphSAGE does not improve results, report that honestly.

## 10. Statistical discipline

Use:
- repeated trials,
- fixed scenario definitions,
- model/version tracking,
- graph/version tracking,
- mean/median,
- variation/confidence intervals where appropriate.

Do not cherry-pick.

## 11. Research limitations

- small API ecosystem,
- controlled failure distribution,
- external API drift,
- limited recovery history,
- model nondeterminism,
- possible domain-specific graph patterns.

## 12. Final evidence required

The final report should answer:

1. Does graph context improve recovery?
2. Does graph learning outperform the chosen baseline?
3. How often is LLM escalation required?
4. Does recovery memory reduce future LLM calls?
5. Does the safety layer prevent unsafe corrections?
6. What latency/cost does recovery introduce?
