# Ownership map

Generated from each component's `owns` / `not_here` in
`registry/components.yaml`. If this page is wrong, fix the registry.

| Component | Owns | Explicitly does not own |
|-----------|------|--------------------------|
| `aodl` | typed intent IR, compiled plan, observed state, harness catalog, mesh registry, fail-closed validation | model selection, routing policy, provider catalogs, runtime execution |
| `dash` | multi-harness phone control surface | execution, intent ownership |
| `evolution-lab` | experiment execution, frozen grouped comparisons, training and search, qualification evidence | activation/deployment state, publication of frozen studies |
| `flow` | predicted OS/context state | OMP coupling, training logic |
| `frontier-kb` | public research evidence | architecture truth, runtime policy, private traces |
| `hermes-jev-skills` | Hermes Jev skills | decision ownership |
| `hermes-keel` | Hermes execution kernel | harness catalog |
| `hermes-mesh-keel` | signed transport, authorization | production activation |
| `kerdoios` | resource inventory, hard constraint filtering, quota and capacity ledger, Pareto / portfolio allocation, reservations, placement | provider execution, generic model gateway, token measurement, routing policy |
| `kvnloo-skills` | personal Hermes skills | architecture |
| `ripple` | ephemeral intent surface | AODL ownership, execution |
| `rlm` | addressable evidence plane, evidence handles, context virtualization, selected retrieval | provider transport, canonical transcript |
| `sol-pi-hermes` | Action Fusion, ObservationPack | canonical context plane |
| `sol-pi-omp` | Action Fusion, ObservationPack | canonical context plane |
| `tokenomics` | token/cost/latency semantics, verified outcome, context economics, experiment identity, receipt schema | OTel transport, provider catalogs, routing, execution |
| `verified-oss-loop` | contribution and evidence governance | runtime |
| `z0` | registry truth, profiles, generated architecture, install matrix, onboarding | runtime execution, provider catalogs, telemetry semantics |
| `z0archy` | architecture visualization | registry truth |
| `z0evals` | frozen studies, publication, immutable evidence | activated routing policy, training |
| `z0intelligence` | semantic model selection, escalation policy, context resolution, DecisionBackend contracts, local SLM portfolio, cognition receipts, activation (shadow / canary / active) | provider daily-quota accounting, RPM/RPD/TPM/TPD, GPU and resource placement, token measurement |

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
