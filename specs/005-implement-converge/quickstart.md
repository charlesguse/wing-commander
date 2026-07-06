# Quickstart: Validating the Implement/Converge Stage

Prerequisites: a repo checkout with `gh` authenticated as a maintainer, and a
scratch specification that has already completed the tasks stage (a
`spec/NNN-slug` branch with `spec.md`, `plan.md`, `tasks.md`, and
`spec-meta.json` at `stage: "tasks"`, `iteration: 0` — e.g. run the tasks
stage against a scratch spec first).

## Scenario 1 — Common case: converges within the cap (US1, SC-001)

1. Ensure `vars.SPECKIT_MAX_ITERATIONS` is unset or `5`, and
   `vars.SPECKIT_IMPLEMENT_MODEL` is unset or `claude-sonnet-5`.
2. Dispatch the stage for iteration 1:
   `gh workflow run speckit-5-implement.yml -f spec_dir=specs/NNN-slug -f issue=<N> -f iteration=1`.
3. Expected, with zero manual steps:
   - Commits appear directly on `spec/NNN-slug` (`implement:` prefix, and a
     `converge:` commit on any cycle that isn't the last).
   - `specs/NNN-slug/spec-meta.json` shows `"stage": "implement"` and
     `"iteration"` advancing by one each cycle.
   - A progress comment appears on the lifecycle issue after each cycle
     (check with `gh issue view <N> --comments`); the issue's `stage:*`
     label reads `stage:implement` from the first cycle onward.
   - Once a cycle produces no `converge:` commit, a
     `speckit-6-finalize.yml` run is dispatched with `converged=true`
     (check `gh run list --workflow speckit-6-finalize.yml`), and no further
     `speckit-5-implement.yml` re-dispatch occurs.

## Scenario 2 — Cap reached without convergence (US2, SC-002, SC-003)

1. Set a low cap: `gh variable set SPECKIT_MAX_ITERATIONS --body 2`.
2. Use a scratch spec whose `/speckit-converge` keeps finding gaps every
   cycle (e.g. a spec with a requirement the implementation deliberately
   never satisfies).
3. Dispatch iteration 1 as in Scenario 1.
4. Expected:
   - Exactly 2 cycles run (`iteration` never exceeds 2 in
     `spec-meta.json`, and no third `speckit-5-implement.yml` dispatch
     occurs — confirm via `gh run list --workflow speckit-5-implement.yml`).
   - After cycle 2, the remaining work (the last `converge:` commit's
     appended tasks) is posted on the lifecycle issue (SC-005).
   - A `speckit-6-finalize.yml` run is dispatched with `converged=false`.
5. Reset with `gh variable delete SPECKIT_MAX_ITERATIONS` (or set back to
   `5`) afterward.

## Scenario 3 — Model opt-in (US3, SC-004)

1. Apply the `model:opus` label to the scratch spec's lifecycle issue.
2. Dispatch a cycle as in Scenario 1.
3. Expected: the implement/converge agent step runs with
   `--model claude-opus-4-8` (check the uploaded `claude-execution-output`
   artifact, or the step logs) instead of the default
   `vars.SPECKIT_IMPLEMENT_MODEL`.
4. Remove the label afterward to confirm the next cycle falls back to the
   default tier.

## Scenario 4 — Idempotency (Edge Case, FR-011, SC-006)

1. Note the current `iteration` in `spec-meta.json` after a cycle
   completes (say it's `2`).
2. Re-dispatch the same iteration:
   `gh workflow run speckit-5-implement.yml -f spec_dir=specs/NNN-slug -f issue=<N> -f iteration=2`.
3. Expected: the run observes `iteration_input (2) <= recorded_iteration (2)`,
   logs a no-op step-summary note, and exits successfully — no new commits,
   no duplicate progress comment, no duplicate finalize/re-dispatch. Confirm
   via `git log --oneline spec/NNN-slug` (no new commits from the
   re-dispatch) and the issue's comment history (unchanged count).

## Scenario 5 — Outright failure, retry, and stall (Edge Case, FR-013)

1. Force a failure on a cycle — e.g. temporarily set an unreasonably low
   `--max-turns` for the implement/converge agent step, or point
   `SPECIFY_FEATURE_DIRECTORY` at a spec missing `tasks.md` after the
   pre-flight check (to simulate a mid-run tooling failure rather than the
   pre-flight refusal in Scenario 6).
2. Dispatch a cycle.
3. Expected on the *first* failure (starting tier was `claude-sonnet-5`):
   - A second attempt at the same iteration runs automatically at
     `claude-opus-4-8`.
   - If that retry succeeds, the cycle proceeds normally (converged/not
     converged as usual).
   - If that retry also fails, `spec-meta.json`'s `stage` becomes
     `"stalled"`, the issue's label reads `stage:stalled`, a comment
     explains the failure and that a maintainer must re-dispatch the same
     `iteration` manually, and no `speckit-6-finalize.yml` run is
     dispatched.
4. Expected if the starting tier was already `claude-opus-4-8` (e.g.
   `model:opus` applied, or `SPECKIT_IMPLEMENT_MODEL=claude-opus-4-8`): a
   single failure goes straight to `stalled` — no retry attempt, since
   there is no higher tier (research.md).

## Scenario 6 — Ambiguous hand-off (Edge Case, FR-012)

1. Dispatch with a `spec_dir` that doesn't exist, or that exists but is
   missing `tasks.md`:
   `gh workflow run speckit-5-implement.yml -f spec_dir=specs/does-not-exist -f issue=<N> -f iteration=1`.
2. Expected: the job fails with a clear `::error::` and step-summary
   message before any commit, comment, or dispatch occurs.

See `contracts/implement-workflow.md` for the exact trigger/idempotency/cycle
contract and `data-model.md` for the `spec-meta.json` state transitions each
scenario above exercises.
