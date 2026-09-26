---

description: "Task list for A Fold Report Credits Only Its Own Run — Run-Scoped Fold Evidence"
---

# Tasks: A Fold Report Credits Only Its Own Run — Run-Scoped Fold Evidence

**Input**: Design documents from `/specs/075-run-scoped-fold-evidence/`
**Prerequisites**: plan.md, spec.md, research.md (D1–D7), data-model.md (§1–§7), contracts/run-scoped-fold-evidence.md, quickstart.md

**Tests**: This feature's own coverage IS part of its deliverable (User Story 3 / FR-009–FR-011) — an extension of the existing Gate 34 (`verify-fold-dispatch-once.py`), not a new gate. New scenarios/mutations are added per-story, immediately after that story's workflow edits, following `verify-fold-dispatch-once.py`'s own established shape (spec 042).

**Organization**: Tasks are grouped by user story. All three stories share one workflow file (`pr-conversation.yml`, two different jobs) and one gate script (`verify-fold-dispatch-once.py`, extended); each story's tasks are still independently completable and independently checkable via the scenarios/mutations it adds.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, or non-overlapping steps/scenarios within a file, no ordering dependency on an incomplete task)
- **[Story]**: US1–US3 per spec.md's priorities
- File paths and line numbers are exact where research.md/data-model.md/contracts/ cite them; those numbers are plan-time citations, already reconfirmed against the shipped file as of this tasks.md's writing (Setup, T001) — reconfirm again at the start of implementation per this repository's convention, since intervening merges can shift them.

## Path Conventions

Single project — this repository is a GitHub Actions pipeline, not an application with a `src`/`tests` split. All paths below are repository-root-relative:

- `.github/workflows/pr-conversation.yml` — Foundational (`act` job), US1 (`report-fold-outcomes`), US2 (`dispatch-once`)
- `.github/actions/wing-commander-fold-evidence/action.yml` (new) — Foundational
- `.github/scripts/verify-fold-dispatch-once.py` — Foundational (harness extension), US1, US2, US3 (new scenarios/mutation)
- `.github/workflows/lint-workflows.yml` — US3 (reflexive confirmation only, no edit expected)

---

## Phase 1: Setup

**Purpose**: Confirm the plan-time citations this feature depends on still hold, before any edit begins.

- [ ] T001 Confirm the current line numbers/shape of `.github/workflows/pr-conversation.yml`'s `act` job "Checkout working tree for this leg" (~1909–1916) and "Act on this classification" (~1959, fold commit message at ~2009–2013); `dispatch-once`'s "Checkout spec branch at its current tip" (~2674–2681) and "Dispatch implement once for the whole review" (~2688–2751, fold-list build at ~2707–2709); and `report-fold-outcomes`'s "Checkout spec branch at its current tip" (~2861–2868) and "Report fold-route leg outcomes" (~2874–2954, job-conclusion read at ~2921, per-leg fold check at ~2923–2926) — against research.md D1–D7 and data-model.md §1–§6. Note any drift from the plan-time line numbers before starting Foundational/US1/US2 tasks.

**Checkpoint**: Every citation this plan makes is either confirmed or corrected before any workflow edit begins.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The run-attribution mechanism (the git hook and the composite action that reads it) is shared by every downstream story — `report-fold-outcomes` (US1) and `dispatch-once` (US2) both call the same composite, and Gate 34's harness must be able to execute it before either story's new scenarios can run at all.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 Create `.github/actions/wing-commander-fold-evidence/action.yml` (data-model.md §3, research.md D2): a composite action with inputs `working-directory` (required), `base-sha` (required), `tip-sha` (required), `run-id` (optional, default `${{ github.run_id }}`), and output `folded-json`. Its single `shell: bash` step runs `git -C <working-directory> log --grep '^fold(' --format='%H%x1f%s' <base-sha>..<tip-sha>`; for each candidate line, matches the subject against `^fold\(([^)]+)\): (.*)$`, reads the full commit body with `git -C <working-directory> show -s --format=%B <sha>`, and keeps only commits whose body contains the exact line `Wing-Commander-Run-Id: <run-id>`; emits `folded-json=$(...)` as a JSON array of `{id, summary}` objects (`[]` when the range is empty or nothing matches, never a missing output) to `$GITHUB_OUTPUT`. Follow `wing-commander-inspected-run-identity`'s header-comment convention to record this as fold evidence's one home (FR-009).
- [ ] T003 [P] In `.github/workflows/pr-conversation.yml`'s `act` job, add a new step "Install run-attribution hook for this leg's commits" between "Checkout working tree for this leg" (~1909–1916) and "Act on this classification" (~1959), gated identically to the checkout step (`steps.relay-gate.outputs.proceed == 'true' && steps.route.outputs.needs-checkout == 'true'`). It writes a `prepare-commit-msg` script to a path OUTSIDE the checked-out working tree (e.g. under `$RUNNER_TEMP`) that appends a blank line then `Wing-Commander-Run-Id: ${{ github.run_id }}` to the file named in its first argument, then runs `git config core.hooksPath <that path>` inside the leg's own checkout only — never a global git config, never touching any other leg's or job's working tree (data-model.md §2, research.md D1). The agent's own prompt (~1974–2013) and allowed-tools list are byte-for-byte unchanged.
- [ ] T004 [P] In `.github/scripts/verify-fold-dispatch-once.py`, add `RUN_ID_UNDER_TEST`/`RUN_ID_SIBLING` constants and extend `make_repo()`'s fold-commit loop with a `stamp_run_id` parameter (per-commit, allowing `RUN_ID_UNDER_TEST`, `RUN_ID_SIBLING`, or `None` for no trailer at all) so a fixture can produce commits carrying either run's attribution or none (research.md D7a). Existing callers of `make_repo()` keep their current behavior (default `stamp_run_id=RUN_ID_UNDER_TEST`, matching today's single-run fixtures).
- [ ] T005 In `.github/scripts/verify-fold-dispatch-once.py`'s `load_steps()`, add a second extraction — via `find_step` on `.github/actions/wing-commander-fold-evidence/action.yml` — of the composite action's own `run:` text, and stitch it into the synthetic execution wherever `dispatch-once`'s and `report-fold-outcomes`'s shipped steps' `uses:` line calls the composite (matching the composite's declared inputs/outputs to the harness's env/`$GITHUB_OUTPUT` plumbing), so the harness continues to exercise the exact shipped bash on both sides of the call (research.md D7c, contracts/run-scoped-fold-evidence.md's "Gate 34 extension"). Depends on T002, T004.

**Checkpoint**: The attribution mechanism exists end to end (hook → trailer → composite → `folded-json`) and Gate 34's harness can execute all of it. US1 and US2 can now proceed.

---

## Phase 3: User Story 1 - A lost item is still reported as lost when two runs overlap (Priority: P1) 🎯 MVP

**Goal**: `report-fold-outcomes` counts a `fold(<leg-id>):` commit as evidence for one of its own legs only when that commit carries this run's own `Wing-Commander-Run-Id:` trailer — a leg cancelled before it folded anything is reported "not folded" even when a sibling run's same-id commit is present in range.

**Independent Test**: Reproduce two overlapping runs (or their fixture equivalent) where run A's `leg-0` is cancelled with no fold of its own and run B's `leg-0` folds; confirm run A's report says `leg-0` was not folded.

### Implementation for User Story 1

- [ ] T006 [US1] In `.github/workflows/pr-conversation.yml`'s `report-fold-outcomes` job, add a new step "Compute this run's fold evidence" between "Checkout spec branch at its current tip" (~2861–2868) and "Report fold-route leg outcomes" (~2874), `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-fold-evidence` with `working-directory: .` (this job's spec-branch checkout root), `base-sha: ${{ needs.classify-and-announce.outputs.base-sha }}`, `tip-sha: ${{ steps.tip.outputs.sha }}`. Gate it the same way "Checkout spec branch at its current tip" is gated (`steps.tip.outputs.sha != ''`) (data-model.md §5).
- [ ] T007 [US1] In "Report fold-route leg outcomes" (~2874–2954), replace the per-leg evidence check at ~2923–2926 (`folded=false; if [ -n "$range" ] && git log --grep "^fold($id):" ... "$range" | grep -q .; then folded=true; fi`) with a membership test of `id` against the new step's `folded-json` output — parse `folded-json` once into a shell variable before the per-leg `while` loop (read once per job invocation, not re-queried per leg, data-model.md §5) and test membership per leg (e.g. `printf '%s' "$FOLDED_JSON" | jq -e --arg id "$id" 'any(.[]; .id == $id)' >/dev/null`). Leave the job-conclusion read (~2921, #417 caller-prefixed match) and the outcome derivation (~2928–2935) byte-for-byte unchanged. Remove the now-unused `range`/`BASE_SHA`/`TIP_SHA` range computation (~2892–2895) if nothing else in the step reads it. Depends on T002, T006.
- [ ] T008 [P] [US1] Extend Gate 34's `SCENARIOS` with new scenario 1 (contracts/run-scoped-fold-evidence.md "New scenarios" #1, FR-010 case 1): this run's leg succeeded with its own fold commit present (stamped `RUN_ID_UNDER_TEST`) **and** a sibling run's commit under the same id (stamped `RUN_ID_SIBLING`) is also present in range → `report-fold-outcomes` stays silent (healthy). Depends on T005, T007.
- [ ] T009 [P] [US1] Extend Gate 34's `SCENARIOS` with new scenario 2 (contracts #2, FR-010 case 2, SC-001): this run's leg concluded `cancelled` with no commit of its own, while a sibling run's commit under the same id is present in range → reported **not folded**. Depends on T005, T007.
- [ ] T010 [P] [US1] Extend Gate 34's `SCENARIOS` with new scenario 3 (contracts #3, FR-010 case 3): this run's leg concluded `success` but wrote no fold commit of its own (sibling commit present or not) → reported **partly folded**. Depends on T005, T007.
- [ ] T011 [P] [US1] Extend Gate 34's `SCENARIOS` with new scenario 4 (contracts #4, FR-010 case 4, FR-007): a fold commit under the announced leg id carrying **no** `Wing-Commander-Run-Id:` trailer at all → not counted as this (or any) run's evidence, regardless of the leg-id match. Depends on T005, T007.

**Checkpoint**: A run whose leg was cancelled without folding, while a sibling run's same-id commit exists, reports "not folded" — SC-001/SC-002 hold for `report-fold-outcomes`.

---

## Phase 4: User Story 2 - The maintainer's fold list names this review's folds only (Priority: P2)

**Goal**: `dispatch-once`'s fold list and dispatch decision both narrow to this run's own fold evidence; a run that folded nothing of its own declines to dispatch and says so on the PR.

**Independent Test**: With two overlapping runs' fold commits on one branch, confirm each run's PR comment lists only the items it folded, and that a run with no folds of its own dispatches no implement cycle and says so on the PR.

### Implementation for User Story 2

- [ ] T012 [US2] In `.github/workflows/pr-conversation.yml`'s `dispatch-once` job, add a new step "Compute this run's fold evidence" between "Checkout spec branch at its current tip" (~2674–2681) and "Dispatch implement once for the whole review" (~2688), calling the same composite action with this job's own `base-sha`/`tip-sha` (`working-directory: .`, `base-sha: ${{ needs.classify-and-announce.outputs.base-sha }}`, `tip-sha: ${{ steps.tip.outputs.sha }}`), gated identically to the existing checkout/dispatch steps (`steps.tip.outputs.sha != needs.classify-and-announce.outputs.base-sha && steps.tip.outputs.sha != ''`) (data-model.md §4). Depends on T002.
- [ ] T013 [US2] In "Dispatch implement once for the whole review" (~2688–2751), replace the unscoped fold-list build at ~2707–2709 (`folded=$(git log --grep '^fold(' ... "$BASE_SHA..$TIP_SHA" | sed ...)`) with rendering `- <id>: <summary>` lines directly from the new step's `folded-json` output (e.g. `printf '%s' "$FOLDED_JSON" | jq -r '.[] | "- " + .id + ": " + .summary'`), so the `$folded` variable both the standalone-mode reply (~2716–2727) and the dispatched-cycle reply (~2740–2751) already build their comment bodies from is now this run's own evidence only (data-model.md §4, contracts). Depends on T012.
- [ ] T014 [US2] Change the dispatch decision inside the same step (research.md D3, FR-014): add a check that the new step's `folded-json` is non-empty before the existing `gh workflow run` call fires; when `folded-json` is empty, skip `gh workflow run` entirely and fall through to T015's declined-dispatch notice instead of dispatching on a moved-but-not-this-run's-own tip. Depends on T012.
- [ ] T015 [US2] Add the declined-dispatch notice (data-model.md §6, FR-015): when `folded-json` is empty (this step already only runs when the tip moved, since the job-level `if:` excludes the unmoved case), post exactly one PR comment stating this run folded nothing of its own and therefore dispatched no implement cycle — wording distinct from both the existing dispatch-confirmation comment and `report-fold-outcomes`'s warning comment, and from #415 option 4's concurrency-cancellation notice (out of scope here). Depends on T014.
- [ ] T016 [P] [US2] Extend Gate 34's `SCENARIOS` with new scenario 5 (contracts #5, FR-010 case 5, SC-007): this run folds nothing of its own while a sibling run's fold commit sits in this run's range → `dispatch-once` computes zero `gh workflow run` invocations and posts exactly one declined-dispatch notice naming that this run folded nothing. Depends on T005, T013, T014, T015.

**Checkpoint**: A maintainer reading a review's fold list sees only items that review folded (SC-005), and a run with nothing of its own to dispatch says so on the PR rather than dispatching on someone else's commit (SC-007).

---

## Phase 5: User Story 3 - The rule has a fixture that fails when it is broken (Priority: P2)

**Goal**: The two-run case is covered by checked-in fixtures; a mutation that reverts fold evidence to an unscoped range grep fails Gate 34.

**Independent Test**: Run the repository's PR-time gate suite against a deliberately unscoped fold-evidence read and confirm a gate fails.

### Implementation for User Story 3

- [ ] T017 [US3] Extend Gate 34's `SCENARIOS` with new scenario 6 (contracts #6, FR-010 case 6, FR-012): the single-run baseline (no sibling commits at all) produces a byte-identical outcome to the existing `scenario_three_clean_legs`, confirming the single-run-unchanged bar now that evidence is run-scoped. Depends on T005, T007, T013–T015.
- [ ] T018 [US3] Add the new mutation to Gate 34's `MUTATIONS` list (contracts "New mutation", FR-011): replace the composite-action call in the extracted `run:` text with the pre-fix inline `git log --grep '^fold(' "$BASE_SHA..$TIP_SHA"` (no run-id filtering); assert the mutation is caught because the new scenario 2 (T009) then misreports the sibling's commit as this run's own (or, checked against the dispatch side, that `dispatch-once` dispatches on it) — the gate must fail while the mutation is applied and pass once reverted. Depends on T009, T016.
- [ ] T019 [US3] Confirm Gate 34 still appears as `Gate 34 —` in `.github/workflows/lint-workflows.yml`, unrenumbered, and that `wc_gate_registry.py`'s wiring assertion (Gate 10) still passes with the extended scenario/mutation count — no code change expected here (contracts/run-scoped-fold-evidence.md: "needs no new code... it already covers this extension"), just confirmation that it holds. Depends on T018.

**Checkpoint**: Reintroducing the unscoped-range defect now fails Gate 34 automatically. SC-003 holds.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Confirm the feature-wide invariants no single story's gate fully covers on its own, and the manual post-merge proof step spec.md names directly.

- [ ] T020 Run `python3 .github/scripts/run-local-gates.py verify-fold-dispatch-once.py` (verbose) and confirm all thirteen scenarios pass against the shipped workflow/composite action, and every one of the five mutations is caught (quickstart.md Scenarios 1–4).
- [ ] T021 [P] Confirm data-model.md §7 / Constitution VII: diff `pr-conversation.yml`'s declared `workflow_call` `inputs`/`outputs`/`secrets` blocks against their pre-feature shape and confirm nothing was added, removed, or renamed by this feature.
- [ ] T022 Run the full PR-time gate suite (`python .github/scripts/run-local-gates.py`, per this repository's "Before pushing" rule) and confirm it passes clean.
- [ ] T023 Record, on lifecycle issue #565 (or a follow-up note there), that quickstart.md Scenario 5 (SC-006's post-merge live re-drive of a `pr-conversation` run — confirming a real fold commit carries the `Wing-Commander-Run-Id:` trailer and `report-fold-outcomes` reads it back correctly) remains a manual post-merge confirmation per this repository's "prove it after merge" rule for Actions-only behaviour — not part of this feature's own gate suite, and not blocking this feature's completion.

**Checkpoint**: The full gate suite is green, the published interface is unchanged, and the post-merge proof step is recorded as outstanding rather than silently skipped.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — confirms citations before any edit.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS both user stories — the composite action (T002) and the harness's ability to execute it (T005) are prerequisites for every new Gate 34 scenario in US1/US2/US3.
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on US2.
- **User Story 2 (Phase 4)**: Depends on Foundational. No dependency on US1 — different job, different step, same composite action.
- **User Story 3 (Phase 5)**: Depends on US1 (T007, T009) and US2 (T013–T015) — its scenario 6 and mutation exercise the finished mechanism from both jobs together.
- **Polish (Phase 6)**: Depends on US1, US2, and US3 all being complete.

### User Story Dependencies

- **US1 (P1)**: Can start immediately after Foundational. No dependency on US2.
- **US2 (P2)**: Can start immediately after Foundational, in parallel with US1 — different job (`dispatch-once` vs. `report-fold-outcomes`), same composite action, no shared step.
- **US3 (P2)**: Depends on both US1 and US2 being complete, since its fixtures (scenario 6, the mutation) and its wiring confirmation cover the whole mechanism, not one job in isolation.

### Within Each User Story

- Workflow edits before the Gate 34 scenarios that exercise them.
- Gate 34 scenarios before US3's mutation, which targets one of US1's scenarios (T009) directly.

### Parallel Opportunities

- T003 and T004 (Foundational) can run in parallel with each other and with T002 — different files, no shared line.
- T008–T011 (US1's four new scenarios) can be written in parallel once T007 lands — different, independent scenario functions in the same file.
- US1 (T006–T011) and US2 (T012–T016) can proceed in parallel once Foundational is complete — different jobs, different steps, no shared line in `pr-conversation.yml`.
- T021 (Polish) can run in parallel with T020.

---

## Parallel Example: Foundational

```bash
# Launch the hook step and the harness's run-id plumbing together
# (different files, no ordering dependency on each other):
Task: "Add the run-attribution hook step to the act job (T003)"
Task: "Add RUN_ID_UNDER_TEST/RUN_ID_SIBLING + stamp_run_id to make_repo() (T004)"
```

## Parallel Example: User Story 1's new scenarios

```bash
# Launch all four new Gate 34 scenarios together, once T007 lands:
Task: "Scenario 1: own-success + sibling-same-id -> silent (T008)"
Task: "Scenario 2: own-cancelled-no-commit + sibling-same-id -> not folded (T009)"
Task: "Scenario 3: own-success-no-commit -> partly folded (T010)"
Task: "Scenario 4: no-trailer commit -> not this run's evidence (T011)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (the hook, the composite action, the harness extension).
3. Complete Phase 3: User Story 1 (`report-fold-outcomes` narrows to this run's evidence).
4. **STOP and VALIDATE**: Run Gate 34 (T008–T011) standalone; confirm SC-001/SC-002 hold — a cancelled leg is reported "not folded" even with a sibling's same-id commit present.
5. This closes the reported defect (a false "folded cleanly"/"partly folded" over a lost item) even before US2/US3 land.

### Incremental Delivery

1. Setup → Foundational → validate the composite action and hook exist and the harness can execute them.
2. Add US1 (`report-fold-outcomes`, Gate 34 scenarios 1–4) → validate independently — the worst defect (silent review-item loss) is closed.
3. Add US2 (`dispatch-once`, Gate 34 scenario 5) → validate independently — the fold list and dispatch decision now match US1's attribution rule.
4. Add US3 (Gate 34 scenario 6 + the unscoped-grep mutation) → validate that reintroducing the original defect now fails the gate.
5. Polish (Phase 6) → run the full local gate suite, confirm the published interface is unchanged, record the post-merge proof step.

### Suggested Team Split

With parallel capacity: one line of work on `report-fold-outcomes` (US1), one on `dispatch-once` (US2) — both can proceed simultaneously after Foundational, converging at US3's cross-job confirmation.

---

## Notes

- [P] tasks touch different files, or different/non-overlapping steps and scenario functions within a file.
- US1 and US2 are independent of each other (different jobs) but both depend on the same Foundational composite action and hook — the attribution mechanism, not the two jobs' consumption of it, is what is shared.
- US3 adds no new mechanism; it proves the mechanism fails loudly when reverted, per this repository's Constitution VIII and the CLAUDE.md "single home" rule (a second, undetected copy of the range-and-grep is exactly how this defect shipped twice before).
- No `pr-conversation.yml` `workflow_call` input, output, or secret is added, removed, or renamed by this feature (Constitution VII) — T021 confirms this explicitly.
- No new gate number is introduced; every new scenario and the new mutation extend the existing Gate 34 (FR-009).
- Commit after each task or logical group, consistent with this repository's existing per-task commit discipline on the implementation stage.
