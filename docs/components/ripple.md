---
id: components.ripple
title: Ripple
scope: [ripple]
status: generated
---

# Ripple

**Repo:** `kvnloo/ripple`  
**Plane:** interaction  
**Architecture status:** `merged`  
**Implementation status:** `experimental`  
**tested_ref:** `ea63d72` on `main`

Ephemeral intent surface mounted by Dash. Consumes AODL as data; does not own it.

## Owns

- ephemeral intent surface

## Explicitly does not own

- AODL ownership
- execution

## Relationships

| Type | Target |
|------|--------|
| `consumes_contract` | `aodl` |

## Install

```bash
git clone https://github.com/kvnloo/ripple.git
git checkout main
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
