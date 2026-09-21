---
id: getting-started.five-minute-start
title: Five-minute start
scope: [z0, aodl, tokenomics]
concepts: [install, profiles, harnesses]
status: canonical
---

# Five-minute start

```bash
git clone https://github.com/kvnloo/z0
cd z0
pip install -r requirements.txt
./z0 init --profile core
```

`core` installs the **owned** spine — `z0`, `aodl`, `tokenomics` — into
`~/.z0/repos/` and records state in `~/.z0/workspace.yaml`.

It does **not** install a harness. Harnesses are upstream systems you choose
separately, because they are not Zer0 components:

```bash
./z0 init --profile core          # then pick Hermes, DeepSeek Harness or OMP
```

Verify:

```bash
./z0 doctor                       # installed vs registry tested_ref
./z0 registry doctor              # validate the almanac + live upstream heads
./z0 status
```

Next: follow the chosen harness's own README for credentials and setup. See
[generated/upstreams.md](../../generated/upstreams.md) for the peer executors.
