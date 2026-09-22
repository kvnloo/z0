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

## `frozen-eval-publication` — Frozen evaluation publication
- **Kind:** evidence
- **Stage:** active
- **Purpose:** Turn pinned experiment inputs and independently inspectable outcomes into frozen datasets, analyses, figures, and public claims without becoming the experiment engine or verifier.
- **Implemented by:** `kvnloo/z0evals`

## `hermes-lossless-context-dag` — Recoverable context DAG
- **Kind:** context
- **Stage:** experimental
- **Purpose:** Keep active context bounded while preserving raw-message lineage, hierarchical summaries, exact drill-down, and recoverable externalized payloads.
- **Implemented by:** `hermes`

## `jev-typed-decision` — Jev / typed bounded decision
- **Kind:** decision
- **Stage:** experimental
- **Purpose:** Replace autoregressive choice generation with bounded typed scoring/readout when the decision space is explicit.
- **Implemented by:** `z0intelligence`, `oh-my-pi`

## `keel-governed-execution` — Keel governed execution
- **Kind:** governance
- **Stage:** bootstrap
- **Purpose:** Bound agent execution with explicit capability rules, evidence requirements, staged promotion, adversarial verification, rollback, and non-self-authorizing evolution.
- **Implemented by:** `kvnloo/hermes-keel`

## `mesh-signed-intent-transport` — Signed Mesh intent transport
- **Kind:** transport
- **Stage:** experimental
- **Purpose:** Transport bounded signed execution intents between nodes while revalidating authority at the destination and returning signed receipt/evidence without replacing the canonical task lifecycle.
- **Implemented by:** `hermes`

## `model-passport-identity` — Model passport identity
- **Kind:** metadata
- **Stage:** design_seed
- **Purpose:** Keep maker, canonical model identity, verified capabilities, lifecycle, and serving route distinct while exposing one portable descriptor to every UI.
- **Implemented by:** `kvnloo/hermes-model-passports`

## `realtime-voice-orchestration` — Realtime voice orchestration
- **Kind:** interaction
- **Stage:** experimental
- **Purpose:** Keep a duplex voice session active while delegating durable background agent work, querying memory/tools, and speaking results when they arrive.
- **Implemented by:** `hermes`

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

## `split-authority-privilege-broker` — Split-authority privilege broker
- **Kind:** security
- **Stage:** development_candidate
- **Purpose:** Separate request, operator approval, immutable grant, and bounded privileged execution so an agent cannot manufacture its own elevation authority.
- **Implemented by:** `kvnloo/hermes-privilege-broker`

## `z0archy-hierarchy-meta-learning` — Slow architecture hierarchy meta-learning
- **Kind:** learning
- **Stage:** experimental
- **Purpose:** Analyze architecture history for conservative keep, merge, split, prune, or no-update proposals while keeping canonical ontology changes human-approved.
- **Implemented by:** `kvnloo/z0archy`

## `z0archy-history-fork-diff` — Replayable architecture fork and diff
- **Kind:** history
- **Stage:** active
- **Purpose:** Preserve content-addressed architecture history as event-sourced runs that can be replayed, forked at prior states, reconciled to alternate ref selections, and structurally diffed without contaminating canonical truth.
- **Implemented by:** `kvnloo/z0archy`

## `z0archy-semantic-compression` — Loss-aware semantic architecture compression
- **Kind:** compression
- **Stage:** active
- **Purpose:** Compile a large architecture world into question- or zoom-conditioned maps while emitting receipts for retained structure, hidden evidence, cut edges, provenance reconstructability, and high-relevance omissions.
- **Implemented by:** `kvnloo/z0archy`

_Generated from `registry/mechanisms.yaml`._
