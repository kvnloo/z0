---
id: architecture.system-map
title: System map
scope: [z0]
concepts: [ecosystem, dependencies, planes]
status: canonical
---

# System map

The graph is **generated** from typed relationships in the registry. There is no
hand-maintained Mermaid diagram to drift: an ambiguous edge is not expressible,
because `integrates_with` was replaced by a closed vocabulary.

- **[generated/graph.mmd](../../generated/graph.mmd)** — the typed relationship graph
- **[generated/almanac.json](../../generated/almanac.json)** — the same facts, machine-readable
- **[generated/components.md](../../generated/components.md)** — owned components
- **[generated/upstreams.md](../../generated/upstreams.md)** — external systems
- **[generated/sources.md](../../generated/sources.md)** — delegated catalog authorities

Regenerate with `./z0 docs generate`; CI fails on drift (`scripts/docs-check`).

## Reading the graph

The shape is planes converging on execution, not one runtime at the root:

```text
surfaces → intent/authority → execution harnesses
                                    │
                    ┌───────────────┴───────────────┐
              context/evidence                  cognition
                    └───────────────┬───────────────┘
                                 execution
                                    │
                    ┌───────────────┼───────────────┐
                placement       measurement      inspection
                    └───────────────┼───────────────┘
                    qualify → publish → activate
```

Three harnesses are peers. z0 declares `executes_via` each of them rather than
making any one of them the architectural root.
