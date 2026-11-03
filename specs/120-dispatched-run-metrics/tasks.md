# Tasks: Prompt Metrics Records for Pipeline-Dispatched Runs

**Input**: Design documents from `specs/120-dispatched-run-metrics/` (plan.md, spec.md, research.md, data-model.md, contracts/persisting-job.md, quickstart.md)

**Tests**: The spec requires a deterministic gate (FR-009) with a fixture per failure branch, and a test-first re-run key check (research R6). Those are included; no other test tasks.

**Organization**: Grouped by user story. Run `python .github/scripts/run-local-gates.py` before every push (CLAUDE.md "Before pushing"); that is guidance, not a task. Workflow comments are load-bearing (gates byte-compare them), so treat comment edits as code edits. A change touching any `if:` / `continue-on-error:` also gets a `review-step-gating` skill pass; a `container:` / `run:` change gets `container-shell-safety`.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: Establish the baseline before editing.

- [ ] T001 Read `.github/workflows/metrics-persist.yml`, `.github/workflows/wing-commander-5-implement.yml`, `.github/workflows/wing-commander-6-finalize.yml`, `.github/actions/wing-commander-metrics-persist/action.yml` and `.github/scripts/verify-metrics-wrapper-trigger-drops-watchdog.py` (Gate 79); note the current `if:` of `verify-image-prerequisites` and `persist` and the existing `workflow_run`/`sweep` job call shapes.
- [ ] T002 Run `python .github/scripts/run-local-gates.py` on the unmodified branch and record which gates (if any) already fail, so later failures are attributable.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Stage inputs and the re-run key check that every story depends on.

**⚠️ CRITICAL**: No wrapper edits until T003 shows whether the record key is stable (research R6, highest risk).

- [ ] T003 Write a failing-first fixture test for re-run key stability in the existing composite test location for `wing-commander-metrics-persist` (find it under `.github/scripts/` via grep for the composite's tests): feed two `jobs.json` snapshots for one run (attempt 1 and attempt 2, different job ids for the same `job_key`) plus the same record artifact, assert `records.jsonl` ends with exactly one record. Fails today if `record_key` (rewritten to `run_id:job_id:step_index`, action.yml ~L336-343) is unstable.
- [ ] T004 Add optional `workflow_call` input `run-in-cancelled-run` (boolean, `default: false`) to `.github/workflows/metrics-persist.yml`: when true, `verify-image-prerequisites` and `persist` gate on `always()`; when false, today's gating bit for bit (contracts/persisting-job.md section 2).
- [ ] T005 Add optional `workflow_call` input `tolerate-failure` (boolean, `default: false`) to `.github/workflows/metrics-persist.yml`: `continue-on-error: ${{ inputs.tolerate-failure }}` on `verify-image-prerequisites` and `persist`, plus a final `if: failure()` step in `persist` emitting `::warning::` and a step-summary line naming the daily sweep as the backstop (FR-007). Keep `persisted-count` and `unpersisted-record-keys` outputs unchanged. Same file as T004, so sequential.
- [ ] T006 If T003 fails, fix `record_key` derivation in `.github/actions/wing-commander-metrics-persist/action.yml` so a record persisted on attempt 1 keeps the same key on attempt 2 (for example key on the first attempt's job id, or de-dup on `run_id:job_key:step_index`); no workaround in the wrappers (FR-004). If T003 passes, note that in the PR description and skip.

**Checkpoint**: Stage supports cancelled-run and tolerant modes with defaults unchanged; key stability proven.

---

## Phase 3: User Story 1 - Rollup reflects implement and finalize spend promptly (Priority: P1) 🎯 MVP

**Goal**: Every implement and finalize run, however dispatched, persists its own records in a last job.

**Independent Test**: A pipeline-dispatched implement run's last job `persist-metrics` is green, the record is on the metrics branch within 15 minutes, and the rollup is updated (quickstart D1).

- [ ] T007 [US1] Add job `persist-metrics` to `.github/workflows/wing-commander-5-implement.yml` per contracts/persisting-job.md section 1: `uses: ./.github/workflows/metrics-persist.yml`; `needs: [resolve-model, implement]`; `if: always() && vars.WING_COMMANDER_METRICS_PAUSED != 'true' && needs.resolve-model.result == 'success' && needs.implement.result != 'skipped'`; `with:` `run-id: ${{ github.run_id }}` (string-formatted), destination branch/path from `vars.WING_COMMANDER_METRICS_*` with the same defaults as `wing-commander-metrics-persist.yml`, runner, container-image, `run-in-cancelled-run: true`, `tolerate-failure: true`; `secrets:` exactly `pipeline-repo-token`, `container-registry-username`, `container-registry-password`; `permissions: contents: write, issues: write, actions: read, id-token: write`; no `concurrency:` key; no inline discovery/append/rollup shell.
- [ ] T008 [US1] Add job `persist-metrics` to `.github/workflows/wing-commander-6-finalize.yml` with the same shape, `needs: [finalize]`, using the fallback gate `always() && vars.WING_COMMANDER_METRICS_PAUSED != 'true' && needs.finalize.result != 'skipped'` initially (research R2 fallback); add a wrapper comment recording that the queued-cancel case relies on the zero-record no-op (spec 043 FR-021) until the `started` signal is proven (T017). Same pattern as T007; different file, so [P] with T007 is possible but keep the comment wording consistent (one canonical comment, other site points at it, Gate 47).
- [ ] T009 [US1] Extend Gate 79 in `.github/scripts/verify-metrics-wrapper-trigger-drops-watchdog.py` with a "persisting job" section (FR-009, research R9): both wrappers contain `persist-metrics`; it calls `metrics-persist.yml`; `needs` includes the stage job; `if` contains `always()` and the kill switch and does not rely on bare `success()`/`!cancelled()`; no `speckit-app-*`/`APP_TOKEN` secret; no `concurrency:` key; no inline discovery/append/rollup shell in the wrappers (single-home assertion).
- [ ] T010 [US1] Extend Gate 79 with stage-side invariants: both `run-in-cancelled-run` and `tolerate-failure` exist in `metrics-persist.yml` with `default: false`, and neither the `workflow_run` job nor the `sweep` job in `wing-commander-metrics-persist.yml` passes either input (contracts section 3, items 2-3).
- [ ] T011 [US1] Add one checked-in fixture per failure branch for Gate 79 (VIII) alongside the gate's existing fixtures under `.github/scripts/`: missing job in implement, missing job in finalize, gating without `always()`, missing `needs` on the stage job, job not calling `metrics-persist.yml`, App secret handed to the job, `concurrency:` key present, input missing or default not `false`, `workflow_run`/`sweep` job passing a new input. Each fixture must make the gate fail.
- [ ] T012 [US1] Confirm the gate is registered and path-triggered in `.github/workflows/lint-workflows.yml` for every file it now reads (`metrics-persist.yml`, both wrappers); touch the workflow only if a path is missing.

**Checkpoint**: US1 complete; MVP. Run the full gate suite.

---

## Phase 4: User Story 2 - Mid-lifecycle readers see current data, once (Priority: P2)

**Goal**: Records appear exactly once across the persisting job, the `workflow_run` path and the sweep.

**Independent Test**: After a person-dispatched run, persisting job and `workflow_run` job both run and `records.jsonl` holds one copy per `record_key` (quickstart D4, D6).

- [ ] T013 [US2] Add a composite fixture test next to T003 asserting idempotence across three encounters of one run (persisting-job call, `workflow_run`-style call, sweep-style call) yields one copy of each record (FR-004, SC-002); fix in the composite only if it fails.
- [ ] T014 [P] [US2] Audit the readers of an in-progress implement run (research R7): `.github/workflows/wing-commander-9-pr-conversation.yml` (`stop`), `.github/workflows/lifecycle-review-gate.yml`, `.github/workflows/fold-cycle-guard.yml` and `.github/workflows/wing-commander-9b-fold-cycle-guard.yml`, `.github/actions/wing-commander-fold-dispatch`, `.github/workflows/board-loop.yml`, `.github/workflows/auto-release.yml`. Complete the "Readers" table in `specs/120-dispatched-run-metrics/data-model.md` with a disposition and proof (SC-003, FR-011) for each; if any reader changes behaviour, record the finding in the PR description rather than widening this change.

---

## Phase 5: User Story 3 - A failed or cancelled run's spend is still visible (Priority: P2)

**Goal**: Failed runs and runs cancelled after starting still persist; runs cancelled before any job starts do not start the job.

**Independent Test**: Quickstart D2 (cancel mid-cycle persists; cancel while queued does not start it).

- [ ] T015 [US3] Review the `if:` and `continue-on-error:` lines added in T005, T007, T008 with the `review-step-gating` skill (`always()` vs `!cancelled()`, outputs readable from an always-gated job, teardown not stranded); fix findings in `.github/workflows/metrics-persist.yml` and both wrappers.
- [ ] T016 [US3] Review the added `persist-metrics` job and the `run-in-cancelled-run` gating with the `container-shell-safety` skill (the stage's `run:` steps run inside a caller-supplied container); fix any step lacking an effective `shell: bash` in `.github/workflows/metrics-persist.yml`.
- [ ] T017 [US3] Add an optional `started` output to `.github/workflows/finalize.yml` published by an early record-free job, and gate finalize's `persist-metrics` on it in `.github/workflows/wing-commander-6-finalize.yml` (research R2) — only after the maintainer drill (T022) shows the output is readable from the wrapper when a later job was cancelled; if the drill fails, keep the T008 fallback and record it as a measured exception to FR-011 in the wrapper comment. Update Gate 79 and its fixtures (T009, T011) if the gate text changes.

---

## Phase 6: User Story 4 - Rollup is honest about what it may be missing (Priority: P3)

**Goal**: The rollup states when the last sweep ran and that later runs may be missing.

**Independent Test**: Render a rollup and check the line is present with the sweep time or `unknown`.

- [ ] T018 [US4] In `.github/actions/wing-commander-metrics-persist/action.yml` (rollup renderer, ~L542-600) add the line "Last daily sweep: `<high_water_mark | unknown>` — runs completed since then may be missing from the total." sourced from `sweep-state.json` on the destination branch (FR-006, research R8). This is the single home of the prose; no wrapper copy.
- [ ] T019 [US4] Add a fixture test for the rollup line in the composite's test location: one case with a `sweep-state.json` high-water mark, one without (renders `unknown`); and extend the "single home" check so the prose appears only in the composite (Gate 47 pointers if repeated).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T020 [P] Amend `specs/058-per-job-minute-floor/contracts/metrics-persist-sweep-delta.md` (implement/finalize completion-triggered path restated per FR-008; `tasks` and `rebase` stay sweep-only), `specs/043-durable-metrics-record/contracts/persist-workflow.md` ("runs only after the origin run has concluded" amended; document both new inputs and defaults) and `specs/043-durable-metrics-record/contracts/wrapper-contract.md` (the persisting job). These contracts are live; fix like code. Do not edit any spec.md.
- [ ] T021 [P] Grep `docs/` for pages stating the metrics trigger model (for example "workflow_run" with "implement"/"finalize" near "metrics") and update any that claim implement/finalize persistence comes from the completion trigger.
- [ ] T022 Run `python .github/scripts/run-local-gates.py` and confirm every gate is green (Gates 12, 45, 47, 79 in particular); fix anything red before pushing.

---

## Phase 8: Maintainer follow-up

**Purpose**: Real dispatches, re-drives and post-merge proof that only the repository owner can do. Use the `prove-after-merge` skill; record evidence on the PR or lifecycle issue.

- [ ] T023 [maintainer] Drill D2 for finalize before T017 is merged: dispatch a finalize run, cancel it while queued, and report whether the `started` output was readable from the wrapper and `persist-metrics` stayed unstarted; hand the result to the implement stage to decide T017 versus the fallback.
- [ ] T024 [maintainer] After merge, drill D1: let tasks or a fold re-drive dispatch an implement cycle, then confirm `persist-metrics` is green, the record is in `records.jsonl` within 15 minutes and the rollup updated; repeat for finalize.
- [ ] T025 [maintainer] After merge, drill D2 (implement): cancel a run after the agent step emitted a record and confirm `persist-metrics` persisted it; cancel another while queued and confirm the job did not start.
- [ ] T026 [maintainer] After merge, drill D3: measure the `stalled` queueing delay for a stage failure after next-cycle dispatch and record it as evidence for the SC-001 exception.
- [ ] T027 [maintainer] After merge, drill D4: `gh workflow run` the implement wrapper, confirm both `persist-metrics` and the later `workflow_run` job run with one copy of each record, then re-run failed jobs and confirm no duplicate.
- [ ] T028 [maintainer] After merge, drill D5: with an unwritable metrics destination on a scratch run, confirm `persist-metrics` ends green with a warning, the run conclusion is unchanged and the next sweep picks the run up.
- [ ] T029 [maintainer] After the next daily sweep, drill D6: confirm each `record_key` in `records.jsonl` occurs exactly once (SC-002).
- [ ] T030 [maintainer] Add the Maintenance backlog (#889) line for `tasks` and `rebase` pipeline-dispatched runs staying sweep-only (owner decision 2026-10-26, Q2 (a)) if it is not already there.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. T003 gates T006; T004 before T005 (same file); T004/T005 before T007/T008.
- US1 (T007-T012) is the MVP. T009-T011 follow T007/T008 (the gate reads the wrappers).
- US2 (T013, T014) can start after Phase 2; T014 is independent of the code tasks.
- US3 (T015-T017): T015/T016 after US1; T017 only after T023.
- US4 (T018, T019) is independent of US1-US3 (composite only), but T018 and T006 touch the same file, so sequence them.
- Polish after the stories; maintainer phase after merge (except T023).

## Parallel Opportunities

- T007 and T008 (different wrapper files).
- T014 alongside any code task.
- T020 and T021.
- US4 alongside US1 once T006 is done.

## Implementation Strategy

MVP is Phase 1-2 plus US1: stage inputs, both wrapper jobs, extended Gate 79 with fixtures. Then US2 (idempotence and reader audit), US3 (gating reviews, finalize signal), US4 (rollup label), polish. Maintainer drills prove the behaviour after merge; D2 for finalize is the one drill that informs implementation.
