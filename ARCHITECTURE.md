# ARCHITECTURE.md — Zer0 (L1, ~5 minutes)

## Responsibility

`kvnloo/z0` is the **canonical front door**: semantic architecture registries, install profiles, generated architecture artifacts, and cross-system onboarding. It answers "what exists?", "what depends on what?", and "what should I install?" — never "run this agent turn."

## Inputs

- Hand-maintained YAML in `registry/`
  - `components.yaml`: installable Zer0 components
  - `harnesses.yaml`: execution surfaces and adoption facts
  - `mechanisms.yaml`: reusable cross-harness mechanisms
  - `interfaces.yaml`: cross-system contracts
  - `lifecycles.yaml`: promotion/history state machines
  - `representations.yaml`: information forms flowing through context, planning, decision and measurement paths
  - `evidence_dependencies.yaml`: epistemic edges with evidence recipes, invariants, invalidators and abstention rules
  - `suite.yaml`: repository surfaces, roles, authority and links into components/harnesses/mechanisms/lifecycles
  - `profiles.yaml`: installable component bundles
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
| Harness adoption / Zer0 role | `z0` harness registry; AODL remains harness-id authority |
| Cross-harness mechanism identity | `z0` mechanism registry |
| Promotion/history semantics | `z0` lifecycle registry |
| Information representation identity | `z0` representation registry |
| Cross-system evidence recipes / architectural claim invariants | `z0` evidence-dependency registry |
| Suite repository membership and semantic role | `z0` suite registry |
| Implementation | Each component repo |
| Research evidence | `frontier-kb` |
| Private traces | `memento` / `z0intelligence` (not frontier-kb) |
| Usage events | `tokenomics` |

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
