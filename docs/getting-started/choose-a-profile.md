---
id: getting-started.choose-a-profile
title: Choose a profile
scope: [z0]
concepts: [profiles, install, harnesses]
status: canonical
---

# Choose a profile

A profile answers two separate questions:

1. **What capabilities do I want?**
2. **Which harness do I execute through?**

Harnesses are upstream systems, never installed as components.

| Profile | Capabilities | Adds |
|---------|--------------|------|
| `minimal` | execution | nothing — one supported harness, your choice |
| `core` | execution, contracts, measurement | `z0`, `aodl`, `tokenomics` |
| `personal` | + cognition | `z0intelligence` |
| `desktop` | + context, interaction | `flow`, `dash`, `ripple` |
| `compute` | + resources | `kerdoios` |
| `context` | + context | `rlm`, `sol-pi-hermes` |
| `research` | + evaluation, research | `evolution-lab`, `z0evals`, `frontier-kb` |
| `full` | all of the above | every experimental component |

```bash
./z0 init --profile desktop
./z0 add kerdoios   # à la carte
```

`full` deliberately excludes reference-only and donor repos: contributing to a
repository does not make it supported infrastructure.

See [generated/install-matrix.md](../../generated/install-matrix.md).
