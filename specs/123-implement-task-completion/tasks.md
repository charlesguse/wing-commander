# Tasks: Implement Finishes Its Tasks

**Input**: Design documents from `/specs/123-implement-task-completion/`

**Prerequisites**: plan.md, spec.md, research.md (D1–D8), data-model.md, contracts/buildable-classification.md, quickstart.md

**Tests**: The spec requires checked-in fixtures for every failure branch (FR-017, constitution VIII), so fixture and gate tasks are included. Fixtures live under `.github/scripts/fixtures/123-implement-task-completion/`.

**Organization**: Grouped by user story. Story 4 (low-progress, FR-011–FR-013) is deferred by FR-016 and has no tasks here; its follow-up is recorded on the Roadmap by the maintainer (final phase).

Before pushing, run `python .github/scripts/run-local-gates.py` (see CLAUDE.md). Workflow comments are load-bearing: treat comment edits as code edits. A change touching an `if:` or `continue-on-error:` also needs the `review-step-gating` skill pass.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Create the fixture directory `.github/scripts/fixtures/123-implement-task-completion/` with a README.md listing the fixture families (classification, cap-outcome, finalize-wait, review-gate-skip, cycle-outcome, migration, watchdog-handoff)
- [x] T002 [P] Read `specs/117-implement-stall-handoff/contracts/shared-scripts.md` and `.github/actions/_shared/count-tasks-checkboxes.sh`, `decide-implement-outcome.sh`, `classify-out-of-boundary-tasks.sh`, `render-remaining-work.sh` to confirm the current line-class order and output names before editing (no file change; note findings in the T004 commit message)

---

## Phase 2: Foundational (blocking: the one classification home)

**Purpose**: Extend the single counter (research D1/D2/D3/D4); every story reads its outputs.

- [x] T003 Add classification fixtures in `.github/scripts/fixtures/123-implement-task-completion/classification/`: tasks.md files covering standing line, `Review finding:` fold, `Recurring review finding:` fold, `[maintainer]` tag, post-merge proof, drill, `.claude/` write, gate-suite run with `GATE_SUITE_READY=false` and `true`, ambiguous line (must be buildable), checked and unchecked variants, each with an expected-output file
- [x] T004 Extend `.github/actions/_shared/count-tasks-checkboxes.sh` with line-class order standing → fold → maintainer tag → deterministic-unbuildable → buildable; emit `buildable-checked-count`, `buildable-unchecked-count`, `buildable-unchecked-ids`, `buildable-unchecked-items`, `fold-unchecked-count`, `fold-unchecked-items`; `maintainer-items` includes deterministic-unbuildable lines; `impl-*` = buildable + folds; read env `GATE_SUITE_READY` (default `true`) and `NO_WRITE_PATHS` (default `.claude/,.git/`); post-merge-proof and drill patterns anchored (e.g. "re-drive", "prove after merge", "post-merge", "drill") applied after the tag run; an unreadable ref:path still exits non-zero with empty stdout
- [x] T005 Make the write-boundary class in `.github/actions/_shared/count-tasks-checkboxes.sh` call `.github/actions/_shared/classify-out-of-boundary-tasks.sh` (no second pattern list); extend the classifier only if a `.claude/` write fixture from T003 is missed
- [x] T006 [P] Expose the new outputs and a `gate-suite-ready` input in `.github/actions/wing-commander-tasks-checkbox-count/action.yml`
- [x] T007 [P] Amend the live contract `specs/117-implement-stall-handoff/contracts/shared-scripts.md` (the tasks.md-with-no-markers rule now excludes the FR-004 classes and folds from the buildable view) and add the announcement of the changed output meanings required by constitution VII
- [x] T008 Create `.github/scripts/verify-buildable-classification.py` (gate) that runs `count-tasks-checkboxes.sh` over every T003 fixture and fails on any mismatch, and fails if a second classification pattern list for the write-boundary class appears outside `classify-out-of-boundary-tasks.sh` ("single home" check, FR-017); register it so `run-local-gates.py` runs it

**Checkpoint**: classification fixtures and gate pass; consumers can now read `buildable-*`.

---

## Phase 3: User Story 1 - A cycle keeps building until the buildable work is done (P1) 🎯 MVP

**Goal**: One cycle builds across phases; each cycle's outcome is recorded by deterministic code.

**Independent Test**: The implement prompt states a checkpoint is not a stopping point while push-per-phase remains; the cycle-outcome line shows ticked, remaining and turns from tasks.md base/tip and the execution record.

- [x] T009 [US1] Add cycle-outcome fixtures in `.github/scripts/fixtures/123-implement-task-completion/cycle-outcome/` (base/tip tasks.md pairs plus a sample execution record giving turns used and budget; include a case where converge appended tasks)
- [x] T010 [US1] Edit the implement prompt in `.github/workflows/implement.yml` (both copies, near the two existing prompt blocks) to direct the agent to keep building every buildable unchecked task across phases, state that a phase checkpoint is not a stopping point, and keep "push at each phase boundary" (FR-001, FR-002); if the copies are byte-compared by an existing gate, update that gate's expectation in the same change
- [x] T011 [US1] In `.github/actions/wing-commander-implement-outcome/action.yml` (and `.github/actions/_shared/decide-implement-outcome.sh` if the arithmetic belongs there) compute `buildable_ticked` (tip minus base `buildable-checked-count`), `buildable_remaining` (tip `buildable-unchecked-count` plus dropped ids) and `turns_used`/`turn_budget` from the run's execution record, and emit a single cycle-outcome line output (FR-003)
- [x] T012 [US1] Append the cycle-outcome line to the lifecycle issue comment and the metrics record in `.github/workflows/implement.yml`, consuming the composite output only (no formatter pasted into the workflow; single-home rule)
- [x] T013 [US1] Pass the cycle-start gate-suite job's readiness as `GATE_SUITE_READY` into the base and tip counter calls in `.github/workflows/implement.yml` (same value for both, FR-008)
- [x] T014 [US1] Extend `.github/scripts/verify-buildable-classification.py` (or add a sibling `.github/scripts/verify-cycle-outcome.py`) to check the T009 fixtures and that the implement prompt contains the "not a stopping point" and push-per-phase statements

**Checkpoint**: US1 independently verifiable via gates.

---

## Phase 4: User Story 2 - Tasks no cycle can finish never block convergence (P1)

**Goal**: Deterministically-unbuildable and `[maintainer]` tasks never hold the loop open and are listed as human work.

**Independent Test**: A tasks.md with only maintainer-only/unbuildable unchecked lines yields `impl-unchecked`=0, converged, and the remaining-work report lists them.

- [x] T015 [US2] Add cap-outcome fixtures in `.github/scripts/fixtures/123-implement-task-completion/cap-outcome/`: only-maintainer-only left at cap (converged, FR-014), all tasks maintainer-only (converges immediately), ambiguous task (buildable)
- [x] T016 [US2] Update `.github/actions/_shared/decide-implement-outcome.sh` so convergence keys on `impl-unchecked` (folds included) and maintainer-only/unbuildable lines never count, and the cap with only maintainer-only unchecked reports converged, not cap-reached (FR-006, FR-014)
- [x] T017 [P] [US2] Update `.github/actions/_shared/render-remaining-work.sh` and `.github/actions/wing-commander-remaining-work/action.yml` to list buildable remaining and maintainer-only (including deterministic-unbuildable) tasks as human work
- [x] T018 [US2] Extend the gate from T008 (or `.github/scripts/verify-buildable-classification.py`) to run the T015 fixtures through `decide-implement-outcome.sh` and the remaining-work renderer

---

## Phase 5: User Story 3 - Review fixes do not consume the implementation budget (P2)

**Goal**: Folds are out of cap/progress/FR-010 counts but still must be ticked; finalize and the review gate wait on buildable tasks.

**Independent Test**: With folds plus buildable tasks outstanding, finalize opens no PR and the review gate skips a final PR; with only folds left, neither refuses.

- [x] T019 [US3] Add fixtures in `.github/scripts/fixtures/123-implement-task-completion/finalize-wait/` and `.../review-gate-skip/`: buildable unchecked (refuse/skip), only folds unchecked (proceed), only maintainer-only unchecked (proceed), duplicate fold of a spec task
- [x] T020 [US3] In `.github/actions/_shared/decide-implement-outcome.sh` take new env `BUILDABLE_UNCHECKED_TIP`, `BUILDABLE_CHECKED_BASE`, `BUILDABLE_CHECKED_TIP`; `progressed` uses the buildable checked delta; the cap/blocker hand-off keys on buildable unchecked (plus dropped ids) > 0; cap with only folds left proceeds to finalize (no hand-off)
- [x] T021 [US3] Wire the new inputs through `.github/actions/wing-commander-implement-outcome/action.yml` and the call site in `.github/workflows/implement.yml`
- [x] T022 [US3] In `.github/workflows/finalize.yml` add a refusal step before PR creation that reads `buildable-unchecked-count` from `wing-commander-tasks-checkbox-count` at the spec-branch tip and, when > 0, comments the remaining list on the lifecycle issue and fails closed with no PR; no override input; give it a one-line fallback if the composite did not run (FR-010)
- [x] T023 [US3] In `.github/workflows/lifecycle-review-gate.yml` make the select step read the same composite at the PR head and skip a final PR with `buildable-unchecked-count` > 0, logging the reason (FR-010)
- [x] T024 [US3] Run the `review-step-gating` skill over the T022/T023 `if:`/exit-code changes and fix findings in `.github/workflows/finalize.yml` and `.github/workflows/lifecycle-review-gate.yml`
- [x] T025 [P] [US3] Create `.github/scripts/verify-finalize-buildable-wait.py` (gate) that drives the T019 fixtures through the decision logic and asserts finalize and the review gate both consume the composite's `buildable-unchecked-count` (no second counter), and register it in `run-local-gates.py`'s derivation

---

## Phase 6: User Story 5 - Defined outcome at the cap (P3)

**Goal**: Cap or validated blocker with buildable tasks left hands the lifecycle to a person, resumable one cycle at a time.

**Independent Test**: Cap-outcome fixtures show hand-off with listing, no finalize, no dispatch; a resumed cycle lifts `stage:stalled`; the watchdog does not report the hand-off.

- [x] T026 [US5] Add hand-off fixtures in `.github/scripts/fixtures/123-implement-task-completion/cap-outcome/`: cap with buildable left (hand-off), validated blocker with buildable left (FR-015a), blocker with only folds/maintainer-only left, resumed cycle at recorded+1
- [x] T027 [US5] Ensure `.github/actions/_shared/decide-implement-outcome.sh` sets `handoff=true` for the cap and for a validated blocker only when buildable unchecked (plus dropped ids) > 0, with no finalize dispatch and the remaining buildable and maintainer-only tasks listed on the lifecycle issue via the remaining-work composite (FR-015, FR-015a)
- [x] T028 [US5] Extend "Flip stage label (first cycle)" in `.github/workflows/implement.yml` so a resumed cycle (iteration recorded+1 after a stalled hand-off) also removes `stage:stalled`; leave the idempotency guard unchanged
- [x] T029 [US5] Add a watchdog fixture showing the FR-015 hand-off (stage `stalled`, label, hand-off comment) yields no `stage-mismatch` or `lost-progress` finding; adjust the watchdog's classification in `.github/workflows/watchdog.yml` or its script only if the fixture fails, and add the fixture check to the gate from T025
- [ ] T030 [US5] Run `python .github/scripts/run-local-gates.py` and fix failures introduced by Phases 2–6

---

## Phase 7: Migration (FR-018)

**Goal**: Lifecycles already stranded at `review` with buildable tasks are handed off once.

- [x] T031 Add migration fixtures in `.github/scripts/fixtures/123-implement-task-completion/migration/`: qualifying lifecycle, only folds or maintainer-only left (untouched), already migrated (idempotent: no second commit or comment), closed issue (untouched)
- [x] T032 Create `.github/actions/_shared/migrate-stranded-review-lifecycles.sh` (inputs `repo`, optional `dry-run`): for each open lifecycle issue at spec-meta stage `review` with `buildable-unchecked-count` > 0 at the spec branch tip, commit `stage: stalled` (iteration preserved) through the pipeline's hardened push path, add `stage:stalled`, and post one comment listing remaining buildable and maintainer-only tasks and the resuming dispatch (`spec_dir`, `issue`, `iteration`); idempotency marker is stage already `stalled` plus the hand-off comment marker
- [x] T033 Add a manually dispatched `workflow_dispatch` workflow `.github/workflows/migrate-stranded-review-lifecycles.yml` that calls the T032 script with a `dry-run` input; least-privilege permissions, explicit shell on any container job (`container-shell-safety` skill if a `container:` block is used)
- [x] T034 [P] Create `.github/scripts/verify-migrate-stranded-review-lifecycles.py` (gate) that runs the T031 fixtures against the script in dry-run/stubbed mode and register it

---

## Phase 8: Polish & Cross-Cutting

- [x] T035 [P] Add the "single home" check for the cycle-outcome formatter and counting to the nearest existing gate (e.g. `verify-metrics-summary-record-emission.py`) so a pasted copy in a workflow fails
- [ ] T036 [P] Update `specs/123-implement-task-completion/quickstart.md` only if the shipped fixture names or commands differ from it
- [ ] T037 Run `python .github/scripts/run-local-gates.py` and confirm every gate, including all new ones, passes

---

## Phase 9: Maintainer follow-up

- [ ] T038 [maintainer] Merge the implementation PR (touches `.github/workflows/`, needs a token with the `workflow` scope: `gh auth refresh -h github.com -s workflow`)
- [ ] T039 [maintainer] After merge, dispatch `migrate-stranded-review-lifecycles.yml` with `dry-run: true`, review the listed lifecycles (expected: #1100 / spec 120 and #1102 / spec 119), then dispatch it for real
- [ ] T040 [maintainer] Prove after merge with the `prove-after-merge` skill: re-drive one implement run and confirm the cycle-outcome line, the buildable-only cap outcome and finalize's refusal took the changed path; record the evidence on #1111
- [ ] T041 [maintainer] Record lever (b) low-progress handling (FR-011–FR-013) as a follow-up on the Roadmap issue, and switch the hand-off to `lifecycle:held` once #1102 merges

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (blocks all stories). T004 → T005 → T008; T006, T007 follow T004.
- US1 (Phase 3) and US2 (Phase 4) depend only on Phase 2; US3 (Phase 5) depends on Phase 2 and T016; US5 (Phase 6) depends on T020/T021.
- Migration (Phase 7) depends on T004/T006 (reads the composite) and T027 (same hand-off shape).
- Polish after all; Maintainer follow-up last.

## Parallel Opportunities

- T006 and T007 after T004; T017 beside T016; T025 beside T022–T023 once fixtures exist; T034 beside T032–T033; T035 and T036.
- Tasks in the same file (`implement.yml`: T010, T012, T013, T021, T028; `decide-implement-outcome.sh`: T016, T020, T027) are sequential.

## Implementation Strategy

### MVP First

Phases 1–2, then US1 and US2 (the two P1 stories): the classification home, the "keep building" prompt, the cycle-outcome record and convergence that ignores unbuildable work. Validate with the gates, then add US3, US5, the migration and the polish phase. Maintainer follow-up runs after merge.

## Maintainer Feedback

- [ ] TF001 Replace the inline `git show` read of a spec branch's `spec-meta.json` at `.github/workflows/migrate-stranded-review-lifecycles.yml:55` with the single shared reader: the `wing-commander-spec-meta` composite, or `.github/actions/_shared/read-spec-meta.sh` sourced from a composite. Keep at most a one-line fallback at the call site (source: maintainer comment on PR #1119, Gate 61 failure on `lint`, head eea92254).
- [ ] TF002 Run `python .github/scripts/run-local-gates.py` and confirm Gate 61 and its self-test pass, with no other gate regressions. Treat comment edits as code edits.
