---
id: components.sol-pi-omp
title: SoL-Pi for OMP
scope: [sol-pi-omp]
status: generated
---

# SoL-Pi for OMP

**Repo:** `kvnloo/sol-pi-omp`  
**Plane:** context  
**Architecture status:** `open_pr`  
**Implementation status:** `experimental`  
**tested_ref:** `—` on `main`

OMP-loadable implementation of the SoL-Pi mechanism family — Action Fusion and ObservationPack — without patching the harness.

## Owns

- Action Fusion
- ObservationPack

## Explicitly does not own

- canonical context plane

## Relationships

| Type | Target |
|------|--------|
| `implements` | `sol-pi` |
| `depends_on` | `oh-my-pi` |

## Install

```bash
git clone https://github.com/kvnloo/sol-pi-omp.git
git checkout main
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
