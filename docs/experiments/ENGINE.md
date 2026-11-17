# Experiment research engine

Master RFC: https://github.com/kvnloo/z0/issues/45 · z0intelligence + Hermes: https://github.com/kvnloo/z0intelligence/issues/320 · .files: https://github.com/kvnloo/.files/issues/147

## Pieces

| piece | where | status |
|---|---|---|
| Map (definitions, north stars, data tiers, referee defaults) | `registry/experiments.yaml` | shipped |
| CLI: `list`, `show`, `render`, `start`, `fingerprint`, `post`, `ledger`, `verify` | `lib/z0/experiments.py` (`./z0 exp ...`) | shipped |
| Ledger: result markers in issue comments -> `generated/experiments-ledger.jsonl` + `generated/experiments/<id>.md` | `./z0 exp ledger --refresh`; scheduled Action `experiments-ledger.yml` commits them | shipped |
| Referee contract every runner imports | [eng-referee](https://github.com/kvnloo/z0/issues/43) | open |
| Unattended keep/revert driver | [eng-hillclimb](https://github.com/kvnloo/z0/issues/44) | open |
| Capped runner on any host | [.files fx-k3s-runner](https://github.com/kvnloo/.files/issues/142) | open |
| Runners | each experiment's owning repo, path in the map | mostly open (`runner: missing`) |

## Agent protocol: "start experiment X"

1. `./z0 onboard --auto --llm none` once per host (AGENTS.md).
2. `./z0 exp start X` prints `z0.exp.start.v1` JSON. Follow `next_action`:
   - `build` with an `arm` like `compactor-<name>`: the fixed arms are measured and the next cell is your own arm of that open family. Write it with a test in the worktree from `command`, commit, run the runner with your arm id (so `repo_sha` is your commit), then `then`.
   - `build` without an `arm`: no runner yet. Build it to the issue's spec in a worktree of the owning repo. Interface: `--arm A --tier public|self --out result.json`, output `z0.exp.result.v1`. Ask the user before pushing or opening a PR.
   - `run`: run `command`, then `then` (`./z0 exp post ...`). Controls are always offered first.
   - `done`: every arm has a result for this tier and hardware. Propose a new arm by PR to the map.
3. `./z0 exp post X result.json` validates and prints the comment. Post with `--yes` only after the user agrees.

## Result: `z0.exp.result.v1`

Required: `schema, exp_id, epoch, arm, data_tier, data_manifest_sha256, hardware_class, repo_sha, n, metric{name,value[,ci95]}, verdict (KEEP|DISCARD|NULL|INVALID), command`. A `repo_sha` ending in `+dirty` (run with uncommitted changes) is refused. Optional: `controls{arm: value}` (required for KEEP), `arm_spec_sha256` (for open arm families like `teacher-<model>`), `artifacts`, `notes`, `model`, `harness`.

## Verify: `z0.exp.verify.v1`

A referee re-run that reproduces a measured cell marks it without posting a new
measurement: `./z0 exp verify <id> --fingerprint <fp> [--by <login>] [--note <text>]`
prints a `<!-- z0-exp-verify {...} -->` marker comment (`--yes` posts it after the
user's explicit yes, like `exp post`). `./z0 exp ledger` merges verify markers into
the matching ledger row as `verified` (+ `verified_by`, `verified_note`), shown in
the leaderboard. `exp verify` refuses a fingerprint that no result row carries.

## Dedup

Fingerprint = sha256 of `(exp, epoch, arm, arm_spec, tier, data manifest, hardware class)`. `start` merges the committed `generated/experiments-ledger.jsonl` with fresh issue markers (or the `~/.z0` cache when gh is unavailable), so a measured cell is skipped even without GitHub auth. `start` skips an arm when:
- public tier: you already have a result on this hardware class, or 3 hardware classes already do;
- self tier: a result exists for the same data manifest hash.

INVALID rows and rows from older epochs never count. Editing an entry's arms, metric, gates or data requires bumping `epoch`.
