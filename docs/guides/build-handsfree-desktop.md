---
id: guides.build-handsfree-desktop
title: Predictive desktop
scope: [flow, dash, ripple, oh-my-pi]
concepts: [context, interaction, harnesses]
status: canonical
---

# I want a predictive desktop

```
Flow (predict OS/context state) -> z0intelligence (compile provider-visible state)
        +
Dash / Ripple (interaction surfaces)
        +
a harness that provides the desktop/voice surface you actually want
```

```bash
./z0 init --profile desktop     # flow + dash + ripple, on top of core
```

Notes:

- **Flow** is an owned component with `emits_contract` toward z0intelligence.
  Its scripts live in `kvnloo/.files`; the earlier registry pointed at branch
  `feat/workspace-copilot-flow`, which is a leftover pin — the capability entry
  now records `tested_ref: bb5c0ea` on `master`.
- **Dash** is the multi-harness control surface; **Ripple** is the ephemeral
  intent surface it mounts. Neither executes anything.
- **Handsfree / Live / Stage** are OMP-provided. Since OMP is an upstream
  harness, those features arrive by choosing OMP — they are not Zer0 components.
- **Memento** is a 2024 fork of a screen recorder. It is a possible *future*
  sensor, not the desktop memory authority, and it is not installable.
