---
id: components.rlm
title: RLM
scope: [rlm]
status: generated
---

# RLM

**Repo:** `kvnloo/oh-my-pi`  
**Plane:** context  
**Architecture status:** `branch_only`  
**Implementation status:** `experimental`  
**tested_ref:** `—` on `exp/rlm-evidence-addressing`

The addressable evidence/context plane: evidence handles, cognitive-state compilation and context virtualization. It has NO repo of its own — it lives as branches on the OMP fork, which currently carries 102 local branches across six checkouts. One lineage must be designated canonical before anything about "the RLM design" is claimed.

## Owns

- addressable evidence plane
- evidence handles
- context virtualization
- selected retrieval

## Explicitly does not own

- provider transport
- canonical transcript

## Relationships

| Type | Target |
|------|--------|
| `depends_on` | `oh-my-pi` |
| `emits_contract` | `z0intelligence` |

## Install

```bash
git clone https://github.com/kvnloo/oh-my-pi.git
git checkout exp/rlm-evidence-addressing
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
