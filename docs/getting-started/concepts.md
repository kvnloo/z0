---
id: getting-started.concepts
title: Core concepts
scope: [z0]
concepts: [verified-success, receipts, profiles]
status: canonical
---

# Concepts

## Verified success

Claims of "it worked" need a verifier — not just model prose. Tokenomics tracks verified outcomes separately from raw usage.

## Decision receipts

`z0int.decision_receipt.v1` records routing and policy choices for audit and replay.

## Profiles vs package manager

Profiles are **curated component sets**. `z0 init` clones repos and runs each component's native setup — it does not replace npm/pip.

## Three doc levels

- **L0** — component README (30 seconds)
- **L1** — `ARCHITECTURE.md` (5 minutes)
- **L2** — component `docs/` (deep reference)

Central `z0` docs are L0–L1 only.
