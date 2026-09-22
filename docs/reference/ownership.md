# Ownership map

Generated from each component's `owns` / `not_here` in
`registry/components.yaml`. If this page is wrong, fix the registry.

| Component | Owns | Explicitly does not own |
|-----------|------|--------------------------|
| `aodl` | typed intent IR, compiled plan, observed state, harness catalog, mesh registry, fail-closed validation, typed intent/plan contracts | model selection, routing policy, provider catalogs, runtime execution, runtime implementation, provider execution |
| `dash` | multi-harness phone control surface | execution, intent ownership |
| `evolution-lab` | experiment execution, frozen grouped comparisons, training and search, qualification evidence, experiment search, autoresearch orchestration | activation/deployment state, publication of frozen studies, production runtime, personal traces |
| `flow` | predicted OS/context state, OS prediction, prepare, routine mining | OMP coupling, training logic, agent runtime, token accounting, training loops |
| `frontier-kb` | public research evidence, research evidence, external references | architecture truth, runtime policy, private traces, private user traces, runtime code |
| `hermes-agent-cluster` | agent worker fleet, worker leases and heartbeat, orphan rescheduling | resource placement (Kerdoios owns placement), provider and model inventory, capability trust, measurement |
| `hermes-jev-skills` | Hermes Jev skills | decision ownership |
| `hermes-keel` | Hermes execution kernel | harness catalog |
| `hermes-mesh-keel` | signed transport, authorization | production activation |
| `kerdoios` | resource inventory, hard constraint filtering, quota and capacity ledger, Pareto / portfolio allocation, reservations, placement, provider routing, allocation policy | provider execution, generic model gateway, token measurement, routing policy, agent runtime |
| `kvnloo-skills` | personal Hermes skills | architecture |
| `ripple` | ephemeral intent surface | AODL ownership, execution |
| `rlm` | addressable evidence plane, evidence handles, context virtualization, selected retrieval | provider transport, canonical transcript |
| `sol-pi-hermes` | Action Fusion, ObservationPack | canonical context plane |
| `sol-pi-omp` | Action Fusion, ObservationPack | canonical context plane |
| `tokenomics` | token/cost/latency semantics, verified outcome, context economics, experiment identity, receipt schema, usage attribution, savings reports, reconciliation | OTel transport, provider catalogs, routing, execution, routing policy, provider execution, agent runtime |
| `verified-oss-loop` | contribution and evidence governance | runtime |
| `z0` | registry truth, profiles, generated architecture, install matrix, onboarding | runtime execution, provider catalogs, telemetry semantics |
| `z0archy` | architecture visualization | registry truth |
| `z0evals` | frozen studies, publication, immutable evidence | activated routing policy, training |
| `z0intelligence` | semantic model selection, escalation policy, context resolution, DecisionBackend contracts, local SLM portfolio, cognition receipts, activation (shadow / canary / active), personal policy, routine promotion, specialists | provider daily-quota accounting, RPM/RPD/TPM/TPD, GPU and resource placement, token measurement, coding agent runtime, OS prediction, measurement kernel |

## Promotion is three acts, not one

The word "promotion" was overloaded across three systems. Split:

| Act | Owner | Meaning |
|-----|-------|---------|
| Qualify | `evolution-lab` | the candidate clears frozen experimental gates |
| Publish | `z0evals` | the reproducible study is frozen and published |
| Activate | `z0intelligence` | the qualified policy enters shadow → canary → active |

Evolution Lab may not activate; z0evals may not train or activate;
z0intelligence may not declare a candidate qualified.

## Rule

Every cross-repo fact has one authoritative owner. Other repos may consume,
reference or observe it, but must not silently redefine it. Where an
upstream already owns the fact, z0 delegates — see `sources.md`.

_Generated from `registry/*.yaml`. Do not edit by hand._
