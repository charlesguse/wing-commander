# Contract: Prove Step

## Entry (FR-041)

Triggered by `pull_request: types: [closed]` where the closing PR's body
cites an issue this loop selected (contracts/board-item-marker.md) and
`github.event.pull_request.merged == true`. A closed-not-merged PR is
recorded on the issue and the prove step is never entered (edge case,
User Story 6 scenario 5).

(#557) The closing PR must also be this loop's own: `BOARD_PR_OWNED_JQ`
(`board:owned`, head in this repository) applied to the event's
`pull_request`. A PR that fails it is not a board item, so prove is not
entered and nothing is recorded on the issue. A failed fetch of the
issue's comments (for the marker check) fails the gate with an
`::error::` annotation. It is not treated as "no marker".

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

Before dispatching, two pre-dispatch checks (specs/060-self-redrive-concurrency
FR-001/FR-001a) decide whether a dispatch could even start; the outcome
itself is one of the eight reasons
`specs/060-self-redrive-concurrency/contracts/proof-outcome-taxonomy.md`
specifies (`group-busy`/`not-started`/`unfinished`/`displaced`/
`uncorrelated`/`no-target`/`nothing-reaches`/`success`/`failure`), computed
by `board_prove.outcome_reason()` — never the three-branch
success/failure-or-timeout/uncorrelated shape this section stated before
specs/060-self-redrive-concurrency shipped. Every non-`success` reason
leaves the issue open, carrying which of the eight conditions applied.

## Directed proof run (specs/060-self-redrive-concurrency)

When the workflow this feature would re-drive is `board-loop.yml` itself
(the wrapper's own case 1, "the changed workflow dispatches itself"), the
re-drive is a **directed proof run**: a `workflow_dispatch` of
`board-loop.yml` carrying a non-empty `directed-stage` input, running
exactly one job (`triage`/`review`/`readiness`/`prove` — never
`select`/`route`/`fix`, which either pick a board item or open a fix PR)
against the caller-supplied issue (and, for `prove`, PR) rather than one
`select()` chose. It selects no board item and opens no fix PR (FR-002),
and it is the only kind of `board-loop.yml` run permitted to be in flight
at the same time as the run that dispatched it — see
`specs/060-self-redrive-concurrency/contracts/directed-proof-run.md` for
the full mechanism (the `workflow_dispatch` input table, the aimable-stage
set, and job gating) and
`specs/060-self-redrive-concurrency/contracts/concurrency-groups.md` for
the per-job concurrency groups this depends on. An external,
non-`board-loop.yml` target (FR-004) is unaffected: it continues to be
dispatched and waited on exactly as before this feature.
