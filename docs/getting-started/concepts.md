---
id: getting-started.concepts
title: Core concepts
scope: [z0]
concepts: [verified-success, receipts, profiles, promotion]
status: canonical
---

# Concepts

## Verified success

Claims of "it worked" need a verifier — not model prose. Tokenomics tracks
verified outcomes separately from raw usage, and a null `verified_success` is
**not** success.

## Decision receipts

`z0int.decision_receipt.v1` and `z0int.cognition.receipt.v1` record routing and
cognition choices — state, eligible candidates, quota, prediction, outcome — for
audit and replay. That record is the training evidence for progressively cheaper
routing.

## Qualify, publish, activate

Three acts that used to share the word "promotion":

| Act | Owner |
|-----|-------|
| Qualify | `evolution-lab` — clears the frozen experimental gates |
| Publish | `z0evals` — freezes the reproducible study |
| Activate | `z0intelligence` — shadow → canary → active |

No one repo holds all three.

## Entity classes

An **owned component** is installable. An **upstream system** is a harness or
external project you depend on — never installable. A **delegated source** is an
authority z0 discovers facts from and never recopies. See
[SYSTEM.md](../../SYSTEM.md).

## Profiles vs package manager

Profiles are curated capability sets. `z0 init` clones repos and runs each
component's native setup — it does not replace npm/pip.

## Three doc levels

- **L0** — component README (30 seconds)
- **L1** — `ARCHITECTURE.md` / `SYSTEM.md` (5 minutes)
- **L2** — component `docs/` (deep reference)

Central `z0` docs are L0–L1 only. Per-component pages under `docs/components/`
are generated from the registry.
