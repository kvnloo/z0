---
id: architecture.measurement-plane
title: Measurement plane
scope: [tokenomics, oh-my-pi, z0intelligence]
concepts: [verified-success, token-attribution, receipts]
status: canonical
---

# Measurement plane

**Owner:** Tokenomics

## Events

- `tokenomics.event.v0` — incremental usage from OMP, workers, verifiers
- `omp.session.aggregate` — session rollup for reconciliation (avoid double-count)

## Reports

- `tokenomics.report.v1` — savings, reconciliation, token coverage

## Rules

1. Incremental rows contribute to `actual_frontier_tokens`.
2. Aggregate rows reconcile but do not double-count.
3. Token/cost claims in docs or agents require report evidence.
