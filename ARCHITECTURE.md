# ARCHITECTURE.md — Zer0 (L1, ~5 minutes)

## Responsibility

`kvnloo/z0` is the **federated network almanac**: reconciled registry truth,
capability profiles, the contract registry, and every generated architecture
artifact. It answers *what exists?*, *who owns each semantic responsibility?*,
*what do we support versus merely reference?*, and *where is the authoritative
metadata?* — never "run this agent turn."

## The core rule

> Store Zer0-specific relationships and policy.
> Fetch upstream facts from the authority that already owns them.

Every duplicated-looking fact therefore has an explicit **authority** and a
**cache policy**. `registry/sources.yaml` records the relationship and the
refresh policy — never the facts, and never a snapshot treated as fresher than
its source.

## Inputs

- Hand-maintained YAML in `registry/` (components, upstreams, sources,
  interfaces, profiles, cognition)
- Local workspace state at `~/.z0/workspace.yaml`
- **Not** an input: live upstream state. That is discovered by
  `z0 registry doctor` and cached only under the gitignored `.z0-cache/`.

## Outputs

- `generated/almanac.json` — the whole reconciled almanac, machine-readable
- `generated/graph.mmd` — the **typed** relationship graph
- `generated/{components,upstreams,sources,interfaces,install-matrix}.md`
- `docs/reference/ownership.md` — generated from each component's
  `owns` / `not_here`
- `zer0.registry.yaml` — flat agent-consumable summary

Everything above is generated. If a generated page is wrong, fix the registry.

## Relationships are typed

An ambiguous `integrates_with` is refused. The vocabulary is closed and lives in
`lib/z0/registry.py`:

```text
owns · depends_on · implements · consumes_contract · emits_contract
discovers_from · executes_via · measured_by · governed_by · trains_for
legacy_of · reference_to · provides_research_evidence · governs · evaluated_by
qualifies · publishes_evidence_to · activates
```

The last three encode the promotion split — see below.

## Authoring boundaries

| Data | Authority |
|------|-----------|
| Component boundaries, planes, profiles | `z0` registry |
| Harness catalog and mesh registry | **AODL** — z0 consumes it, never recopies it |
| Implementation | each component repo |
| Local cognition model list | `z0intelligence` — referenced, never copied |
| Local cognition stage map + owners | `z0` (`registry/cognition.yaml`) |
| Provider/model identity (DSH routes) | DeepSeek Harness `llm-pi-ai` catalog |
| Model metadata, files, licences | Hugging Face Hub (delegated) |
| Provider/model cost tables | LiteLLM (delegated) |
| Live provider inventory | OpenRouter (delegated, live-only) |
| Served models / architecture support | vLLM, Ollama (delegated) |
| Telemetry transport | OpenTelemetry (delegated) |
| Measurement semantics, verified outcome | `tokenomics` |
| Resource placement and quota | `kerdoios` |
| Research evidence | `frontier-kb` |
| Private traces | never in `frontier-kb`; no current authority |

## Promotion is three acts

The word "promotion" was overloaded across three systems. It is split:

| Act | Owner | Meaning |
|-----|-------|---------|
| **qualify** | `evolution-lab` | the candidate clears the frozen experimental gates |
| **publish** | `z0evals` | the reproducible study is frozen and published |
| **activate** | `z0intelligence` | the qualified policy enters shadow → canary → active |

Evolution Lab may not activate. z0evals may not train or activate.
z0intelligence may not declare a candidate qualified.

## Failure boundaries

- `z0 doctor` and `z0 registry doctor` report drift; they never fix or mutate it
- `z0 init` clones and prints setup commands; it is not a package manager
- Stale generated docs fail CI (`scripts/docs-check`)
- A malformed registry fails CI (`scripts/registry-check`) rather than
  silently generating wrong docs

## Non-goals

- Replacing npm/pip/cargo
- Hosting runtime services
- Duplicating component READMEs
- A second AODL harness catalog or Mesh Registry
- Treating a cached upstream snapshot as authoritative

## Diagram

See [generated/graph.mmd](generated/graph.mmd) — **never edit by hand**; run
`./z0 docs generate`.
