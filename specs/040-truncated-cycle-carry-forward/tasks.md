---

description: "Task list for A Turn-Exhausted Implement Cycle Is Carried Forward, Not Redone from Cold"
---

# Tasks: A Turn-Exhausted Implement Cycle Is Carried Forward, Not Redone from Cold

**Input**: Design documents from `/specs/040-truncated-cycle-carry-forward/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/implement-cycle-outcome.md, contracts/truncated-cycle-coverage.md, quickstart.md

**Tests**: Requested — FR-018/FR-019/FR-020 require executable coverage that drives the shipped `implement.yml` steps against synthetic git history and a stubbed upstream verdict, proving both the carry-forward path and the no-progress/genuine-failure paths, with five distinct required mutations each independently failing the check. Coverage tasks are folded into the user-story phase whose behavior they prove (US1's classification, US2's forced convergence, US3's no-progress guard, US4's retry-path classification, US5's counter/reporting), plus a dedicated mutation-proof phase for US6, rather than a separate testing phase.

**Organization**: This feature's footprint is one existing workflow file rewired/extended in place (`.github/workflows/implement.yml`: "Read back cycle outcome", "Read back retry outcome", "Consolidate final outcome", "Dispatch next step" rewired; "Record retry base SHA", "Record truncated-cycle count" newly added), one new coverage script (`.github/scripts/verify-truncated-cycle-carry-forward.py`), and one new gate step wiring it into `.github/workflows/lint-workflows.yml` as Gate 26 (plan.md's Structure Decision). No new directory, no new composite action, zero edits to `wing-commander-5-implement.yml` or the `wing-commander-agent-verdict` composite. Because FR-002's three-way classification (exhausted + advanced + progress) and FR-005's forced-not-converged rule are one inseparable conditional in "Read back cycle outcome" (research.md D1-D4) — R1 in spec.md is explicit that shipping the classification without the forced-false guard is worse than shipping nothing — the whole rewrite of that one step lands under User Story 1 (its P1 MVP), and User Story 2/3 build coverage proving the convergence-forcing and no-progress-guard facets of that same rewrite, matching the precedent set by specs/039-lifecycle-gate-retry's tasks.md for an identically-shaped single-step rewrite.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US6)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split. All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the gate number this feature claims is actually free, and establish the pre-feature baseline every non-truncated-path scenario (FR-017, SC-006) will be diffed against.

- [X] T001 Run `grep -n "name: Gate [0-9]" .github/workflows/lint-workflows.yml` and confirm no step is already named `Gate 26` (research.md D8 — the highest number in use today is Gate 25, `specs/039-lifecycle-gate-retry`). Record the current byte-for-byte text of "Read back cycle outcome" (`implement.yml:878-926`), "Read back retry outcome" (`implement.yml:1146-1196`), "Consolidate final outcome" (`implement.yml:1201-1230`), and "Dispatch next step" (`implement.yml:1422-1485`) — e.g. via `git show HEAD:.github/workflows/implement.yml` — as the FR-017/SC-006 baseline later Polish tasks diff a healthy/ordinary-failure scenario's outputs against.

**Checkpoint**: Gate 26 numbering is free; the pre-feature baseline is captured.

---

## Phase 2: Foundational (Blocking Prerequisites)

**No blocking prerequisites.** This feature's entire implementation is the rewrite of one step (T002) plus a small number of new/extended steps in the same job (T006, T007, T008, T010, T011), and one coverage script that grows across the user-story phases below; there is no shared scaffolding to build before story work can begin.

---

## Phase 3: User Story 1 - A cycle that ran out of turns keeps its work and carries on (Priority: P1) 🎯 MVP

**Goal**: A turn-exhausted cycle whose lifecycle record advanced and whose work moved forward is classified as completed-but-unconverged rather than failed — the escalated redo does not run, and the next cycle starts at the same tier from the branch the truncated cycle pushed.

**Independent Test**: Drive the stage's cycle-outcome decision with a record of an agent run that ended because it ran out of turns, on a branch whose lifecycle record advanced and whose work moved forward, and confirm the decision is "completed, did not converge" — the next cycle is started at the ordinary tier and no escalated redo of the same cycle is run.

### Implementation for User Story 1

- [X] T002 [US1] Rewrite "Read back cycle outcome"'s `run:` block in `.github/workflows/implement.yml` (lines 878-926) per research.md D1-D4 and contracts/implement-cycle-outcome.md's `outcome` section:
  - Add a new env input, `VERDICT: ${{ steps.cycle-verdict.outputs.verdict }}` (already computed upstream by "Compute agent run verdict (cycle)", `implement.yml:798-804` — no new agent turn, no new parse of the transcript).
  - Keep the existing `advanced` check (`CYCLE_RESULT == "success"` and `spec-meta.json` on `origin/<branch>` reads `stage=implement, iteration=$ITERATION`) but broaden the entry condition so it also runs when `VERDICT == "exhausted"` (today's block only enters this check when `CYCLE_RESULT = "success"`; an exhausted run's `CYCLE_RESULT` is `failure`, forced there by "Fail loud on non-healthy agent verdict (cycle)", `implement.yml:820-828`).
  - Add the two-arm progress test (research.md D3, data-model.md "Progress evidence"), evaluated only when `VERDICT == "exhausted"` and the lifecycle record advanced: **Arm A** — count `- [x]`/`- [X]` lines in `$SPEC_DIR/tasks.md` at `BASE_SHA` (`steps.base.outputs.base-sha`, default 0 if the file did not exist there) versus the same file at `origin/${SPEC_PREFIX}$SLUG` tip; progress if the tip's count is higher. **Arm B** — `git diff --name-only "$BASE_SHA..origin/${SPEC_PREFIX}$SLUG" -- . ":(exclude)$SPEC_DIR/**"` non-empty. Progress is Arm A OR Arm B. Because `spec-meta.json` lives inside `$SPEC_DIR` and is not `tasks.md`, the lifecycle-record advance itself satisfies neither arm (FR-004a) — no separate SHA-exclusion logic is needed.
  - Produce exactly one of the three reachable `(ok, truncated)` pairs (FR-001, research.md D2): (1) `CYCLE_RESULT == "success"` AND `VERDICT != "exhausted"` AND advanced → `ok=true`, `truncated=false` — today's completed path, byte-for-byte unchanged, including the existing convergence scan (lines 909-918) for `converged`. (2) `VERDICT == "exhausted"` AND advanced AND progress → `ok=true`, `truncated=true`, and `converged=false` set directly **without running the convergence scan at all** (research.md D4 — never run the scan and then override a `true` result; there must be no intermediate `converged=true` value ever assigned on this path). (3) Everything else (advance failed, or `VERDICT == "exhausted"` with no progress, or any other non-success/non-exhausted shape) → `ok=false`, `truncated=false` — today's failed path, with `reason` populated the same way it is today.
  - Add the new `truncated` output (`"true"`/`"false"`) alongside the existing `ok`/`converged`/`reason`/`remaining`.
  - Do not touch the retry step's gate condition (`implement.yml:962`, `steps.outcome.outputs.ok == 'false'`) or the `stalled` job's gate (`implement.yml:1494`, `needs.implement.outputs.final-ok == 'false'`) — both already stop firing for a truncated cycle for free because it collapses onto `ok=true` (FR-006, FR-009).

**Checkpoint**: "Read back cycle outcome" classifies truncated-with-progress cycles as `ok=true, truncated=true, converged=false` without touching either downstream gate's condition text. Not yet provable without T003.

- [X] T003 [P] [US1] Create `.github/scripts/verify-truncated-cycle-carry-forward.py` (contracts/truncated-cycle-coverage.md), following `verify-stall-restart-runbook.py`'s (Gate 14) established shape: `use_utf8_stdout()`, `resolve_bash()`, `ensure_jq()`, a real git repository plus a local bare remote per scenario (`make_workspace`-style, torn down with the rest of the temp directory) so the step's git reads execute for real, and `find_step()`/`run_step()`/`parse_github_output()` to extract and execute "Read back cycle outcome"'s real, unmutated `run:` text directly out of `implement.yml` (no second copy), with `VERDICT`/`CYCLE_RESULT`/`BASE_SHA`/etc. supplied as env vars standing in for what the upstream verdict step would have produced (Gate 14's existing model for testing one named step without re-running the whole job). Implement and assert this story's three scenarios (contracts/truncated-cycle-coverage.md's scenarios 1, 3, 4; US1 Acceptance Scenario 1; FR-004):
  - **Exhausted, Arm-A progress, no converge commit**: synthetic history has one commit ticking a `tasks.md` checkbox plus the lifecycle-record-advance commit, `VERDICT=exhausted`. Assert `ok=true`, `truncated=true`, `converged=false`.
  - **Arm-A-only progress**: same shape (Arm A alone is sufficient — FR-004). Assert `ok=true`, `truncated=true`.
  - **Arm-B-only progress**: a file changed outside `$SPEC_DIR` plus the advance commit, `tasks.md` unchanged, `VERDICT=exhausted`. Assert `ok=true`, `truncated=true` (Arm B alone is sufficient).
  For each of these three, also assert that the retry step's real, unmutated gate condition text (`steps.outcome.outputs.ok == 'false'`, extracted via `find_step()`/inspected directly from `implement.yml`) evaluates false against the produced `ok=true` — i.e. no escalated retry would fire (SC-001, SC-002). Each assertion failure must print scenario name, expected vs. actual, and captured stdout/stderr, matching every other `verify-*.py` gate's convention. Exit 0 iff every scenario in the script (including those later tasks add) passes; non-zero otherwise. This task's own scenarios will not pass until T002 lands.

**Depends on**: T003's scaffolding can be drafted in parallel with T002; its scenario assertions only pass once T002 lands.

**Checkpoint**: User Story 1 is independently testable — `python3 .github/scripts/verify-truncated-cycle-carry-forward.py` passes its three scenarios, proving a turn-exhausted cycle with progress carries forward without an escalated redo.

---

## Phase 4: User Story 2 - An unfinished feature is never handed to finalization as converged (Priority: P1)

**Goal**: A truncated cycle's convergence answer is always "not converged," regardless of whether a `converge:` commit happens to be present on the branch — the absence of that commit is never read as evidence of convergence for a run that was cut off.

**Independent Test**: Drive the cycle-outcome decision with a record of a turn-exhausted run on a branch that carries **no** convergence commit, and confirm the computed convergence answer is "not converged." A test that cannot distinguish "no convergence commit because nothing remained" from "no convergence commit because the run was cut off" does not satisfy this story.

### Implementation for User Story 2

- [X] T004 [US2] Extend `.github/scripts/verify-truncated-cycle-carry-forward.py` (T003) with the scenario US2's own bar requires — one that a naive "converged = absence of a converge commit" implementation would get wrong in the *other* direction (US2 Acceptance Scenario 5, spec Edge Case "cut off after its convergence pass ran"): synthetic history for the Arm-A-progress scenario **plus a `converge:`-prefixed commit touching `tasks.md`** (i.e. a convergence commit **is** present), `VERDICT=exhausted`. Assert `truncated=true` and — critically — `converged=false` still, proving the scan is skipped entirely rather than run and overridden (research.md D4; a naive flip that runs the scan unconditionally would compute `converged=true` here, since a converge commit is present). Also assert, on the existing scenario 6 (normal successful cycle, `VERDICT=healthy`) once added by T003/later tasks, that `converged` is still derived from the existing converge-commit scan unaffected — the special case applies only to runs that were cut off (US2 Acceptance Scenario 4).

**Depends on**: T004 depends on T002 (the forced-false logic it asserts on) and T003 (the harness).

**Checkpoint**: SC-003 holds — zero truncated-and-cut-off runs are ever reported converged across the coverage, including the specific case a naive implementation gets wrong.

---

## Phase 5: User Story 3 - A truncated cycle that achieved nothing still gets escalated (Priority: P1)

**Goal**: A cycle that exhausts its turn budget without moving the feature forward — including one whose only landed change is its own lifecycle-record advance — is not carried forward; it takes today's escalated-redo path unchanged.

**Independent Test**: Drive the cycle-outcome decision with a record of a turn-exhausted run on a branch that did **not** move the feature forward, and confirm the escalated redo of the same iteration runs, exactly as it does today.

### Implementation for User Story 3

- [X] T005 [US3] Extend `.github/scripts/verify-truncated-cycle-carry-forward.py` with contracts/truncated-cycle-coverage.md's scenario 2 (US3 Acceptance Scenarios 1-3, FR-004a, spec Edge Case "only commit is its own lifecycle bookkeeping"): synthetic history has **only** the lifecycle-record-advance commit (`spec-meta.json` moved to `stage=implement, iteration=$ITERATION`) — no `tasks.md` checkbox newly ticked, no file outside `$SPEC_DIR` changed — `VERDICT=exhausted`. Assert `ok=false`, `truncated=false`: the lifecycle-record advance is a precondition of carry-forward, not evidence of progress, so this cycle fails both arms and takes today's failed path exactly as it does now. Also assert the retry step's real gate condition text evaluates true against this `ok=false` output (the escalated redo fires, unchanged) — US3's explicit bar that a test unable to tell "escalates" from "carries forward" does not satisfy this story.

**Depends on**: T005 depends on T002 and T003.

**Checkpoint**: SC-004 holds — a no-progress truncated cycle still escalates on its first occurrence rather than being carried forward to burn the whole iteration budget. All three P1 stories (the MVP) are now independently testable.

---

## Phase 6: User Story 4 - A truncated top-tier cycle no longer strands its work (Priority: P2)

**Goal**: When the escalated retry itself runs out of turns with progress, it is classified and carried forward by the identical rule, measured against where the *retry* started — not stranded in `stalled` the way today's guard-skip does.

**Independent Test**: Drive the cycle-outcome decision with a record of a turn-exhausted run that made progress and whose tier is already the escalation tier, and confirm the next cycle is started rather than the run being marked stalled.

### Implementation for User Story 4

- [X] T006 [US4] Add a new step, "Record retry base SHA," to `.github/workflows/implement.yml`, inserted immediately before "Implement and converge (retry at escalation model)" (`implement.yml:957`), with the identical gate condition as that step (`implement.yml:947-964`). Records `origin/${SPEC_PREFIX}$SLUG`'s current tip as a new `base-sha` output — the same shape as the existing "Record base SHA" step (`implement.yml:613-616`), but scoped to wherever the primary attempt's push left the branch, not the original pre-primary-cycle base (research.md D7).

- [X] T007 [US4] Rewrite "Read back retry outcome"'s `run:` block in `.github/workflows/implement.yml` (lines 1146-1196) with the same treatment T002 gave "Read back cycle outcome" (research.md D7, FR-016 — "classified by the same rules as any other cycle"): add `VERDICT: ${{ steps.retry-verdict.outputs.verdict }}` as a new env input (already computed by "Compute agent run verdict (retry)", `implement.yml:1083-1089`); broaden the advance check to also enter when `VERDICT == "exhausted"`; add the identical two-arm progress test, but measured against **T006's new retry `base-sha` output**, not `steps.base.outputs.base-sha` (measuring against the original base would let the retry inherit the primary attempt's own partial progress even if the retry itself achieved nothing — exactly the no-progress failure mode this feature must not let happen at the escalation tier, since there is nowhere further to escalate to); produce the same three `(ok, truncated)` outcomes with `converged` forced `false` (scan skipped) on the truncated path; add the new `truncated` output.

- [X] T008 [US4] Add a `truncated` output to "Consolidate final outcome" in `.github/workflows/implement.yml` (lines 1201-1230), selected from `retry-outcome`'s or `outcome`'s value using the exact same `RETRY_RAN` ternary already governing `ok`/`converged`/`remaining`/`tier` (lines 1217-1221) — one more field added to the existing selection pattern, no new selection logic.

- [X] T009 [P] [US4] Extend `.github/scripts/verify-truncated-cycle-carry-forward.py` with contracts/truncated-cycle-coverage.md's "Retry-truncation (FR-016)" assertion: drive "Read back retry outcome" the same way as User Story 1's scenarios but with the synthetic history's progress measured from a base reflecting where the primary attempt's own partial push left the branch (not the original `BASE_SHA`), `VERDICT=exhausted` on the retry's own verdict. Assert `ok=true`, `truncated=true` on the retry-outcome step, and — separately — that "Consolidate final outcome" selects the retry's `truncated` value (not the primary's) when `RETRY_RAN=true`.

**Depends on**: T007 depends on T006 (the new base-sha output it reads). T008 depends on T002 and T007 (both step outputs it selects between). T009 depends on T006, T007, T008, and T003 (the harness).

**Checkpoint**: SC-005 holds — a truncated cycle already on the escalation tier is carried forward like any other, never marked stalled, and "Consolidate final outcome" correctly threads the retry's own classification.

---

## Phase 7: User Story 5 - Repeated truncation is counted and visible, not silent (Priority: P2)

**Goal**: Each truncated cycle is reported to the lifecycle issue in terms that name turn exhaustion and carry a consecutive-truncation count, which resets on any completed or failed cycle — visible at every tier, including the escalation tier.

**Independent Test**: Drive a sequence of cycles that each truncate with progress, and confirm each is reported to the lifecycle issue as a truncation carrying an increasing consecutive-truncation count, and that a completed or failed cycle in between resets that count.

### Implementation for User Story 5

- [X] T010 [US5] Add a new step, "Record truncated-cycle count," to `.github/workflows/implement.yml`, inserted immediately after "Consolidate final outcome" (`implement.yml:1201-1230`) and before "Flip stage label (first cycle)" (`implement.yml:1401`), gated on `steps.lifecycle-gate.outputs.is-open == 'true' && steps.guard.outputs.skip != 'true'` (runs on every non-skipped consolidated outcome, including a genuine failure that goes on to `stalled` — research.md D5, so the count resets across a stall-then-manual-restart boundary too). Reads the current `truncated_count` from `origin/<branch>`'s `spec-meta.json` (`jq -r '.truncated_count // 0'`, default 0 for every spec created before this feature), computes `new_count = steps.final.outputs.truncated == "true" ? current + 1 : 0`, and — only when `new_count != current` — patches `spec-meta.json` (`jq '.truncated_count = $new_count'`), commits (message `"implement: record truncated cycle (consecutive count=$new_count)"` when incrementing, `"implement: reset truncated-cycle count"` when resetting), and pushes — mirroring the `stalled` job's existing no-agent jq-patch-commit-push shape (`implement.yml:1580-1600`). New output: `count`.

- [X] T011 [US5] Extend "Dispatch next step" in `.github/workflows/implement.yml` (lines 1422-1485) with two new env inputs — `TRUNCATED: ${{ steps.final.outputs.truncated }}`, `TRUNCATED_COUNT: ${{ steps.record-truncation.outputs.count }}` — and two new message branches, inserted **ahead of** the existing `CONVERGED != true` branches (data-model.md "Lifecycle issue report" table, research.md D6) so a truncated cycle never falls into the generic "completed without converging" wording:
  - Not at cap: a body naming that the cycle ran out of its turn budget, stating work already landed on the branch, that the next cycle continues on the same tier, and the consecutive-truncation count — never the word "failed," never presenting an empty remaining-work block (FR-013, FR-015).
  - At cap: a body stating the iteration cap was reached and the last cycle ran out of turns **before it could assess what remained** — replacing the `$REMAINING`-block body (which a truncated cycle's missing `converge:` commit would otherwise leave empty) with this explanation, and still dispatching `$NEXT_WORKFLOW` with `converged=false` exactly as today's at-cap branch does (FR-014).
  Leave the existing `CONVERGED == 'true'` branch and the non-truncated `CONVERGED != 'true'` branches (both below-cap and at-cap) completely unchanged — reached exactly as today whenever `TRUNCATED == 'false'`.

- [X] T012 [P] [US5] Extend `.github/scripts/verify-truncated-cycle-carry-forward.py` with contracts/truncated-cycle-coverage.md's "Additional assertions":
  - **Counter (FR-011)**: starting a synthetic `spec-meta.json` at `truncated_count: 1`, run "Record truncated-cycle count" against a truncated outcome and assert it ends at `2`; run it again against a failed or a completed outcome and assert it resets to `0`; run a second consecutive truncated outcome against the resulting state and assert it reaches `3`.
  - **Below-cap reporting (FR-013, FR-015)**: run "Dispatch next step" with `TRUNCATED='true'`, below cap, and assert the composed body does not contain the word "failed" and does contain the consecutive-truncation count.
  - **At-cap reporting (FR-014)**: run "Dispatch next step" with `ITERATION == MAX` and `TRUNCATED='true'`, and assert the composed body contains wording that the last cycle ran out of turns before it could assess what remained, and does **not** contain an empty fenced `remaining` block.

**Depends on**: T010 depends on T002 and T008 (`steps.final.outputs.truncated`, the field it reads). T011 depends on T010 (`steps.record-truncation.outputs.count`). T012 depends on T003, T010, and T011.

**Checkpoint**: SC-007/SC-008 hold — a reader of the lifecycle issue alone can tell a truncated cycle from a failed one and from a normally unconverged one, and can see the consecutive-truncation count, without opening a run log.

---

## Phase 8: User Story 6 - The decision is proven against recorded runs, not merely shipped (Priority: P2)

**Goal**: Removing the forced not-converged answer, removing the no-progress guard, removing either arm of the progress test, counting the lifecycle-record advance as progress, or widening truncation to cover ordinary failures each independently fail a check — and the coverage's own presence in the gate registry is itself checked.

**Independent Test**: Run the coverage against a synthetic record of a turn-exhausted run with no convergence commit and confirm it asserts "not converged"; then remove the forced answer from the shipped decision and confirm a check fails.

### Implementation for User Story 6

- [X] T013 [US6] Add FR-019's six required mutations to `.github/scripts/verify-truncated-cycle-carry-forward.py` (research.md D8, contracts/truncated-cycle-coverage.md's "Required mutations" table), each applied to a deep copy of the real step text extracted by `find_step()` — never to the file on disk — using the `if mutated == steps: raise` self-check `verify-stall-restart-runbook.py:345` establishes, so a mutation helper that silently fails to apply is itself caught rather than producing a false pass:
  1. **Remove the forced `converged=false`** (let the converge-commit scan run unconditionally and set its result without ever forcing false on the truncated path). Assert the T004 (converge-commit-present) scenario now reports `converged=true` where it must be `false`.
  2. **Remove the no-progress guard** (classify any `VERDICT == "exhausted"` + advanced run as `truncated` without checking either arm). Assert the T005 (only-the-advance-commit) scenario now reports `truncated=true` where it must be `false`.
  3. **Drop Arm A** (the task-checkbox count) from the progress test. Assert the Arm-A-only scenario (T003) now reports `truncated=false` where it must be `true`.
  4. **Drop Arm B** (the outside-spec-dir file change) from the progress test. Assert the Arm-B-only scenario (T003) now reports `truncated=false` where it must be `true`.
  5. **Count the lifecycle-record advance itself as progress** (e.g. treat "the branch tip moved" as sufficient). Assert the T005 (only-the-advance-commit) scenario now reports `truncated=true` where it must be `false` — the same failure mode the FR-004a exclusion prevents, caught by a different mutation than #2.
  6. **Widen `VERDICT == "exhausted"` to also match `VERDICT == "failed"`.** Assert an ordinary-failure scenario (`VERDICT=failed`, no relevant commits beyond `BASE_SHA`) now reports `ok=true`/`truncated=true` where it must be `false`/`false`.

- [X] T014 [US6] Add a reflexive check (FR-020) inside `.github/scripts/verify-truncated-cycle-carry-forward.py`: assert that a step whose name starts with `Gate 26` exists, is enabled (not `if: false`), and invokes this script by path in `.github/workflows/lint-workflows.yml` — mirroring Gate 25's own reflexive check (`specs/039-lifecycle-gate-retry`'s T008 mutation 4), so disabling or removing Gate 26 is caught by this script's own assertion about itself, not only by the general-purpose gate-wiring detector.

- [X] T015 [US6] Wire `.github/scripts/verify-truncated-cycle-carry-forward.py` into `.github/workflows/lint-workflows.yml`'s `lint` job as a single step named `Gate 26 — a turn-exhausted cycle is classified truncated only with positive evidence, and carried forward without ever reporting converged` (`run: python3 .github/scripts/verify-truncated-cycle-carry-forward.py`), placed immediately after Gate 25's step (`lint-workflows.yml:1729-1730`) — a single-step shape matching Gate 14/25's precedent (no separate self-test step; the mutation checks T013/T014 add live inside the script itself). Confirm `python3 .github/scripts/run-local-gates.py` (if present) and Gate 10's naming-convention discovery would pick it up automatically with no manifest edit.

**Depends on**: T013 depends on T002, T003, T004, T005, T007-T009, T010-T012 (mutates and re-runs every scenario those tasks establish). T014 and T015 depend on each other only loosely (T014's assertion needs T015's step to exist to pass, but can be written first and fail until T015 lands).

**Checkpoint**: `python3 .github/scripts/verify-truncated-cycle-carry-forward.py` fails on each of the six mutations and passes on the delivered feature; Gate 26 proves itself present in the registry, not only the composite logic. SC-009 holds.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Whole-feature validation once every story has landed.

- [X] T016 [P] Run quickstart.md's seven scenarios end to end: `python3 .github/scripts/verify-truncated-cycle-carry-forward.py` (Scenarios 1-3, 5), its retry-scenario assertions (Scenario 4's underlying check plus `grep -n "final-ok" .github/workflows/implement.yml` confirming the `stalled` job's gate condition text is unchanged), the counter/reporting assertions (Scenario 5), the by-hand mutation drill confirming a non-zero exit per mutation and exit 0 once reverted (Scenario 6), and the byte-for-byte diff of an ordinary-failure and a normal-successful-cycle scenario's `ok`/`converged`/`remaining` outputs against T001's captured pre-feature baseline (Scenario 7, FR-017/SC-006).
- [X] T017 [P] Confirm FR-021/FR-022/SC-010: diff `implement.yml`'s `workflow_call` `inputs:`/`outputs:` blocks against T001's pre-feature baseline (unchanged — no new input, output, or secret); confirm no edit to `wing-commander-5-implement.yml`, any other calling wrapper, or the `wing-commander-agent-verdict` composite; confirm no change to `max-turns`, `max-iterations`, or any turn-budget-ceiling default anywhere in this feature's diff.
- [X] T018 Run `actionlint` (with shellcheck) against `.github/workflows/implement.yml` and `.github/workflows/lint-workflows.yml`, and run `python3 .github/scripts/run-local-gates.py` if available in the executing environment, confirming every gate — including the new Gate 26 — passes cleanly against the repository as it stands after all six user stories land.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Empty — no blocking prerequisites beyond Setup.
- **User Stories (Phase 3-8)**: US1 (T002/T003) is the sole edit to "Read back cycle outcome" and the base of every later phase's coverage. US2 (Phase 4) and US3 (Phase 5) both extend the same script T003 creates, asserting different facets of T002's rewrite, and can proceed in either order once T002/T003 land. US4 (Phase 6) is independent production code (the retry path, T006-T008) but its coverage (T009) depends on the harness (T003). US5 (Phase 7) depends on US4's T008 (`steps.final.outputs.truncated`). US6 (Phase 8) depends on every earlier story's scenarios existing, since its mutations re-run them.
- **Polish (Phase 9)**: Depends on all six user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories — the MVP. Contains the only edit to "Read back cycle outcome" (T002).
- **User Story 2 (P1)**: Depends on User Story 1's T002 (the forced-false logic it asserts on) and T003 (the harness).
- **User Story 3 (P1)**: Depends on User Story 1's T002 and T003.
- **User Story 4 (P2)**: No dependency on US2/US3 for its production code (T006-T008 extend the retry path independently of the primary-cycle progress test's specific scenarios), but its coverage task (T009) depends on T003's harness existing.
- **User Story 5 (P2)**: Depends on User Story 4's T008 (`steps.final.outputs.truncated`) and User Story 1's T002.
- **User Story 6 (P2)**: Depends on User Stories 1 through 5 (mutates and re-runs every scenario they establish) and User Story 1's eventual Gate wiring point (T015 itself, for its own reflexive check).

### Within Each User Story

- T002 (the primary-cycle rewrite) must land before any scenario asserting on it can genuinely pass, even though T003's harness scaffolding can be drafted first.
- Story complete before moving to the next priority, per the Implementation Strategy below.

### Parallel Opportunities

- T003 (new coverage script scaffolding) can be drafted in parallel with T002 (the step rewrite it will validate), marked `[P]` — though its scenarios only pass once T002 lands.
- T009 (US4 coverage) and T012 (US5 coverage) touch the same file as T003/T004/T005 additively and are marked `[P]` against unrelated tasks in other phases, but are sequential edits relative to same-file tasks in their own phase.
- T016 and T017 (Polish) touch different concerns (behavioral quickstart validation vs. contract-surface diffing) and are marked `[P]`.

---

## Parallel Example: User Story 1

```bash
# T002 and T003 can start together once Setup completes:
Task: "Rewrite the three-way classification in implement.yml's 'Read back cycle outcome' (T002)"
Task: "Scaffold verify-truncated-cycle-carry-forward.py's harness and first three scenarios (T003)"
# T003's own scenario assertions will not pass until T002 lands.
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 3: User Story 1 — this alone stops every escalated redo triggered by turn exhaustion with progress (SC-001, SC-002), the single largest cost line in the source request's measurement.
3. **STOP and VALIDATE**: Run `python3 .github/scripts/verify-truncated-cycle-carry-forward.py`; confirm its three US1 scenarios pass against the real shipped step.

### Recommended Scope: All Three P1 Stories

User Story 1 alone is unsafe to ship on its own — R1 in spec.md is explicit that a naive version of this change inverts the convergence signal and hands an unbuilt feature to finalization as done. User Story 2 (forced not-converged) and User Story 3 (the no-progress guard) are the two preconditions that make User Story 1 safe rather than merely fast. All three are P1 for that reason; the underlying production code (T002) already implements all three together — the phases exist to prove each facet independently, not to defer any of them.

### Incremental Delivery

1. Complete Setup → Gate 26 numbering confirmed free, baseline captured.
2. Add User Story 1 → validate via `verify-truncated-cycle-carry-forward.py`'s first three scenarios → the core defect (cold Opus redos) is fixed.
3. Add User Story 2 → validate via the converge-commit-present scenario → the blocking risk (R1) is proven closed.
4. Add User Story 3 → validate via the no-progress scenario → the escalation guard is proven to still fire.
5. Add User Story 4 → validate via the retry-path scenario → a truncated top-tier/retry cycle no longer strands.
6. Add User Story 5 → validate via the counter and reporting assertions → repeated truncation is visible on the lifecycle issue.
7. Add User Story 6 → validate via the six mutations and the reflexive check → the whole proof is wired into the gate registry.
8. Phase 9 Polish → whole-feature sweep.

---

## Notes

- `[P]` tasks touch different files, or the same file in a way with no ordering dependency on other unfinished tasks in the same phase.
- `[Story]` label maps each task to its user story for traceability.
- T002, T006, T007, T008, T010, and T011 are the only tasks that edit `.github/workflows/implement.yml` — every other task builds or extends `verify-truncated-cycle-carry-forward.py`, wires it into `lint-workflows.yml` (T015), or validates the result.
- This feature does not touch `implement.yml`'s declared `workflow_call` inputs/outputs, `wing-commander-5-implement.yml`, any other calling wrapper, the `wing-commander-agent-verdict` composite, `max-turns`, `max-iterations`, or the runaway turn-budget ceiling (FR-021, FR-022, Out of Scope) — no task above should introduce such an edit.
- Removing T002's forced-false logic, its no-progress guard, either arm of its progress test, or widening its `VERDICT == "exhausted"` check must each independently fail T013's mutation checks, not merely reduce a test count — this is the FR-019/US6 bar the whole story exists to enforce.

## Maintainer Feedback

- [ ] Persist the tier a truncated cycle actually ran on (ordinary or `inputs.escalation-model`) into a `spec-meta.json` field written alongside the existing truncated-cycle bookkeeping commit (`implement.yml`'s "Record truncated-cycle count" step, ~line 1515).
- [ ] At cycle start, when that field marks the carried tier as the escalation tier, use `inputs.escalation-model` for the cycle instead of `inputs.model` — no new `workflow_dispatch` input on the self-workflow (FR-021, FR-007).
- [ ] Rewrite Gate 26's `check_final_selects_retry_truncated` scenario in `verify-truncated-cycle-carry-forward.py` to assert the tier the *next* cycle will actually use (reading the persisted field / effective model), not just the printed lifecycle-issue text.
- [ ] Add a mutation that removes the carry-over write/read and confirm it fails the new assertion (FR-019 shape).

## Maintainer Feedback

- [ ] Add a scenario to `verify-truncated-cycle-carry-forward.py` for the primary read-back ("Read back cycle outcome") with `CYCLE_RESULT=success` and `VERDICT=exhausted` set together (with qualifying progress); assert `truncated=true`, `converged=false`.
- [ ] Add the equivalent scenario for the retry read-back ("Read back retry outcome").
- [ ] Add a mutation that swaps the order of the `VERDICT == "exhausted"` / `CYCLE_RESULT == "success"` checks in both steps and confirm it fails the new assertions (FR-019 shape).

## Maintainer Feedback

- [ ] Change `implement.yml`'s "Fail loud on non-healthy agent verdict (cycle)" (and its retry-path mirror) so that when the eventual classification is truncated, it emits `::notice::` or `::warning::` naming the truncation and the step stays green; keep `::error::` (and the red step) for the failed classification only. This likely requires deferring or re-deriving the annotation after "Read back cycle outcome" has classified the run, since verdict alone can't distinguish truncated from failed.
- [ ] Add a Gate 26 scenario asserting the annotation kind/step outcome for a truncated cycle is not `::error::`, and that a genuinely failed exhausted-with-no-progress cycle still gets `::error::` (FR-015, FR-013).

## Maintainer Feedback

- [ ] In `implement.yml`'s "Record truncated-cycle count" step, only emit the `count` output after the commit+push has actually succeeded (or verify the push landed before reporting the new value); on a persist failure, emit an explicit unknown/failed marker instead of a stale or empty count.
- [ ] In "Dispatch next step", when the persisted-count marker indicates failure, state in the lifecycle comment that the consecutive-truncation count could not be recorded, rather than printing an empty or wrong number.
- [ ] Add a Gate 26 scenario simulating a persist failure (e.g. push rejection) and asserting the lifecycle comment never renders an empty or unpersisted count (FR-011, FR-012, SC-007).

## Maintainer Feedback

- [ ] Rename this feature's gate from "Gate 26" to "Gate 30" in `lint-workflows.yml`'s step name and any nearby comment header.
- [ ] Update `verify-truncated-cycle-carry-forward.py`'s `GATE_PREFIX` constant (and any other Gate-26-specific text/docstrings) to "Gate 30".
- [ ] Update this spec's plan.md/tasks.md/contracts and any other docs referring to "Gate 26" for this feature to "Gate 30".
- [ ] Confirm no remaining collision: grep `lint-workflows.yml` for `Gate 30` before landing, and confirm the FR-020 reflexive self-check still matches only this feature's own step.
