# AGENTS.md — Zer0 ecosystem

You are operating in the Zer0 ecosystem.

## Before modifying code

1. Read `zer0.registry.yaml` (or `registry/components.yaml`).
2. Identify the **owning component** for the change.
3. Read that component's `AGENTS.md` / `README.md` in its repo.
4. Do **not** move responsibilities across component boundaries without updating the registry.
5. Token/cost claims require **Tokenomics** evidence.
6. Verified-success claims require a **verifier**.
7. **AODL** owns typed intent/plan contracts — not runtime execution.
8. **`z0` owns the map** — not business logic. Never add runtime code here.

## Where things belong

See [docs/reference/ownership.md](docs/reference/ownership.md) (generated).

## Registry commands

```bash
./z0 doctor
./z0 status
./z0 graph --json
```

## Maturity

Check `status` and `execution` in the registry before recommending install:

- `idea` / `shadow` → do not tell users to install
- `experimental` / `canary` → caveat APIs
- `stable` / `live` → default recommendation
