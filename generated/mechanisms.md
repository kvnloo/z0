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

## `limitless-cron-job-spec` — Windowed cron job spec
- **Kind:** contract
- **Stage:** experimental
- **Purpose:** Derive the host cron job each sending job would be (an interval that only polls for events, a script run with no agent turn, local delivery so the send gate stays the only sender, and the job's window class and staleness), then compare it with the host's job records as a verdict per job, a plan of create and update calls, or the host's own CLI lines. It never creates, resumes or deletes a job.
- **Implemented by:** `limitless`

## `limitless-decision-window-gate` — Decision-window gate
- **Kind:** interaction
- **Stage:** experimental
- **Purpose:** Let a proactive job declare a window class (peak, trough, wind_down, anytime) and return deliver, hold or drop with a one-line reason from the window a pluggable provider reports from events, never from clock times. On a host whose cron gate takes a window provider, the same window is registered as that provider; asleep, a focus block or an unknown window hold every windowed job.
- **Implemented by:** `limitless`

## `limitless-evidence-envelope` — Evidence envelope
- **Kind:** evidence
- **Stage:** experimental
- **Purpose:** Return every tool value as {value, modality, age_h, evidence_tier}, with modality measured, imported, proxy, self_report or messages and a tier label (direct, indirect, stale, none); missing data is a null value with a reason, never a guess, and an optional label beside the value never changes those fields.
- **Implemented by:** `limitless`

## `limitless-message-shape` — Push message shape
- **Kind:** interaction
- **Stage:** experimental
- **Purpose:** Keep every push short with the most important line first: the first line (the TLDR) stays in place, the closing reply-choices line and the "Why now" line are never folded or cut, extra middle lines fold into one line said in words, and a long line is cut at a word boundary unless it carries a link. Nothing is reworded and no digit is added; a message that already fits is unchanged.
- **Implemented by:** `limitless`

## `limitless-send-gate` — Proactive send gate
- **Kind:** interaction
- **Stage:** experimental
- **Purpose:** Pass every proactive push through one policy: drop a repeat of the same message inside the dedupe window and a second send for an event key already claimed, enforce a daily cap, drop every push while pushes are muted, hold non-critical sends while asleep or outside the job's decision window, fold pending-asks into the brief, strip internal card ids, and end each push with one plain-words "Why now" line.
- **Implemented by:** `limitless`

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

## `unified-memory-evidence-path` — Unified memory evidence path
- **Kind:** memory
- **Stage:** experimental
- **Purpose:** Resolve explicit information needs into provenance-bearing ContextPackets, inject only bounded evidence through harness-native seams, and preserve support/abstention evidence without replacing source stores with one database.
- **Implemented by:** `z0intelligence`

## `verified-specialist-evolution` — Verified specialist evolution
- **Kind:** learning
- **Stage:** experimental
- **Purpose:** Search bounded specialist implementations against locked corpora, controls, sealed splits and external outcomes, then export only evidence-backed candidates into the z0intelligence runtime without allowing the optimizer to redefine its judge.
- **Implemented by:** `evolution-lab`

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
