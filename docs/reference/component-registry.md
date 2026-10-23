---
id: reference.component-registry
title: Component registry
scope: [z0]
status: canonical
---

# Component registry

Canonical source: [`registry/components.yaml`](../../registry/components.yaml)

Generated table: [`generated/components.md`](../../generated/components.md)

Install matrix: [`generated/install-matrix.md`](../../generated/install-matrix.md)

## Host intent and native binding health (Draft)

The canonical add-a-tool runbook is [Draft PR #31](https://github.com/kvnloo/z0/pull/31).
Do not create a parallel onboarding convention. Its earlier `z0 apply` and
`.files z0_components` statements described **proposals**, not merged/live
features. [Draft PR #30](https://github.com/kvnloo/z0/pull/30) registers native
recipes; [Draft PR #32](https://github.com/kvnloo/z0/pull/32) implements guarded
native plans and receipts. The present stacked draft adds direct
[`.files fleet.toml`](https://github.com/kvnloo/.files/issues/40) consumption,
read-only `doctor --bindings --json` health, and the source-verified
z0intelligence stdio MCP recipe. All remain unmerged, unverified on MBP and
not deployed. Update the existing PR #31 runbook's status when these drafts land.

For supported host/profile selections, JSON `status` is one of
`MATCH`, `DRIFT`, `UNKNOWN`, or `ERROR`. Exit 0 can mean UNKNOWN; consumers
must inspect `status` and `configs[].findings`. Missing fleet
`z0_components` is unknown; `components = []` explicitly selects none.
Unknown, unmanaged or unselected bindings do not become desired drift.
No observed state confers execution authorization or verified memory use.

Exact invocation, safe Hermes clean-profile example, variable prerequisites,
and OMP verification commands are in the
[repository native binding section](../../README.md#native-config-plans-and-observations).
GraphRAG remains unbound pending a real query backend and full index.
