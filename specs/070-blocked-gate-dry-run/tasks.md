---

description: "Task list for feature 070: A never-unblocking merge gate is named"
---

# Tasks: A never-unblocking merge gate is named

**Input**: Design documents from `/specs/070-blocked-gate-dry-run/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/gate-allowance-decision.md, quickstart.md (all present)

**Tests**: Not explicitly requested as TDD. FR-009, SC-002, and Constitution VIII require every decision branch this feature introduces to ship with a checked-in, locally runnable fixture reachable from the existing gate registry — those fixture tasks are folded into the single user story below as the feature's own acceptance mechanism, not a separate opt-in pass. No new gate is registered (research.md D5, CLAUDE.md's single-home rule): Gate 66 and Gate 52 are extended in place.

**Organization**: spec.md defines exactly one user story (P1). The two script changes (research.md D1, D2) are pulled into Foundational rather than into User Story 1, because the poll-step wiring and both fixture extensions in User Story 1 call or assert against them from the moment they exist — see Dependencies & Execution Order below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1)
- Line numbers cited below are today's (`9649f1a`) positions in the cited files, taken from research.md/data-model.md/contracts/. Locate sites by the quoted step name, array declaration, or scenario text once a prior task in the same phase has landed, since each edit shifts later line numbers in the same file.

## Path Conventions

CI/CD pipeline infrastructure repository — no `src`/`tests` split. Paths below are repository-root-relative (`.github/`), per plan.md's Project Structure. No published stage workflow (`.github/workflows/{intake,clarify,plan,tasks,implement,converge,finalize,cleanup,watchdog}.yml`) is touched by any task below (plan.md Constraints, spec.md Assumptions).

---

## Phase 1: Setup

**Purpose**: Confirm the baseline this feature edits against, before any file changes.

- [X] T001 Confirm today's line anchors for the sites this feature touches: `auto-release-e2e-merge-decision.sh`'s step 6 `mergeStateStatus == "BLOCKED"` block and its `still_pending` branch (`.github/actions/_shared/auto-release-e2e-merge-decision.sh:76-122`); the `poll` step's env block (`.github/workflows/auto-release.yml:754-769`, `POLL_BUDGET_SECONDS: "8100"` at line 767), the three existing per-gate associative arrays (`:866-869`), and the `case "$merge_head" in ... esac` dispatch (`:998-1029`); `MERGE_SCENARIOS`' three "BLOCKED, still pending"/"no check registered yet" entries and `MERGE_MUTATIONS`' matching entries in `.github/scripts/verify-auto-release-e2e-gate-decisions.py:264-293,351-380`; and the `gate_stall()` helper plus the three existing `GATE_STALL_*` fixtures and their `SCENARIOS` entries in `.github/scripts/verify-auto-release-report.py:119-136,427-471`. Record any drift from research.md/data-model.md/contracts/gate-allowance-decision.md's citations (taken at `0c12ced`/`9649f1a`) in the PR description rather than in a spec file. No file changes.

**Checkpoint**: Baseline confirmed; Foundational work can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The amended merge-decision token and the new allowance-decision script every User Story 1 task (poll-step wiring, both fixture extensions) depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Amend `.github/actions/_shared/auto-release-e2e-merge-decision.sh` per contracts/gate-allowance-decision.md's contract for step 6: when `mergeStateStatus == "BLOCKED"` and `still_pending == "true"` (nothing in `statusCheckRollup` has resolved — empty array, every CheckRun entry not yet `COMPLETED`/without a `conclusion`, or a legacy StatusContext entry in `PENDING`/`EXPECTED`), print `blocked-pending` instead of `wait` (research.md D1). Every other branch — durably `blocked` (`still_pending == "false"`), `isDraft` → `wait` (step 4), `UNKNOWN`/`BEHIND` → `wait` (step 7), and all of steps 1-5 and 8 — is unchanged. Update the script's header comment's output vocabulary line (`:27-33`) and the inline comment above the `still_pending` check (`:97-104`, "indistinguishable... from a genuinely misconfigured required check that will never report") to name `blocked-pending` as the token this ambiguity now resolves to, since research.md D1 replaces the "treated as still-pending (wait)" framing those comments currently state.
- [X] T003 [P] Create `.github/actions/_shared/auto-release-e2e-gate-allowance-decision.sh`, invoked as `bash .github/actions/_shared/auto-release-e2e-gate-allowance-decision.sh "$MERGE_DECISION" "$BLOCKED_SINCE" "$NOW" "$ALLOWANCE_SECONDS"` per contracts/gate-allowance-decision.md: print `clear` if `MERGE_DECISION` is not `blocked-pending` (FR-005 — the gate has left the blocked-with-unresolved-checks state, or never entered it this iteration); else print `start` if `BLOCKED_SINCE` is empty (first continuous `blocked-pending` observation); else print `stall` if `NOW - BLOCKED_SINCE >= ALLOWANCE_SECONDS` (FR-003, FR-004 — the allowance is exhausted); else print `wait` (still within the allowance). Pure function of its four arguments — no `gh` call, no network, no file read beyond argv (Constitution VIII, research.md D2). Match the header-comment style and `set -uo pipefail` idiom of T002's script and `auto-release-verdict.sh`; never sourced.

**Checkpoint**: the amended token and the new allowance script exist and are independently invocable. User story work can begin.

---

## Phase 3: User Story 1 - A gate that will never unblock says so (Priority: P1) 🎯 MVP

**Goal**: A merge gate whose pull request sits blocked with no resolved check result for longer than a 20-minute per-gate allowance ends the attempt with a gate-stall verdict naming that gate and the pull request, instead of silently consuming the full 135-minute poll budget and reporting the generic timeout; a gate that resolves inside the allowance still merges, and every other outcome (the pass path, the four existing gate-stall reasons, infrastructure, pipeline-defect, and the generic timeout) is unchanged.

**Independent Test**: drive the merge-gate decision and the poll loop's handling of it with fixtures whose pull request stays blocked with an unresolved check rollup for longer than the waiting allowance, and confirm the attempt ends with a gate-stall verdict naming that gate rather than the generic timeout — and, separately, that a pull request whose checks resolve inside the allowance still merges. No live run is required.

### Implementation for User Story 1

- [X] T004 [US1] In the `poll` step's `env:` block (`.github/workflows/auto-release.yml:754-769`), add `GATE_BLOCKED_ALLOWANCE_SECONDS: "1200"` beside `POLL_BUDGET_SECONDS: "8100"` (FR-004: 20 minutes, well under the 135-minute/8100-second poll budget). Depends on T001.
- [X] T005 [US1] Beside the existing `declare -A gate_merged=(...)` / `gate_name=(...)` / `gate_failures=(...)` / `gate_last_failure=(...)` (`.github/workflows/auto-release.yml:866-869`), add `declare -A gate_blocked_since=([spec-draft/]="" [plan/]="" [spec/]="")`, keyed by the same `prefix` values, per data-model.md's Gate waiting state entity (research.md D3). Depends on T004.
- [X] T006 [US1] Extend the `case "$merge_head" in ... esac` dispatch (`.github/workflows/auto-release.yml:998-1029`) per contracts/gate-allowance-decision.md's call-site: add a `blocked-pending)` arm that calls T003's script with `"$merge_head" "${gate_blocked_since[$prefix]}" "$SECONDS" "$GATE_BLOCKED_ALLOWANCE_SECONDS"` and applies its answer — `start` sets `gate_blocked_since[$prefix]="$SECONDS"`; `stall` calls `write_verdict "fail-gate-stall" "${gate_name[$prefix]}" "gh pr merge succeeds" "PR #${pr_number}: required checks never reported a result"` (research.md D4) then `emit_verdict` and `exit 0`; `wait` does nothing. Every other arm that decides a durable outcome this iteration (`merge`, `conflicting`, `blocked`, `wrong-attempt`, `wrong-base`) additionally resets `gate_blocked_since[$prefix]=""`. The plain `wait` token (draft PR, `UNKNOWN`/`BEHIND` — currently falls through the `case` doing nothing) gains a new `wait)` arm that also resets `gate_blocked_since[$prefix]=""`, since FR-005 requires the timer to reset on leaving the blocked-with-unresolved-checks state even when the new state is itself an ordinary wait. A failed read never reaches this `case` at all (it is inside the same `else` branch that already requires a successful merge-decision call), so FR-006 holds with no extra guard needed. Depends on T002, T003, T005.
- [X] T007 [P] [US1] In `.github/scripts/verify-auto-release-e2e-gate-decisions.py`, change `expect_head` from `"wait"` to `"blocked-pending"` on the three `MERGE_SCENARIOS` entries T001 anchored ("BLOCKED, a check still running", "BLOCKED, no check has registered yet (freshly opened PR)", "BLOCKED, a legacy StatusContext... still pending", and the EXPECTED variant — `:269-293`), since T002 renames exactly that branch. Update the matching `MERGE_MUTATIONS` entries ("a pending required check reads as blocked instead of wait", "an empty statusCheckRollup... reads as blocked instead of wait", the legacy-StatusContext-shape mutation, and the EXPECTED mutation — `:361-376`) so each still asserts against `blocked-pending` rather than `wait`, proving a regression that collapses `blocked-pending` back into `wait` still fails the mutation check (research.md D5(a)). Depends on T002.
- [X] T008 [P] [US1] In `.github/scripts/verify-auto-release-e2e-gate-decisions.py`, add `ALLOWANCE_SCRIPT` (mirroring `MERGE_SCRIPT`'s path constant) and a new `ALLOWANCE_SCENARIOS` list + `run_allowance_suite()` (mirroring `MERGE_SCENARIOS`/`run_merge_suite()`) exercising T003's script directly against synthetic `(merge_decision, blocked_since, now, allowance_seconds)` argument tuples — no real waiting, no mocked `gh` — covering all four branches per contracts/gate-allowance-decision.md and research.md D5(a): `blocked-pending` with empty `blocked_since` → `start`; `blocked-pending` with `now - blocked_since` under the allowance → `wait`; `blocked-pending` with `now - blocked_since` at/over the allowance → `stall`; and a non-`blocked-pending` decision (e.g. `merge`, or a plain `wait` from a draft/`UNKNOWN`/`BEHIND` PR) with a previously-set `blocked_since` → `clear`. Add a matching `ALLOWANCE_MUTATIONS` list breaking each of the four branches once (inverting the script's `clear`/`start`/`stall` conditionals in turn), wire `run_allowance_suite` into `run_all()`, `ALLOWANCE_MUTATIONS` into `self_test()`, and `len(ALLOWANCE_SCENARIOS)` into `main()`'s scenario-count total. Depends on T003.
- [X] T009 [P] [US1] In `.github/scripts/verify-auto-release-report.py`, add `GATE_STALL_BLOCKED_PENDING = gate_stall("<gate name>", "gh pr merge succeeds", "PR #<n>: required checks never reported a result")` beside the existing `GATE_STALL_SPEC_DRAFT`/`GATE_STALL_PLAN`/`GATE_STALL_FINALIZE` (`:130-136`, using the exact `expected`/`observed` strings from T006/research.md D4), and a matching `SCENARIOS` entry beside the existing three gate-stall entries (`:440-471`) with `body_contains=["gate stall", "<gate name>", "PR #<n>: required checks never reported a result"]` and `body_excludes=["**Classification**: infrastructure", "**Classification**: pipeline defect"]`, proving the rendering and "gate stall" classification path needs no code change for the new reason (research.md D5(b)). Depends on T006 (for the exact evidence strings to assert against).
- [X] T010 [US1] Run `python .github/scripts/run-local-gates.py` per CLAUDE.md and confirm it passes clean, including Gate 66 and Gate 52's self-tests. Then work quickstart.md's five scenarios in order, confirming each Pass condition: Scenario 1 (blocked-pending inside the allowance is still waited on), Scenario 2 (allowance exhausted ends the attempt as a named gate stall, in both the decision-script output and the rendered failure report), Scenario 3 (a gate that resolves to a pass inside the allowance still merges), Scenario 4 (the allowance resets only on observable progress, never on rollup shape alone), and Scenario 5 (the generic timeout and the classification `case` at `auto-release.yml:1083-1089,1790-1794` are byte-identical to this branch's base). Depends on T006, T007, T008, T009.

**Checkpoint**: User Story 1 is independently functional and testable — SC-001, SC-002, and SC-003 all hold with no live dispatch of `auto-release.yml` required.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS User Story 1. T002 and T003 touch different files and have no dependency on each other; they can run in parallel.
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion. Within it: T004 → T005 → T006 is a strict chain (each edits state introduced by the previous task in the same file); T007, T008, and T009 each depend on exactly one Foundational task (T002, T003, and T006 respectively) and touch three different files, so once their own dependency lands they can run in parallel with each other and with the rest of the `case`-dispatch chain up to the point T009 needs T006's exact evidence strings; T010 is the final integration/validation task and depends on everything before it.

### Within User Story 1

- T004 → T005 → T006 (same file, each builds on the previous task's state).
- T007 depends only on T002 (not on T004-T006).
- T008 depends only on T003 (not on T004-T006).
- T009 depends on T006 (needs the exact `gate_name`/evidence strings T006 wires into the workflow).
- T010 depends on T006, T007, T008, T009 (runs the full gate suite and the quickstart scenarios against the finished change).

### Parallel Opportunities

- T002 and T003 (Foundational) can run in parallel — different files, no shared state.
- Once T002 lands, T007 can run in parallel with T004/T005/T006 and with T003/T008.
- Once T003 lands, T008 can run in parallel with T004/T005/T006 and with T002/T007.
- T007, T008, and T009 (once its own T006 dependency is met) touch three different files and can run in parallel with each other.

---

## Parallel Example: Foundational + fixture tasks

```bash
# Launch the two Foundational script tasks together (different files):
Task: "Amend auto-release-e2e-merge-decision.sh step 6 to print blocked-pending"
Task: "Create auto-release-e2e-gate-allowance-decision.sh"

# Once each lands, its fixture extension can proceed independently of the
# workflow wiring chain (T004-T006):
Task: "Rename the three BLOCKED-still-pending MERGE_SCENARIOS/MUTATIONS entries to blocked-pending"
Task: "Add ALLOWANCE_SCENARIOS/run_allowance_suite()/ALLOWANCE_MUTATIONS to Gate 66"
```

---

## Implementation Strategy

### MVP First (and only) — User Story 1

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002, T003 — CRITICAL, blocks User Story 1).
3. Complete Phase 3: User Story 1 (T004-T010).
4. **STOP and VALIDATE**: T010's `run-local-gates.py` run plus the five quickstart scenarios are the complete evidence for SC-001/SC-002/SC-003 (quickstart.md's own closing section) — no live dispatch of `auto-release.yml` is part of this feature's validation.

spec.md defines exactly one user story, so there is no incremental multi-story delivery plan here: Setup → Foundational → User Story 1 → done. No Polish/cross-cutting phase is needed — the fixture, documentation-comment, and validation work FR-009/SC-002 require is already folded into User Story 1's own tasks (T007-T010), and this feature touches no published stage workflow, adopter-facing surface, or shared documentation beyond the two comment updates T002 already covers.

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specs.md's single user story (US1) for traceability.
- No test tasks are separately called out beyond T007-T010: this feature's fixtures (Gate 66, Gate 52) are its acceptance tests, not a TDD red/green pass, per the Tests note above.
- Verify `run-local-gates.py` passes before push, per CLAUDE.md.
- Commit after each task or logical group; stop at the Phase 2/Phase 3 checkpoints to confirm the prior phase is solid before continuing.
- Avoid: re-deriving the rollup-shape judgment a second time outside `auto-release-e2e-merge-decision.sh` (CLAUDE.md's single-home rule, research.md D1's rejected alternative); a third fixture harness alongside Gate 66/Gate 52 (research.md D5's rejected alternative); a new `outcome` value instead of a new `fail-gate-stall` reason (spec.md Assumptions).

## Maintainer Feedback

- [X] Before writing `fail-timeout` in the poll step's post-loop block (`.github/workflows/auto-release.yml`, currently ~1083-1089), check whether any `gate_blocked_since[$prefix]` is non-empty. If one is, write `fail-gate-stall` for the first such gate (`"gh pr merge succeeds"` expected / `"PR #<n>: required checks never reported a result"` observed, matching T006's evidence strings) instead of the generic timeout — per spec.md's "the waiting allowance is reached late in the poll budget" edge case and FR-007 (the generic timeout must remain the outcome only when *no* gate is blocked).
- [X] Add a Gate 66 or Gate 52 fixture covering a gate that goes blocked-pending late enough in the poll budget that its 1200s allowance would not otherwise fully elapse before the loop exits on budget, asserting the outcome is `fail-gate-stall` naming that gate, not the generic timeout.
- [X] Update the stale comment in `.github/actions/_shared/auto-release-e2e-merge-decision.sh` (~line 81, "confirm a pending-checks PR is never declared a gate stall") to reflect that a pending-checks PR is now declared stalled after the 20-minute allowance, per FR-004.
