# Contract: Prove Step

## Entry (FR-041)

Triggered by `pull_request: types: [closed]` where the closing PR's body
cites an issue this loop selected (contracts/board-item-marker.md) and
`github.event.pull_request.merged == true`. A closed-not-merged PR is
recorded on the issue and the prove step is never entered (edge case,
User Story 6 scenario 5).

## `.github/actions/wing-commander-dispatch-and-wait/action.yml` (extracted, shared)

| Input | Notes |
|---|---|
| `workflow-file` | the workflow to re-drive |
| `workflow-inputs` | JSON, passed as `-f` pairs to `gh workflow run` |
| `attempt-token` | correlation token, e.g. `${{ github.run_id }}-${{ github.run_attempt }}` |
| `poll-attempts` / `poll-interval-seconds` | default to `auto-release.yml`'s existing values |

| Output | Notes |
|---|---|
| `run-url` | the correlated run, or empty if correlation was ambiguous/absent |
| `conclusion` | terminal `conclusion`, or `timeout` if polling exhausted its budget |

`auto-release.yml`'s `dispatch-release` job is repointed at this composite
in the same change that introduces it (research.md D14); its own dispatch
behavior (attempt-token, correlate-by-title, poll `status` to `completed`,
verify the tag independently) is unchanged.

## Actions-only decision (research.md D15)

`board_prove.py` decides `actions_only` from the merged PR's changed
paths: `docs/**`/`specs/**`-only, or `.github/scripts/verify-*.py`-only
(already proven by that PR's own required checks) → `actions_only: false`,
recorded with the reason, issue closes on the merge evidence alone
(FR-041 scenario 4). Any other changed path → `actions_only: true`.

## Re-drive (FR-042/FR-043)

When `actions_only: true`: call `wing-commander-dispatch-and-wait` against
the wrapper workflow that can dispatch the changed behavior; record
`run-url`/`conclusion` on the PR or issue.

- `conclusion == success` → close the issue, citing the run URL and
  outcome (FR-043).
- `conclusion in {failure, timeout}` → issue stays open, carrying the
  failing/unresolved run URL (FR-043, User Story 6 scenario 3).
- Dispatch itself could not be correlated (`run-url` empty) → issue stays
  open, carrying that fact.
