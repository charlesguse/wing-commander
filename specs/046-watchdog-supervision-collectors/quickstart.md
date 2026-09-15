# Quickstart: Validating the Four New Watchdog Collectors

Prerequisites: a checkout of this repository with the feature branch's
changes, `gh` authenticated against a test repository (or this one, with
write access), `jq`, `git`. Each scenario below is the Independent Test
from spec.md's corresponding user story, made runnable. Where a scenario
needs a live pipeline run, prefer seeding fixtures and driving the
relevant `verify-*` gate script directly (`contracts/gate-coverage-046.md`)
over waiting on real runs — the gates exercise the exact same jq/bash the
live collector runs, per constitution VIII's "same subject, same
arguments, locally and in CI."

## Story 1 — A developing turn-budget trend is visible before it becomes a hard stop

1. Seed `records.jsonl`-shaped fixture lines for one stage with counted
   turns climbing 160/180 → 197/180 → 226/180 against an enforced ceiling
   of 450 (data-model.md's Budget trend fixture).
2. Run `collect-turn-budget`'s logic against the last of those three
   records (`verify-turn-budget-collector.sh` drives this without a live
   run). Confirm: the per-run signal for the last record carries the
   counted turns, intended budget, enforced ceiling, and consumed
   fraction; a `turn-budget-trend` signal is also emitted, band `watch`
   (three consecutive at-or-over-budget runs, ceiling fraction under
   0.6).
3. Confirm a run with only the first record in history emits the per-run
   signal but no cross-run signal (Acceptance Scenario 1).
4. Add a fourth consecutive at-or-over-budget record. Confirm the new
   trend signal hashes to the same signal id as the third run's (same
   `{stage, band}`) — `contracts/turn-budget-trend.md`'s walkthrough Run 4.
5. Drive a full watchdog pass on run 3's evidence and confirm exactly one
   `pipeline-defect` issue is created, labeled `🐕 · turn-budget-trend`.
   Drive it again on run 4's evidence and confirm the *same* issue gets a
   new comment, not a second issue (SC-004).
6. Close that issue. Drive a fifth consecutive-at-or-over-budget run's
   evidence through `collect-turn-budget` directly and confirm the
   collector emits **no** cross-run signal at all — `verify-turn-budget-suppression.sh`'s
   positive case (Acceptance Scenario 4). Confirm no new issue and no
   reopen.
7. Push the window to also cross the 0.6 climb-fraction threshold (band
   now `critical`). Confirm `collect-turn-budget` emits again (the
   suppression check finds no closed match for `critical`) and driving
   the watchdog on this evidence creates a **second**, distinct issue —
   the first (`watch`) issue remains closed and untouched (Acceptance
   Scenario 5, SC-004's "the first run that escalates the band produces
   exactly one").
8. Seed a run comfortably under budget and confirm zero signals of any
   kind (Acceptance Scenario 6). Seed a run whose metrics record marks
   `turns.available: false` and confirm the collector reports outcome
   `ok` with zero signals (Acceptance Scenario 7).

## Story 2 — Every cost-bearing stage's spend actually reaches the lifecycle issue, correctly formatted

1. Seed a metrics record with `cost_available: true` for a run, and a
   lifecycle issue with no comment attributable to that run. Drive
   `collect-cost-report` and confirm a `cost-line-missing` signal naming
   the stage and run (Acceptance Scenario 1).
2. Seed a lifecycle comment carrying the literal string `Cost:
   $COST_LINE · 40 turns` (the #272 leak shape) attributed to a run whose
   metrics record marks `cost_available: true`. Confirm a
   `cost-line-malformed` signal carrying that exact observed text
   (Acceptance Scenario 2).
3. Seed a run with `cost_available: false` and no cost line. Confirm no
   signal (Acceptance Scenario 3).
4. Seed a well-formed `$0.42` line and, separately, a well-formed
   sub-$1 `$0.0042` line (research.md R8's 4-decimal case). Confirm
   neither produces a signal regardless of magnitude (Acceptance Scenario
   4) — this is the case most likely to regress if a future edit reverts
   to a single fixed-decimal pattern.

## Story 3 — The final PR's narrative is checked against the repository it describes

1. Construct a final PR fixture whose body claims a task count off by
   one from `tasks.md`'s checked-box count, a commit count off by two
   from `git rev-list --count <base>..<head>`, and a test count that
   doesn't match the fixture-files-added count (research.md R7). Drive
   `collect-final-pr-claims` and confirm three distinct `narrative-drift`
   signals, each carrying claimed value, actual value, and source
   (Acceptance Scenarios 1-3).
2. Drive a full watchdog pass on this evidence and confirm each mismatch
   reaches the lifecycle issue's report **and that no `pipeline-defect`
   issue is created for any of them** — `verify-narrative-drift-routing.sh`'s
   positive case (Acceptance Scenario 4, FR-025).
3. Construct a PR body with a claim in a shape the parser doesn't
   recognize (e.g. prose with no isolable number). Confirm no signal for
   that claim (Acceptance Scenario 5).
4. Construct a PR body whose three claims all match ground truth. Confirm
   zero `narrative-drift` signals (Acceptance Scenario 6).

## Story 4 — Two in-flight specs claiming the same number are detected, not discovered later

1. With one spec-draft PR open for number `046`, construct a second
   fixture branch also prefixed `046-` and register it as a second open
   PR. Drive `collect-spec-collision` for an intake run that allocated
   `046` and confirm a `spec-number-collision` signal naming both PRs and
   the contested number (Acceptance Scenario 1).
2. Repeat with one open PR numbered to match an existing `specs/046-*`
   directory already on `main`, and confirm a collision naming the PR and
   the directory (Acceptance Scenario 2).
3. Seed every open spec PR with a distinct number and confirm no signal
   (Acceptance Scenario 3).
4. Drive the watchdog twice on the same two-PR collision (simulating a
   second intake run observing the still-unresolved collision) and
   confirm the second pass comments on the existing finding rather than
   opening a second one (Acceptance Scenario 4, FR-029).

## Cross-cutting: zero new agent invocations (SC-003)

After wiring all four collectors, count `uses: anthropics/claude-code-action`
occurrences inside the `collect` job of `watchdog.yml` — must remain zero
(the only such step in the whole workflow is `diagnose`, unchanged).
Re-run `run-local-gates.py` and confirm the new `verify-*` scripts from
`contracts/gate-coverage-046.md` are present and passing.
