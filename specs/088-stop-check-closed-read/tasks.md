---

description: "Task list for An Honest Read-Failure Policy for board-stop-check's Closed Check"
---

# Tasks: An Honest Read-Failure Policy for board-stop-check's Closed Check

**Input**: Design documents from `/specs/088-stop-check-closed-read/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/board-stop-check-composite.md, contracts/errexit-claim-gate.md, quickstart.md

**Tests**: This repository's tests are its own deterministic gate scripts (CLAUDE.md, Constitution VIII). FR-013 requires every behavioural requirement to be proved by extending the existing `verify-board-stop-check.py` harness rather than a new parallel one, and FR-009 requires the new gate's own mutation self-test — both are embedded in the relevant story's implementation tasks below, not a separate test-first phase.

**Organization**: Tasks are grouped by user story (spec.md) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)
- Include exact file paths in descriptions

## Path Conventions

CI/CD pipeline repository, no `src/`. All changes live under `.github/actions/`, `.github/workflows/`, and `.github/scripts/`, matching plan.md's Project Structure.

---

## Phase 1: Setup

**Purpose**: Pin down the two facts every later task depends on for correct file targeting, both of which plan.md/research.md flag as time-sensitive against this checkout.

- [ ] T001 [P] Confirm the next sequential gate number for FR-009's new gate: grep `.github/workflows/lint-workflows.yml` for every `Gate NNN —` step name and take the highest + 1. research.md D5 recorded this as 101 (highest shipped: Gate 100, `.github/workflows/lint-workflows.yml:4168`) at plan time — re-confirm it at implementation time in case another branch landed Gate 101+ in the interim, and use the confirmed number in T020.
- [ ] T002 [P] Confirm the current line of `.github/workflows/implement.yml`'s "No `-e`" comment by content search for `No .-e.: an unreadable file degrades` rather than trusting spec.md's stale `implement.yml:2785` citation (research.md D9: confirmed at line 3013 as of this checkout, content search finds a different, already-correct comment at 2785) — re-confirm at implementation time since the file continues to change, and use the confirmed line in T016.

---

## Phase 2: Foundational

None. Every user story below is additive over the currently shipped `action.yml`/workflow comments/gate scripts, and no shared infrastructure (build config, schema, base model) needs to land before any of them start — this is the same conclusion research.md reaches by construction (D1-D8 each modify one already-existing file in place).

---

## Phase 3: User Story 1 - The read-failure policy is a decision, stated truthfully (Priority: P1) 🎯 MVP

**Goal**: Make `closed-check`'s read-failure policy fail-loud, truthfully documented, and unable to strand the kill-switch/stop-request check — without changing the composite's published `paused` output name or shape.

**Independent Test**: Read the composite with no other context and state (a) what happens on a total read failure and (b) what the pre-#465 code did; both must match shipped behaviour and git history. Drive `verify-board-stop-check.py`'s extended harness and confirm every SC-007 branch and the reinstated-`continue-on-error` mutation behave as documented.

### Implementation for User Story 1

- [X] T003 [US1] In `.github/actions/wing-commander-board-stop-check/action.yml`, reorder `runs.steps` so the kill-switch/stop-request step (`id: check`) runs **first**, unconditionally, and the lifecycle-issue read (`id: closed-check`, `if: inputs.check-issue-closed == 'true'`) runs **second** (research.md D1).
- [X] T004 [US1] In the same file's `check` step `run:` script, remove the `ISSUE_IS_OPEN` env var (currently `env.ISSUE_IS_OPEN: ${{ steps.closed-check.outputs.is-open }}`) and the `if [ "$ISSUE_IS_OPEN" = "false" ]; then paused=true; fi` block — `check` no longer depends on `closed-check`'s output at all (D1).
- [X] T005 [US1] In the same file, delete `continue-on-error: true` from the `closed-check` step (FR-002).
- [X] T006 [US1] In the same file, rewrite the `closed-check` step's header comment (the block currently reading "continue-on-error: the behaviour this replaces already treated a failed read as 'not closed, keep going' rather than failing the job; this keeps that same fallback...") to state the real policy: fail-loud, the trade-off it resolves (one deferred `prove` the next scheduled run retries, bought against closing or re-driving an issue a maintainer already closed), and that the pre-#465 code *failed the job* on a read failure rather than preserving a fallback. End it with a `-- see verify-errexit-claim-comments.py.` pointer (FR-001, FR-002, FR-008, D4).
- [X] T007 [US1] In the same file, add a new step `id: closed-check-note` positioned after `closed-check`, gated `if: steps.closed-check.outcome == 'failure'`, that echoes one `::error::` line naming `inputs.issue-number` and the fail-loud consequence (e.g. that this composite's policy stops the job before its next durable action), and exits 0 without changing the job's already-failed conclusion (FR-004, D3).
- [X] T008 [US1] In the same file, change `outputs.paused.value` from `${{ steps.check.outputs.paused }}` to `${{ steps.check.outputs.paused == 'true' || (inputs.check-issue-closed == 'true' && steps.closed-check.outputs.is-open == 'false') }}` (D2, contracts/board-stop-check-composite.md §3).
- [X] T009 [US1] Confirm — no edit expected — that `board-loop.yml`'s `prove` job's two durable-action steps ("Close the issue on the merge evidence alone", "Re-drive the changed behaviour to prove the fix") still gate on `steps.killswitch-recheck.outputs.paused != 'true'` with a bare `if:` (implicit `success()`), so T005's removal alone stops the job before either runs (contracts/board-stop-check-composite.md §4, Acceptance Scenario 4). If this turns out false against the current file, fix it here.
- [X] T010 [US1] Extend `.github/scripts/verify-board-stop-check.py` with structural assertions against the parsed `action.yml`: the `closed-check` step carries no truthy `continue-on-error`; `check`'s index in `runs.steps` is lower than `closed-check`'s; `check`'s `run:` text contains no `steps.closed-check` reference (research.md D7 item 1).
- [X] T011 [US1] In the same file, extend the `check`-step shell-case harness to drive the script with `check-issue-closed` both unset and `"true"`, and add coverage that evaluates the composite's new `outputs.paused` expression (reuse `.github/scripts/wc_gha_expr.py` per D7's alternatives-considered, not a hand-written second parser) against every SC-007 combination: read succeeds OPEN, succeeds CLOSED, fails all attempts (`closed-check.outcome == 'failure'`), and fails-then-succeeds (same code path as succeeds — `lifecycle-gate`'s own retry is Gate 25's territory, untested here).
- [X] T012 [US1] In the same file, add a mutation that reintroduces `continue-on-error: true` on `closed-check` (the pre-fix shape) as a structural YAML toggle (not a `run:`-string regex substitution, since the fix is YAML-level), and assert at least one check from T010/T011 catches it (D7 item 3, FR-013).

**Checkpoint**: At this point, `closed-check`'s fail-loud policy is truthfully documented, structurally enforced, and covered end-to-end by `verify-board-stop-check.py` — independently testable and shippable on its own.

---

## Phase 4: User Story 2 - A tolerated read failure does not accuse a healthy run (Priority: P1) — satisfied by construction

**Goal**: Confirm the FR-002 fail-loud policy (User Story 1) makes "green `prove` job carrying a `closed-check` failure annotation" unreachable, with no filtering remedy added anywhere.

**Independent Test**: Confirm no `prove` job can complete green while carrying a `closed-check` read-failure annotation, and that this feature's diff introduces no annotation filtering in `lifecycle-gate` or the watchdog's collector.

- [X] T013 [US2] Confirm, via `git diff main --name-only` (or equivalent), that this feature's diff does not touch `.github/actions/wing-commander-lifecycle-gate/action.yml` or `.github/workflows/watchdog.yml` (`Collect: annotations` step and the diagnose classifier), and introduces no other annotation suppression/downgrade/filtering — this story ships with no code change of its own; T003-T012 already make the accusing combination structurally impossible (FR-005, FR-006).

**Checkpoint**: Confirmed unreachable by construction; no remedy shipped in `lifecycle-gate` or the watchdog.

---

## Phase 5: User Story 3 - The `-e` fact has one home and a gate behind it (Priority: P2)

**Goal**: Correct all five shipped comments that misstate errexit semantics, give the corrected fact exactly one canonical statement, and gate future recurrences.

**Independent Test**: Search the repository for any comment claiming a `shell: bash` step runs without errexit — the search returns nothing, and one canonical statement exists that every other site points at. Introduce such a claim and confirm the gate suite fails.

### Implementation for User Story 3

- [X] T014 [P] [US3] Correct `.github/workflows/board-loop.yml`'s comment at line 1653 (currently "#514: this step runs without -e, so a failed create would...") to state errexit is active and describe the step's actual safety property (the URL-format guard sits behind an assignment that would already have aborted on failure), preserving the #514 historical narrative, and end with a `-- see verify-errexit-claim-comments.py.` pointer (FR-007, FR-008, FR-010).
- [X] T015 [P] [US3] Correct `.github/workflows/metrics-persist.yml`'s comment at line 348 (currently "...and under `set -uo pipefail` with no `-e` the resulting empty window_start/list_from silently listed the repository's ENTIRE run history rather than failing loudly") to reframe that outcome as the pre-fix historical bug (tense/framing correction, not deletion — the edge case requires the historical record survive) rather than a live claim about the shipped step, and end with the same pointer (FR-007, FR-008, FR-010).
- [X] T016 [US3] Correct `.github/workflows/implement.yml`'s comment at the line confirmed by T002 (currently "No `-e`: an unreadable file degrades to empty fields, the same as a missing one — this step must never fail, since 'Mark lifecycle record stalled' below carries no always() and would be stranded") to state the step's actual safety property (each read is `||`-guarded, each write cannot fail, so the step already cannot abort) instead of relying on a false errexit premise, and end with the same pointer (FR-007, FR-008, FR-010).
- [X] T017 [P] [US3] Correct `.github/workflows/lint-workflows.yml`'s Gate 19 comment at line 1921 (currently "...silently drops every annotation past page 1 under `set -uo pipefail` with no `-e` — the failure never surfaces, it just reads as 'nothing to report'") to describe the pre-fix pagination-loss bug under corrected tense/framing (the fix removed a step that would have silently dropped annotations under the mistaken belief errexit was off — not a live claim), and end with the same pointer (FR-007, FR-008, FR-010).
- [X] T018 [US3] Create `.github/scripts/verify-errexit-claim-comments.py`: module docstring states the FR-008 canonical fact (D4 — a `shell: bash` step runs as `bash --noprofile --norc -eo pipefail {0}` so errexit is active from the outer invocation before the script's first line runs; `set -uo pipefail` only touches `-u`/`-o pipefail`, leaving `-e` untouched; a failing command inside a plain `var="$(...)"` assignment therefore still aborts the step); scans `.github/workflows/*.yml` and `.github/actions/*/action.yml` plus `.github/actions/**/action.yml` recursive (reusing `verify-actions-layer-invariants.py`'s glob shape, D5 — deliberately wider than Gate 24's workflow-only scope); imports `comment_blocks()`/`_joined()` from `.github/scripts/verify-comment-canonical-pointers.py` rather than reimplementing (CLAUDE.md "Shared logic has exactly one home"); applies the five phrase patterns from research.md D6 with the negation-window (3 preceding words: not/never/n't/doesn't/does/cannot) and quoted-span (longer than the flag token alone) exclusions; emits one `::error file=...::` per surviving violation naming file and starting line, plus a `N file(s) scanned, M violation(s)` summary line; exits 1 if any violation survives, else 0 (FR-009, contracts/errexit-claim-gate.md).
- [X] T019 [US3] Implement `verify-errexit-claim-comments.py --self-test`: synthetic tempdir fixtures proving (1) a comment using the gate's own canonical phrasing produces no violation, (2) a comment quoting the false claim inside a longer quoted span to correct it produces no violation, (3) the negated true form ("does not clear `-e`") produces no violation, (4) each of the five bare, un-negated phrase patterns is caught, naming the right file and line, and (5) mutation coverage — taking the real, shipped corrected text of each of the five sites (T006, T014, T015, T016, T017) and mutating it back to its pre-fix false claim is caught. Depends on T006 and T014-T017 already being landed, since (5) mutates their real shipped text, not a fixture (contracts/errexit-claim-gate.md §Self-test, FR-009).
- [X] T020 [US3] Register the new gate in `.github/workflows/lint-workflows.yml`: add a `Gate <T001's confirmed number> — ...` step running `python3 .github/scripts/verify-errexit-claim-comments.py` and a `Gate <N> self-test — ...` step running it with `--self-test`, both `if: "!cancelled()"`, following Gate 100's registration pattern at `.github/workflows/lint-workflows.yml:4168-4173`.

**Checkpoint**: All five sites state the true premise, `verify-errexit-claim-comments.py` is wired into the PR-time suite via Gate 10's naming-convention check, and its self-test proves it can fail its own shipped subject.

---

## Phase 6: User Story 4 - Gate 24's scope is recorded where the next PR will read it (Priority: P3)

**Goal**: Record Gate 24's `.github/workflows/*.yml`-only scope in its own docstring, pointing at a real, open follow-up issue for widening it — without widening it in this feature.

**Independent Test**: Read `verify-gate-24.py` and its documented scope with no other context and answer "does Gate 24 inspect `.github/actions/**`?" correctly.

- [ ] T021 [US4] File a new GitHub issue tracking widening Gate 24 to scan `.github/actions/**` (a plain bug/enhancement issue, no `spec-request` label — CLAUDE.md's routing rule treats this as deterministic and gate-shaped, not a design trade-off). Record its number for T022 (FR-012, D8).
- [ ] T022 [US4] Add a paragraph to `.github/scripts/verify-gate-24.py`'s module docstring near `WORKFLOWS_GLOB` (line 93) stating that Gate 24 inspects only `.github/workflows/*.yml`, that `.github/actions/**` — including `wing-commander-board-stop-check` — is out of its scope, and naming the follow-up issue filed in T021 (FR-012, D8).

**Checkpoint**: A reader of Gate 24 alone can no longer cite "Gate 24: 0 findings" as evidence about a composite action.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Run every gate this feature's changes must pass, per CLAUDE.md and quickstart.md.

- [ ] T023 [P] Run `python .github/scripts/verify-errexit-claim-comments.py` and `python .github/scripts/verify-errexit-claim-comments.py --self-test` standalone; confirm zero violations on the shipped tree (SC-002) and a passing self-test (SC-003).
- [ ] T024 [P] Run `python .github/scripts/verify-board-stop-check.py` standalone; confirm every pre-existing fixture/shell case, the T011 SC-007 coverage, and both mutations (T012's and the pre-existing cancel-guard mutation) pass (SC-007).
- [ ] T025 Run quickstart.md's Gate-24-boundary check and composite step-order sanity-check snippets; confirm `check` precedes `closed-check` in `runs.steps`, `continue-on-error` is absent from `closed-check`, and `verify-gate-24.py`'s docstring names a real, open issue (T021).
- [ ] T026 Get a `review-step-gating` skill pass on the `.github/actions/wing-commander-board-stop-check/action.yml` diff, since it touches `if:` and `continue-on-error:` (CLAUDE.md "Before pushing").
- [ ] T027 Run `python .github/scripts/run-local-gates.py` and confirm it exits 0 (quickstart.md's primary acceptance signal; SC-008).
- [ ] T028 Confirm `git diff main --name-only` excludes `.github/actions/wing-commander-lifecycle-gate/action.yml` and `.github/workflows/watchdog.yml`, and that `action.yml:171`'s `gh run cancel ... failed: $cancel_error` interpolation is unchanged (FR-005, FR-006, FR-011).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: None — nothing blocks any user story.
- **User Story 1 (Phase 3)**: Depends on Setup's T001 (gate number, used only in T006's/T020's pointer text — T003-T012 do not otherwise need it). Fully self-contained otherwise.
- **User Story 2 (Phase 4)**: Depends on User Story 1 being complete (T013 confirms the combination T003-T012 make unreachable).
- **User Story 3 (Phase 5)**: Depends on Setup's T001 (gate number) and T002 (implement.yml line). T006 (US1's comment rewrite) is one of the five sites T019's mutation coverage exercises, so T019 depends on T006 as well as T014-T017.
- **User Story 4 (Phase 6)**: Independent of US1-US3; can start any time after Setup.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on other stories — the MVP.
- **User Story 2 (P1)**: Depends on User Story 1 (its independent test verifies US1's construction).
- **User Story 3 (P2)**: Independent of US1/US2 except that T019's mutation coverage needs T006 (US1) landed; can otherwise proceed in parallel with US1.
- **User Story 4 (P3)**: Fully independent of US1-US3.

### Within Each User Story

- US1: T003-T008 touch the same file (`action.yml`) and must run in the order given; T009 confirms a different file needs no change; T010-T012 extend `verify-board-stop-check.py` after the composite shape they test exists.
- US3: T014, T015, T017 (three different workflow files) can run in parallel with each other and with T016 once T002 confirms its line. T018 (new gate script) can be written in parallel with T014-T017. T019 (self-test) must come after T006, T014, T015, T016, T017 all exist, since its mutation coverage mutates their real shipped text. T020 (registration) comes last.
- US4: T021 (file the issue) before T022 (point at its number).

### Parallel Opportunities

- T001 and T002 (Setup) are independent reads and can run in parallel.
- T014, T015, T017 (US3, three different workflow files) can run in parallel with each other; T016 joins them once T002 resolves its line.
- T018 (new gate script) can be written in parallel with T014-T017 — it only needs their *final* text for T019's self-test, not to exist alongside them.
- User Story 4 (T021-T022) can run in parallel with User Story 1 and User Story 3 — it touches only `verify-gate-24.py` and a new issue.
- T023 and T024 (Polish) are independent gate runs and can run in parallel.

---

## Parallel Example: User Story 3

```bash
# Launch the four independent comment corrections together (T016 after T002 resolves its line):
Task: "Correct board-loop.yml's comment at line 1653 (T014)"
Task: "Correct metrics-persist.yml's comment at line 348 (T015)"
Task: "Correct implement.yml's comment at the line T002 confirmed (T016)"
Task: "Correct lint-workflows.yml's Gate 19 comment at line 1921 (T017)"

# The new gate script can be drafted in parallel with the above:
Task: "Create verify-errexit-claim-comments.py (T018)"

# T019 (self-test) waits for T006 + T014-T017 to land before it can mutate their real text.
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002).
2. Phase 2: Foundational — nothing to do.
3. Complete Phase 3: User Story 1 (T003-T012).
4. **STOP and VALIDATE**: run `python .github/scripts/verify-board-stop-check.py` and re-read the composite per US1's Independent Test.
5. This alone corrects the load-bearing comment and makes the fail-loud policy real — the issue's core defect is fixed.

### Incremental Delivery

1. Setup → User Story 1 (MVP: the policy is fixed and truthfully documented).
2. User Story 2 (confirm the fix makes the watchdog false-positive unreachable — no new code).
3. User Story 3 (the root-cause comment-pattern fix, gated against recurrence) — can be developed in parallel with User Story 1 except for T019's dependency on T006.
4. User Story 4 (Gate 24's scope recorded, follow-up issue filed).
5. Polish: full gate suite, quickstart checklist, `review-step-gating` skill pass.

### Parallel Team Strategy

With two agents (per CLAUDE.md's "concurrent local agents to two" board-working guidance):

1. Agent A: Setup (T001-T002) → User Story 1 (T003-T012) → User Story 2 (T013).
2. Agent B: User Story 4 (T021-T022) once Setup's T001 is available, then joins User Story 3 (T014-T020) once T006 (Agent A) lands, for T019's mutation coverage.
3. Either agent runs Polish (T023-T028) once both stories converge.
