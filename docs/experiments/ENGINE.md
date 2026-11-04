# Experiment research engine

Master RFC: https://github.com/kvnloo/z0/issues/45 · z0intelligence + Hermes: https://github.com/kvnloo/z0intelligence/issues/320 · .files: https://github.com/kvnloo/.files/issues/147

## Pieces

| piece | where | status |
|---|---|---|
| Map (definitions, north stars, data tiers, referee defaults) | `registry/experiments.yaml` | shipped |
| CLI: `list`, `show`, `render`, `start`, `fingerprint`, `post` | `lib/z0/experiments.py` (`./z0 exp ...`) | shipped |
| Ledger: result markers in issue comments, cached in `~/.z0/experiments/<id>.ledger.json` | `./z0 exp start` reads it | shipped (read); aggregation Action is [eng-ledger](https://github.com/kvnloo/z0/issues/42) |
| Referee contract every runner imports | [eng-referee](https://github.com/kvnloo/z0/issues/43) | open |
| Unattended keep/revert driver | [eng-hillclimb](https://github.com/kvnloo/z0/issues/44) | open |
| Capped runner on any host | [.files fx-k3s-runner](https://github.com/kvnloo/.files/issues/142) | open |
| Runners | each experiment's owning repo, path in the map | mostly open (`runner: missing`) |

## Agent protocol: "start experiment X"

1. `./z0 onboard --auto --llm none` once per host (AGENTS.md).
2. `./z0 exp start X` prints `z0.exp.start.v1` JSON. Follow `next_action`:
   - `build`: no runner yet. Build it to the issue's spec in a worktree of the owning repo. Interface: `--arm A --tier public|self --out result.json`, output `z0.exp.result.v1`. Ask the user before pushing or opening a PR.
   - `run`: run `command`, then `then` (`./z0 exp post ...`). Controls are always offered first.
   - `done`: every arm has a result for this tier and hardware. Propose a new arm by PR to the map.
3. `./z0 exp post X result.json` validates and prints the comment. Post with `--yes` only after the user agrees.

## Result: `z0.exp.result.v1`

Required: `schema, exp_id, epoch, arm, data_tier, data_manifest_sha256, hardware_class, repo_sha, n, metric{name,value[,ci95]}, verdict (KEEP|DISCARD|NULL|INVALID), command`. Optional: `controls{arm: value}` (required for KEEP), `arm_spec_sha256` (for open arm families like `teacher-<model>`), `artifacts`, `notes`, `model`, `harness`.

## Dedup

Fingerprint = sha256 of `(exp, epoch, arm, arm_spec, tier, data manifest, hardware class)`. `start` skips an arm when:
- public tier: you already have a result on this hardware class, or 3 hardware classes already do;
- self tier: a result exists for the same data manifest hash.

INVALID rows and rows from older epochs never count. Editing an entry's arms, metric, gates or data requires bumping `epoch`.
