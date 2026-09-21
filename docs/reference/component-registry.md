---
id: reference.component-registry
title: Registry reference
scope: [z0]
status: canonical
---

# Registry reference

The registry is **federated** — three entity classes in three files.

| Class | Source | Generated view |
|-------|--------|----------------|
| Owned components | [`registry/components.yaml`](../../registry/components.yaml) | [generated/components.md](../../generated/components.md) |
| Upstream systems | [`registry/upstreams.yaml`](../../registry/upstreams.yaml) | [generated/upstreams.md](../../generated/upstreams.md) |
| Delegated sources | [`registry/sources.yaml`](../../registry/sources.yaml) | [generated/sources.md](../../generated/sources.md) |
| Interfaces | [`registry/interfaces.yaml`](../../registry/interfaces.yaml) | [generated/interfaces.md](../../generated/interfaces.md) |
| Profiles | [`registry/profiles.yaml`](../../registry/profiles.yaml) | [generated/install-matrix.md](../../generated/install-matrix.md) |

Machine-readable: [`generated/almanac.json`](../../generated/almanac.json).
Ownership map: [`docs/reference/ownership.md`](ownership.md).

Validate with `./scripts/registry-check`; discover live upstream heads with
`./z0 registry doctor`.
