---
id: getting-started.what-is-zer0
title: What is Zer0?
scope: [z0]
concepts: [ecosystem, profiles, measurement, harnesses]
status: canonical
---

# What is Zer0?

Zer0 is personal AI infrastructure organized as **independently useful
components** with shared contracts and measurement.

It is not a runtime. It is not a model catalog. It is not a provider gateway.

## What it is made of

- **Execution harnesses** — Hermes, DeepSeek Harness and OMP are peers you
  *execute through*. None is mandatory.
- **Contracts** — AODL owns typed intent, compiled plan, observed state, and the
  harness catalog.
- **Cognition** — z0intelligence selects, escalates and activates. JEV/NanoJev/
  OpenJev are implementations behind its DecisionBackend contract.
- **Context** — RLM is an addressable evidence plane, not a harness feature.
- **Measurement** — Tokenomics owns usage, cost, latency and verified outcome.
- **Resources** — Kerdoios places work; it does not execute providers.
- **Evaluation** — Evolution Lab qualifies, z0evals publishes, z0intelligence
  activates.

## What z0 the repo is

`kvnloo/z0` is the **federated almanac**: the reconciled map, capability
profiles, contract registry and generated architecture. It stores Zer0
relationships and policy; it fetches upstream facts from whoever already owns
them.

See [SYSTEM.md](../../SYSTEM.md) for the entity classes and the plane table.
