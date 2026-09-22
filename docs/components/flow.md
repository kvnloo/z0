---
id: components.flow
title: Flow
scope: [flow]
status: generated
---

# Flow

**Repo:** `kvnloo/.files`  
**Plane:** context  
**Architecture status:** `merged`  
**Implementation status:** `experimental`  
**tested_ref:** `bb5c0ea` on `master`

Predicted OS/context state feeding z0intelligence and context compilation. Harness-neutral; the OMP coupling is incidental and must not become architectural.

## Owns

- predicted OS/context state
- OS prediction
- prepare
- routine mining

## Explicitly does not own

- OMP coupling
- training logic
- agent runtime
- token accounting
- training loops

## Relationships

| Type | Target |
|------|--------|
| `emits_contract` | `z0intelligence` |

## Install

```bash
git clone https://github.com/kvnloo/.files.git
git checkout master
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
