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

Zer0 should use **NVIDIA NeMo Relay** as the preferred live lifecycle
instrumentation substrate for agent execution while preserving the existing Zer0
separation between execution, observation, measurement, decision policy, typed
intent and evaluation.

Relay should sit *under* AgentTrace, Tokenomics and z0intelligence and *around*
execution boundaries owned by harnesses.

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
    native Relay      Relay adapter   Relay adapter
          |               |               |
          +---------------+---------------+
                          |
                     ATOF events
               live scope/event lineage
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

Adopt Relay as a **cross-harness live execution-observation mechanism**.

Tentative Zer0 mechanism identity:

```text
relay-runtime-observation
```

The mechanism belongs in the architecture registry only after the first
implementation proves the contract. Relay itself should not become a Zer0
"component" merely because multiple harnesses use it.

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
relay_scope_uuid
relay_parent_uuid
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
```

Rules:

1. no field is fabricated;
2. unknown and unavailable are distinct from empty strings;
3. native Relay scope UUIDs remain stable through downstream projections;
4. downstream IDs may point back to a scope, but must not redefine its parent;
5. a single decision receipt may correlate with several execution scopes;
6. a single execution scope may produce several measurement events.

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

OMP should use an in-process or binding-level adapter around boundaries it
already owns.

Candidate scope/event boundaries:

- coding session;
- turn;
- main agent;
- subagent;
- LLM invocation;
- tool invocation;
- advisor/reviewer;
- verifier;
- retry/recovery;
- context compaction;
- model/provider route changes.

Candidate Zer0-specific marks:

- RLM spill/resolve;
- z0int/Jev decision receipt ID;
- context compression boundary;
- verifier start/outcome;
- route/escalation decision.

Requirements:

- prefer managed Relay wrappers where OMP owns the invocation;
- avoid proxying through a gateway solely to obtain telemetry when direct
  instrumentation is available;
- golden-test event ordering and parentage;
- prove enabled/disabled behavioral equivalence.

OMP owns implementation.

### DeepSeek Harness

DeepSeek Harness should integrate at Cordis/plugin service seams rather than
patching the central loop.

Requirements:

- represent session/agent execution as Relay scopes;
- wrap model and tool services;
- preserve DSH's append-only log as an independent durable source;
- map `Agent.inject()`, `followup()`, `steer()` and pre-step interventions
  without misclassifying injected context as a fresh user turn;
- expose the adapter as a replaceable plugin/service;
- retain native DSH identifiers for provenance.

DeepSeek Harness owns implementation.

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

Tokenomics should consume derived measurement facts, not raw trace authority.

Candidate derivations:

- LLM latency;
- observed input/output/cache tokens;
- provider/model route;
- tool latency;
- tool retry/error count;
- subagent fanout;
- execution wall time;
- verifier latency;
- decision/escalation count.

Rules:

- provider billing remains reconciled separately where possible;
- missing token fields stay missing;
- trace-derived cost is an estimate unless reconciled;
- Relay marks may carry measurement hints but do not become the canonical
  economics policy.

## z0intelligence integration

z0intelligence should attach Relay lineage to existing durable receipts.

Targets:

- `z0int.decision_receipt.v1`;
- `z0int.context_resolve.v1`;
- specialist ACT/OBSERVE/ASK/ABSTAIN/ESCALATE decisions;
- evidence-sufficiency/verifier decisions;
- route/deopt/recovery decisions where applicable.

Relay marks may expose IDs for live correlation.

The versioned z0int receipt remains the durable semantic record.

## AODL integration

AODL should define the comparison seam between expected and observed execution.

```text
AODL intent
  -> compiled plan
  -> harness execution
  -> Relay observed DAG
  -> topology comparison
  -> evidence receipt
```

Useful comparisons include:

- expected node executed / not executed;
- unexpected execution node;
- expected edge vs observed parent relation;
- retry expansion;
- fanout expansion;
- fallback route;
- verifier present/missing;
- authority boundary crossed/not crossed.

The comparison should tolerate runtime implementation details that AODL does
not model.

## z0evals and Evolution Lab

Before default-on promotion, freeze an integration study containing:

- exact Relay version;
- exact harness refs;
- synthetic nested-agent fixtures;
- sanitized ATOF fixtures;
- expected AgentTrace projections;
- expected Tokenomics projections;
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

### P2 — OMP and DSH shadow adapters

Deliver:

- disabled-by-default adapters;
- contract tests;
- fault injection;
- golden lifecycle fixtures;
- version guards.

Exit gate: adapters produce truthful comparable semantics without requiring
shared internal implementation.

### P3 — downstream consumers

Deliver:

- AgentTrace ATOF ingestion;
- Tokenomics projection;
- z0int receipt correlation;
- AODL desired-vs-observed comparison.

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

Relay may become Zer0's default live observation substrate only if:

1. Hermes native integration passes real-run tests;
2. OMP and DSH adapters pass behavioral-equivalence tests;
3. instrumentation overhead is measured and acceptable;
4. privacy-safe defaults require no full-payload retention;
5. event loss and broken lineage are detectable;
6. AgentTrace preserves honest fidelity semantics;
7. Tokenomics projections reconcile without becoming billing truth;
8. z0int receipts remain durable and independently interpretable;
9. AODL desired/observed comparisons work without conflating the two;
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
    - repo: kvnloo/oh-my-pi
      harness: omp
    - repo: kvnloo/deepseek-harness
      harness: deepseek
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
| OMP adapter | `kvnloo/oh-my-pi` |
| DSH adapter | `kvnloo/deepseek-harness` |
| ATOF ingestion/diagnostics | `kvnloo/agenttrace` |
| measurement projection | `kvnloo/tokenomics` |
| decision/context correlation | `kvnloo/z0intelligence` |
| intended-vs-observed comparison | `kvnloo/aodl` |
| frozen integration study | `kvnloo/z0evals` |
| candidate experiments | `kvnloo/evolution-lab` |

## Open questions for the pilot

1. Which Relay binding is least invasive for OMP's TypeScript/Rust boundary?
2. Which DSH Cordis service should own Relay activation lifetime?
3. Should `z0_run_id` be generated by the harness or an existing Zer0 caller?
4. Which receipt IDs belong in Relay marks versus scope attributes?
5. What is the minimum sanitized ATOF subset sufficient for AgentTrace?
6. Should raw ATOF be ephemeral after successful AgentTrace/Tokenomics projection?
7. Which verifier outcomes need direct scope correlation versus run-level joins?
8. What Relay version compatibility window should Zer0 test?
9. Does ATIF add useful evaluation portability beyond preserving raw ATOF?
10. Which active middleware features, if any, deserve a separate future RFC?

## Follow-up issue structure

The tracking issue should fan out implementation only after this RFC is accepted:

```text
z0 #21
  -> Hermes native pilot
  -> OMP Relay adapter
  -> DSH Relay/Cordis adapter
  -> AgentTrace ATOF ingestion
  -> Tokenomics Relay projection
  -> z0int receipt correlation
  -> AODL observed-topology adapter
  -> z0evals frozen integration study
```

These child issues should use blocked-by links so runtime work cannot be
mistaken for a completed cross-repo integration before the evidence path exists.
