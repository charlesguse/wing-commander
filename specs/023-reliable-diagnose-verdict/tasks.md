---

description: "Task list for Restore Reliable Watchdog Diagnosis — Stop Masked Diagnose-Agent Crashes"

---

# Tasks: Restore Reliable Watchdog Diagnosis — Stop Masked Diagnose-Agent Crashes

**Input**: Design documents from `/specs/023-reliable-diagnose-verdict/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/watchdog-diagnose-retry-delta.md, quickstart.md

**Tests**: No unit-test framework applies to workflow YAML in this repo (constitution I — dogfooding); verification is real-run and fault-injection validation per quickstart.md, captured below as explicit tasks rather than a separate test suite.

**Organization**: Tasks are grouped by user story (spec.md) to enable independent implementation and validation of each story. Every functional task targets the single reusable workflow file `.github/workflows/watchdog.yml`'s `diagnose` job, per plan.md's Project Structure — there is no `src/`/`tests/` split for this pipeline-component feature.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact — this feature touches `.github/workflows/watchdog.yml`, `.github/scripts/verify-watchdog-run.sh` (read-only), and `docs/architecture.md`

---

## Phase 1: Setup

**Purpose**: Establish the exact current shape of the code this feature edits, before any change lands

- [ ] T001 Review the current `diagnose` job in `.github/workflows/watchdog.yml` (the `Diagnose` step, `Read back diagnose outcome` step, `Report "diagnose failed" to lifecycle issue` step, and `Upload Claude execution log` step, roughly lines 811-902 per plan.md/research.md R1) and confirm the exact step `id`s, `if:` conditions, and job `timeout-minutes` this feature's edits will attach to

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the classification step both US1 (retry) and US2 (honest read-back/report) depend on for their outputs

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T002 Add the `Classify diagnose attempt` step (`id: diagnose-classify`, `if: always()`) to `.github/workflows/watchdog.yml`'s `diagnose` job, immediately after the existing `Diagnose` step, per contracts/watchdog-diagnose-retry-delta.md's "Step addition: `Classify diagnose attempt`": emits `agent-ok` and `retryable` outputs using the three-way rule (healthy attempt → `agent-ok=true`/`retryable=false`; a genuine terminal `result` record that is not OK → `agent-ok=false`/`retryable=true`; file missing/empty/no `result` record → `agent-ok=false`/`retryable=false`), and copies `${{ runner.temp }}/claude-execution-output.json` to `${{ runner.temp }}/claude-execution-output-diagnose-attempt1.json` before any retry can overwrite it

**Checkpoint**: Classification outputs (`agent-ok`, `retryable`) and the attempt-1 forensic copy exist — US1 and US2 can now proceed

---

## Phase 3: User Story 1 - Every watchdog diagnosis reaches a genuine verdict or an honest failure (Priority: P1) 🎯 MVP

**Goal**: A diagnose attempt that hits a recognized transient/infrastructure crash signature gets one bounded retry instead of ending in an avoidable honest failure, while a deterministic failure still reports immediately with no retry — closing the reliability gap issue #117 exposed without touching the existing honesty mechanism.

**Independent Test**: Trigger the watchdog and force the diagnose agent to crash without a terminal result (both a retryable and a non-retryable shape, per quickstart.md Scenario 2); confirm the retryable shape gets a second attempt and a normal run stays single-attempt with unchanged behavior.

### Implementation for User Story 1

- [ ] T003 [US1] Add the `Diagnose (retry)` step (`id: diagnose-retry`, `if: steps.diagnose-classify.outputs.agent-ok != 'true' && steps.diagnose-classify.outputs.retryable == 'true'`, `continue-on-error: true`, `timeout-minutes: 10`) to `.github/workflows/watchdog.yml`'s `diagnose` job, immediately after `Classify diagnose attempt`, with byte-for-byte identical `with:`/`claude_args:` to the original `Diagnose` step (same model, prompt, `--json-schema`, `--allowedTools`/`--disallowedTools`) per contracts/watchdog-diagnose-retry-delta.md's "Step addition: `Diagnose (retry)`"
- [ ] T004 [US1] Raise the `diagnose` job's `timeout-minutes` from `20` to `35` in `.github/workflows/watchdog.yml` per research.md R4, so a legitimate retry attempt is never cut off by the job timeout
- [ ] T005 [US1] Add the "Upload attempt-1 execution log (only if retried)" step to `.github/workflows/watchdog.yml`'s `diagnose` job (`if: always() && steps.diagnose-retry.outcome != 'skipped'`, `uses: actions/upload-artifact@v4`, artifact name `claude-execution-output-diagnose-attempt1`, path `${{ runner.temp }}/claude-execution-output-diagnose-attempt1.json`, `if-no-files-found: ignore`) per contracts/watchdog-diagnose-retry-delta.md's "Step change: `Upload Claude execution log`" — the existing `claude-execution-output-diagnose` upload keeps its exact name and continues uploading whichever attempt's output is at the fixed path (FR-007)
- [ ] T006 [US1] Validate on a throwaway branch/PR (never `main`) per quickstart.md Scenario 1 (normal run: `Diagnose (retry)` shows `skipped`, unchanged report text, `verify-watchdog-run.sh` still passes) and Scenario 2's retryable-shape fault injection (force a genuine `is_error`/non-`success` terminal result on attempt 1; confirm `retryable=true`, `Diagnose (retry)` runs, and the final outcome reflects whichever attempt succeeded); revert the injected breakage afterward

**Checkpoint**: A recognized transient/infrastructure diagnose crash now recovers via one bounded retry; a healthy run is provably unaffected

---

## Phase 4: User Story 2 - A crashed diagnosis never masquerades as "passed inspection" on the lifecycle issue (Priority: P1)

**Goal**: The lifecycle issue always reflects the true outcome of whichever diagnose attempt was final (including a retry), and a maintainer can tell from the report text alone whether a retry was already tried.

**Independent Test**: For a run whose final diagnose attempt produced an empty/`is_error`/error-subtype output, confirm the lifecycle issue does not receive "passed inspection" and instead reports the honest failure, with attempt-count wording when a retry occurred (quickstart.md Scenario 2's non-retryable case, Scenario 4).

### Implementation for User Story 2

- [ ] T007 [US2] Update the "Read back diagnose outcome" step in `.github/workflows/watchdog.yml`'s `diagnose` job to use `steps.diagnose-retry.outcome` as the pre-`continue-on-error` outcome input when that step ran (`!= 'skipped'`), else `steps.diagnose.outcome`, feeding the existing unchanged `agent_ok`/`outcome` computation; add a new job output `retried` (`true` iff `steps.diagnose-retry.outcome != 'skipped'`) per contracts/watchdog-diagnose-retry-delta.md's "Step change: `Read back diagnose outcome`" and data-model.md's `agent-step-outcome`/`retried` fields
- [ ] T008 [US2] Update the "Report 'diagnose failed' to lifecycle issue" step in `.github/workflows/watchdog.yml` so its message includes attempt-count wording (`"...the diagnose agent failed after 2 attempts, so this run was not inspected..."`) when `needs.diagnose.outputs.retried == 'true'`, and stays byte-for-byte unchanged otherwise, per data-model.md's Lifecycle issue verdict table and contracts/watchdog-diagnose-retry-delta.md's "Step change: `Report \"diagnose failed\"...`" (same trigger condition, `steps.diagnose-outcome.outputs.outcome == 'diagnose-failed'`, unchanged)
- [ ] T009 [US2] Validate on the same throwaway branch/PR per quickstart.md Scenario 2's non-retryable-shape fault injection (force a failure before any terminal `result` record, e.g. break `--json-schema`; confirm `retryable=false`, `Diagnose (retry)` is `skipped`, and the report reads "diagnose failed" with single-attempt wording and no added latency) and Scenario 4 (diff `.github/scripts/verify-watchdog-run.sh` before/after — confirm zero changes — and confirm it still fails this run); revert the injected breakage afterward

**Checkpoint**: The posted verdict always matches the true outcome of the final attempt, with wording that discloses whether a retry happened; the stage-8b verifier's contract is untouched

---

## Phase 5: User Story 3 - The issue-#117 crash class is root-caused and stops recurring (Priority: P2)

**Goal**: The specific crash signature that produced issue #117 (run 30161188955) is identified and fixed at its source, so stage 8 stops auto-filing this `pipeline-defect` issue for the same reason.

**Independent Test**: After the fix, reproduce or re-inject the conditions that triggered the issue-#117 crash and confirm it no longer occurs (or, if it was classified retryable, that it now recovers via US1's retry path instead of a bare failure) (quickstart.md Scenario 3).

### Implementation for User Story 3

- [ ] T010 [US3] Fetch the diagnose job log for run 30161188955 via `gh api repos/<owner>/<repo>/actions/jobs/<diagnose-job-id>/logs` to identify which of the four known crash signatures fired (`Action failed with error`, `SDK execution error`, `Workflow initiated by non-human actor`, `json-schema is not valid JSON`); if the run has aged out of log retention, select the most plausible signature to reproduce on a throwaway branch instead, per research.md R3 and quickstart.md Scenario 3 step 1
- [ ] T011 [US3] Apply the targeted root-cause fix in `.github/workflows/watchdog.yml` indicated by research.md R3's decision tree for the confirmed signature — depends on T010's finding: no further change needed beyond US1's retry coverage if `SDK execution error`/`Action failed with error`; widen/correct `allowed_bots` (currently `"github-actions,${{ steps.ctx.outputs.bot-slug }}"`) if `Workflow initiated by non-human actor`; or fix the `--json-schema` string's shell-quoting/escaping in the `Diagnose` step's `claude_args` if `json-schema is not valid JSON`
- [ ] T012 [US3] Validate on a throwaway branch per quickstart.md Scenario 3 steps 2-3 (re-run or re-inject the confirmed signature after the fix; confirm it no longer occurs, or recovers via US1's retry path if classified retryable) and Scenario 5 (confirm both the no-retry and one-retry cases stay within the new 35-minute job timeout and don't trip `verify-watchdog-run.sh`'s duration-anomaly band)

**Checkpoint**: The issue-#117 signature is fixed at its source; all three user stories are independently verified

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and a final construction-time check that the verifier contract truly held throughout

- [ ] T013 [P] Update `docs/architecture.md`'s Stage 9 — Watchdog section to document the bounded one-time retry (`Classify diagnose attempt` and `Diagnose (retry)` steps) and the `diagnose` job's new 35-minute timeout, per plan.md's Project Structure
- [ ] T014 Diff `.github/scripts/verify-watchdog-run.sh` against its pre-feature state and confirm zero changes (FR-007, quickstart.md Scenario 4 step 1)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001) — BLOCKS User Story 1 and User Story 2 (both consume `diagnose-classify`'s outputs)
- **User Story 1 (Phase 3)**: Depends on Foundational (T002) completion
- **User Story 2 (Phase 4)**: Depends on Foundational (T002); T007 also depends on User Story 1's T003 (references `steps.diagnose-retry.outcome`, which does not exist until T003 lands)
- **User Story 3 (Phase 5)**: T010 (investigation) has no dependency and can run at any time, including in parallel with Phases 2-4; T011 depends on T010's finding and, for the traceability quickstart.md Scenario 3 describes, is easiest to verify once User Story 1's retry path (T003) exists; T012 depends on T011
- **Polish (Phase 6)**: T013 depends on all of Phases 2-5 being complete (documents the final shape); T014 depends on T002-T012 (diffs the finished state)

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Foundational — no dependency on US2 or US3
- **User Story 2 (P1)**: Depends on Foundational and on US1's T003 (reads `steps.diagnose-retry.outcome`) — cannot be fully implemented before the retry step exists, even though its own concern (honest read-back/report) is conceptually independent
- **User Story 3 (P2)**: T010 is independent of US1/US2; T011/T012 are easiest to land and verify after US1's retry mechanism exists, since the decision tree's first branch is "already covered structurally" by the retry

### Parallel Opportunities

- T013 (`docs/architecture.md`) is a different file from every other task and can run in parallel with Phase 5 or after Phase 4
- T010 (log investigation, read-only) can run in parallel with Phases 2-4's edits since it touches no shared file
- All other tasks edit the same file (`.github/workflows/watchdog.yml`) in overlapping regions of the same `diagnose` job — run them sequentially in ID order to avoid merge conflicts, even where no strict logical dependency exists

---

## Parallel Example: Cross-story

```bash
# These two can run at the same time — no shared file, no shared step:
Task: "T010 [US3] Fetch the diagnose job log for run 30161188955..."
Task: "T002 [Foundational] Add the `Classify diagnose attempt` step..."
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002) — CRITICAL, blocks US1 and US2
3. Complete Phase 3: User Story 1 (T003-T006)
4. **STOP and VALIDATE**: Run quickstart.md Scenarios 1 and 2 (retryable case) on a throwaway branch
5. This alone closes the reliability half of issue #117: a recognized-transient diagnose crash now recovers instead of ending in an avoidable honest failure

### Incremental Delivery

1. Setup + Foundational → classification exists
2. Add User Story 1 (retry mechanism) → validate independently → this is the MVP
3. Add User Story 2 (honest read-back/report reflecting the final attempt) → validate independently
4. Add User Story 3 (root-cause the specific issue-#117 signature) → validate independently — can start its investigation (T010) at any point, but its fix (T011) is best sequenced after US1 lands
5. Polish (docs + verifier-diff check) once all three stories are in

### Suggested MVP Scope

**User Story 1 (T001-T006)** is the suggested MVP: it is the P1 story that delivers the largest immediate reduction in issue-#117-style noise (a bounded retry recovering recognized transient crashes) and has no dependency on US2 or US3. Note, however, that spec.md marks US1 and US2 as equally load-bearing P1 stories ("A verdict that is wrong is worse than a verdict that is missing") — shipping US1 without US2's T007 (which US1's own T003 makes necessary, since the read-back step must learn to look at the retry attempt's output at all) would leave the read-back step blind to the retry's result. In practice T007 should land alongside T003-T006 as part of the same MVP slice.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- No test-framework tasks are included — this repo has no unit-test harness for workflow YAML (constitution I); validation tasks (T006, T009, T012) are quickstart.md-driven real-run and fault-injection checks instead
- Every fault-injection validation task explicitly runs on a throwaway branch/PR, never against `.github/workflows/watchdog.yml` on `main`, and reverts the injected breakage afterward
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
