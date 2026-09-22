---
id: components.aodl
title: AODL
scope: [aodl]
status: generated
---

# AODL

**Repo:** `kvnloo/aodl`  
**Plane:** contracts  
**Architecture status:** `merged`  
**Implementation status:** `live`  
**tested_ref:** `549f2a1` on `main`

Typed intent IR, compiled plan and observed state with fail-closed validation. Also owns the harness catalog and the Mesh Registry, which z0 CONSUMES rather than duplicating.

## Owns

- typed intent IR
- compiled plan
- observed state
- harness catalog
- mesh registry
- fail-closed validation
- typed intent/plan contracts

## Explicitly does not own

- model selection
- routing policy
- provider catalogs
- runtime execution
- runtime implementation
- provider execution

## Relationships

| Type | Target |
|------|--------|
| `emits_contract` | `dash` |
| `emits_contract` | `ripple` |

## Install

```bash
git clone https://github.com/kvnloo/aodl.git
git checkout main
python3 -m pip install -e .
```

## Verify

```bash
python3 -m pytest -q
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
