# Mechanism registry

## `agenttrace-cross-harness-observation` — Cross-harness trace normalization
- **Kind:** observability
- **Stage:** experimental
- **Purpose:** Normalize session/cost/token/time evidence from heterogeneous harness logs without pretending missing event-level evidence exists.
- **Implemented by:** `agenttrace`

## `aodl-intent-plan-observed` — AODL intent → compiled plan → observed topology
- **Kind:** contract
- **Stage:** experimental
- **Purpose:** Keep desired orchestration, runtime-safe compiled plan and observed topology distinct so intended and actual execution can be compared.
- **Implemented by:** `aodl`

## `jev-typed-decision` — Jev / typed bounded decision
- **Kind:** decision
- **Stage:** experimental
- **Purpose:** Replace autoregressive choice generation with bounded typed scoring/readout when the decision space is explicit.
- **Implemented by:** `z0intelligence`, `oh-my-pi`

## `rlm-context-spill` — RLM context spill
- **Kind:** context
- **Stage:** production
- **Purpose:** Keep large context addressable outside the frontier model's active window.
- **Implemented by:** `oh-my-pi`

## `sol-pi-action-fusion` — SoL-Pi Action Fusion
- **Kind:** efficiency
- **Stage:** experimental
- **Family:** `sol-pi`
- **Purpose:** Fuse an edit/write and its predictable validation into one tool action.
- **Implemented by:** `pi`, `hermes`

## `sol-pi-evidence-reducer` — SoL-Pi Evidence-Preserving Reducer
- **Kind:** compression
- **Stage:** experimental
- **Family:** `sol-pi`
- **Purpose:** Compress long diagnostic observations into receipts while retaining quote-verifiable evidence and falling open on verification failure.
- **Implemented by:** `pi`, `hermes`

## `sol-pi-observation-pack` — SoL-Pi ObservationPack
- **Kind:** context
- **Stage:** experimental
- **Family:** `sol-pi`
- **Purpose:** Replace repeated large observations with stable handles and exact recall.
- **Implemented by:** `pi`, `hermes`

## `sol-pi-online-context-compact` — SoL-Pi Online Context Compact
- **Kind:** compression
- **Stage:** experimental
- **Family:** `sol-pi`
- **Purpose:** Trigger bounded context compaction at completed plan boundaries using economics/window pressure rather than replaying completed work indefinitely.
- **Implemented by:** `pi`, `hermes`

_Generated from `registry/mechanisms.yaml`._
