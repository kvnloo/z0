---
id: components.evolution-lab
title: Evolution Lab
scope: [evolution-lab]
status: generated
---

# Evolution Lab

**Repo:** `kvnloo/evolution-lab`  
**Plane:** evaluation  
**Architecture status:** `branch_only`  
**Implementation status:** `experimental`  
**tested_ref:** `—` on `main`

Experiment execution: frozen grouped comparisons, training/search, and the QUALIFICATION decision — whether a candidate clears the frozen gates, producing promotion evidence. It neither publishes studies nor activates anything.

## Owns

- experiment execution
- frozen grouped comparisons
- training and search
- qualification evidence

## Explicitly does not own

- activation/deployment state
- publication of frozen studies

## Relationships

| Type | Target |
|------|--------|
| `qualifies` | `z0evals` |
| `trains_for` | `z0intelligence` |

## Install

```bash
git clone https://github.com/kvnloo/evolution-lab.git
git checkout main
python3 -m pip install -e .
```

## Verify

```bash
python3 -m unittest discover -s tests
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
