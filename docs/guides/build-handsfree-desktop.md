---
id: guides.build-handsfree-desktop
title: Build Handsfree desktop
scope: [oh-my-pi, flow]
concepts: [handsfree, stage]
status: canonical
---

# I want a predictive desktop

```
OMP (Handsfree + Live + Stage)
+ Flow (prediction / prepare)
 ↓ optional
z0intelligence
 ↓ later
Memento
```

```bash
./z0 init --profile desktop
```

Handsfree lives in OMP (`python/omp-hud`). Flow scripts live in `kvnloo/.files` branch `feat/workspace-copilot-flow`.
