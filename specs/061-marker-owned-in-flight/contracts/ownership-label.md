# Contract: Loop Ownership Label

FR-013/FR-014. See [research.md](../research.md) D6 for why `board:owned`
was chosen over alternatives.

## Write

The fix step's existing PR-creation call gains one flag:

```diff
- gh pr create -R "$GITHUB_REPOSITORY" --title "..." --body "..." --head "$BRANCH" --base main
+ gh pr create -R "$GITHUB_REPOSITORY" --title "..." --body "..." --head "$BRANCH" --base main --label board:owned
```

One call, one API round-trip — there is no window between "PR exists" and
"PR is labeled" for a run to die inside.

## Read

Only [resume-recovery.md](./resume-recovery.md)'s PR-recovery step 2 reads
this label (`gh api .../issues -f labels=board:owned`, filtered to `state=
open`). No other job, gate, or eligibility input reads it —
`board_eligibility.py`'s `classify_issue()`/`is_excluded()`/
`in_flight_candidate()` take no label input beyond what they already read
from the *issue's* own labels (never a PR's).

## Prerequisites

The label must already exist in the repository (created once by a
maintainer via `gh label create board:owned ...`, documented in
`docs/setup.md` alongside `board:stalled`) before the fix step's first run
after this feature ships. `gh pr create --label` on a nonexistent label
fails the whole PR-creation call — this is a one-time setup cost, not a
runtime concern the fix step needs to handle (per the spec's own
Assumptions section).

## Non-goals (Out of Scope, restated for this contract's own boundary)

- Not retrofitted onto PRs the loop opened before this feature ships.
- Never removed by the loop once applied.
- Never used as a routing signal, an eligibility input, or anywhere other
  than the FR-007 fallback lookup above.
