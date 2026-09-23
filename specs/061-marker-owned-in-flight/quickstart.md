# Quickstart: Validating The Loop Recognizes Its Own Work

**Feature**: specs/061-marker-owned-in-flight | **Spec**: [spec.md](./spec.md)

These are the runnable checks that prove this feature works, in the order
they become available as implementation lands. See
[contracts/in-flight-detection.md](./contracts/in-flight-detection.md),
[contracts/resume-recovery.md](./contracts/resume-recovery.md), and
[contracts/ownership-label.md](./contracts/ownership-label.md) for exact
shapes; see [data-model.md](./data-model.md) for the entities referenced
below.

## Prerequisites

- A checkout of this repository with `.github/scripts/board_eligibility.py`
  and `.github/scripts/board_item_marker.py` present.
- Python 3 (whatever the repository's own CI runner provides — no
  feature-specific dependency).
- For the end-to-end scenario only: `gh` authenticated against a repository
  where the `board:owned` label exists (see
  [contracts/ownership-label.md](./contracts/ownership-label.md)
  "Prerequisites").

## 1. Unit-level: the in-flight decision (SC-004)

```bash
python3 .github/scripts/run-local-gates.py
```

This runs the full PR-time gate suite, including Gate 81
(`verify-board-eligibility.py`), which after this feature lands asserts
`in_flight_candidate()`'s exact return value against all ten fixture cases
FR-012 names. Expected: `verify-board-eligibility: 0 failure(s).`

To confirm the gate can actually fail (not vacuously pass — Constitution
VIII): temporarily edit `board_eligibility.py`'s `in_flight_candidate()` to
admit an issue with no marker (e.g. `return open_issues[0]["number"],
False` unconditionally), re-run the command above, and confirm Gate 81
fails with a message naming the `no-marker` fixture case. Revert the edit
afterward.

## 2. Unit-level: resume never leaves `step` empty (SC-002)

Exercised as part of the same gate suite once `board-loop.yml`'s resume
logic changes are covered by a `verify-*` gate; until that gate exists,
inspect `board-loop.yml`'s `resume` step directly against
[contracts/resume-recovery.md](./contracts/resume-recovery.md)'s decision
table and confirm every branch assigns one of `triage`/`fix`/`review`/the
marker's own step — never leaves `step` unset. (Whether this becomes its
own fixture-backed gate, or remains covered by inspection plus the
end-to-end scenario below, is an implementation-time decision; either way
Gate 81 above is the one FR-012 requires.)

## 3. Replaying the reported failure (SC-001/SC-003)

Against a disposable or forked repository (never against `wing-commander`
itself — this durably opens issues/PRs):

1. Open two ordinary issues, A (older) and B (newer), each eligible per
   `classify_issue()` (e.g. maintainer-authored).
2. Open two ordinary PRs, one saying `Fixes #A` and one saying `Fixes #B`
   (mirroring run 35839986595's #467/#469) — neither carrying `board:owned`,
   neither issue carrying a board item marker.
3. Dispatch `board-loop.yml` (`workflow_dispatch`).
4. Confirm the run's own step summary states it selected issue A (the
   oldest-first eligibility scan's answer), not the issue either PR cites
   by coincidence of list order.

## 4. Interrupt-and-resume cycle (SC-005/SC-006)

1. Let a dispatched run reach the fix step and open a PR (marker step now
   `review`, PR carries `board:owned`).
2. Manually delete the marker comment (simulating a run that died before
   writing it) but leave the PR and branch in place.
3. Dispatch the loop again.
4. Confirm: the run's summary states it recovered the PR via the FR-007
   label fallback (not a marker), continues at `review`, and opens no
   second branch or PR (`gh pr list` for that issue still shows exactly
   one open PR after the run).

## 5. Stale marker falls through (SC-007)

1. With an issue carrying a marker at `review` or later naming a real PR
   number, close that PR without merging it.
2. Dispatch the loop again.
3. Confirm the run's summary states the marker's recorded PR is no longer
   open and that selection fell through to the oldest-first scan — not that
   the run stalled or re-attached to the closed PR.

## Non-goals for this quickstart

Does not re-validate spec 057's own oldest-first ordering, exclusion list,
or triage/route/review/readiness/prove step bodies — those are unchanged by
this feature (Out of Scope) and are already covered by spec 057's own
validation.
