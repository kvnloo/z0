---
id: guides.optimize-tokens
title: Optimize tokens
scope: [tokenomics, rlm]
concepts: [context, token-attribution, measurement]
status: canonical
---

# I want a faster / cheaper coding agent

```
pick a harness (Hermes · DeepSeek Harness · OMP)
        ↓
   Tokenomics (measure everything)
        ↓ optional
   Context plane — RLM evidence addressing
        ↓ optional
   z0intelligence (select / escalate / activate)
```

```bash
./z0 init --profile core      # z0 + aodl + tokenomics
```

Then:

1. Measure first. `tokenomics report --range today` is the baseline; without it
   any saving claim is unverified.
2. Add the context plane (`./z0 init --profile context`) to introduce evidence
   addressing.

**The measurement gap is real.** Tokenomics does not yet carry enough
causal/context lineage to *verify* a context saving. Until it does, treat
context-optimization numbers as unverified. See
[docs/architecture/context-plane.md](../architecture/context-plane.md).

RLM is not an OMP switch — it is its own plane and currently
`architecture_status: branch_only`.
