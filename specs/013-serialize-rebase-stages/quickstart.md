# Quickstart: Validating Per-Specification Serialization of Rebase and Stages

Prerequisites: a repo checkout with `gh` authenticated as a maintainer, and
one or more scratch specifications at various stages (at least one with a
`spec/NNN-slug` branch created, i.e. past planning). Manual `gh workflow
run` dispatches are used throughout to control timing precisely — the
GitHub Actions UI's run list for the repository is where "queued vs.
running vs. completed" is observed for each scenario.

## Scenario 1 — Main-line advance during an in-flight stage does not force-push the branch (US1, SC-001, SC-002)

1. Dispatch a stage for a scratch specification against its `spec/NNN-slug`
   branch (e.g. `gh workflow run wing-commander-3-plan.yml -f
   slug=NNN-scratch`) and confirm in the Actions UI that its job has
   started (not just queued).
2. While it is still running, push a commit to the default branch (or wait
   for the next automation merge) so that a rebase of `spec/NNN-slug` would
   ordinarily fire (via `wing-commander-rebase.yml`'s `push` trigger).
3. Expected:
   - The rebase workflow's matrix job for this branch appears in the
     Actions UI as **queued**, not running, for as long as the stage job
     is still in progress (both share `wing-commander-specs/NNN-scratch`,
     contracts/concurrency-groups.md).
   - The stage completes and its publish (branch push / PR) succeeds —
     `spec/NNN-slug`'s tip is exactly what the stage produced, with no
     intervening force-push.
   - The queued rebase job then starts and completes normally, rebasing
     the now-updated branch onto the (already-current, since the stage's
     own push may itself be based on old main, or not — either way,
     idempotent) default branch tip.
4. Non-expected (the bug this feature fixes): the rebase job runs
   concurrently with the stage and force-pushes over it, causing the
   stage's own publish step to fail as non-fast-forward.

## Scenario 2 — A stage dispatched during an in-progress rebase waits for it to settle (US2)

1. Trigger a rebase for a scratch branch that will hit a conflict needing
   AI resolution (see `specs/008-auto-rebase/quickstart.md` Scenario 3's
   setup) — this keeps the rebase job running for a while.
2. While it is still running, dispatch a stage for the same specification
   (e.g. `gh workflow run wing-commander-4-tasks.yml -f slug=NNN-scratch`).
3. Expected:
   - The stage's job appears queued in the Actions UI until the rebase job
     completes.
   - Once the rebase finishes (settles, one way or the other) and releases
     `wing-commander-specs/NNN-scratch`, the stage's job starts and
     checks out the branch as the rebase left it (rebased-and-pushed, or
     untouched if the rebase was abandoned/escalated) — never a
     half-rewritten mid-rebase state, since the two never overlap.

## Scenario 3 — Unrelated specifications still run concurrently (US3, SC-003)

1. Set up two different scratch specifications, A and B, each with its own
   `spec/NNN-slug` branch.
2. Dispatch a rebase-triggering push affecting A's branch, and in the same
   window dispatch a stage for B.
3. Expected: both runs proceed at the same time in the Actions UI — neither
   waits on the other (different concurrency groups,
   `wing-commander-specs/A-slug` vs. `wing-commander-specs/B-slug`). This
   should look identical to today's behavior with no measurable added
   delay.

## Scenario 4 — A deferred rebase still lands eventually (US3, SC-004)

1. Repeat Scenario 1 through the point where the rebase job is queued
   behind a running stage.
2. Instead of waiting, immediately dispatch a *second* rebase-triggering
   push (or another stage dispatch) for the same specification while the
   first rebase is still queued.
3. Expected (research.md D4): GitHub Actions keeps only the most-recently
   queued request pending — the first queued rebase attempt may be
   superseded rather than itself running, but the specification's branch
   is still brought current, either by the request that does survive to
   run, or by the next opportunity: the nightly `schedule` trigger
   (`wing-commander-rebase.yml`), or the next default-branch push. Confirm
   by leaving the branch alone afterward and observing that a subsequent
   trigger (manual `gh workflow run wing-commander-rebase.yml`, simulating
   the nightly run) rebases it onto current main with no manual
   intervention.

## Scenario 5 — No contention: uncontended runs are unchanged (US3 Acceptance Scenario 3, FR-006)

1. With no stage or rebase in flight for a scratch specification, advance
   the default branch so a rebase of its branch would fire.
2. Expected: the rebase runs immediately, exactly as it does today (no
   queuing, no added delay) — cross-check timing against
   `specs/008-auto-rebase/quickstart.md` Scenario 1.
3. Separately, dispatch a stage for a specification with no rebase in
   flight and confirm it likewise starts immediately.

## Scenario 6 — Two stages for the same specification never overlap (US1 Edge Case, FR-008)

1. Dispatch a stage for a scratch specification (e.g. `plan`).
2. While it is running, attempt to dispatch a different stage for the
   *same* specification that would not normally be reachable yet (e.g. a
   manual `tasks` restart) — or, more realistically, trigger a duplicate
   dispatch of the same stage (a re-sent merge notification).
3. Expected: the second stage's job queues behind the first under the same
   `wing-commander-specs/NNN-scratch` group and only starts once the first
   releases it — the existing duplicate-attempt guards inside each stage
   (e.g. `plan.yml`'s "Check for a prior planning attempt") still apply
   once it does run, so this is belt-and-braces, not a new no-op path.

See `contracts/concurrency-groups.md` for the exact group string and job
membership each scenario above exercises, and `data-model.md` for the
state-transition table GitHub Actions' own concurrency queuing follows.
