# Tasks: Review Loops That Notice They Aren't Converging, and an Analyze Check Before Folded Review Tasks Reach Implement

**Input**: Design documents from `specs/116-review-convergence-analyze/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/convergence-signals.md, contracts/fold-analyze.md, quickstart.md

**Tests**: Required. Constitution VIII and FR-019/SC-007 demand a checked-in fixture for every gate failure branch; SC-001..SC-004 demand replay fixtures.

**Organization**: Grouped by user story. US5 is out of scope (FR-020) and has no tasks.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Repository is CI/CD tooling: scripts in `.github/scripts/`, composites in `.github/actions/`, workflows in `.github/workflows/`. Before pushing: `python .github/scripts/run-local-gates.py`. Workflow comments are load-bearing; re-run the gate suite after any comment edit. Do not edit `.claude/skills/speckit-*`. Never reference private downstream consumers.

---

## Phase 1: Setup

- [X] T001 Read `.claude/skills/review-until-clean/scripts/thrash_signals.py`, `.github/scripts/verify-metrics-summary-record-emission.py`, `.github/actions/wing-commander-fold-commit/action.yml`, `.github/actions/wing-commander-fold-dispatch/action.yml` and the gate registry used by `.github/scripts/run-local-gates.py`, and note the conventions to follow (no file changes)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared module that Stories 1, 2 and 4 all call.

- [X] T002 Create `.github/scripts/wc_convergence.py` by moving the attribution (`Origins`/`blame_commits`), churn and growth arithmetic from `.claude/skills/review-until-clean/scripts/thrash_signals.py`; expose `measure(base, heads, findings, cwd)` and `validate_line(path, line, head, cwd)` per contracts/convergence-signals.md; `validate_line` returns true only when `1 <= line <= lines(file@head)`; classify merges from the freshly fetched base as `main`, not loop-written (research D2)
- [X] T003 Add to `.github/scripts/wc_convergence.py` the single `THRESHOLDS = {min_round: 3, self_inflicted_share: 0.5, consecutive_churn_rounds: 2, growth_ratio: 0.5}` table, `classify_recurrence(findings, ledger)` (dismissed fingerprints never match), `decide(history, thresholds=THRESHOLDS)` returning `{signals, tripped, stop, reason}` (tripped ⊆ {count-not-falling, self-inflicted, recurrence, churn-streak, growth}; empty before round 3; round 1 signals zero; unattributable findings excluded from share numerator and denominator), `render_handoff(decision)` producing the comment with marker `<!-- wing-commander-not-converging: round=N -->`, per-round table, unattributable count and open findings, and the CLI `decide --history <json> --base <ref> [--json]`
- [X] T004 [P] Create unit tests in `.github/scripts/wc_convergence_tests/` covering each FR-006 rule, round-2 record-only, round-1 zeros, unattributable and invalid-line handling, main-merge exclusion, zero-findings round, dismissed-list non-recurrence, and port the `--self-test` cases of `thrash_signals.py`
- [ ] T005 Make `.claude/skills/review-until-clean/scripts/thrash_signals.py` a thin caller of `wc_convergence` that keeps its flags and `--self-test`; update `.claude/skills/review-until-clean/SKILL.md` to point at the shared module (if the stage is denied writes under `.claude/`, flag this task for a human maintainer per research D10 rather than working around it)

**Checkpoint**: One module answers all arithmetic; stories can start.

---

## Phase 3: User Story 1 - A recurring finding is never reported as a clean round (P1) 🎯 MVP

**Goal**: A finding re-raised after being folded or fixed is classified `recurrence`, keeps the round non-clean, and is named.

**Independent Test**: Replay #833's case: a round whose only finding matches an earlier folded fingerprint is not `clean`, posts no `success`, and names the recurrence.

- [X] T006 [P] [US1] Add replay fixture for #833 (round 2 folds F, round 3 raises only F) plus a fresh-only-findings fixture under `.github/scripts/wc_convergence_tests/fixtures/` and tests asserting SC-001 and acceptance scenario 2 (unchanged behaviour)
- [X] T007 [US1] In `.github/workflows/lifecycle-review-gate.yml` extend the `disposition` partition step to call `wc_convergence.classify_recurrence` against the persisted `folded_fingerprints` ledger instead of dropping matches; a round with a recurrence does not resolve `clean`, posts no `success` status, keeps the finding open (re-fold or carry) and names it on the lifecycle issue; persist the resolved-finding ledger additively in the round marker (data-model.md)
- [ ] T008 [US1] In `.github/workflows/board-loop.yml` record fixed-finding fingerprints in the PR round marker and classify recurrences the same way, naming them on the PR and not resolving the round clean
- [ ] T009 [US1] Update any existing `verify-*.py` gate or fixture that byte-compares the changed workflow regions, and run `python .github/scripts/run-local-gates.py`

**Checkpoint**: False green removed (MVP).

---

## Phase 4: User Story 2 - Loops stop early when they stop converging (P1)

**Goal**: Both loops compute signals each round and, from round 3, stop with `not-converging` and the standard hand-off.

**Independent Test**: Replay #954 and #969 histories: each stops at or before round 3; each FR-006 rule trips on its own fixture.

- [ ] T010 [P] [US2] Add replay fixtures from the #954 and #969 round histories and per-rule trip fixtures in `.github/scripts/wc_convergence_tests/fixtures/`, with tests for SC-002 and acceptance scenarios 1–8 (including budget and not-converging on round 5 naming the budget and still listing signals)
- [ ] T011 [P] [US2] Add optional `line` (integer ≥ 1, not part of the fingerprint) to the reviewer finding schemas of both loops in `.github/workflows/lifecycle-review-gate.yml` and `.github/workflows/board-loop.yml`; where a schema sits in a published composite, keep it optional
- [ ] T012 [US2] In `.github/workflows/lifecycle-review-gate.yml` persist each round's record (head SHA, finding fingerprint/file/line/attributable, count) in the round marker, call `wc_convergence decide`, and on `stop` take the existing budget-exhaustion hand-off with stall reason `not-converging` and `render_handoff` output; PR left open and unmerged; budget (`LIFECYCLE_REVIEW_ROUND_BUDGET`) unchanged and still wins
- [ ] T013 [US2] Do the same in `.github/workflows/board-loop.yml` for review rounds (fixup commits as the loop's own commits, `BOARD_LOOP_ROUND_BUDGET` unchanged)
- [ ] T014 [US2] Ensure the `not-converging` stall reason is accepted wherever stall reasons are enumerated (labels, re-eligibility rule, watchdog/board-status parsing, existing gates) by grepping `.github/` for the existing budget stall reason and extending each site
- [ ] T015 [US2] Run `python .github/scripts/run-local-gates.py`; apply `review-step-gating` skill to the changed `if:` conditions

**Checkpoint**: Both loops stop early; US1 + US2 deliver the observed-failure fixes.

---

## Phase 5: User Story 4 - One home for the convergence arithmetic (P2)

**Goal**: A second copy of the arithmetic fails a gate.

**Independent Test**: Skill and loops give identical signals on one history; reintroducing a copy fails the gate.

- [X] T016 [P] [US4] Create `.github/scripts/verify-convergence-single-home.py` that fails when blame/churn/diff-size arithmetic or the threshold literals appear in a workflow, composite or skill outside `wc_convergence.py` (and the allowed thin callers), in the manner of `verify-metrics-summary-record-emission.py`
- [X] T017 [P] [US4] Add checked-in fixtures for every failure branch of the gate (copied arithmetic in a workflow, in a composite, in a skill script, a duplicate threshold literal) and a passing fixture in a `verify-convergence-single-home-fixtures/` directory beside the gate, following existing fixture layout
- [ ] T018 [US4] Add a parity test in `.github/scripts/wc_convergence_tests/` asserting the skill's `thrash_signals.py` and the module's CLI emit identical signals on the same history (SC-003)
- [ ] T019 [US4] Register the gate in the gate registry and in `.github/workflows/lint-workflows.yml` so `run-local-gates.py` runs it; run the full suite

---

## Phase 6: User Story 3 - A folded task that contradicts the spec reaches the owner before implement (P2)

**Goal**: Analyze runs between fold-commit and fold-dispatch on both paths; only a constitution conflict or a failed check holds.

**Independent Test**: Constitution-conflicting fold task is held with a question naming task and principle; FR-contradicting task without a constitution conflict is dispatched with the report linked.

- [X] T020 [P] [US3] Create the deterministic decision script (in `.github/actions/wing-commander-fold-analyze/` or `.github/actions/_shared/` if reused) that validates the agent JSON schema `{"findings":[{severity,category,fold_task,location,principle,detail}]}`, decides `hold` iff any finding has `category == constitution-conflict` or the step failed/mismatched schema, else `dispatch`, and renders `report-markdown` and `question-markdown` (names the task and, for constitution conflicts, the principle; options: amend the spec / drop the fold task / proceed anyway, or proceed anyway / retry the check for `analyze-failed`)
- [X] T021 [P] [US3] Add fixture tests beside the composite in the style of `wing-commander-fold-queue-*-tests/run-tests.sh`: constitution conflict → hold (SC-004), FR contradiction only → dispatch with report (SC-005), inconsistency/duplication → dispatch, no findings → dispatch, malformed JSON → hold analyze-failed, empty fold section → skipped
- [X] T022 [US3] Create `.github/actions/wing-commander-fold-analyze/action.yml` per contracts/fold-analyze.md: inputs spec-dir, fold-ref-before, fold-ref-after, folded-json, credentials, optional max-turns (bounded default 12); skip when fold section has no tasks; run `anthropics/claude-code-action` with model `claude-sonnet-5-5`, `--max-turns`, tools restricted to Read/Grep/Glob, prompt invoking `/speckit-analyze` scoped to the new fold section with spec text framed as data; outputs decision, hold-reason, report-markdown, question-markdown; any `run:` step sets `shell: bash` (apply `container-shell-safety`)
- [X] T023 [US3] Add optional additive outputs to `.github/actions/wing-commander-fold-commit/action.yml` (fold-section range / before and after refs) needed by the analyze composite; no rename or removal
- [X] T024 [US3] Wire the composite between `wing-commander-fold-commit` and `wing-commander-fold-dispatch` in `.github/workflows/lifecycle-review-gate.yml` (`disposition`) and `.github/workflows/pr-conversation.yml` (`act` path); call `fold-dispatch` only when `decision != hold`; link the report on the lifecycle issue when dispatching; on hold post the question with marker `<!-- wing-commander-fold-hold: fold=<id> -->` on the lifecycle issue
- [ ] T025 [US3] Implement hold release: a maintainer-authorized answer comment (reuse pr-conversation's existing authorization) handled as *proceed* → dispatch, *drop* → deterministic commit removing the fold section's tasks then dispatch, *amend* → wait for the spec amendment then dispatch on next lifecycle trigger, *retry* → rerun the check; place the handler in `.github/workflows/pr-conversation.yml` or a small dedicated wrapper job (research D9)
- [X] T026 [P] [US3] Create `.github/scripts/verify-fold-analyze-wiring.py` asserting the composite sits between fold-commit and fold-dispatch in both callers, declares model `claude-sonnet-5-5`, a `--max-turns`, a read-only tool list, and `shell: bash` in container jobs; add a checked-in fixture per failure branch
- [ ] T027 [US3] Register `verify-fold-analyze-wiring.py` in the gate registry and `.github/workflows/lint-workflows.yml`; update existing `verify-fold-*.py` gates and fixtures for the new step; run `python .github/scripts/run-local-gates.py`

---

## Phase 7: Polish & Cross-Cutting

- [ ] T028 [P] Run the scenarios in `specs/116-review-convergence-analyze/quickstart.md` and record any divergence
- [ ] T029 [P] Update live docs that describe the loops' stop reasons or the fold flow (grep `docs/` and README for "round budget" and "fold-dispatch")
- [ ] T030 Final pass: `python .github/scripts/run-local-gates.py`; apply `review-step-gating` and `container-shell-safety` skills to workflow/composite changes

---

## Dependencies & Execution Order

- Phase 2 blocks all stories (T002 → T003 → T004/T005).
- US1 (Phase 3) needs T003. US2 needs T003 and shares the two workflows with US1, so do US1 first (T007/T008 before T012/T013).
- US4 needs T002–T005; independent of US1/US2 otherwise.
- US3 needs only Setup; it touches `lifecycle-review-gate.yml` and `pr-conversation.yml`, so sequence T024 after T012 to avoid conflicts.
- Polish last.

## Parallel Opportunities

- T004 with T005; T006 with T010 with T011; T016 with T017; T020, T021, T026 are independent files.
- US3 can proceed in parallel with US1/US2 apart from the shared-workflow tasks.

## Implementation Strategy

- **MVP**: Phase 1 + 2 + US1 (T001–T009): removes the false green.
- Next: US2 (observed thrash), then US4 (gate), then US3 (analyze).
- Out of scope: US5 / part 3 (FR-020).
