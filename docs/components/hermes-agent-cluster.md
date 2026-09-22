---
id: components.hermes-agent-cluster
title: Hermes Agent Cluster
scope: [hermes-agent-cluster]
status: generated
---

# Hermes Agent Cluster

**Repo:** `kvnloo/hermes-agent-cluster`  
**Plane:** execution  
**Architecture status:** `merged`  
**Implementation status:** `experimental`  
**tested_ref:** `—` on `main`

Application-layer cluster of Hermes agent workers with its own capability scheduler, leases, heartbeat state machine (online -> degraded -> offline) and orphan rescheduling. Recorded because it performs RESOURCE PLACEMENT, which the architecture assigns to Kerdoios: it is a competing placement authority, not a peer runtime substrate. Two schedulers over one fleet is exactly the duplication this registry exists to surface. The repository is live, so `architecture_status` is merged; what is superseded is its claim on placement, recorded in `not_here` and the `legacy_of` edge.

## Owns

- agent worker fleet
- worker leases and heartbeat
- orphan rescheduling

## Explicitly does not own

- resource placement (Kerdoios owns placement)
- provider and model inventory
- capability trust
- measurement

## Relationships

| Type | Target |
|------|--------|
| `legacy_of` | `kerdoios` |

## Install

```bash
git clone https://github.com/kvnloo/hermes-agent-cluster.git
git checkout main
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
