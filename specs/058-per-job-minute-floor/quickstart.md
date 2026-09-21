# Quickstart: Validating The Per-Job Minute Floor

Prerequisites: a checkout of this repository with the feature branch's
changes, `gh` authenticated against a test repository (or this one, with
write access), `jq`, `git`. All scenarios below are the Independent
Tests from spec.md's three user stories, made runnable, plus the gate
regression pass. Run stage dispatches against a disposable test
repository or a scratch branch where practical — Stories 1-3 create real
runs, comments, and (Story 3) branch commits.

## Story 1 — The image check contributes no billed job on the no-image path

1. Pick any published stage (e.g. `intake`) and dispatch it twice via
   `gh workflow run`:
   - once with no `container-image` input (or the wrapper's default),
   - once with a deliberately unusable image (bad tag, or credentials
     the registry rejects).
2. For the first run: `gh run view <run-id> --json jobs | jq
   '.jobs[] | {name, conclusion}'` — confirm
   `verify-image-prerequisites` shows `conclusion: skipped` and contests
   no billed minute, and every other job's conclusion matches what the
   same dispatch produces on current `main` (Acceptance Scenario 1).
3. For the second run: confirm `verify-image-prerequisites` shows
   `conclusion: failure`, ran before any dependent job's container was
   created (check job start/end timestamps against dependents'), and
   every job naming it as a dependency shows `conclusion: skipped`
   (Acceptance Scenario 2, SC-002).
4. Repeat step 1's no-image dispatch for a job with two dependencies —
   the image check and another job — while forcing the other dependency
   to fail; confirm the dependent job is skipped (Acceptance Scenario 4:
   the image check tolerating skip never widens a dependent's other
   requirements).
5. Run `python .github/scripts/run-local-gates.py` and confirm the
   amended Gate 22/23 pass on the real tree.
6. Revert one dependent job's `if:` to bare `needs:` on a scratch branch
   and confirm Gate 23 fails, naming that stage and job (Acceptance
   Scenario 5, FR-007); revert the scratch change afterward.
7. Repeat step 1-3 for a representative sample of the remaining 12
   stages (or all 13, if time allows) to confirm FR-002's "not a subset"
   requirement — SC-001/SC-002/SC-004 apply to each one individually.

## Story 2 — A clean watchdog inspection costs no agent call

1. Drive one watchdog inspection over a run known to be healthy (every
   collector reports, no signals) — dispatch `wing-commander-8-
   watchdog.yml` with that run's id, or wait for its natural completion
   trigger.
2. `gh run view <watchdog-run-id> --json jobs | jq '.jobs[] |
   {name, conclusion}'` — confirm `diagnose`, `triage`, `act`, and
   `findings-dropped` all show `skipped`, and no step anywhere in the
   run invoked `anthropics/claude-code-action` (grep the run's own job
   logs for the action name as a second check). Confirm the lifecycle
   issue received exactly one passed-inspection comment and no issue was
   filed (Acceptance Scenario 1, SC-005).
3. Confirm the run billed at most two jobs (`collect` +
   `report-unhandled-failure`) — SC-006.
4. Drive a second inspection over a run with one failed collector and at
   least one reporting collector, both with an empty signal set —
   confirm the posted comment uses the partial-pass wording naming both
   counts (Acceptance Scenario 2).
5. Drive a third inspection over a run carrying at least one real signal
   — confirm `diagnose` ran and the run's filing/triage/action outcome
   is unchanged from current `main` for the same evidence (Acceptance
   Scenario 3, SC-007, FR-012).
6. Confirm the all-failed-collectors case still reaches the "could not
   inspect" path and posts no passed-inspection record (Acceptance
   Scenario 4).
7. Confirm the aggregate-step-failure case posts no passed-inspection
   record (Edge Case).
8. Dispatch a watchdog run inspecting the watchdog's own run and confirm
   it is neither skipped nor softened (Acceptance Scenario 6, FR-015).
9. Kill every other job in a watchdog run deliberately (or find a
   historical run where this happened) and confirm
   `report-unhandled-failure` still executed (Acceptance Scenario 7,
   SC-008).
10. Dispatch `wing-commander-8-watchdog.yml` with no `run-name` supplied
    and confirm the wrapper's own job list is exactly one job, and the
    stage's posted comments carry a correctly resolved run name
    (FR-020).
11. Let `wing-commander-8b-watchdog-self.yml` inspect the healthy
    inspection from step 2: confirm it reports the run verified and
    files nothing (Acceptance Scenario 8, SC-014). Then run
    `verify-watchdog-run-failure-paths.sh` locally and confirm every
    pre-existing failure shape (crashed agent, could-not-inspect,
    fired safety net, fabricated verdict) still fails, alongside the new
    healthy-shape fixture passing (SC-012).

## Story 3 — Metrics persistence pays only for record-bearing completions

1. Drive a burst of stage completions inside a short window (e.g.
   dispatch `intake`, `clarify`, and `plan` back to back on a scratch
   spec) plus one healthy watchdog inspection (Story 2, step 2).
2. `gh run list --workflow=wing-commander-metrics-persist.yml --json
   databaseId,event,conclusion,createdAt` — confirm one persistence run
   per stage completion, and zero persistence runs whose triggering
   event is the watchdog completion (Acceptance Scenario 1, SC-009).
3. `git fetch origin metrics && git show origin/metrics:records.jsonl`
   — confirm each burst completion that emitted a record appears exactly
   once, and its `record_key` landed within minutes of that run
   concluding (Acceptance Scenario 2, SC-010, SC-011's ten-minute clause).
4. Manually trigger the sweep
   (`gh workflow run wing-commander-metrics-persist.yml -f
   since=<a timestamp before the signal-bearing watchdog inspection you
   drove in Story 2, step 5>`), then confirm that inspection's record
   now appears in `records.jsonl` exactly once (Acceptance Scenario 3).
5. Re-trigger the same sweep with the same `since` value and confirm
   `records.jsonl`'s line count is unchanged, and `sweep-state.json`'s
   `high_water_mark` did not regress (Acceptance Scenario 4, FR-022).
6. Trigger the hand-driven single-run re-drive
   (`-f run-id=<a burst run's id>`) while a sweep dispatched moments
   earlier is still in flight; confirm both complete without a
   duplicate record and without either failing the other (Acceptance
   Scenario 5, FR-024).
7. Engineer a persistence failure (e.g. point `destination-branch` at a
   protected ref the token cannot push to) and confirm the origin run
   it was collecting from is untouched — no comment, no status change on
   that run (Acceptance Scenario 6, FR-025).
8. Using the schema-conformance fixture harness, simulate a run whose
   metrics artifact has already expired; confirm `unpersisted.jsonl`
   gains exactly one line naming it and the sweep's high-water mark
   still advances past it (Acceptance Scenario 7, FR-028).
9. Confirm `sweep-state.json` and `records.jsonl` are updated together
   under contention: drive two overlapping sweep dispatches and confirm
   neither loses a record nor strands the mark (Edge Case: "two
   persistence runs overlapping").

## Gate regression pass (all three sub-problems)

Run every new/amended gate locally exactly as CI does
(`python3 .github/scripts/run-local-gates.py`, or the individual
`verify-*` invocations from `contracts/gate-coverage-058.md`) against:

1. The correct tree — all gates pass (SC-012).
2. Each gate's own negative fixture in turn (a reverted dependent job, a
   partial-pass fixture, an aggregate-failure fixture, a sweep-idempotence
   fixture, an expired-artifact fixture, the wrapper trigger list with
   watchdog still present) — confirm each turns its specific gate red,
   and that removing a gate's `run:` line from `lint-workflows.yml` is
   itself caught by the existing `verify-gate-wiring.py`.
3. Confirm no gate anywhere in the repository gained an agent invocation
   as a side effect of this feature (SC-013) — `grep -rn
   "anthropics/claude-code-action" .github/workflows .github/actions`
   and diff the match set against current `main`.

## Cleanup

Scenarios that create real branches, comments, or issues in a shared
repository (Stories 2 and 3 especially) should run against a disposable
test repository or be reverted afterward — deleting scratch comments,
resetting `metrics` branch test state, and closing any issue opened only
for this exercise before merging this feature's own implementation PR.
