---
id: guides.optimize-tokens
title: Optimize tokens
scope: [oh-my-pi, tokenomics]
concepts: [rlm, token-attribution]
status: canonical
---

# I want a faster / cheaper coding agent

```
OMP
 ↓
Tokenomics (measure)
 ↓ optional
RLM (context spill)
 ↓ optional
z0int specialists
```

```bash
./z0 init --profile core
```

Then enable RLM in OMP and verify with `tokenomics savings --range today`.
