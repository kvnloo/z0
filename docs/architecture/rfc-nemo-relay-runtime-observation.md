---
id: architecture.rfc-nemo-relay-runtime-observation
title: "RFC: NeMo Relay as Zer0's live execution-observation substrate"
scope: [z0, agenttrace, tokenomics, z0intelligence, aodl, oh-my-pi, hermes, deepseek]
status: proposed
tracking_issue: https://github.com/kvnloo/z0/issues/21
date: 2026-09-30
---

# RFC: NeMo Relay as Zer0's live execution-observation substrate

## Status

**Proposed.**

Tracking issue: [z0 #21](https://github.com/kvnloo/z0/issues/21)

This RFC defines cross-repository ownership, interfaces, rollout gates and evidence
requirements. It does **not** add runtime implementation code to `kvnloo/z0`.

## Summary

Zer0 should integrate **NVIDIA NeMo Relay** only at each runtime's existing,
owned observability/extension seam. Relay is a useful live lifecycle substrate
where a harness natively supports it; it is **not** Zer0's universal wire format
and must not replace repo-native telemetry, logs, measurement contracts, receipts,
or typed orchestration.

AgentTrace remains the cross-harness normalizer. The shared cross-repo contract is
vendor-neutral correlation plus honest fidelity, not mandatory ATOF everywhere.

```text
                    authored intent
                        AODL
                          |
                    compiled plan
                          |
                          v
                   execution harness
          +---------------+---------------+
          |               |               |
       Hermes            OMP             DSH
    native Relay      existing OTel   session-telemetry
      runtime            seam             seam
          |               |               |
          +---------------+---------------+
                          |
                native truthful evidence
                 + Relay where native
                          |
          +---------------+------------------+
          |               |                  |
      AgentTrace       Tokenomics       z0intelligence
      diagnostics      measurements     decision receipts
          |               |                  |
          +---------------+------------------+
                          |
                       z0evals
               frozen replay/evaluation
```

Relay is **not** a Zer0 orchestrator and does not replace any existing owner.

## Motivation

Zer0 already has strong post-hoc and typed evidence surfaces:

- execution harnesses emit their own logs and trajectory data;
- AgentTrace normalizes heterogeneous historical session evidence;
- Tokenomics measures usage, cost and latency;
- z0intelligence emits decision/context receipts;
- AODL separates authored intent from compiled and observed execution;
- z0evals freezes evidence for reproducible evaluation.

The missing primitive is one **live, hierarchical execution lineage** shared
across harnesses.

Today a root task, subagent, LLM call, tool call, verifier and decision receipt
may be observable, but their identities are not guaranteed to share one
cross-harness parent/child graph at execution time.

NeMo Relay supplies a useful substrate for that gap:

- nested execution scopes;
- managed LLM and tool lifecycle boundaries;
- middleware and plugin hooks;
- subscribers;
- canonical Agent Trajectory Observability Format (ATOF) events;
- ATIF trajectory export;
- OpenTelemetry and OpenInference projections.

As of 2026-09-30, NVIDIA documents NeMo Relay 0.10.x and ATOF 0.1.
Hermes Agent 0.18.2+ includes a native Relay integration. These are baseline
facts for the initial implementation, not permanent compatibility promises.

References:

- https://docs.nvidia.com/nemo/relay/about-nemo-relay/overview
- https://docs.nvidia.com/nemo/relay/latest/reference/atof-event-format
- https://docs.nvidia.com/nemo/relay/configure-plugins/observability/about
- https://docs.nvidia.com/nemo/relay/dev/getting-started/installation
- https://github.com/NVIDIA/NeMo-Relay

## Decision

Adopt Relay as an **optional cross-harness execution-observation mechanism** implemented only through repo-owned seams.

Tentative Zer0 mechanism identity:

```text
relay-runtime-observation
```

The mechanism belongs in the architecture registry only after implementation
evidence proves the contract. Relay itself should not become a Zer0 component
merely because multiple harnesses can interoperate with it.

### Boundary rule

A repository keeps ownership of its native execution/telemetry contract. Relay-
specific glue attaches to that contract and must not redefine it. If two or more
repos eventually need the same substantial vendor-specific adapter, move that
shared glue to a dedicated integration package/repo — never into `kvnloo/z0`.

### Ownership

| Surface | Owns | Does not own |
|---|---|---|
| execution harness | scheduling, retries, tool/model execution, agent loop | cross-harness analysis |
| NeMo Relay | execution scopes, lifecycle events, middleware boundary, subscriber stream | Zer0 orchestration policy |
| AgentTrace | trace ingestion, normalization, diagnostics, fidelity reporting | live execution |
| Tokenomics | neutral usage/cost/latency/resource measurement | trace authority or billing truth |
| z0intelligence | context resolution, bounded decisions, receipts, specialist policy | execution lineage storage |
| AODL | authored intent, authority and portable plan contracts | runtime execution |
| z0evals | frozen evidence and reproducible evaluation | live runtime policy |
| Evolution Lab | experiment/search/promotion machinery | protected truth |
| z0 | canonical ownership/interface/mechanism map | runtime implementation |

## Non-goals

This RFC does not propose:

- replacing Hermes, OMP or DeepSeek Harness;
- moving orchestration into `kvnloo/z0`;
- replacing AgentTrace with an NVIDIA UI/backend;
- replacing Tokenomics with OpenTelemetry;
- replacing z0int decision receipts with Relay marks;
- replacing AODL with observed scope trees;
- making ATIF or OTLP the universal durable schema;
- turning on Relay adaptive/control features before passive observation works;
- storing private raw traces in public repositories.

## Core invariants

### 1. Intended, compiled and observed execution remain separate

```text
authored intent
    |
    v
compiled runtime-safe plan
    |
    v
actual runtime execution
    |
    v
Relay observed scope DAG
```

Observed Relay topology is evidence about execution. It cannot rewrite the
authored AODL intent or silently redefine the compiled plan.

### 2. Missing evidence remains missing

A historical harness session with aggregate token counts does not become a
"detailed trace" because Relay exists elsewhere.

AgentTrace must preserve its current fidelity distinction for partial sources.

### 3. Relay events are transport/observation, not semantic truth

A scope completing means the scope completed. It does not prove:

- the requested objective was achieved;
- the generated artifact is correct;
- the user preferred the result;
- the action was economically optimal.

Those claims still require their owning verifiers/outcomes.

### 4. Instrumentation must not change application-visible behavior

With Relay observation enabled and disabled, the same deterministic fixture
must produce the same:

- tool inputs and outputs;
- model request semantics;
- persisted application state;
- authority decisions;
- verifier outcome.

Any instrumentation path that mutates these by default fails the RFC.

### 5. Privacy is stricter than observability completeness

ATOF can represent detailed model/tool payloads. Zer0 must not equate maximum
payload capture with correct instrumentation.

Default Zer0 profiles should prefer metadata/sanitized observation and keep
full payload capture opt-in.

## Correlation contract

Every integration should propagate a minimal common correlation envelope where
the underlying surface can supply it.

```text
z0_run_id
trace_id?
span_id?
parent_span_id?
execution_ref?
harness_id
harness_session_id
harness_turn_id?
agent_id?
aodl_intent_id?
aodl_plan_id?
z0int_decision_receipt_id?
z0int_context_receipt_id?
tokenomics_event_id?
verifier_outcome_id?
repo_identity?
worktree_identity?
model_route_id?
relay_scope_uuid?
relay_parent_uuid?
```

Rules:

1. no field is fabricated;
2. unknown and unavailable are distinct from empty strings;
3. prefer existing OTel trace/span IDs where an owning repo already emits them;
4. Relay IDs are optional adapter metadata, not required AODL/z0int/Tokenomics fields;
5. downstream IDs may point back to a scope, but must not redefine its parent;
6. a single decision receipt may correlate with several execution scopes;
7. no correlation field can mint verified success.

The exact versioned schema should live in the owning implementation repo once a
pilot proves the minimum field set.

## Event hierarchy

The desired semantic hierarchy is:

```text
run/session
  turn
    agent
      decision/context marks
      llm
      tool
      subagent
        llm
        tool
      verifier
```

This is a semantic target, not a requirement that every harness expose every
level.

Adapters should use the nearest truthful scope category available rather than
inventing missing structure.

## Harness integration

### Hermes Agent

Hermes is the lowest-risk pilot because current Hermes releases have native
Relay integration.

Requirements:

- verify the forked Hermes version includes the current native integration;
- do not install the removed/legacy separate Hermes Relay CLI integration;
- enable one minimal ATOF exporter profile;
- validate root agent, subagent, LLM and tool nesting from a real run;
- correlate Hermes session/trajectory identity to Relay scope identity;
- verify no duplicate lifecycle events from older hooks or MCP wiring;
- measure event completeness and instrumentation overhead;
- document feature/version guards.

Hermes owns implementation.

### Oh My Pi (OMP)

OMP already owns generic OpenTelemetry GenAI instrumentation in
`packages/agent/src/telemetry.ts` and opt-in OTLP export in
`packages/coding-agent/src/telemetry-export*.ts`. Its agent loop already emits
`invoke_agent`, `chat`/`judgment`, `execute_tool`, and `handoff` spans.

Therefore:

- do not instrument LLM/tool execution a second time just to produce ATOF;
- keep the existing OMP telemetry contract canonical inside OMP;
- add only generic correlation attributes if they are broadly useful;
- consume existing OTel spans downstream for cross-harness correlation;
- if a concrete Relay-only capability is later required, start with an external
  extension/adapter that consumes the existing telemetry seam.

Any Relay-specific OMP work must prove it adds information unavailable through
the current generic telemetry path and adds no startup/runtime cost when disabled.
### DeepSeek Harness

DSH already owns a generic session-telemetry capability seam:

`canonical Session log -> session-telemetry coordinator -> SessionTelemetryBackend`.

It also has an OTel backend/transport implementation. Passive Relay integration
therefore belongs behind `SessionTelemetryBackend` or another documented Cordis
service/plugin seam.

Requirements:

- do not patch `agent-loop` for passive Relay telemetry;
- do not create parallel model/tool lifecycle events when the canonical Session
  stream already records the observation;
- preserve DSH authorization/redaction semantics;
- register through Cordis effects and make the backend optional/unloadable;
- retain the Session log as canonical durable runtime evidence.

A future `session-telemetry-relay` backend/package is acceptable if those
constraints hold.
### Other harnesses

Codex, Claude Code and future harnesses may use maintained Relay integrations
when they preserve Zer0's correlation and privacy requirements.

A maintained upstream integration does not automatically satisfy Zer0's
fidelity, retention or identity contracts.

## AgentTrace integration

AgentTrace remains the primary cross-harness inspection and diagnostics layer.

Add an ATOF-native parser/source with the following properties:

- preserves native scope UUID and parent UUID;
- reconstructs execution DAGs without flattening subagents;
- preserves event timestamps and ordering semantics;
- emits detailed fidelity only for evidence actually present;
- normalizes model/tool/error timing;
- supports partial/corrupt streams explicitly;
- avoids storing prompt, response, tool argument and tool result bodies in its
  normalized privacy-safe step representation by default;
- can compare Relay-native runs with historical parser-derived sessions.

AgentTrace should distinguish at minimum:

```text
relay_native_detailed
native_nonrelay_detailed
aggregate
limited
```

Exact naming is implementation-owned.

## Tokenomics integration

Tokenomics remains the canonical semantic measurement/economics contract and
durable offline truth. Do **not** turn it into a generic Relay projection.

Preferred path:

`harness observation -> Tokenomics event directly -> attach trace/span/execution correlation`.

Relay-derived measurements are a fallback observer path only when no direct
measurement event exists. Such records must preserve measurement provenance and
completeness state and must never mint authoritative billing, missing token
counts, measured savings from absent data, or `gold` verified outcomes.

Relay scope completion remains execution evidence, not verified task success.
## z0intelligence integration

z0intelligence should remain Relay-agnostic. Its durable decision/context
receipts may carry a **generic** execution-correlation object using trace/span
IDs or an opaque execution reference. Relay-specific adapters may map that
correlation to Relay scope IDs.

Relay marks may reference receipt IDs for live correlation, but Relay marks do
not replace versioned z0int receipts and Relay types must not become z0int core
schema dependencies.
## AODL integration

AODL already owns `intentGraph`, compiled-plan semantics, and optional
`observedGraph`. It should own only the IR shape, mapping/profile documentation,
conformance fixtures, and static comparison semantics.

A live Relay -> AODL projector belongs with the runtime/integration adapter that
has the live events. Do not add a Relay client, subscriber, exporter, scheduler,
or runtime dependency to AODL.
## z0evals and Evolution Lab

Before default-on promotion, freeze an integration study containing:

- exact Relay version;
- exact harness refs;
- synthetic nested-agent fixtures;
- sanitized ATOF fixtures;
- expected AgentTrace projections;
- expected Tokenomics correlation/reconciliation behavior;
- AODL desired/observed comparison fixture;
- fault-injection results;
- overhead measurements.

Evolution Lab may use these frozen traces for candidate experiments, but
protected verifier outcomes remain outside optimizer control.

## Privacy, retention and security

### Payload policy

Default:

```text
full model payloads: OFF
full tool arguments/results: OFF unless explicitly required
secrets/env values: NEVER
stable IDs/timestamps/categories: ON
usage/latency/error metadata: ON where available
```

### Retention classes

At minimum distinguish:

1. raw ATOF;
2. sanitized ATOF;
3. ATIF trajectory;
4. AgentTrace normalized record;
5. Tokenomics measurement event;
6. z0int durable receipt;
7. frozen z0evals fixture.

Retention and access policy may differ for each.

### Active middleware boundary

Relay middleware can observe and can also transform/block execution.

Zer0 must treat those as different capability classes.

Passive telemetry does not grant:

- action authority;
- secret access;
- privilege elevation;
- policy override.

Any active Relay middleware entering production must pass the existing
governance/authority path for that harness.

## Failure model

### Exporter unavailable

Default observation policy should be fail-open for application execution unless
the owning harness explicitly defines a stronger audit requirement.

Failure must be visible in health/coverage metadata.

### Subscriber throws

No silent event loss. Record coverage degradation and continue or fail according
to the configured observation policy.

### Missing parent scope

Keep the event and flag broken lineage. Do not invent a parent.

### Process crash / incomplete root scope

Preserve the partial ATOF stream and mark it incomplete.

### Duplicate events

Detect using native event/scope identity plus lifecycle category. Do not
blindly deduplicate events that differ semantically.

### Version mismatch

Reject unsupported schemas at the adapter boundary or parse them as explicitly
unknown fidelity. Never silently reinterpret fields.

## Rollout

### P0 — contract and fixtures

Deliver:

- accepted RFC;
- pinned tested Relay baseline;
- synthetic nested run;
- sanitized ATOF fixture;
- expected downstream projections;
- correlation-envelope proposal;
- privacy threat model.

Exit gate: all owning repos agree on boundaries.

### P1 — Hermes native pilot

Deliver:

- one real Hermes trace;
- correct root/subagent/tool/LLM nesting;
- session correlation;
- duplicate-event audit;
- overhead measurement;
- privacy inspection.

Exit gate: no application-visible behavior difference.

### P2 — OMP and DSH seam pilots

OMP reuses its existing OTel instrumentation and proves required correlation can
be carried without Relay-specific loop code.

DSH composes only at its session-telemetry/Cordis backend seam and proves no
agent-loop patch is required.

Exit gate: both expose truthful comparable evidence without duplicating native
instrumentation.

### P3 — downstream consumers

Deliver:

- AgentTrace ATOF ingestion;
- Tokenomics correlation/reconciliation;
- generic z0int receipt correlation;
- AODL observedGraph mapping fixture produced outside the AODL runtime-free core.

Exit gate: every projection can be traced to raw evidence.

### P4 — frozen evaluation

Deliver:

- z0evals study;
- overhead/error/privacy matrix;
- cross-harness comparison;
- promotion recommendation supported by measured evidence.

Exit gate: no unresolved P0 privacy, lineage or behavior-equivalence failures.

## Required tests

### Contract

- valid nested scopes;
- concurrent siblings;
- missing parent;
- incomplete root;
- duplicate lifecycle event;
- malformed payload;
- unsupported ATOF version.

### Behavioral equivalence

For deterministic fixtures:

```text
Relay OFF output == Relay ON output
```

for application-visible state and authority decisions.

### Privacy

Fixtures containing:

- API keys;
- auth headers;
- environment variables;
- private prompt text;
- tool arguments;
- tool results.

Verify forbidden payloads do not reach sanitized durable exports.

### Failure injection

- exporter unavailable;
- exporter slow;
- subscriber exception;
- disk full/read-only output;
- process kill mid-turn;
- malformed downstream consumer;
- network OTLP failure.

### Cross-harness semantic parity

Run the same small logical task through Hermes, OMP and DSH and compare whether
each truthfully exposes:

- root/turn identity;
- agent/subagent hierarchy;
- LLM calls;
- tool calls;
- errors/retries;
- decision/verifier correlation where present.

Parity means semantic comparability, not identical event counts.

## Measurements

Track before/after:

- p50/p95 added wall latency;
- CPU overhead;
- memory overhead;
- trace bytes per run;
- event drop rate;
- orphan-scope rate;
- duplicate-event rate;
- receipt correlation coverage;
- AgentTrace parse coverage;
- Tokenomics reconciliation coverage;
- privacy fixture failures.

Do not infer token savings or productivity gains merely from adding Relay.

## Promotion criteria

Promote `relay-runtime-observation` only as an experimental mechanism with specific implementations if:

1. Hermes native integration passes real-run tests;
2. OMP reuses its existing OTel telemetry seam and DSH uses its existing session-telemetry/plugin seam;
3. instrumentation overhead is measured and acceptable;
4. privacy-safe defaults require no full-payload retention;
5. event loss and broken lineage are detectable;
6. AgentTrace preserves honest fidelity semantics;
7. Tokenomics remains the measurement/economics authority;
8. z0int remains Relay-agnostic and its receipts independently interpretable;
9. AODL remains runtime-free while its observedGraph contract can represent the projection;
10. a frozen z0evals study records the evidence.

## Stop conditions

Do not promote if any of the following remains true:

- instrumentation changes execution semantics;
- correlation ambiguity cannot be detected;
- privacy-safe operation requires persistent raw prompts/tool results;
- adapters require invasive forks of harness loops when stable extension seams exist;
- Relay version churn cannot be isolated behind adapter contracts;
- instrumentation overhead materially harms the workloads Zer0 is optimizing;
- downstream consumers must fabricate missing trace detail.

## Registry changes after pilot

After P1 proves the mechanism, add something equivalent to:

```yaml
relay-runtime-observation:
  name: NeMo Relay runtime observation
  kind: observability
  stage: experimental
  purpose: >
    Provide live hierarchical execution scopes and canonical lifecycle events
    across supported harnesses while keeping orchestration, measurement,
    semantic decisions and verification in their owning systems.
  implementations:
    - repo: kvnloo/hermes-agent
      harness: hermes
      mode: native
    # Add OMP/DSH only after concrete adapter evidence exists.
```

Do not register this before an implementation/evidence ref exists.

A future versioned Zer0 interface may be justified for the correlation envelope,
but this RFC deliberately avoids inventing it before the pilot determines which
fields are actually stable.

## Implementation ownership map

| Work | Owning repo |
|---|---|
| central RFC / mechanism map | `kvnloo/z0` |
| Hermes pilot | `kvnloo/hermes-agent` |
| OMP generic telemetry/correlation | `kvnloo/oh-my-pi` |
| DSH telemetry-backend composition | `kvnloo/deepseek-harness` |
| ATOF/cross-format ingestion + diagnostics | `kvnloo/agenttrace` |
| measurement/outcome semantics + correlation | `kvnloo/tokenomics` |
| decision/context receipt semantics | `kvnloo/z0intelligence` |
| intent/plan/observedGraph contract | `kvnloo/aodl` |
| frozen integration study | `kvnloo/z0evals` |
| candidate experiments | `kvnloo/evolution-lab` |
| shared Relay-specific glue, if proven necessary | dedicated adapter package/repo, not `z0` |

## Open questions for the pilot

1. Which Relay binding is least invasive for OMP's TypeScript/Rust boundary?
2. Which DSH Cordis service should own Relay activation lifetime?
3. Should `z0_run_id` be generated by the harness or an existing Zer0 caller?
4. Which receipt IDs belong in Relay marks versus scope attributes?
5. What is the minimum sanitized ATOF subset sufficient for AgentTrace?
6. Should raw ATOF be ephemeral after successful AgentTrace ingestion and Tokenomics correlation/reconciliation?
7. Which verifier outcomes need direct scope correlation versus run-level joins?
8. What Relay version compatibility window should Zer0 test?
9. Does ATIF add useful evaluation portability beyond preserving raw ATOF?
10. Which active middleware features, if any, deserve a separate future RFC?

## Follow-up issue structure

The tracking issue should fan out implementation only after this RFC is accepted:

```text
z0 #21
  -> Hermes native pilot
  -> OMP correlation through existing OTel seam
  -> DSH experiment through session-telemetry seam
  -> AgentTrace ATOF + cross-format normalization
  -> Tokenomics correlation / fallback provenance
  -> z0int generic execution-ref correlation
  -> AODL observedGraph mapping profile + fixtures
  -> z0evals frozen integration study
```

These child issues should use blocked-by links so runtime work cannot be
mistaken for a completed cross-repo integration before the evidence path exists.
