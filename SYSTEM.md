# SYSTEM.md — Zer0 at a glance

Zer0 is a **federation of independently useful repos** united by shared measurement, contracts, install profiles, execution harnesses, reusable mechanisms, and evidence-gated evolution.

## Planes

| Plane | Components | Role |
|-------|------------|------|
| **Interaction** | OMP (Handsfree, Live, RLM, Jev, CU) | User-facing agent runtime |
| **Decision** | z0intelligence, AODL | Policy, receipts, typed plans |
| **Measurement** | Tokenomics, AgentTrace | Usage, savings, spans |
| **Desktop** | Flow | OS prediction and prepare |
| **Compute** | Kerdoios | Provider routing |
| **Research** | Evolution Lab, frontier-kb | Experiments and evidence |

Jev/OpenJev is a reusable bounded-decision **mechanism**, not a separate installable component. Hermes, DeepSeek, Codex and Pi are execution **harnesses**, not component dependencies.

## Canonical facts

- Components: `registry/components.yaml`
- Harnesses: `registry/harnesses.yaml`
- Mechanisms: `registry/mechanisms.yaml`
- Interfaces: `registry/interfaces.yaml`
- Lifecycles: `registry/lifecycles.yaml`
- Profiles: `registry/profiles.yaml`
- Generated graph: `generated/graph.mmd`

## Non-goals for this repo

- No model weights
- No orchestration engine
- No duplicated package source
- No runtime state (z0archy may project observed state, but it does not make z0 a runtime)
