# AGENTS.md — Zer0 ecosystem

You are operating in the Zer0 ecosystem.

## Start here (any agent, any harness)

If the user asks for general help with this repo, or you have no task, onboard this host first:

1. Run `./z0 onboard --auto --llm none < /dev/null` from this checkout (it sets up z0evals,
   z0intelligence and dash next to the hardware-default profile). It needs only bash, git and
   curl; it installs into `~/.z0` and user-local dirs. **Never add `--yes` or `--accept`
   yourself**: those grant consent bundles (toolchains, harness, services, models) that only the
   user may grant. Exit 0 = done; exit 3 = done except steps that need the user's consent.
   Any other exit = report the `FAILED` lines.
2. Show the user the "What you need to do" section of the printed report (also in
   `~/.z0/onboard/current/report.md`). Each ask names the exact command. Do not run C1/C2 asks.
3. To contribute to z0intelligence: `cd ~/.z0/repos/z0intelligence`, `export Z0_HOME=~/.z0`,
   then follow that repo's `AGENTS.md` "Start here" (`z0int contribute --json`, follow
   `next_action`, stop at `ask_human` and show `needs_human`).
4. Never push, never post to GitHub (issues, comments, PRs) and never log in to anything
   (gh, tailscale, harnesses) without the user's explicit yes.
5. Undo everything z0 did: `./z0 onboard rollback` (owned files only).

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
