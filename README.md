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
`z0 apply` reconciles only declared MCP entries and Hermes `memory.provider`.
`z0 doctor --bindings` records native config observations without stage promotion.

### Native config plans and observations

```bash
./z0 apply --dry-run --components agentsview,ctx --harness hermes
./z0 apply --dry-run --components agentsview --harness codex
./z0 doctor --bindings
./z0 doctor --bindings --components agentsview,tencentdb-memory
```

Use `--profile <z0-profile>` or `--components a,b` until `.files` supplies its
host intent field. An existing z0 workspace `profile` is the fallback desired
selection. Configured bindings never become desired state automatically.
Without intent, doctor marks desired state unknown. Apply refuses to infer it.
An empty `--components ''` selects no components. It does not prune old entries.

Both commands accept `--host-profile /path/to/intent.yaml`. The input is an
explicit temporary contract, not a claim about an existing `.files` field:

```yaml
host: groot                     # optional, must match this host
components: [agentsview]
harnesses:
  hermes:
    profiles:
      clean:
        components: [ctx]
      chiefstaff:
        components: [agentsview, tencentdb-memory]
```

Each selection uses either `components` or a z0 `profile`. Native profile
selections override harness selections, which override the host selection.
A multi-host file can use `hosts: {groot: {components: [agentsview]}}`.
All selections must name registered components. Unknown fields fail closed.

Supported adapters are Hermes YAML, Claude Code JSON (`claude`), Codex TOML,
and OMP JSON. Hermes includes its root config (`default`) and every existing
`~/.hermes/profiles/*/config.yaml`. Use `--harness hermes --harness-profile clean`
to select one native profile. `--profile` always means a z0 component profile.
`--host` accepts only this host, never a remote target.

Dry-run is the default. Unified diffs show only owned native fragments.
Environment values, header values and command arguments show as `<set>`.
URL credentials and query values are masked. A change hidden by redaction
still reports drift. `${VARIABLE}` recipes use the current environment.
Apply refuses unset variables before the first write.

Actual writes require `--apply --yes`. This opt-in command changes only
component-named MCP entries and the declared Hermes memory provider.
It never enables services, prunes unrelated entries, edits OMP extensions,
or changes registry maturity. Unsupported recipes appear as notices, not
successful integration claims. A timestamped, owner-only backup precedes
each existing config replacement. New configs use owner-only permissions.
YAML and TOML retain unrelated settings and comments. JSON retains unrelated
values, but its whitespace is normalized. Symlink configs refuse writes.
Config changes after the plan refuse replacement.

Doctor distinguishes registered-but-unbound, bound-but-unregistered,
bound-but-service-not-running, missing desired components, recipe mismatches,
and bindings outside the observable native surfaces. Disabled servers do not
count as bound. `service: {unit: ctx.service}` declares an optional user unit
for `systemctl --user is-active`; doctor never starts or enables it.
A configured component without a declared unit has no inferred service state.
An active unit does not establish MCP connectivity or retrieval quality.
Components with no declared harness binding and no observed native entry appear
once under `registry/inspected-native-scope`, not as desired enablement.

Doctor writes a JSON observation receipt under
`$Z0_HOME/observations/bindings-<UTC timestamp>.json` (default `~/.z0`).
The receipt contains host, timestamp, config mtimes, desired selections,
configured names, findings and declared unit observations. It contains no
config secrets and never promotes a stage. `--receipt /new/path.json` selects
another destination and refuses any existing file. Doctor does not write
live harness configs.

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
| `./z0 doctor --bindings` | Read-only native binding drift and JSON observation receipt |
| `./z0 apply --dry-run --components a,b` | Masked native config diffs for explicit intent |
| `./z0 apply --apply --yes --profile core` | Back up configs, then write only owned binding keys |
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
