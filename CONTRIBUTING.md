# Contributing to z0

## What belongs here

- Registry changes (`registry/*.yaml`)
- Generated docs (`generated/`, run `./z0 docs generate`)
- Human onboarding (`docs/getting-started/`, `docs/guides/`)
- CLI installer (`lib/z0/`, `z0`)

## What does NOT belong here

- Component implementation code
- Runtime orchestration
- Model weights or private traces
- The local cognition model list (model ids, roles, licences, benchmarks, local measurements, promotion state) — that is canonical in `kvnloo/z0intelligence` (`manifests/local_cognition.v1.json`) and is referenced, never copied

## Workflow

1. Edit `registry/components.yaml` (or profiles/interfaces/cognition).
2. Run `./scripts/registry-check`.
3. Run `./z0 docs generate`.
4. Run `./scripts/docs-check` (must be clean git diff; it also runs `./scripts/cognition-check`).
5. Open PR.

## Per-repo manifests (future)

Each component may add `zer0.component.yaml` at its root. CI can diff against central registry. Until then, update `registry/components.yaml` directly.
