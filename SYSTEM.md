# SYSTEM.md — Zer0 at a glance

Zer0 is a **federation of independently useful repos** united by shared
contracts, measurement and install profiles. No single harness is its centre.

## Entity classes

The almanac distinguishes things that are routinely conflated:

| Class | File | Installable | Meaning |
|-------|------|-------------|---------|
| **owned component** | `registry/components.yaml` | yes | a Zer0-owned semantic responsibility |
| **upstream system** | `registry/upstreams.yaml` | no | an external system we depend on or execute through |
| **delegated source** | `registry/sources.yaml` | no | an authority we *discover* facts from, never recopy |
| **contract** | `registry/interfaces.yaml` | n/a | a cross-system interface |
| **adapter** | `registry/interfaces.yaml` | n/a | an implementation-specific wire surface, named to its harness |

A repository we contribute to is not automatically supported infrastructure.

## Planes

| Plane | Owned components | Role |
|-------|------------------|------|
| **Interaction** | Dash, Ripple | human/agent surfaces — not executors |
| **Contracts** | AODL | typed intent, compiled plan, observed state, harness catalog |
| **Cognition** | z0intelligence, hermes-jev-skills, kvnloo-skills | selection, escalation, activation |
| **Context** | RLM, sol-pi-omp, sol-pi-hermes, Flow | evidence addressing and context compilation |
| **Measurement** | Tokenomics | usage, cost, latency, verified outcome |
| **Resources** | Kerdoios | inventory, quota, Pareto placement |
| **Evaluation** | Evolution Lab, z0evals | qualify → publish |
| **Research** | frontier-kb, z0archy | public evidence, architecture view |
| **Governance** | verified-oss-loop | contribution and evidence protocol |
| **Execution** | *(upstream)* Hermes · DeepSeek Harness · OMP | the harnesses z0 executes *via* |

## Status is two facts, not one

- **architecture_status** — where the *design* currently lives
  (`merged` / `open_pr` / `branch_only` / `local_only` / `planned` / `legacy` / `superseded`).
- **implementation_status** — whether it *runs* (`live` / `canary` /
  `experimental` / `pre_activation` / `idea`).

`tested_ref` is a third, separate fact: the ref last validated for install. A
stale `tested_ref` does not make the design stale, and a recent SHA does not make
the design canonical. **Upstream heads are never stored** — run
`./z0 registry doctor` to discover them live.

## Canonical facts

- Components: `registry/components.yaml`
- Upstreams: `registry/upstreams.yaml`
- Delegated sources: `registry/sources.yaml`
- Interfaces: `registry/interfaces.yaml`
- Profiles: `registry/profiles.yaml`
- Generated: `generated/almanac.json`, `generated/graph.mmd`

## Non-goals for this repo

- No model weights
- No orchestration engine
- No duplicated package source
- No provider gateway or model catalog
- No runtime state, and no cached upstream snapshot presented as truth
