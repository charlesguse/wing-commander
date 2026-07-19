---

description: "Task list for 013-serialize-rebase-stages"
---

# Tasks: Keep Auto-Rebase From Force-Pushing a Spec Branch Out From Under an In-Flight Stage

**Input**: Design documents from `/specs/013-serialize-rebase-stages/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/concurrency-groups.md, quickstart.md

**Tests**: No automated test suite exists for GitHub Actions workflow bodies in this repository (research.md D6, consistent with specs 008/010) — validation is the manual `quickstart.md` scenarios, one per user story below, run by hand against scratch specifications and observed via the Actions UI.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single project — CI/CD automation under `.github/workflows/`. No `src/`/`tests/` split (plan.md Structure Decision).

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Converge all six job instances across `rebase.yml`, `plan.yml`, and `tasks.yml` onto the one shared `wing-commander-<spec-dir>` concurrency group (contracts/concurrency-groups.md), and confirm `implement.yml`/`finalize.yml` already match it. This is a single, atomic mechanism — GitHub Actions treats two jobs as mutually exclusive only once their group *strings* are identical, so every user story's acceptance test depends on the full convergence below, not a subset of it (research.md D2/D3; quickstart.md Scenario 1 itself dispatches a `plan` stage, so even US1 requires `plan.yml`'s fix, not just `rebase.yml`'s).

**⚠️ CRITICAL**: No user story's quickstart scenario can be meaningfully validated until this phase is complete.

- [ ] T001 [P] In `.github/workflows/rebase.yml`, change the `rebase` matrix job's `concurrency.group` from `wing-commander-rebase-${{ matrix.slug }}` to `wing-commander-${{ matrix.spec_dir }}` (matrix already carries `spec_dir` from the `discover` job's existing `{slug, spec_dir, issue}` output — no new computation needed). `cancel-in-progress: false` stays unchanged.

- [ ] T002 In `.github/workflows/plan.yml`, add a new `resolve-spec` job (placed before the `plan` job): `runs-on: ubuntu-latest`, `permissions: {}`, no checkout step. Its single step reproduces the existing "Resolve spec identity" logic verbatim (strip `spec-draft/` from `inputs.head-ref` when `inputs.slug` is empty, validate `^[0-9]{3}-[a-z0-9][a-z0-9-]*$`, `::error::` + `exit 1` on failure) and emits job outputs `slug` and `spec-dir` (`specs/<slug>`), per contracts/concurrency-groups.md's `resolve-spec` job contract.

- [ ] T003 In `.github/workflows/plan.yml`, update the `plan` job: add `needs: resolve-spec`; change `concurrency.group` to `wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}`; delete the job's own "Resolve spec identity" step (now redundant with T002); replace every remaining reference to `steps.spec.outputs.slug` / `steps.spec.outputs.spec-dir` in this job (including its own `outputs.spec-branch` / `outputs.spec-dir` job outputs and every step that reads them) with `needs.resolve-spec.outputs.slug` / `needs.resolve-spec.outputs.spec-dir`.

- [ ] T004 [P] In `.github/workflows/tasks.yml`, add a new `resolve-spec` job (placed before the `tasks` job): `runs-on: ubuntu-latest`, `permissions: {}`, no checkout step, gated on `inputs.mode` to select which prefix to strip (`plan/` for `mode: generate`, `tasks/` for `mode: approved`) when `inputs.slug` is empty. Reproduces the existing "Resolve spec identity" validation (`^[0-9]{3}-[a-z0-9][a-z0-9-]*$`, `::error::` + `exit 1` on failure) and emits job outputs `slug` and `spec-dir`, shared by both the `tasks` and `tasks-approved` jobs (only one of which runs per call, gated on the same `inputs.mode`).

- [ ] T005 In `.github/workflows/tasks.yml`, update the `tasks` job (`mode: generate`): add `needs: resolve-spec`; change `concurrency.group` to `wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}`; delete the job's own "Resolve spec identity" step (now redundant with T004); replace every remaining reference to `steps.spec.outputs.slug` / `steps.spec.outputs.spec-dir` in this job (including its `outputs.spec-dir` job output) with `needs.resolve-spec.outputs.slug` / `needs.resolve-spec.outputs.spec-dir`.

- [ ] T006 In `.github/workflows/tasks.yml`, update the `tasks-approved` job (`mode: approved`): add `needs: resolve-spec`; change `concurrency.group` to `wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}`; delete the job's own "Resolve spec identity" step (now redundant with T004); replace every remaining reference to `steps.spec.outputs.slug` / `steps.spec.outputs.spec-dir` in this job (including its `outputs.spec-dir` job output) with `needs.resolve-spec.outputs.slug` / `needs.resolve-spec.outputs.spec-dir`.

- [ ] T007 [P] Review `.github/workflows/implement.yml` (`implement` and `stalled` jobs) and `.github/workflows/finalize.yml` (`finalize` job) and confirm their `concurrency.group` is already `wing-commander-${{ inputs.spec-dir }}` — the canonical form T001/T003/T005/T006 converge onto. No edit expected; record confirmation only (research.md D1/D2, contracts/concurrency-groups.md Members table).

**Checkpoint**: All six job instances (`rebase`, `plan`, `tasks`, `tasks-approved`, `implement`, `finalize`) now share one concurrency group per specification. Every user story below can now be validated.

---

## Phase 2: User Story 1 - A stage run is never interrupted by an auto-rebase of the same specification's branch (Priority: P1) 🎯 MVP

**Goal**: A running `plan`/`tasks`/`implement`/`finalize` stage for a specification is never force-pushed underneath by a same-specification auto-rebase; the rebase queues instead, and the stage's publish succeeds without manual re-dispatch.

**Independent Test**: Start a stage run against a specification's working branch and, while it is mid-run, advance the main line so an auto-rebase of that same branch would be triggered; verify the branch is not force-updated while the stage runs, the stage's publish is accepted, and no manual re-dispatch is needed (quickstart.md Scenario 1).

- [ ] T008 [US1] Run quickstart.md Scenario 1 against a scratch specification: dispatch `wing-commander-3-plan.yml` (or `-4-tasks.yml`) for `spec/NNN-scratch`, and while it is running, push a commit to the default branch so `wing-commander-rebase.yml`'s `push` trigger fires. Confirm in the Actions UI that the rebase matrix job for this branch is **queued** (not running) for the duration of the stage run, that the stage's publish succeeds, and that the queued rebase then runs and completes normally once the stage releases `wing-commander-specs/NNN-scratch`.

- [ ] T009 [US1] Run quickstart.md Scenario 6 (US1 Edge Case, FR-008): dispatch a stage for a scratch specification, and while it is running, trigger a duplicate dispatch of the same stage for the same specification. Confirm the second run queues behind the first under the same `wing-commander-specs/NNN-scratch` group and only starts once the first completes.

**Checkpoint**: User Story 1 is independently verified — the reported collision (rebase force-pushing an in-flight stage) no longer reproduces.

---

## Phase 3: User Story 2 - A stage dispatched while a rebase is in progress starts from the rebased branch (Priority: P2)

**Goal**: A stage dispatched for a specification whose branch is mid-rebase waits for the rebase to settle rather than starting against a half-rewritten branch.

**Independent Test**: Begin an auto-rebase of a specification's working branch and, while in progress, dispatch a stage for that same specification; verify the two never modify the branch concurrently and the stage runs only once the rebase has settled (quickstart.md Scenario 2).

- [ ] T010 [US2] Run quickstart.md Scenario 2 against a scratch specification: trigger a rebase that hits a conflict needing AI resolution (keeping the rebase job running), and while it runs, dispatch `wing-commander-4-tasks.yml` for the same specification. Confirm the stage's job appears queued in the Actions UI until the rebase job completes, then starts and checks out the branch exactly as the settled rebase left it.

**Checkpoint**: User Story 2 is independently verified — a stage dispatched mid-rebase never observes a half-rewritten branch.

---

## Phase 4: User Story 3 - Unrelated specifications still run concurrently and in-flight branches still stay current (Priority: P2)

**Goal**: The fix is surgical — different specifications' rebases/stages still run concurrently, uncontended runs are unchanged, and a rebase held or deferred by same-specification contention still eventually lands.

**Independent Test**: With work in flight for two different specifications, trigger a rebase for one and a stage for the other and confirm they run concurrently; separately, confirm a held/deferred rebase for a contended specification is subsequently applied rather than permanently skipped (quickstart.md Scenarios 3–5).

- [ ] T011 [P] [US3] Run quickstart.md Scenario 3: set up two scratch specifications A and B; dispatch a rebase-triggering push affecting A's branch and, in the same window, a stage for B. Confirm both runs proceed concurrently in the Actions UI with no measurable added delay.

- [ ] T012 [US3] Run quickstart.md Scenario 4: repeat Scenario 1 (T008) to the point where a rebase queues behind a running stage, then immediately dispatch a second rebase-triggering push (or stage dispatch) for the same specification while the first rebase is still queued. Confirm the specification's branch is still brought current — either by the request that survives to run, or by a subsequent manual `gh workflow run wing-commander-rebase.yml` simulating the nightly schedule.

- [ ] T013 [P] [US3] Run quickstart.md Scenario 5: with no stage or rebase in flight for a scratch specification, advance the default branch and confirm the resulting rebase runs immediately with no queuing; separately, dispatch a stage for a specification with no rebase in flight and confirm it likewise starts immediately (cross-check timing against `specs/008-auto-rebase/quickstart.md` Scenario 1).

**Checkpoint**: All three user stories are independently verified; the fix adds no cross-specification serialization and no currency regression.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Documentation follow-up now that the shared group convergence is real, not just asserted.

- [ ] T014 [P] Correct `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s per-spec serialization claim (currently asserting a shared `concurrency: speckit-<slug>` convention that, before this feature, only held within a single stage's own re-dispatch chain) to accurately describe the now-real `wing-commander-<spec-dir>` group shared by `rebase`, `plan`, `tasks`/`tasks-approved`, `implement`, and `finalize` (research.md D1, contracts/concurrency-groups.md).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately. BLOCKS all user stories (every quickstart scenario needs the full six-job group convergence to mean anything).
- **User Story 1 (Phase 2)**: Depends on Foundational completion. No dependency on US2/US3.
- **User Story 2 (Phase 3)**: Depends on Foundational completion. Independent of US1/US3.
- **User Story 3 (Phase 4)**: Depends on Foundational completion. Independent of US1/US2.
- **Polish (Phase 5)**: Depends on Foundational completion (describes the shipped mechanism); independent of which user stories have been validated.

### Within Foundational

- T001 (`rebase.yml`), T002→T003 (`plan.yml`), T004→T005→T006 (`tasks.yml`), and T007 (review only) touch four independent surfaces and may proceed in parallel with each other; within `plan.yml` and `tasks.yml`, the `resolve-spec`-adding task must land before the task(s) that wire the downstream job(s) to consume it.

### Parallel Opportunities

- T001, T002, T004, T007 can start together (different files; T002/T004 are each the first edit to their file).
- T011 and T013 (US3) touch no files and can be run/observed in parallel with each other and with T014.

---

## Parallel Example: Foundational Phase

```bash
# Launch independent file-scoped work together:
Task: "rebase.yml — retarget the rebase job's concurrency group to matrix.spec_dir (T001)"
Task: "plan.yml — add the resolve-spec job (T002)"
Task: "tasks.yml — add the resolve-spec job (T004)"
Task: "Review implement.yml/finalize.yml groups for the canonical form (T007)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (the full group convergence — required even for US1 alone, since quickstart Scenario 1 dispatches a `plan`/`tasks` stage).
2. Complete Phase 2: User Story 1 — validate via quickstart Scenarios 1 and 6.
3. **STOP and VALIDATE**: confirm the reported rebase-vs-stage collision no longer reproduces.

### Incremental Delivery

1. Foundational → six-job group convergence shipped.
2. Add User Story 1 → validate → this is the fix for the reported bug (SC-001, SC-002).
3. Add User Story 2 → validate → closes the reverse-direction collision (SC-005).
4. Add User Story 3 → validate → confirms no regression to cross-spec concurrency or branch currency (SC-003, SC-004).
5. Polish → correct the now-accurate stage-interfaces.md claim.

---

## Notes

- [P] tasks = different files or no shared dependency
- [Story] label maps a validation task to the user story whose acceptance scenario it exercises
- No code test tasks: this repository has no automated test suite for GitHub Actions workflow bodies (research.md D6); the "tests" here are the manual `quickstart.md` scenarios
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- Avoid: editing files outside `.github/workflows/` (except the Polish-phase `stage-interfaces.md` follow-up), widening any stage's `--allowedTools`/model/trust boundary, or introducing any new persisted "contention" state (explicitly out of scope — research.md D4, contracts/concurrency-groups.md Non-goals)
