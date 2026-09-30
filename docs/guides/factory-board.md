# z0 factory board

One GitHub Projects board over every z0 repo. It replaces Linear as the *view* of z0 work:
the board is filled from GitHub by `scripts/board-sync`, so it can't drift from git.

## How to read it

| Field | Meaning | Who sets it |
|---|---|---|
| **Status** | Hermes Ship lifecycle: Triage → Backlog → Todo → In Progress → Ready to Review → Maintainer Review → Done | sync fills it when empty; **only you** move items into Todo or Maintainer Review |
| **Lane** | Core = targets the default branch (minimal main); Nightly = ships on nightly first; Frontier = RFC / research / experiment | derived: PR base branch, `lane:*` label, or title prefix |
| **Agent** | Who did the work: claude, grok, omp, hermes, codex, cursor, human, … | derived from `agent:*` labels, branch prefix, bot signature, author |
| **Kind** | Registry component kind of the repo (intelligence, compute, contract, …) | derived from `registry/components.yaml` |
| **Priority** | P0–P3 | from `priority:*` labels when empty; then yours to change |
| **Repository** | built in | GitHub |

Closing an issue or merging a PR moves it to Done (built-in workflow).

## Everyday use

- **Queue work:** drag a card from Backlog to Todo. Agents claim Todo.
- **Approve publication or merge:** drag from Ready to Review to Maintainer Review.
- **Reprioritize:** change Priority on the card; sync won't undo it.
- **Tag bot work:** agents follow the oss-factory convention — a `<worker> bot` label (`claude bot`, `grok bot`, …) and `"from": "<worker>"` in the hidden `oss-factory:v1` block; a branch prefix (`claude/`, `codex/`, …) also works.

## One-time setup in the UI (the API can't create views)

Open the project → **+ New view** for each:

1. **Board** — layout *Board*, column by *Status*, filter `-status:Done`. Your daily view.
2. **Needs me** — layout *Table*, filter `status:"Ready to Review"`, group by *Repository*.
3. **Lanes** — layout *Board*, column by *Lane*, filter `is:open`. Core vs Nightly vs Frontier at a glance.
4. **By agent** — layout *Table*, group by *Agent*, filter `is:open`, sort by *Priority*.

Then **⋯ → Workflows**: check *Item closed* and *Pull request merged* both set Status = Done
(on by default). Leave *Auto-add* off; `board-sync` covers every repo, and free plans get only one auto-add workflow.

## Keeping it fresh

```
scripts/board-sync --plan   # dry run
scripts/board-sync          # sync now
```

Run on a schedule, e.g. a Hermes cron no-agent job every 15 minutes.
Repos come from the registry, so a new component shows up on the board automatically.

## Relation to Linear and Keel

Keel and the Hermes Ship authority chain still read Linear for upstream OSS
(Noctalia, Omarchy, …) publication authority. This board covers the z0 repos.
Move the authority chain over only after Keel can read the board.
