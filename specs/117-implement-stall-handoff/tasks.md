# Tasks: Implement Stall Hand-off and Honest Remaining-Work Reporting

**Input**: Design documents from `specs/117-implement-stall-handoff/`

**Prerequisites**: plan.md, spec.md, research.md (D1-D10), data-model.md, contracts/shared-scripts.md, quickstart.md

**Tests**: Required by FR-012 / SC-006: every deterministic rule gets a checked-in fixture per failure branch, run by the new gate `verify-implement-stall-handoff.py`.

**Organization**: Grouped by user story. Fixtures live under `.github/scripts/fixtures/117-implement-stall-handoff/`; shared scripts under `.github/actions/_shared/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[maintainer]**: only the owner can do it; implement skips it (this feature's own marker, research D1)
- Workflow comments are load-bearing: after any workflow edit run `python .github/scripts/run-local-gates.py`. Do not reference private downstream consumers anywhere.

## Phase 1: Setup

- [x] T001 Create the fixture directory `.github/scripts/fixtures/117-implement-stall-handoff/` with a `README.md` stating each fixture's purpose and naming scheme (`<script>-<branch>.{md,json,env}` plus expected-output files)
- [x] T002 Create the gate skeleton `.github/scripts/verify-implement-stall-handoff.py` (argparse, fixture runner that executes a shared script against an input fixture and diffs against an expected file, non-zero exit on mismatch) and register it in the gate registry that `.github/scripts/run-local-gates.py` derives from `.github/workflows/lint-workflows.yml`, following how an existing `verify-*.py` gate is registered

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: classification of tasks.md lines in the single home of the tasks.md read (research D2, D3).

- [x] T003 Extend `.github/actions/_shared/count-tasks-checkboxes.sh` to classify each `- [ ]`/`- [x]` line outside fenced blocks (first match wins: standing instruction, then maintainer, then implementation) per data-model.md. Maintainer = fixed-string ` [maintainer] ` within the first 40 characters after the checkbox. Standing = closed, case-insensitive pattern table after stripping the checkbox and optional `T###`/`M###` id: `Complete every remaining`, `Keep the gates green`, `Run the (full )?gate suite` with no deliverable noun after it (no `and fix`, no file path, no backtick path), `After each cycle`. Emit new outputs `impl-checked-count`, `impl-unchecked-count`, `standing-count`, and heredocs `impl-unchecked-items` (delimiter `WING_COMMANDER_IMPL_ITEMS_EOF`) and `maintainer-items` (delimiter `WING_COMMANDER_MAINTAINER_ITEMS_EOF`). Keep existing outputs and the non-zero-exit-no-stdout behaviour on an unreadable ref:path unchanged
- [x] T004 [P] Surface `impl-checked-count`, `impl-unchecked-count`, `impl-unchecked-items`, `maintainer-items`, `standing-count` as additive outputs of `.github/actions/wing-commander-tasks-checkbox-count/action.yml` (no existing output renamed or removed; Principle VII widening)
- [x] T005 [P] Add classification fixtures in `.github/scripts/fixtures/117-implement-stall-handoff/` for count-tasks-checkboxes.sh: mixed file (checked, unchecked maintainer, unchecked code, standing lines), every standing-pattern form (one line per table entry), the `Run the gate suite and fix the fallout` line classified as implementation, a prose line mentioning the word maintainer without the token, an unsplit marker line, a legacy file with no markers (all non-standing lines implementation), a stale `M001 Complete every remaining unchecked task` line, and checkbox-like lines inside a fenced block; with expected outputs
- [x] T006 Add the classification cases to `.github/scripts/verify-implement-stall-handoff.py` running T005's fixtures through `count-tasks-checkboxes.sh`, and a check that the composite in T004 exposes each new output

**Checkpoint**: classification is deterministic and gated; stories can proceed.

---

## Phase 3: User Story 1 - Final PR separates owner steps from unfinished code (Priority: P1) 🎯 MVP

**Goal**: finalize renders "Maintainer steps" vs "Unfinished implementation" deterministically, with a stall statement, omitting standing instructions (FR-007, FR-008, FR-009).

**Independent Test**: run `render-remaining-work.sh` on the T007 fixtures and confirm output matches; replay the #1022 and #737 shapes (SC-001, SC-002).

- [x] T007 [P] [US1] Add fixtures in `.github/scripts/fixtures/117-implement-stall-handoff/` for render-remaining-work.sh: maintainer-only, implementation-only, both lists, both empty (expected empty output), standing lines absent, a #1022-shaped file (17 lines, standing instructions plus one constitution-amendment maintainer step) and a #737-shaped file (unchecked code task such as T011); with expected markdown
- [x] T008 [US1] Create `.github/actions/_shared/render-remaining-work.sh <maintainer-items-file> <impl-items-file>` writing to stdout `## Maintainer steps`, `## Unfinished implementation`, and a stall statement ("the lifecycle stalled with implementation outstanding", not the ordinary review framing) when the implementation list is non-empty; empty output when both are empty (contract: shared-scripts.md)
- [x] T009 [US1] Update `.github/workflows/finalize.yml` so `finalize-remaining.md` and the lifecycle announcement body come from `wing-commander-tasks-checkbox-count` outputs piped through `render-remaining-work.sh`; remove the summarising agent's "write the remaining manual work" duty (it keeps change summary and how-to-see-it); key the announce summary to the case (Maintainer steps / Stalled with implementation outstanding / no manual work remains); rename the PR body "Remaining manual work" heading accordingly; leave the out-of-boundary classification report separate and unchanged (FR-009)
- [x] T010 [US1] Add to `verify-implement-stall-handoff.py` the render fixture cases from T007 and an assertion that `finalize.yml` calls `render-remaining-work.sh` and no longer instructs the agent to copy unchecked task lines

**Checkpoint**: finalize report is correct on its own (MVP).

---

## Phase 4: User Story 2 - Maintainer-only tasks never block implementation (Priority: P1)

**Goal**: the tasks stage marks and places maintainer tasks; implement and the loop ignore them (FR-001 to FR-004).

**Independent Test**: tasks stage prompt carries the marker, kinds and placement rules; a fixture whose only unchecked lines are maintainer-tagged yields `impl-unchecked-count=0`.

- [x] T011 [US2] Edit the tasks stage prompt in `.github/workflows/tasks.yml`: add the closed list of maintainer action kinds (real workflow dispatch or run re-drive; reading or changing repository variables or settings; opening or merging a separate human-merged PR; post-merge proof; constitution amendment merge), the `[maintainer]` literal placed after the task ID and before any story tag, the rule that such tasks go only in a final "Maintainer follow-up" phase, the split rule for lines mixing code and maintainer work, and the ban on standing instructions as checkbox tasks (guidance goes in prose)
- [x] T012 [P] [US2] Add the implement-stage guidance in `.github/workflows/implement.yml` prompt text (and any task-skill guidance it embeds) that unchecked `[maintainer]` tasks are skipped, never a reason to stop a cycle or phase
- [x] T013 [US2] Add to `verify-implement-stall-handoff.py` a check that the `tasks.yml` prompt contains the `[maintainer]` literal, the "Maintainer follow-up" phase name and every action kind from T011, and that the `implement.yml` prompt carries the skip rule; add a fixture/case where only maintainer-tagged tasks are unchecked and assert `impl-unchecked-count=0` (SC-003 loop side)

**Checkpoint**: routing rules are in the prompts and enforced by the gate.

---

## Phase 5: User Story 3 - Loop hands off only when continuing cannot help (Priority: P2)

**Goal**: the stop rule becomes a pure shared function with a validated blocker field; stall is always reported (FR-005, FR-006).

**Independent Test**: fixtures (a) zero progress, no blocker → next cycle; (b) valid blocker → handoff quoting it; (c) progress → next cycle; (d) malformed blocker → next cycle; cap → handoff; last task checked → converged.

- [x] T014 [P] [US3] Add blocker fixtures in `.github/scripts/fixtures/117-implement-stall-handoff/` for validate-implement-blocker.sh: valid blocker; missing file; malformed JSON; extra key; missing key; `kind` not in `missing-tool|missing-permission|contradictory-spec|external-dependency`; `detail` empty, multi-line, and 301 chars; `task` not matching `T\d+`; `task` absent from tasks.md; `task` already checked; `task` a maintainer task; with expected outputs
- [x] T015 [P] [US3] Add decision fixtures for decide-implement-outcome.sh covering every transition in data-model.md: converged (`impl_unchecked_tip == 0`, including converging in the same cycle), progressed, converge commit present, valid blocker handoff, cap handoff, no-blocker next cycle, malformed-blocker next cycle, unhealthy cycle (`ok=false`) and truncated cycle untouched by the stop rule, and a check-one-uncheck-another cycle counted as no progress (spec 059 FR-010a); with expected `converged`, `progressed`, `handoff`, `stall-reason`, `stall-comment`
- [x] T016 [US3] Create `.github/actions/_shared/validate-implement-blocker.sh <blocker-json-path> <tasks-ref> <tasks-path>` per contract: exactly keys `task`/`kind`/`detail`, closed `kind` list, `detail` 1-300 chars single line, `task` an unchecked implementation task id at the pushed tip; print `blocker-valid`, `blocker-text` (`<kind: detail (task)>`), `blocker-invalid-reason`; exit 0 on invalid or missing blocker, non-zero only when tasks.md is unreadable. Reuse the classification from T003 rather than re-parsing
- [x] T017 [US3] Create `.github/actions/_shared/decide-implement-outcome.sh` (env or flags: `ok, truncated, impl_checked_base, impl_checked_tip, impl_unchecked_tip, converge_sha, iteration, max_iterations, blocker_valid, blocker_text`) printing `converged`, `progressed`, `handoff`, `stall-reason`, `stall-comment` per the data-model.md transitions; `stall-comment` (empty unless handoff or cap with implementation outstanding) states the outstanding implementation count and the reason (quoted blocker or iteration cap)
- [x] T018 [US3] Wire the primary-cycle read-back arm of `.github/workflows/implement.yml` (~line 1837): read tasks.md through the composite's `impl-*` outputs, call `validate-implement-blocker.sh` on `$RUNNER_TEMP/implement-blocker.json`, replace the inline hand-off rule with `decide-implement-outcome.sh`, and post `stall-comment` on the lifecycle issue through the existing hand-off/exhausted reporting step (also when the loop ends at the cap with implementation outstanding)
- [x] T019 [US3] Wire the retry-arm read-back of `.github/workflows/implement.yml` (~line 2719) identically to T018, via the same scripts and no pasted copy of the rule
- [x] T020 [US3] Add the blocker-field instruction to the implement agent prompt in `.github/workflows/implement.yml`: when stopping on a concrete blocker, write `implement-blocker.json` to the runner temp directory (never the repo or `.claude/`) with the exact shape and closed `kind` list; state it is validated and anything malformed is ignored
- [x] T021 [US3] Add to `verify-implement-stall-handoff.py` the T014 and T015 fixture cases, plus assertions that both implement arms call `validate-implement-blocker.sh` and `decide-implement-outcome.sh` and that no inline copy of the zero-progress hand-off rule remains in `implement.yml`

**Checkpoint**: stop rule is deterministic, reported, and gated.

---

## Phase 6: User Story 4 - Re-entering implement from review is explicit (Priority: P3)

**Goal**: a manual dispatch on a review-stage lifecycle comments why it did nothing; maintainer-comment re-entry reports remaining cycles (FR-010, FR-011).

**Independent Test**: the idempotency guard posts the required comment for stage `review`; the Maintainer Feedback cycle start comment contains the remaining count.

- [x] T022 [US4] In `.github/workflows/implement.yml`'s idempotency-guard step, when spec-meta stage is `review` and the dispatch is manual, post a lifecycle-issue comment through the existing comment composite stating nothing ran, why, and that a comment on the implementation PR (folded into a Maintainer Feedback cycle by pr-conversation) is the only re-entry; keep the skip behaviour. If a new input such as `is-manual-dispatch` is needed, declare it typed, optional and additive (Principle VII) and note it for the release notes
- [x] T023 [US4] Make the Maintainer Feedback cycle's start comment in `.github/workflows/implement.yml` include `max-iterations - iteration` cycles remaining (floor 0) from spec-meta; do not write any state or reset the cap (data-model.md Re-entry)
- [x] T024 [US4] Add to `verify-implement-stall-handoff.py` assertions that the guard step posts the review-stage explanation comment (text names the PR-comment route), that the re-entry start comment computes remaining cycles with a floor of 0, and a fixture case for the remaining-count arithmetic (iteration 4 of 5 → 1; iteration 5 of 5 → 0); verify any added input is declared in the published `implement.yml` contract

**Checkpoint**: all four stories independently verifiable.

---

## Phase 7: Polish & Cross-Cutting

- [x] T025 [P] Update the live docs under `docs/` for the implement loop's stop rule (blocker field, iteration-cap backstop, stall comment, re-entry and cap behaviour) and finalize's remaining-work report (two lists, standing instructions omitted, stall framing); do not edit spec 059's merged documents (FR-013)
- [x] T026 Add the "single home" checks to `verify-implement-stall-handoff.py`: no copy of the classification, stop-rule or remaining-work rendering appears in any workflow `run:` block outside the `_shared` scripts; confirm the gate's `lint-workflows.yml` invocation is the same one `run-local-gates.py` runs
- [ ] T027 Run `python .github/scripts/run-local-gates.py` and fix fallout; per CLAUDE.md also give the `implement.yml`/`finalize.yml` edits a pass from the `review-step-gating` skill
- [x] T028 [P] Walk `specs/117-implement-stall-handoff/quickstart.md` against the fixtures and confirm SC-001 (#1022 replay) and SC-002 (#737 replay) hold
- [ ] T029 [maintainer] After merge, re-drive one finalize run and one implement cycle via `gh workflow run` on the wrapper that can dispatch them, and record on lifecycle issue #992 that the run took the changed path (`prove-after-merge` skill)
- [ ] T030 [maintainer] Note the additive widening of the published `wing-commander-tasks-checkbox-count` composite outputs (and any new `implement.yml` input) in the release notes

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (T003 first; T004, T005 parallel after it; T006 after T005) → stories.
- US1 and US2 are independent after Phase 2 (US1 touches `finalize.yml`; US2 touches `tasks.yml` and the prompt text in `implement.yml`).
- US3 needs T003 (classification) and edits `implement.yml` after T012 (same file: sequence T012 → T018 → T019 → T020 → T022 → T023).
- US4 edits `implement.yml`; run after US3.
- T010, T013, T021, T024 and T026 all edit the one gate file: do them sequentially.
- Polish after all desired stories; T029 and T030 only after merge.

### Parallel Opportunities

- T004 ∥ T005 after T003.
- T007 ∥ T014 ∥ T015 (fixtures only, different files).
- T016 ∥ T008 (different scripts).
- T025 ∥ T028.

## Implementation Strategy

- **MVP**: Phase 1, Phase 2 and US1 (T001-T010): the honest remaining-work report, the defect still live after #996. US2 (T011-T013) is the other P1 and makes the marker real; ship with MVP if the same PR.
- **Then**: US3 (stop rule), US4 (re-entry legibility), Polish.
- Keep to at most one concurrent local agent per review pass; commit after each task or logical group.

## Phase 8: Convergence

- [x] T031 Make the Maintainer Feedback re-entry dispatch comment in `.github/workflows/pr-conversation.yml` (the "Implementation cycle N dispatched" reply, which is where that start comment actually lives, not `implement.yml`) state how many cycles remain (`max-iterations - iteration`, floor 0), taking the cap and recorded iteration from existing inputs or spec-meta without writing any state; then extend `verify-implement-stall-handoff.py` with the T024 remaining-count cases (iteration 4 of 5 → 1; 5 of 5 → 0) per FR-011 (missing)

## Maintainer Feedback

- [x] T027a Fix `verify-gate-24.py`: in implement.yml's "Read back retry outcome" step (~:2654), stop hard-exiting on `steps.retry` (its failure is declared survivable by a `continue-on-error` step above); degrade gracefully so steps below still run (per the `review-step-gating` skill)
- [x] T027b Fix `verify-fold-dispatch-once.py`: give the "Dispatch implement once for the whole review" step a default for `MAX_ITERATIONS` (or pass it in the env block the gate harness reproduces) so scenarios 1, 5 and 6 bind it
- [x] T027c Fix `verify-project-single-home.py`: route implement.yml's 2 inline kv-helper hits through `_shared/project-name.sh` / `wing-commander-project` (0 allowed)
- [x] T027d Fix `verify-intake-routing.py`: record pr-conversation.yml's new `max-iterations` input in `interface.json` additions
- [ ] T027e Give the implement.yml and finalize.yml edits a `review-step-gating` skill pass and fix findings
- [ ] T027f Re-run `python .github/scripts/run-local-gates.py` until green (gate 62 may be skipped without Docker); T029 and T030 remain maintainer steps

## Review Gate Round 1 Findings

- [x] Review finding: pr-conversation max-iterations input never passed by wrapper

  The new max-iterations input defaults to 5 and no wrapper passes it, so 'Cycles remaining' is wrong whenever WING_COMMANDER_MAX_ITERATIONS is set.

  - .github/workflows/pr-conversation.yml

  Detail: implement wrapper passes fromJSON(vars.WING_COMMANDER_MAX_ITERATIONS || '5'); pr-conversation does not, so the count can disagree with implement.yml's cap.

- [x] Review finding: Agent-controlled blocker detail posted unescaped to issue comment

  The blocker detail text from untrusted agent output is only length- and shape-checked, then posted verbatim in the stall comment, allowing mentions, links and markdown injection.

  - .github/actions/_shared/validate-implement-blocker.sh

  Detail: Flows through blocker-text, stall-reason and stall-comment into gh issue comment.

- [x] Review finding: Validate implement blocker steps hard-fail and strand the loop

  The new validate steps exit 1 with no continue-on-error, so the job fails and the read-back, consolidate, dispatch and hand-off steps below are skipped.

  - .github/workflows/implement.yml

  Detail: The script exits non-zero when tasks.md is unreadable at origin/<branch>. The review-step-gating pass (T027e) is still unchecked.

- [x] Review finding: Not-converged banner can say 0 tasks remain

  The finalize banner takes its count from IMPL_COUNT (implementation tasks only), so a not-converged PR can read '0 tasks remain' when only maintainer or routed tasks are left.

  - .github/workflows/finalize.yml

  Detail: impl-count can be 0 or empty, and the :-0 default applies if the render step was skipped.

- [x] Review finding: Hand-off comment lists raw unchecked items next to implementation count

  The stall comment prints REMAINING (the unclassified unchecked-items list, including standing instructions and maintainer tasks) beside an 'N implementation task(s)' statement, so the counts disagree.

  - .github/workflows/implement.yml

  Detail: Should use the classified impl-unchecked-items instead.

- [x] Review finding: Standing-instruction heuristic can drop real implementation tasks

  The 'Run the gate suite' prefix match exempts lines only if they contain 'and fix', a backtick or '/', so a task like 'Run the gate suite, then fix fallout' is classified as standing and dropped from the unfinished count.

  - .github/actions/_shared/count-tasks-checkboxes.sh

  Detail: The spec's edge case says to count ambiguous lines as implementation, but this heuristic errs the other way and can report converged with unbuilt work.

- [x] Review finding: Routed item substitution renders a doubled bullet

  Routed write-boundary items render as '- - [ ] T011 ...' because the rendered line already begins with '- [ ]', and the gate fixture asserts the malformed output.

  - .github/actions/_shared/render-remaining-work.sh
  - render-remaining-work-routed.expected

  Detail: The PR body and lifecycle issue show a nested bullet.

- [x] Review finding: Blocker gate test writes into shared tmp and leaks temp dirs

  The test writes blocker files to the parent of a mkdtemp directory (the shared temp root), and git_repo_with and render never clean up their temp dirs.

  - .github/scripts/verify-implement-stall-handoff.py

  Detail: Shared filenames can race or go stale across concurrent gate runs.

- [x] Review finding: Blocker detail length check is locale-dependent

  The 300-character limit uses bash ${#detail}, which counts bytes in a C locale, so non-ASCII details are accepted or rejected depending on the image locale.

  - .github/actions/_shared/validate-implement-blocker.sh

  Detail: Using jq 'length' counts codepoints regardless of locale.

- [ ] Review finding: Zero-progress cycles with no blocker run to the iteration cap

  The old early hand-off on no progress was removed with no cheaper no-op detection, so a stuck agent that omits or malforms the blocker re-runs identically until the cap, spending the usage window.

  - .github/workflows/implement.yml

  Detail: With the default cap of 5, five identical cycles can run before the loop stops.
