# Interfaces

Generic ecosystem contracts are separated from implementation-specific
adapters. An adapter names the harness it belongs to and must never be
presented as a shared contract.

## Generic ecosystem contracts

| Contract | Owner | Summary |
|----------|-------|---------|
| `aodl.intent.v1` | `aodl` | Typed intent / plan contract. Governs execution; is not runtime execution. |
| `aodl.observed_state.v1` | `aodl` | Observed execution state distinct from the compiled plan. |
| `flow.prediction.v1` | `flow` | OS-context prediction with horizon metadata and gates. |
| `harness.execution.v0` | `aodl` | The harness-neutral execution seam. Every harness adapter implements this and nothing above it may special-case a harness. |
| `kerdoios.placement.v1` | `kerdoios` | Placement decision over a resource portfolio. Allocation, not execution. |
| `kerdoios.quota_state.v1` | `kerdoios` | Dimensional quota state (rpm/rpd/tpm/tpd) with per-dimension provenance. |
| `rlm.evidence_handle.v0` | `rlm` | Addressable handle into the evidence plane, rehydratable on demand. |
| `tokenomics.event.v0` | `tokenomics` | Vendor-neutral usage / cost / latency / outcome event envelope. |
| `tokenomics.report.v1` | `tokenomics` | Aggregated reconciliation, coverage and verified-task report. |
| `z0evals.study.v1` | `z0evals` | Frozen reproducible study record. Immutable once published. |
| `z0int.cognition.receipt.v1` | `z0intelligence` | Cognition decision receipt including the eligible candidate set and surface verdict. |
| `z0int.decision_receipt.v1` | `z0intelligence` | Replayable routing/policy decision receipt (state, candidates, quota, outcome). |

## Implementation-specific adapters

| Adapter | Harness | Owner | Summary |
|---------|---------|-------|---------|
| `agenttrace.span.v0` | `agenttrace` | `agenttrace` | Historical agent span for observability export. Observational only. |
| `cu.stage_intent.v0` | `oh-my-pi` | `oh-my-pi` | OMP-specific Handsfree / computer-use window and layout intent. |
| `dsh.llm_pi_ai.catalog` | `deepseek-harness` | `deepseek-harness` | DSH llm-pi-ai provider/model catalog. The AUTHORITY for provider and model identity — z0 consumes this rather than mirroring it. |
| `hermes.plugin.v0` | `hermes-agent` | `hermes-agent` | Hermes plugin surface. Several Zer0 components ship through it. |
| `omp.rlm.spill.v0` | `oh-my-pi` | `oh-my-pi` | OMP-specific RLM context-spill surface. Not a shared contract. |
| `omp.session.aggregate` | `oh-my-pi` | `oh-my-pi` | OMP-specific session-level token rollup for Tokenomics reconciliation. |

_Generated from `registry/interfaces.yaml`._
