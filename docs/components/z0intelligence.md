---
id: components.z0intelligence
title: z0intelligence
scope: [z0intelligence]
status: generated
---

# z0intelligence

**Repo:** `kvnloo/z0intelligence`  
**Plane:** cognition  
**Architecture status:** `merged`  
**Implementation status:** `experimental`  
**tested_ref:** `4f88010` on `master`

The cognition plane: semantic model selection and escalation, context resolution, bounded DecisionBackend contracts, the local SLM portfolio, cognition receipts, and ACTIVATION of qualified policies into shadow/canary/active. JEV/NanoJev/OpenJev are implementations behind these contracts, not peers of them.

## Owns

- semantic model selection
- escalation policy
- context resolution
- DecisionBackend contracts
- local SLM portfolio
- cognition receipts
- activation (shadow / canary / active)

## Explicitly does not own

- provider daily-quota accounting
- RPM/RPD/TPM/TPD
- GPU and resource placement
- token measurement

## Relationships

| Type | Target |
|------|--------|
| `consumes_contract` | `aodl` |
| `consumes_contract` | `tokenomics` |
| `measured_by` | `tokenomics` |
| `evaluated_by` | `evolution-lab` |
| `reference_to` | `rlm` |

## Install

```bash
git clone https://github.com/kvnloo/z0intelligence.git
git checkout master
python3 -m pip install -e .
```

## Verify

```bash
python3 -m pytest tests/test_cognition_candidates.py -q
```

## Implementation docs (live in the owning repo)

- `readme`: `README.md`
- `portfolio`: `docs/local-cognition-portfolio.md`

_Generated from `registry/components.yaml`. Do not edit by hand._
