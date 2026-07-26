---

description: "Task list for Lint Composite Action Scripts"

---

# Tasks: Lint Composite Action Scripts

**Input**: Design documents from `/specs/025-lint-composite-actions/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/lint-guard-delta.md, quickstart.md

**Tests**: Not requested — no unit-test framework exists for workflow YAML in this repository (plan.md's Testing note, consistent with specs 014/016/017/018/019/020/022). Verification is `quickstart.md`'s seven scenarios, run at each phase's checkpoint and as a final sweep in Polish.

**Organization**: All three user stories land inside the same single step and file, `.github/workflows/lint-workflows.yml`'s "Parse YAML and bash -n every run block" step (contracts/lint-guard-delta.md) — there is no new job, no new file. US1 (P1) is the check-step's discovery/collection extension (FR-001, FR-003, FR-004, FR-005, FR-008, FR-009): composite action files become a second script source walked through the identical `check_script` neutralize-then-`bash -n` path workflow scripts already use. US2 (P1) is the one-line trigger addition (FR-002) that makes a composite-action-only pull request run the guard at all — plan.md is explicit that US1 and US2 "must land together" for the feature to deliver any value (coverage without a trigger, or a trigger without coverage, is each individually inert), but they remain separately testable per quickstart.md's Scenarios 1-3 and are kept as distinct phases here for that reason. US3 (P2) is the header-comment documentation addition (FR-006) and depends on neither US1 nor US2's code paths, only on describing them, so it is safely last.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project GitHub Actions pipeline repository, no `src`/`tests` split (plan.md's Structure Decision). Every change lands inside one existing file, `.github/workflows/lint-workflows.yml`; no new file is created. All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the live shape of `.github/workflows/lint-workflows.yml` and the composite-action tree still matches what research.md/data-model.md/contracts/lint-guard-delta.md were authored against, since those were written in a separate planning session.

- [ ] T001 Re-read `.github/workflows/lint-workflows.yml` lines 41-72 (the "Parse YAML and bash -n every run block" step) and confirm it still matches contracts/lint-guard-delta.md's "before" shape verbatim: a single `glob.glob(".github/workflows/*.yml")` loop, a `failures` counter, the `re.sub(r"\$\{\{[^}]*\}\}", "EXPR", run)` neutralization, and the `subprocess.run(["bash", "-n"], ...)` check inlined per-step rather than in a helper function. Also confirm `on.pull_request.paths` at line 17 is still exactly `[".github/workflows/**"]`, and run `Glob(".github/actions/*/action.yml")` to confirm the six composite actions (`wing-commander-preflight`, `wing-commander-context`, `wing-commander-callout`, `wing-commander-lifecycle-gate`, `wing-commander-bedrock-credentials`, `wing-commander-metrics-summary`) still all sit one level deep with a `.yml` extension. If any of this has drifted, note the discrepancy before proceeding — the line-number references in T002-T004 below assume this baseline.

**Checkpoint**: The file shape this feature's edits are anchored against is confirmed current.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None required. This feature adds no shared scaffolding, dependency, or new file that multiple user stories build on — US1's `check_script` extraction (contracts/lint-guard-delta.md) is self-contained within the single step T002 edits, US2 is a one-line, independent trigger change, and US3 is a documentation-only addition. There is nothing here to block user-story work on.

**Checkpoint**: No blocking prerequisites — proceed directly to Phase 3.

---

## Phase 3: User Story 1 - Composite action scripts are syntax-checked before merge (Priority: P1) 🎯 MVP

**Goal**: The "Parse YAML and bash -n every run block" step's inline Python discovers every `.github/actions/**/action.yml` and `action.yaml` file, walks each one's `runs.steps` list the same way it already walks each workflow job's `steps` list, and syntax-checks every embedded script it finds there through the identical neutralize-then-`bash -n` path — a shell syntax error anywhere in a composite action's embedded script now fails the guard with an annotation naming the action file and step.

**Independent Test**: Introduce a deliberate shell syntax error into a composite action's embedded script on a throwaway branch, open a pull request, and confirm the lint guard fails with an annotation pointing at that action file and step (quickstart.md Scenario 1). Confirm expression interpolation (`${{ ... }}`) in a composite-action script does not cause a false failure (quickstart.md Scenario 2).

### Implementation for User Story 1

- [ ] T002 [US1] In `.github/workflows/lint-workflows.yml`'s "Parse YAML and bash -n every run block" step (lines 41-72), refactor the inline Python per contracts/lint-guard-delta.md: hoist the per-step neutralize-then-`bash -n` logic (currently duplicated inline inside the workflow-job loop) into a `check_script(f, step_identity, run)` helper that returns `1` and prints the `::error file={f}::{step_identity}: {err}` annotation on failure, `0` otherwise. Update the existing `.github/workflows/*.yml` loop to call this helper (`failures += check_script(f, f"{jname} / {name}", run)`) so its behavior, order, and output format stay byte-for-byte unchanged (FR-007 — no regression in existing workflow-script coverage).
- [ ] T003 [US1] In the same step, immediately after the workflow-file loop from T002, add the composite-action loop per contracts/lint-guard-delta.md: build `action_files` from `sorted(glob.glob(".github/actions/**/action.yml", recursive=True) + glob.glob(".github/actions/**/action.yaml", recursive=True))` (FR-008 — recursive at any depth, both extensions). For each file, wrap `yaml.safe_load` in the same `try`/`except` shape the workflow loop uses — on failure, print `::error file={f}::YAML parse failure: {e}` and increment `failures` (FR-009 — parity with workflow parse-failure handling, no skip). On success, walk `(action.get("runs") or {}).get("steps") or []` (FR-003 — the composite-action step layout; naturally empty for container/JavaScript actions with no `runs.steps`, per research.md R4 — no `using:` branch needed) and for each step with a non-empty `run:`, call `check_script(f, step.get("name", f"step {i}"), run)` (FR-004 — identical neutralization/syntax-check treatment; step identity has no job dimension since a composite action has one flat step list, per data-model.md).
- [ ] T004 [US1] Confirm quickstart.md Scenarios 1, 2, 4, and 6 against the edited step: a deliberate shell syntax error in a composite action's `run:` block fails the guard with an annotation naming the action file and step (Scenario 1); a composite-action script using `${{ inputs.* }}` interpolation passes without a false failure (Scenario 2); a composite action file with broken YAML fails with a `::error file=...::YAML parse failure: ...` annotation, not a silent skip (Scenario 4); an action with no `runs.steps` (e.g. a hypothetical `runs.using: node20`/`docker` action) contributes zero failures (Scenario 6). Record whether each was exercised via a live triggered pull request or desk-checked by inspection only.

**Checkpoint**: User Story 1 is independently satisfied — every embedded script in the repository's six composite actions is now covered by the syntax check (SC-001), even before the trigger (User Story 2) fires on a composite-action-only change.

---

## Phase 4: User Story 2 - Changes limited to composite actions still trigger the guard (Priority: P1)

**Goal**: A pull request that changes only a file under `.github/actions/**` and touches no `.github/workflows/**` file now triggers the `lint` job, so User Story 1's new coverage actually runs for the pull requests that need it.

**Independent Test**: Open a pull request that modifies only a composite action file (no workflow file changed) and confirm the lint guard is triggered and evaluates that change (quickstart.md Scenario 3). Confirm a pull request touching both a workflow file and a composite action file still triggers the guard once and evaluates both (quickstart.md Scenario 5, step 4).

### Implementation for User Story 2

- [ ] T005 [US2] In `.github/workflows/lint-workflows.yml`, change line 17's `paths: [".github/workflows/**"]` under `on.pull_request` to `paths: [".github/workflows/**", ".github/actions/**"]` per contracts/lint-guard-delta.md (FR-002). Leave the `push`/`schedule`/`workflow_dispatch` triggers that feed the `registered` job (Gate 1, lines 20-25) untouched — Gate 1's workflow-registration-name check does not apply to composite actions (spec Assumptions, research.md R5).
- [ ] T006 [US2] Confirm quickstart.md Scenario 3 (a composite-action-only pull request triggers `lint · workflows` and the `lint` job evaluates the changed file) and Scenario 5 (a pull request touching both a workflow file and a composite action file triggers the guard once, evaluating both; a deliberate workflow-script syntax error still fails exactly as it did before this feature). Record whether each was exercised via a live triggered pull request or desk-checked by inspection only.

**Checkpoint**: User Stories 1 and 2 both hold together — the coverage gap the issue reported (composite-action scripts unchecked, and composite-action-only pull requests never triggering the guard) is fully closed (SC-001, SC-002, SC-003, SC-004).

---

## Phase 5: User Story 3 - The guard's limits are stated honestly (Priority: P2)

**Goal**: A maintainer reading `lint-workflows.yml`'s header comment can tell that the check is syntax-only and does not exercise or guarantee `errexit`/`pipefail` runtime behavior of composite `shell: bash` steps, so passing the guard is never mistaken for "safe at runtime."

**Independent Test**: Read the lint guard's header comment and confirm it explicitly states the check is a syntax check only and does not verify runtime errexit behavior of composite scripts (quickstart.md Scenario 7).

### Implementation for User Story 3

- [ ] T007 [US3] In `.github/workflows/lint-workflows.yml`'s header comment block (lines 1-12), add a sentence stating that the "Parse YAML and bash -n every run block" check is a syntax check only and does not exercise or guarantee `errexit`/`pipefail` runtime behavior of composite `shell: bash` steps (FR-006, research.md R6) — place it alongside the existing sentences explaining what each gate catches and misses, not in a new file or a new `docs/architecture.md` section (research.md R6's rejected alternative).
- [ ] T008 [US3] Confirm quickstart.md Scenario 7 by inspection: read the edited header comment and confirm it states the syntax-only limitation in terms a maintainer would find before mistaking a passing guard for errexit-safety.

**Checkpoint**: All three user stories hold — SC-005 is satisfied, and the guard's own documentation matches what it actually checks.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Run the full quickstart.md sweep against the finished file to confirm no regression and no scenario left unexercised.

- [ ] T009 Run quickstart.md's full scenario set (1-7) against the finished `.github/workflows/lint-workflows.yml`: composite-action syntax failure (1), interpolation false-positive avoidance (2), composite-action-only trigger (3), malformed composite-action parse failure (4), no regression in existing workflow-script coverage plus combined-change trigger (5), actions with no embedded scripts (6), and the header-comment limitation statement (7). Record which scenarios were exercised via a live triggered pull request versus desk-checked only, matching the validation-record convention specs/020 and specs/022 used.
- [ ] T010 [P] Validate the edited `.github/workflows/lint-workflows.yml` itself parses as valid YAML and passes `bash -n` on every embedded `run:` block — run the guard's own new logic against itself (dogfooding, constitution I), or `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint-workflows.yml'))"` plus manual inspection if `actionlint`/a live Actions run are unavailable in this environment.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: N/A — no blocking prerequisites exist for this feature (see Phase 2's Purpose).
- **User Story 1 (Phase 3)**: Depends on Setup (T001) confirming the baseline file shape T002/T003 edit against.
- **User Story 2 (Phase 4)**: Depends on Setup (T001); independent of User Story 1's code (T005 is a one-line trigger change unrelated to T002/T003's Python edits) but both must land in the same PR/commit for the feature to deliver value (plan.md — "must land together").
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T002/T003) and User Story 2 (T005) existing, since its header-comment sentence (T007) describes behavior those tasks introduce — though it could be drafted from the contract alone, sequencing it last avoids describing code that might still change.
- **Polish (Phase 6)**: Depends on all prior phases.

### Same-file ordering (not story dependencies, but real ordering constraints)

- T002 and T003 edit the same step in the same file and must be applied in order (T002's helper extraction first, then T003's new loop calls it) — no `[P]` marker on either.
- T005 (trigger paths, lines 15-17) and T007 (header comment, lines 1-12) touch different regions of the same file than T002/T003 (lines 41-72+) and could be edited in either order relative to them, but all edits land in one file, so none of T002/T003/T005/T007 carry a `[P]` marker.

### Parallel Opportunities

- T001 (Setup) has no parallel counterpart — it is the sole task in its phase.
- T010 (Polish) can run in parallel with T009 once T007/T008 land, since it only re-validates the finished file's own YAML/bash syntax rather than re-running quickstart's scenario narrative.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the file's live shape)
2. Complete Phase 2: Foundational (no-op — nothing blocks)
3. Complete Phase 3: User Story 1 (composite-action scripts become syntax-checked)
4. **STOP and VALIDATE**: Run quickstart.md Scenarios 1, 2, 4, 6 — confirm composite-action scripts are covered
5. Note: User Story 1 alone does not yet close the issue — a composite-action-only pull request still would not trigger the guard until User Story 2 lands (plan.md's "must land together"). Treat US1+US2 together as the true minimum shippable increment, even though they are organized as separate phases for independent testability.

### Incremental Delivery

1. Setup → confirmed baseline
2. Add User Story 1 → validate Scenarios 1/2/4/6 → coverage exists, but untriggered for composite-action-only changes
3. Add User Story 2 → validate Scenarios 3/5 → coverage now actually fires for the pull requests that need it (this is the real MVP: issue #41's reported gap is closed)
4. Add User Story 3 → validate Scenario 7 → the guard's documentation matches its real scope
5. Polish → full Scenario 1-7 sweep plus self-validation of the finished file's own YAML/bash syntax

### Why User Story 1 and User Story 2 together are the true MVP

FR-001 through FR-005, FR-008, and FR-009 (User Story 1) give composite-action scripts syntax-check coverage, but FR-002 (User Story 2) is what makes a composite-action-only pull request actually run that check. Shipping either alone leaves the issue's reported defect partially unfixed: US1 without US2 covers scripts the guard never looks at for the pull requests that change them; US2 without US1 triggers a guard that still has nothing to say about composite-action content. Both phases are kept separate above only because each has its own independently verifiable acceptance scenario (quickstart.md Scenarios 1-2 vs. 3), not because either delivers standalone value before the other lands.
