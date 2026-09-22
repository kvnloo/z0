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
| `kerdoios.resource_offer.v1` | `kerdoios` | One normalized shape for every execution offer regardless of substrate: host CPU/GPU, Kubernetes, or a remote provider (Groq, Cerebras, OpenRouter, Nous, Vercel, xAI). Kerdoios owns the type and selects among offers. Producers emit it; consumers must NOT special-case a provider outside the adapter/placement boundary. Status is uneven and the registry should say so. Produced today: the host runtime and the remote provider adapters. NOT yet produced: Kubernetes. The only k8s lab (hermes-k8s-lab) is unpublished -- it has no git remote and no GitHub repository -- so the k8s producer is a declared gap, not an implemented one. Fields with no producer anywhere: route, economic_class, throughput, residency, startup_cost, location, node, backend, warm, resident, startup_ms, health_endpoint, queue_depth, namespace, pod, service. `resident` must be a live-runtime observation and never config intent. |
| `kerdoios.route.v1` | `kerdoios` | Model/provider routing decision with cost estimate. |
| `os.next_context.v0` | `flow` | Shadow prediction of next desktop context episode. Restored with the owner origin/main declared; the audit record notes z0intelligence also carries os-context machinery, so ownership here is worth confirming rather than assuming. |
| `rlm.evidence_handle.v0` | `rlm` | Addressable handle into the evidence plane, rehydratable on demand. |
| `tokenomics.event.v0` | `tokenomics` | Vendor-neutral usage / cost / latency / outcome event envelope. |
| `tokenomics.report.v1` | `tokenomics` | Aggregated reconciliation, coverage and verified-task report. |
| `z0eval.study.v1` | `z0evals` | Frozen reproducible study record. Immutable once published. The id is `z0eval` (abbreviated), not `z0evals`. This entry previously read `z0evals.study.v1`, which named a contract that does not exist: z0evals declares `const: z0eval.study.v1` in schemas/study-manifest.schema.json and every real manifest carries `schema_version: z0eval.study.v1`. The registry is supposed to describe what exists, so it now does. Abbreviation is already the convention elsewhere -- z0intelligence emits `z0int.*` -- so this is alignment rather than a new style. |
| `z0int.cognition.receipt.v1` | `z0intelligence` | Cognition decision receipt including the eligible candidate set and surface verdict. |
| `z0int.decision_receipt.v1` | `z0intelligence` | Replayable routing/policy decision receipt (state, candidates, quota, outcome). |
| `z0int.decision_result.v1` | `z0intelligence` | Frozen DecisionRequest/DecisionResult pair for a DecisionBackend. This is the host-vs-k8s parity contract: the same request must produce the same result whether served by an in-process host backend or by a service, with only transport and placement differing. What may differ: transport latency, queue time, process identity. What may NOT differ: the chosen action, probabilities, model identity and revision. No service implementation exists yet, so parity is declared and unproven; any comparison must use the existing comparability gate rather than a bespoke comparator. |

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
