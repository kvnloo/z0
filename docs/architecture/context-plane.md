---
id: architecture.context-plane
title: Context and evidence plane
scope: [rlm, sol-pi-omp, sol-pi-hermes, flow, z0intelligence]
concepts: [context, evidence, rlm, receipts]
status: canonical
---

# Context and evidence plane

This plane existed in the system long before it existed in the docs. It answers:
*what does the model actually see, and how do we get it back?*

## The split

| Layer | Holds | Authority |
|-------|-------|-----------|
| **Canonical transcript** | the audit/recovery record of what happened | the harness session log — the truth of record |
| **Evidence plane (RLM)** | addressable raw evidence, rehydratable on demand | RLM (`rlm.evidence_handle.v0`) |
| **Semantic receipts** | causal consequences: decisions, outcomes, costs | z0intelligence + Tokenomics |
| **Cognitive state** | the provider-visible compiled state for *this* turn | z0intelligence (context resolution) |
| **Selected retrieval** | which evidence is rehydrated into the window | z0intelligence |

The harness extension replaces the **provider-visible** context without
destroying the canonical transcript. Nothing in this plane may rewrite history.

## Lifecycle

Evidence moves through `LIVE → RECEIPT → EXTERNAL → ARCHIVED`. A handle stays
addressable after its payload leaves the window.

## Why it is not an OMP feature

RLM has no repository of its own. It currently lives as branches on the OMP fork,
which carries **102 local branches across six checkouts** and has no designated
canonical lineage. Until one lineage is chosen, any description of "the RLM
design" describes one worktree, not a settled contract. The registry records
`rlm` with `architecture_status: branch_only` for exactly this reason.

z0-specific behaviour must sit behind extension seams so the fork does not
become the architecture. The shared contract is `harness.execution.v0`; a
harness adapter implements it.

## SoL-Pi

There is **no canonical `sol-pi` component**. SoL-Pi is a mechanism family:
Action Fusion, observation packing/reduction, verified reduction, and context
economics. It is implemented in `sol-pi-omp` and `sol-pi-hermes`, both of which
`implements: sol-pi` (the upstream research fork) rather than owning a shared
contract.

The measurement gap is real and open: Tokenomics does not yet carry enough
causal/context lineage to *verify* a claimed saving. Until it does, context
optimization must not be reported as verified.

## Flow

Flow predicts OS/context state and `emits_contract` toward z0intelligence. The
OMP coupling in the original registry entry was incidental and has been removed;
the capability is harness-neutral.
