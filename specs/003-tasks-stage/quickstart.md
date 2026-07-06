# Quickstart: Validating the Tasks Stage

Prerequisites: a repo checkout with `gh` authenticated as a maintainer, and
an existing spec that has already completed the plan stage (a
`spec/NNN-slug` branch with `spec.md`, `spec-meta.json` at `stage: "plan"`,
and `plan.md`/`research.md`/`data-model.md` present — e.g. run the plan
stage against a scratch spec first, or reuse `specs/002-plan-stage/` on its
own `spec/002-plan-stage` branch).

## Scenario 1 — Default (`auto`) mode: direct commit + auto hand-off (US1, SC-001)

1. Ensure `vars.SPECKIT_TASKS_REVIEW` is unset or `auto` on the repo.
2. Open and merge a PR with head `plan/NNN-slug` into base `spec/NNN-slug`
   (the plan stage produces this normally; for a dry run, push a trivial
   change on `plan/NNN-slug` and merge it).
3. Expected, with zero manual steps beyond the merge itself:
   - `tasks.md` appears committed directly on `spec/NNN-slug`.
   - `specs/NNN-slug/spec-meta.json` shows `"stage": "tasks"`.
   - The lifecycle issue gets a comment summarizing the tasks (count,
     per-story breakdown, MVP scope) and its `stage:*` label reads
     `stage:tasks`.
   - A `speckit-5-implement.yml` run is dispatched with
     `spec_dir=specs/NNN-slug iteration=1` (check
     `gh run list --workflow speckit-5-implement.yml`).

## Scenario 2 — Review-required (`pr`) mode (US3, SC-002)

1. Set the repo variable: `gh variable set SPECKIT_TASKS_REVIEW --body pr`.
2. Merge a `plan/NNN-slug → spec/NNN-slug` PR as in Scenario 1.
3. Expected:
   - No commit lands directly on `spec/NNN-slug`; instead a PR
     `tasks/NNN-slug → spec/NNN-slug` opens containing `tasks.md` and the
     `spec-meta.json` update.
   - No `speckit-5-implement.yml` run is dispatched yet.
4. Merge the `tasks/NNN-slug` PR as a maintainer.
5. Expected: same postconditions as Scenario 1 (stage flips to `"tasks"`,
   issue label/comment update, implement stage dispatched) — now triggered
   by the tasks-PR merge instead of the tasks-commit.

Reset with `gh variable delete SPECKIT_TASKS_REVIEW` (or set back to `auto`)
before/after testing to avoid affecting other specs.

## Scenario 3 — Stalled path (Edge Case, FR-013)

1. With `SPECKIT_TASKS_REVIEW=pr`, open a `tasks/NNN-slug` PR as in
   Scenario 2, then close it **without merging**.
2. Expected:
   - `spec-meta.json` shows `"stage": "stalled"`.
   - The lifecycle issue's label reads `stage:stalled`; a comment explains
     the tasks PR was closed unmerged and that a maintainer must delete
     `tasks/NNN-slug` and manually restart the tasks stage.
   - No implementation-stage dispatch occurs; no new task list is
     auto-regenerated.

## Scenario 4 — Idempotency (Edge Case, FR-011, SC-004)

1. Re-deliver the same `plan/NNN-slug → spec/NNN-slug` merged-PR webhook
   (GitHub's redelivery UI on the workflow run, or re-run the job manually
   via the Actions UI "Re-run all jobs").
2. Expected: the second run observes `spec-meta.json` `stage != "plan"`
   (already `"tasks"` from the first run) and exits as a no-op — no second
   `tasks.md` commit, no second `tasks/NNN-slug` PR, no second
   `speckit-5-implement.yml` dispatch. Confirm via
   `gh run list --workflow speckit-5-implement.yml` (still exactly one run)
   and `git log --oneline spec/NNN-slug -- specs/NNN-slug/tasks.md` (still
   exactly one commit).

## Scenario 5 — Ambiguous specification (Edge Case, FR-012)

1. Merge a `plan/does-not-exist → spec/does-not-exist` PR (or dispatch with
   a slug that has no matching `specs/` directory on the `spec/*` branch).
2. Expected: the job fails with a clear `::error::` and step-summary
   message; no task list, PR, label change, or dispatch occurs.

See `contracts/tasks-workflow.md` for the exact trigger/gate/dispatch
contract and `data-model.md` for the `spec-meta.json` state transitions
each scenario above exercises.
