# Zer0

**Personal AI infrastructure that makes frontier models do less.**

`kvnloo/z0` is the **map, installer, contract registry, and documentation source** for the Zer0 ecosystem. It is deliberately **not** a runtime or orchestrator.

```bash
git clone https://github.com/kvnloo/z0
cd z0
pip install -r requirements.txt   # PyYAML for the CLI
./z0 init --profile core
./z0 doctor
```

## I want…

| Goal | Start here |
|------|------------|
| A better coding agent | [OMP](docs/components/oh-my-pi.md) (`oh-my-pi`) |
| Lower token usage | [Tokenomics](docs/components/tokenomics.md) + RLM (in OMP) |
| Personal intelligence | [z0intelligence](docs/components/z0intelligence.md) |
| Predictive desktop UX | [Flow](docs/components/flow.md) + Handsfree (in OMP) |
| Cheaper compute routing | [Kerdoios](docs/components/kerdoios.md) |
| Automatic AI research | [Evolution Lab](docs/components/evolution-lab.md) |
| Typed agent plans | [AODL](docs/components/aodl.md) |
| Agent observability | [AgentTrace](docs/components/agenttrace.md) |
| Everything stable | `./z0 init --profile full` |

## Architecture dimensions

Zer0 no longer treats every architectural concept as an installable repo.

| Registry | Owns |
|---|---|
| `components.yaml` | Installable Zer0 products/services |
| `harnesses.yaml` | Execution surfaces such as OMP, Hermes, DeepSeek, Codex and Pi |
| `mechanisms.yaml` | Cross-cutting mechanisms that may have multiple implementations |
| `interfaces.yaml` | Named cross-component contracts |
| `lifecycles.yaml` | Promotion, experiment and epistemic/history states |
| `suite.yaml` | Zer0 repository surfaces and their semantic roles without treating every repo as a component |
| `profiles.yaml` | Installable component bundles |

This separation is intentional: SoL-Pi's ObservationPack is a mechanism, not a product;
DeepSeek is a harness, not a dependency of every Zer0 install; candidate → preview →
nightly → dev → main is architecture history, not a component; and repos such as
z0archy, Ripple, z0evals, Hermes LCM, and Verified OSS Loop can belong to the suite
without becoming installable components.

### Per-repo implementation manifests

A repository may add `zer0.repo.yaml` at its root using
[`schemas/repo.schema.json`](schemas/repo.schema.json). The manifest describes
the architecture **at that Git ref**: subsystems and paths, implemented canonical
mechanisms/interfaces/representations, ownership boundaries, and evidence locations.

This is implementation evidence, not a second source of cross-system truth. A repo
manifest cannot redefine the canonical identity owned by the central registries.
z0archy can therefore read the same contract from a GitHub branch or local worktree
without guessing repository structure from filenames alone.

### Component bindings and observations

`registry/components.yaml` optionally records **declarative consumption recipes**:

```yaml
bindings:
  mcp: {command: example-mcp, args: [--root, "${EXAMPLE_ROOT}"]}
  harnesses: [hermes]       # authoritative AODL ids, not local aliases
  hermes: {memory_provider: null}
evidence_source_for: [z0intelligence.context-packet]
```

`mcp` accepts either stdio `command`/optional `args`/`env`, or remote `url`/optional
`headers`. Values may refer to environment variables; never commit credentials.
Per-harness mappings are native adapter settings; `memory_provider` is a string
or null, and an optional per-harness `mcp` replaces the shared server definition.
Each override key must occur in `bindings.harnesses`. A missing/empty harness list
does not claim integration. `evidence_source_for` declares an evidence dependency
seam, not proof of consumer adoption or memory quality.

AODL's `harnesses/catalog.json` owns ids (for example, Claude Code is `claude`,
not `claude-code`). Validation reads that authority, not a copied catalog in z0.
By default it fetches the catalog using `registry/harnesses.yaml`; for offline
checks set `Z0_AODL_CATALOG=/path/to/aodl/harnesses/catalog.json`. Missing authority
or an unknown id fails closed.

Artifact `status` and optional rollout `execution` retain their existing meanings.
A separate optional `observed` mapping requires `at`, `host`, `summary` and a
nonempty `evidence` list. These dated, source-linked snapshots distinguish built,
configured, running, blocked and unknown facts without treating them as desired
state. A running unit does not prove retrieval quality or cross-harness continuity.
See [the generated binding/evidence view](generated/component-bindings.md).

`.files` owns host/profile enablement intent. Native harness adapters own binding.
This registry slice neither enables services nor writes live harness configuration;
it does not implement `z0 apply` or a binding-drift doctor.

Check locally:

```bash
scripts/docs-generate
scripts/registry-check
PYTHONPATH=lib python3 -m unittest discover -s tests -v
```

The dependency-light unit suite uses a small injected catalog and makes no
network calls. The full registry check uses AODL (or `Z0_AODL_CATALOG`).

## Profiles

| Profile | Components | For |
|---------|------------|-----|
| `minimal` | OMP | "I want the agent" |
| `core` | OMP + Tokenomics | normal Zer0 user |
| `personal` | core + z0int | personalization |
| `desktop` | core + Flow | daily Handsfree workflow |
| `compute` | core + Kerdoios | model/provider optimization |
| `research` | z0int + Evolution Lab + frontier-kb | AI research |
| `full` | all stable/canary | power users |

```bash
./z0 init --profile core
./z0 add tokenomics
./z0 add flow
```

## CLI

| Command | Purpose |
|---------|---------|
| `./z0 init` | Interactive or `--profile` install plan + clone |
| `./z0 add <id>` | Add one component |
| `./z0 doctor` | What's installed vs registry pins |
| `./z0 status` | Dev-state table (branch, HEAD, maturity) |
| `./z0 graph` | Text dependency tree |
| `./z0 graph --mermaid` | Mermaid for docs |
| `./z0 docs generate` | Regenerate `generated/` from registry |

## Rule

> **Implementation docs live with implementations. Architecture and onboarding live in `z0`.**

See [ARCHITECTURE.md](ARCHITECTURE.md), [AGENTS.md](AGENTS.md), and [docs/getting-started/five-minute-start.md](docs/getting-started/five-minute-start.md).


## Semantic architecture layers

Beyond installable components, Zer0's canonical map includes execution harnesses, reusable mechanisms, promotion/history lifecycles, information representations, and evidence dependencies.

`registry/representations.yaml` names the information forms that flow through context, planning, decision, observability, and measurement paths. `registry/evidence_dependencies.yaml` records epistemic edges with required evidence, invariants, invalidators, retrieval recipes, and abstention conditions so architecture claims can be verified rather than treated as decorative arrows.
