---
id: getting-started.five-minute-start
title: Five-minute start
scope: [z0, oh-my-pi, tokenomics]
concepts: [install, profiles]
status: canonical
---

# Five-minute start

```bash
git clone https://github.com/kvnloo/z0
cd z0
pip install -r requirements.txt
./z0 init --profile core
```

This clones **OMP** and **Tokenomics** to `~/.z0/repos/` and records state in `~/.z0/workspace.yaml`.

Verify:

```bash
./z0 doctor
./z0 status
```

Next: follow OMP's README in the cloned `oh-my-pi` repo for API keys and `./omp` setup.
