---
id: architecture.local-cognition
title: Local cognition portfolio
scope: [z0, z0intelligence, kerdoios, frontier-kb]
concepts: [cognition, tool-calling, placement, ownership]
status: canonical
---

# Local cognition portfolio

The local cognition portfolio is the set of small models that answer a turn in the
Zer0 stack: JEV/OpenJev decision heads, tiny action specialists, a semantic
orchestrator, and a general local fallback. This page is the z0 architecture view.
It is **not** the model list and **not** the runtime registry.

Generated artifact: [`generated/cognition-portfolio.md`](../generated/cognition-portfolio.md)
(and `generated/cognition-flow.mmd`). Never edit either by hand — run `./z0 docs generate`.

## Dataflow and owners

AODL → z0intelligence → local cognition (JEV / tiny specialists / orchestrator / general SLM)
→ Kerdoios → OMP/Hermes → Tokenomics → Evolution Lab → frontier-kb.

| Stage | Owner | Responsibility |
|-------|-------|----------------|
| AODL | Contracts | Typed intent and plan contract; never runtime execution |
| z0intelligence | Personal Intelligence | Which capability/role the turn needs, role defaults, decision receipts, promotion state |
| Local cognition | Personal Intelligence (decision heads with OpenJev) | Serve the selected local role |
| Kerdoios | Compute | Given an already-selected capability and the current machine state, whether it can run locally now |
| OMP / Hermes | Runtime / Interaction | Execute the turn and the tools |
| Tokenomics | Measurement | Usage, cost, latency and verified-task economics |
| Evolution Lab | Research | Experiment search, candidate lineages, promotion gates |
| frontier-kb | Research | External evidence and falsifiable hypotheses |

The stage map and the owner of each stage are z0 registry data
(`registry/cognition.yaml`).

## What z0 does not own

The **model list** — model identity, roles, licences, gated access, benchmarks,
local measurements, promotion state and the serving map — is canonical in
z0intelligence:

- `manifests/local_cognition.v1.json` (source of truth)
- `z0int cognition manifest --json` (load it)
- `z0int cognition roles --json` (role view)

z0 reads that manifest at render time and never commits it. Duplicated model data
fails `./scripts/cognition-check`.

```bash
./z0 cognition portfolio          # stage map + owners, plus live model rows when resolvable
./z0 cognition portfolio --json   # machine-readable view
```

## Boundaries

- **z0intelligence** decides semantic suitability: which capability/role the turn
  needs and which model defaults to it.
- **Kerdoios** decides resource placement for an already-selected capability —
  runtime, quant, co-residency, context and concurrency caps. It never decides
  semantics.
- **frontier-kb** holds external evidence, not runtime state.
- Promotion state and the serving map stay in z0intelligence. z0 carries neither.
