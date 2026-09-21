---
id: components.tokenomics
title: Tokenomics
scope: [tokenomics]
status: generated
---

# Tokenomics

**Repo:** `kvnloo/tokenomics`  
**Plane:** measurement  
**Architecture status:** `merged`  
**Implementation status:** `live`  
**tested_ref:** `9af30ca` on `master`

Vendor-neutral measurement contracts: multi-harness traces, verified outcomes, context economics, experiment identity, quota reconciliation and OTel transport. Owns Zer0-specific semantics; OpenTelemetry remains only the transport.

## Owns

- token/cost/latency semantics
- verified outcome
- context economics
- experiment identity
- receipt schema

## Explicitly does not own

- OTel transport
- provider catalogs
- routing
- execution

## Relationships

| Type | Target |
|------|--------|
| `measured_by` | `kerdoios` |

## Install

```bash
git clone https://github.com/kvnloo/tokenomics.git
git checkout master
python3 -m pip install -e packages/python
```

## Verify

```bash
python3 -m pytest packages/python/tests -q
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
