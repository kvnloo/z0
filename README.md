# Zer0

**Personal AI infrastructure that makes frontier models do less.**

`kvnloo/z0` is the **federated network almanac**: the reconciled map, capability
profiles, contract registry and generated architecture source for the Zer0
ecosystem. It is deliberately **not** a runtime, an orchestrator, a model
catalog, or a provider gateway.

> Store Zer0-specific relationships and policy.
> Fetch upstream facts from the authority that already owns them.

```bash
git clone https://github.com/kvnloo/z0
cd z0
pip install -r requirements.txt     # PyYAML for the CLI
./z0 init --profile core            # capabilities, then choose a harness
./z0 doctor                         # what's installed vs registry tested_refs
./z0 registry doctor                # validate + live upstream heads
```

## The shape of the network

```text
                    HUMAN / AGENT SURFACES
                 Dash · Ripple · harness UIs
                             │
                             ▼
                      INTENT / AUTHORITY
                            AODL
             typed intent · constraints · legal structure
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│                  EXECUTION HARNESSES                     │
│      Hermes          DeepSeek Harness          OMP       │
│        └───────── shared z0 contracts ──────────┘        │
└──────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
   CONTEXT / EVIDENCE               COGNITION
   RLM evidence addressing     z0intelligence
   cognitive-state compiler    deterministic compiler
   receipts + handles          DecisionBackend · JEV
          │                              │
          └──────────────┬───────────────┘
                         ▼
                     EXECUTION
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
    Kerdoios        Tokenomics        AgentTrace
    placement       measurement       inspection
        └────────────────┼────────────────┘
                         ▼
                   Evolution Lab
             qualifies · trains · evaluates
                         │
                         ▼
                      z0evals
              freezes and publishes
                         │
                         ▼
                  z0intelligence
            activates: shadow → canary → active
```

No harness is mandatory. Hermes, DeepSeek Harness and OMP are **peer executor
implementations**; z0 executes *via* one of them.

## I want…

| Goal | Start here |
|------|------------|
| A better coding agent | pick a harness: Hermes, [DeepSeek Harness](generated/upstreams.md), or OMP |
| Lower token usage | [Tokenomics](docs/components/tokenomics.md) + the [context plane](docs/architecture/context-plane.md) (RLM) |
| Personal intelligence | [z0intelligence](docs/components/z0intelligence.md) |
| Cheaper compute placement | [Kerdoios](docs/components/kerdoios.md) |
| Predictive desktop UX | [Flow](docs/components/flow.md) |
| Automatic AI research | [Evolution Lab](docs/components/evolution-lab.md) → [z0evals](docs/components/z0evals.md) |
| Typed agent plans | [AODL](docs/components/aodl.md) |
| Understand what exists | [generated/components.md](generated/components.md), [upstreams.md](generated/upstreams.md), [sources.md](generated/sources.md) |

## Profiles

A profile answers two separate questions: **what capabilities** do you want, and
**which harness** do you execute through.

| Profile | Capabilities | Adds |
|---------|--------------|------|
| `minimal` | execution | nothing — one supported harness, your choice |
| `core` | execution, contracts, measurement | `z0`, `aodl`, `tokenomics` |
| `personal` | + cognition | `z0intelligence` |
| `desktop` | + context, interaction | `flow`, `dash`, `ripple` |
| `compute` | + resources | `kerdoios` |
| `context` | + context | `rlm`, `sol-pi-hermes` |
| `research` | + evaluation, research | `evolution-lab`, `z0evals`, `frontier-kb` |
| `full` | all of the above | every experimental component |

```bash
./z0 init --profile core
./z0 add tokenomics
./z0 registry doctor
```

## CLI

| Command | Purpose |
|---------|---------|
| `./z0 init` | Interactive or `--profile` capability+harnes plan, then clone |
| `./z0 add <id>` | Add one owned component |
| `./z0 doctor` | Installed vs registry `tested_ref` |
| `./z0 registry doctor` | Validate the almanac; report **live** upstream heads |
| `./z0 status` | Dev-state table (branch, HEAD, arch/impl status) |
| `./z0 graph [--mermaid\|--json]` | Typed relationship graph |
| `./z0 docs generate` | Regenerate `generated/` + `zer0.registry.yaml` |
| `./z0 cognition portfolio` | Cognition dataflow; reads the model list live from z0intelligence (never stores it) |

## Rule

> **Implementation docs live with implementations. Architecture and onboarding live in `z0`.**

See [ARCHITECTURE.md](ARCHITECTURE.md), [SYSTEM.md](SYSTEM.md), and
[docs/getting-started/five-minute-start.md](docs/getting-started/five-minute-start.md).
