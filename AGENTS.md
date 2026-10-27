# AGENTS.md — Zer0 ecosystem

You are operating in the Zer0 ecosystem.

## Start here (any agent, any harness)

If the user asks for general help with this repo, or you have no task, onboard this host first:

1. Run `./z0 onboard --auto --llm none < /dev/null` from this checkout (it sets up z0evals,
   z0intelligence and dash next to the hardware-default profile). It needs only bash, git and
   curl; it installs into `~/.z0` and user-local dirs. **Never add `--yes` or `--accept`
   yourself**: those grant consent bundles (toolchains, harness, services, models) that only the
   user may grant. A first run takes 15-40 minutes (clones and builds), longer than most agent
   shell timeouts, so run it detached and poll, and do not end your turn while it runs:
   `mkdir -p ~/.z0/logs && nohup sh -c './z0 onboard --auto --llm none < /dev/null > ~/.z0/logs/onboard.log 2>&1; echo "exit=$?" >> ~/.z0/logs/onboard.log' &`,
   then check `tail -5 ~/.z0/logs/onboard.log` every few minutes until it prints `exit=`. If a run was killed,
   just run it again: it resumes (finished steps are skipped). Exit 0 = done; exit 3 = done
   except steps that need the user's consent; exit 5 = degraded: a component off the
   first-task path failed (listed under `FAILED` and in the report), so continue to steps 2
   and 3 without asking, and list the `FAILED` lines in your summary. Network steps already
   retry, so do not re-run just for a transient error. Any other exit (1) = the first-task
   path itself failed: report the `FAILED` lines and stop.
2. Show the user the "What you need to do" section of the printed report (also in
   `~/.z0/onboard/current/report.md`). Each ask names the exact command. Do not run C1/C2 asks.
3. Then, unless the user named another task, find them a first task. "Help with this repo" already
   authorizes steps 1-3, so do not stop to ask before or during them:
   `cd ~/.z0/repos/z0intelligence && export Z0_HOME=~/.z0`; if `.venv/bin/z0int` is missing, run
   `./scripts/bootstrap.sh` (repo-local `.venv` only; it can take 10+ minutes, so run it detached
   with its log in `~/.z0/logs/` and poll like step 1); then run `.venv/bin/z0int --json contribute`
   and follow its `next_action` until `kind` is `ask_human`.
   Finish by showing the user the pick (task id), the two alternatives and `needs_human`, then
   end your reply with z0int's question, copied verbatim from `next_action.why` of that
   `ask_human` step (for example "Claim t-139-e2e-trace, choose an alternative (...), or stop?").
   Claim, post, push or open a PR only after the user's explicit yes.
4. Keep every log you write under `~/.z0/logs/`; write nothing else in the user's home.
5. Never push, never post to GitHub (issues, comments, PRs) and never log in to anything
   (gh, tailscale, harnesses) without the user's explicit yes.
6. Undo everything z0 did: `./z0 onboard rollback` (owned files only).

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
