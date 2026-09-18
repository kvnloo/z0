# SYSTEM.md — Zer0 at a glance

Zer0 is a **federation of independently useful repos** united by shared measurement, contracts, and install profiles.

## Planes

| Plane | Components | Role |
|-------|------------|------|
| **Interaction** | OMP (Handsfree, Live, RLM, Jev, CU) | User-facing agent runtime |
| **Decision** | z0intelligence, OpenJev, AODL | Policy, receipts, typed plans |
| **Measurement** | Tokenomics, AgentTrace | Usage, savings, spans |
| **Desktop** | Flow | OS prediction and prepare |
| **Compute** | Kerdoios | Provider routing |
| **Research** | Evolution Lab, frontier-kb | Experiments and evidence |

## Canonical facts

- Registry: `registry/components.yaml`
- Profiles: `registry/profiles.yaml`
- Interfaces: `registry/interfaces.yaml`
- Generated graph: `generated/graph.mmd`

## Non-goals for this repo

- No model weights
- No orchestration engine
- No duplicated package source
- No runtime state (see `zer0-cockpit` for operational UI)
