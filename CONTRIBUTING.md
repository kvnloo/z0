# Contributing to z0

Zer0 is personal AI infrastructure that makes frontier models do less: small,
measured components (routing, memory, token accounting, a coding agent) tied
together by one registry. This repo is the map, installer and registry. People
and their coding agents are welcome to help with the open problems below.

## Open problems

- **Experiments** (`claimable` issues, master list in [RFC #45](https://github.com/kvnloo/z0/issues/45)):
  each issue says how to run it, what "done" means and how results are posted.
  The protocol is in [docs/experiments/ENGINE.md](docs/experiments/ENGINE.md).
  - [`claimable` in z0](https://github.com/kvnloo/z0/issues?q=is%3Aopen+label%3Aclaimable)
  - [`claimable` in z0intelligence](https://github.com/kvnloo/z0intelligence/issues?q=is%3Aopen+label%3Aclaimable)
- **RFCs** to think through: [Verified Learning Control Loop](rfcs/verified-learning-control-loop/README.md)
  and the [open RFC issues](https://github.com/kvnloo/z0/issues?q=is%3Aopen+RFC+in%3Atitle).
- Implementation lives in [z0intelligence](https://github.com/kvnloo/z0intelligence)
  and the [semantic-router fork](https://github.com/kvnloo/semantic-router)
  (its issues are off; file them here).

## With a coding agent

Clone this repo and tell your agent: **"read AGENTS.md and help with this repo"**.
[AGENTS.md](AGENTS.md) onboards the host (`./z0 onboard --auto --llm none`, 15-40
minutes the first time), then suggests a first task and asks you before it
claims, posts, pushes or opens a PR. For an experiment, say **"start experiment
<id>"** (the id is in the issue title, e.g. `eng-ledger`).

## Claim a task

Comment `/claim <id>` on the `claimable` issue (for example `/claim eng-ledger`).
A maintainer confirms the claim on the issue; no bot does this yet. Have an
idea instead? Use the "Propose a task or experiment" issue form.

## Run the tests

Python 3.10+ with PyYAML from the hashed lock:

```bash
python3 -m venv ~/.venvs/z0   # outside the checkout: one test refuses an interpreter inside it
~/.venvs/z0/bin/pip install --require-hashes -r requirements.lock
~/.venvs/z0/bin/python -m unittest discover -s tests -t .   # about 30 s; Bend/Lean cases skip unless installed
./scripts/registry-check
./scripts/public-leak-check
```

The laws tests refuse scratch space under `/tmp`. If your `TMPDIR` points there
(common in agent sandboxes), prefix the test command with `env -u TMPDIR`.

CI runs the same suite on every PR (Python 3.10 and 3.12). The required check is
`check`. On your first PR, CI starts after a maintainer approves the run.

## Pull requests, credit and terms

- Open the PR against `main`. The template asks what changed and how you tested it.
- Credit: your authorship is kept in the git history; name upstream projects you
  reused in the PR body.
- Terms: contributions will be accepted under a Contributor License Agreement
  (owner decision). The CLA check is being set up in
  [#49](https://github.com/kvnloo/z0/pull/49).
- Be kind: [Code of Conduct](CODE_OF_CONDUCT.md).

## Talk

[Discussions](https://github.com/kvnloo/z0/discussions) for questions and ideas;
issues for bugs, onboarding feedback and proposals.

## What belongs here

- Registry changes (`registry/*.yaml`)
- Generated docs (`generated/`, run `./z0 docs generate`)
- Human onboarding (`docs/getting-started/`, `docs/guides/`)
- CLI installer (`lib/z0/`, `z0`)

## What does NOT belong here

- Component implementation code
- Runtime orchestration
- Model weights or private traces

## Workflow

1. Edit `registry/components.yaml` (or profiles/interfaces).
2. Run `./scripts/registry-check`.
3. Run `./z0 docs generate`.
4. Run `./scripts/docs-check` (must be clean git diff).
5. Open PR.

## Per-repo manifests (future)

Each component may add `zer0.component.yaml` at its root. CI can diff against central registry. Until then, update `registry/components.yaml` directly.
