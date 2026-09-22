# Evidence dependencies

Epistemic edges: why a semantic relationship is believed. These attach the
retrieval recipe and invalidators to a claim; they are not data-flow edges.

| ID | Kind | From | To |
|----|------|------|----|
| `aodl-intent-to-plan` |  | `representation:aodl-intent` | `representation:compiled-plan` |
| `decision-state-to-receipt` |  | `representation:compiled-decision-state` | `representation:decision-receipt` |
| `evidence-reducer-preserves-verifiability` |  | `representation:raw-context` | `representation:evidence-receipt` |
| `execution-to-tokenomics` |  | `representation:observed-topology` | `representation:tokenomics-event` |
| `observation-pack-compresses-context` |  | `representation:raw-context` | `representation:observation-pack` |
| `omp-rlm-context-spill` |  | `component:oh-my-pi` | `mechanism:rlm-context-spill` |
| `plan-to-observed-topology` |  | `representation:compiled-plan` | `representation:observed-topology` |

_Generated from `registry/evidence_dependencies.yaml`._
