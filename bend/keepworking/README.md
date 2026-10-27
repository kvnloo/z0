# keepworking law

Owner ask: "write bend laws to force yourself to keep working until all of the asks are
at 100% or everything you can do is done, except for only blocked reqs."

Law: a bound Claude Code session may stop iff every entry of the ask ledger
(`~/workspace/.z0/asks.yaml`, JSON syntax) is

- `done` with owner-visible evidence: `deployed_sha` (hex sha), `device_receipt`
  (an existing receipt file) or `pr` (a GitHub PR URL); or
- `blocked` with an owner-only `blocked_by` (`sudo`, `login`, `merge_review`,
  `physical`, `owner_decision`, `payment`) plus a detail, re-`checked` within `stale_days`.

Open, partial, unknown, weak-evidence, agent-doable-blocked and stale entries forbid a
stop, and so does a missing or unparseable ledger. Two exits are laws too: background
tasks or session crons that will wake the session (W1), and the `stop_hook_active` loop
guard when no tool ran since the last block (G1). Claude Code also caps consecutive
stop-hook continuations at 8.

| file | role |
| - | - |
| `MODEL.bend` / `LAWS.bend` / `PROOF.bend` | finite model, owner laws, proofs (`bend PROOF.bend --verdict`) |
| `lib/z0/keepworking/kernel.py` | Python twin; the only code that decides block/allow |
| `lib/z0/keepworking/ledger.py` | ledger reader: classifies entries into the kernel domain |
| `lib/z0/keepworking/hook.py` | Stop hook: stdin event -> `{"decision":"block","reason":...}` |
| `tests/keepworking/` | twin parity (186 rows), Python + Bend mutation, hook e2e with mock transcripts |
| `scripts/keepworking-install` | stamped release under `~/.local/share/z0-keepworking`, `--settings` registers the hook, `--rollback` |

Binding: a session is bound when its cwd is under `scope_cwd_prefixes` (default
`~/workspace`), `enforce` is not `off`, `Z0_KEEPWORKING` is not `off`, and it is not a
child session (`CLAUDE_CODE_CHILD_SESSION=1`) unless `include_child_sessions` is true.

Run the laws: `bend/keepworking/bootstrap.sh <dir>`, export the printed `BEND`/`LEAN_BIN`,
then `python3 -m unittest discover -s tests/keepworking -t .`.
