# Quickstart: Validating Configurable Gates (Gate 3 / plan review)

Prerequisites: a repo checkout with `gh` authenticated as a maintainer, and
an existing spec that has completed the intake stage (a spec PR already
merged into `main`, so `specs/NNN-slug/spec.md` + `spec-meta.json` exist
there with `stage: "spec"` — e.g. reuse a scratch spec, or dispatch the plan
stage manually against one of this repo's own completed specs for a dry
run).

## Scenario 1 — Default (`pr`) mode: no regression (User Story 3, SC-002)

1. Ensure `vars.WING_COMMANDER_PLAN_REVIEW` is unset on the repo (or
   explicitly `pr`).
2. Merge a `spec-draft/NNN-slug → main` PR (or dispatch `plan.yml` manually
   with `slug=NNN-slug`).
3. Expected, identical to today's behavior:
   - `plan/NNN-slug` branch + a plan PR opened against `spec/NNN-slug`.
   - `specs/NNN-slug/spec-meta.json` unchanged until the plan PR merges.
   - Lifecycle issue gets the "planning started" comment, then (after the
     plan PR is manually merged) the existing plan summary + PR link
     comment, and its `stage:*` label reads `stage:plan`.
   - No `wing-commander-4-tasks.yml` dispatch happens automatically — task
     generation still waits for a human to merge the plan PR, exactly as
     before this feature.

## Scenario 2 — Auto mode: Gate 3 bypassed end-to-end (User Story 1, SC-001, SC-004)

1. Set the repo variable: `gh variable set WING_COMMANDER_PLAN_REVIEW --body auto`.
2. Merge a `spec-draft/NNN-slug → main` PR (or dispatch as above).
3. Expected, with zero manual steps beyond the initial spec-PR merge:
   - No `plan/NNN-slug` branch or PR is created.
   - `plan.md` (and `research.md`, `data-model.md`, `contracts/`,
     `quickstart.md`) appear committed directly on `spec/NNN-slug`.
   - `specs/NNN-slug/spec-meta.json` shows `"stage": "plan"`.
   - The lifecycle issue's completion comment states the plan was committed
     directly and that Gate 3 was disabled, so the transition is auditable
     (SC-004); its `stage:*` label reads `stage:plan`.
   - A `wing-commander-4-tasks.yml` run is dispatched automatically (check
     `gh run list --workflow wing-commander-4-tasks.yml`), which in turn runs
     `/speckit-tasks` per the existing tasks-stage contract.
4. Reset with `gh variable delete WING_COMMANDER_PLAN_REVIEW` (or set it back
   to `pr`) afterward so it doesn't affect other in-flight specs.

## Scenario 3 — Invalid configuration falls back to enabled, and is surfaced (User Story 2 AC2, FR-008)

1. Set an unrecognized value: `gh variable set WING_COMMANDER_PLAN_REVIEW --body maybe`.
2. Merge a `spec-draft/NNN-slug → main` PR.
3. Expected:
   - Gate 3 behaves as `pr` (enabled) — a plan PR is opened, nothing is
     auto-dispatched.
   - The workflow run shows a `::warning::` annotation and a
     `$GITHUB_STEP_SUMMARY` line naming the invalid value.
   - The lifecycle issue's "planning started" comment includes a note that
     `WING_COMMANDER_PLAN_REVIEW=maybe` was invalid and Gate 3 defaulted to
     enabled.
4. Reset: `gh variable delete WING_COMMANDER_PLAN_REVIEW`.

## Scenario 4 — Bad/empty artifact stops the pipeline rather than cascading (Edge Case, FR-007)

1. With `WING_COMMANDER_PLAN_REVIEW=auto`, simulate a failed plan generation
   (e.g. temporarily break the `/speckit-plan` skill invocation, or manually
   push an empty `plan.md` to `spec/NNN-slug` and re-run the verification
   step in isolation).
2. Expected:
   - The deterministic verification step fails with `::error::`.
   - No `wing-commander-4-tasks.yml` dispatch occurs.
   - No `stage:plan` label flip occurs — the lifecycle issue still reads
     whatever stage it was in before this run.

## Scenario 5 — Gate independence (User Story 2 AC1, FR-003, SC-005)

1. Set `WING_COMMANDER_PLAN_REVIEW=auto` and, separately,
   `WING_COMMANDER_TASKS_REVIEW=pr` (the tasks step's own, unrelated
   setting).
2. Run Scenario 2's flow end-to-end.
3. Expected: Gate 3 is bypassed exactly as in Scenario 2, but the
   auto-dispatched tasks stage now opens a `tasks/NNN-slug` review PR
   instead of committing directly (per `tasks-review=pr`'s existing,
   unmodified behavior) — confirming the two gates operate independently.
4. Reset both variables afterward.

## Scenario 6 — Mid-lifecycle configuration change doesn't affect an already-passed gate (Edge Case)

1. Start a spec with `WING_COMMANDER_PLAN_REVIEW=pr` (or unset) and merge its
   spec-draft PR, letting the plan PR open normally.
2. While that plan PR is still open (unmerged), set
   `WING_COMMANDER_PLAN_REVIEW=auto`.
3. Merge the still-open plan PR.
4. Expected: nothing unusual — the plan PR merge is picked up by
   `wing-commander-4-tasks.yml`'s existing `pull_request: closed` trigger on
   `plan/*`, which is unaffected by `WING_COMMANDER_PLAN_REVIEW` (that
   variable is only read by the *plan* stage's wrapper, not the tasks
   stage's). This confirms a spec that already has its `plan/NNN-slug` PR
   open is unaffected by a later configuration change — only the *next*
   spec to reach Gate 3 observes the new value.

See `contracts/plan-workflow.md` for the exact input/dispatch/verification
contract and `data-model.md` for the configuration values and lifecycle
record transitions each scenario above exercises.
