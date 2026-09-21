# ARCHITECTURE.md — Zer0 (L1, ~5 minutes)

## Responsibility

`kvnloo/z0` is the **canonical front door**: component registry, install profiles, generated architecture artifacts, and cross-system onboarding. It answers "what exists?", "what depends on what?", and "what should I install?" — never "run this agent turn."

## Inputs

- Hand-maintained YAML in `registry/`
- Optional per-repo `zer0.component.yaml` (future; central registry is source of truth today)
- Local workspace state at `~/.z0/workspace.yaml`

## Outputs

- `generated/` — Mermaid graph, component table, install matrix
- `docs/` — human journeys and reference
- `zer0.registry.yaml` — agent-consumable summary

## Dependencies

- Python 3.10+ and PyYAML for CLI
- Git for clone/install
- Each component's native toolchain (bun, pip, …) remains in that repo

## Data ownership

| Data | Owner |
|------|-------|
| Component boundaries | `z0` registry |
| Implementation | Each component repo |
| Research evidence | `frontier-kb` |
| Private traces | `memento` / `z0intelligence` (not frontier-kb) |
| Usage events | `tokenomics` |

## Execution and evaluation planes

Runtime authority and evaluation evidence are deliberately separate. See [docs/reference/evaluation-plane.md](docs/reference/evaluation-plane.md).

```text
execution:  intent -> harness/controller -> tools/artifacts -> verifier/outcome
evaluation: replayable events -> counters + semantic observers + outcomes
                                      -> Evolution Lab -> credited promotion
```

JEV is the seed semantic observer/reference backend for this evaluation plane. A JEV answer is a probabilistic reading, not verified truth. z0intelligence owns the typed observer/backend contract; Tokenomics owns objective measurement semantics; Evolution Lab owns grouped experiments and promotion gates. AODL may provide authored intent/workflow context but is not a required JEV runtime hop.

Security authority stays outside learned observers: capability policy, sandboxing, scoped credentials, deterministic validation, and explicit approval remain authoritative.

## Failure boundaries

- `z0 doctor` reports drift; it does not fix it
- `z0 init` clones and prints setup commands; it is not a package manager
- Stale generated docs fail CI (`scripts/docs-check`)

## Non-goals

- Replacing npm/pip/cargo
- Hosting runtime services
- Duplicating component READMEs
- GitHub Wiki as canonical source (docs live in Git, publish to Pages later)

## Diagram

See [generated/graph.mmd](generated/graph.mmd) — **never edit by hand**; run `./z0 docs generate`.
