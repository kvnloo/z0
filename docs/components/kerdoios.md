---
id: components.kerdoios
title: Kerdoios
scope: [kerdoios]
status: generated
---

# Kerdoios

**Repo:** `kvnloo/kerdoios`  
**Plane:** resources  
**Architecture status:** `merged`  
**Implementation status:** `live`  
**tested_ref:** `b5755ea` on `main`

Resource placement: inventory, hard constraints, dimensional quota/capacity (RPM/RPD/TPM/TPD), cost/capability/privacy dimensions, Pareto selection, reservations and expiry-aware allocation. It is NOT an LLM gateway and does NOT execute providers. Currently shipped as a Hermes plugin; the logical capability is harness-neutral.

## Owns

- resource inventory
- hard constraint filtering
- quota and capacity ledger
- Pareto / portfolio allocation
- reservations
- placement
- provider routing
- allocation policy

## Explicitly does not own

- provider execution
- generic model gateway
- token measurement
- routing policy
- agent runtime

## Relationships

| Type | Target |
|------|--------|
| `consumes_contract` | `tokenomics` |

## Install

```bash
git clone https://github.com/kvnloo/kerdoios.git
git checkout main
python3 -m pip install -e .
```

## Verify

```bash
python3 -m unittest discover -s tests
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`
- `placement`: `docs/local-cognition-placement.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
