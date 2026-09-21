---
id: architecture.measurement-plane
title: Measurement plane
scope: [tokenomics]
concepts: [verified-success, token-attribution, receipts, harness-neutral]
status: canonical
---

# Measurement plane

**Owner:** Tokenomics. **Transport:** OpenTelemetry (delegated — Tokenomics owns
the semantics, not the wire format).

Measurement is **harness-neutral**: Hermes, DeepSeek Harness, OMP, local models,
z0intelligence decisions, workers, tools and verifiers all enter the same trace
semantics. There is no harness-specific measurement path.

## Contracts

- `tokenomics.event.v0` — the one accounting row per execution: provider, model,
  request/trace/work-item id, prompt/completion/cache tokens, start/end,
  latency, success, verified outcome, retry state, cost.
- `tokenomics.report.v1` — reconciliation, coverage and verified-task report.
- `z0int.receipt.v1` / `z0int.cognition.receipt.v1` — routing and cognition
  decision receipts (state, eligible candidates, quota, outcome).

Harness-specific rollups such as `omp.session.aggregate` are **adapters**, not
shared contracts, and must not become the measurement spine.

## Rules

1. `execution_completed` and `verified_success` are different facts. Null
   `verified_success` is **not** success.
2. Incremental rows contribute to the measured total; aggregate rows reconcile
   without double-counting.
3. Token/cost claims in docs or by agents require report evidence.
4. Kerdoios reconciles its local quota projection against these receipts; it
   keeps no second usage database.

## Where the numbers come from

Facts that an upstream already owns are discovered, never recopied — see
[generated/sources.md](../../generated/sources.md).
