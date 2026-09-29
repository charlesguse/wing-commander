---

description: "Task list template for feature implementation"
---

# Tasks: The Worked Example Outlives Its Code — Keeping spec-cross-reference's Structural Claim True

**Input**: Design documents from `/specs/089-skill-example-drift/`

**Prerequisites**: plan.md, spec.md, research.md (D1-D9), data-model.md (SkillClaim, JobClassification, WorkflowConcurrencyFact, DriftFinding, WaiverEntry), contracts/skill-drift-gate.md, contracts/skill-example-claim.md, quickstart.md

**Tests**: Not explicitly requested as a separate suite. This feature's own correctness proof is Gate 125's required `--self-test` mode (FR-007, SC-005, research.md D9) plus the real-tree/quickstart mutation walks — both are captured as tasks below because the contracts require them as shipped deliverables, not as an optional test layer.

**Organization**: Tasks are grouped by user story (spec.md's three, in priority order) so each can be implemented and verified independently once the shared extraction/comparison engine (Foundational) exists.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Tasks that edit `.github/scripts/verify-skill-board-loop-concurrency-claim.py` or `.claude/skills/spec-cross-reference/SKILL.md` are sequential relative to each other even across story phases, since they share one file — see Dependencies below.

## Path Conventions

Single project, CI-native automation — no `src/`/`tests/` split. All paths are repository-root-relative, per plan.md's Project Structure.

---

## Phase 1: Setup

**Purpose**: Create the two new tracked files Gate 125 and its waiver register live in, empty of logic.

- [x] T001 [P] Create `.github/scripts/skill-example-drift-waivers.json` shipping an empty `waivers` array, with a `$comment` header shaped like `.github/scripts/single-home-waivers.json`'s (name the check it registers for — `skill-board-loop-concurrency-claim` — and the stale-check-in-both-directions property) (research.md D2, data-model.md WaiverEntry)
- [x] T002 [P] Create `.github/scripts/verify-skill-board-loop-concurrency-claim.py` as a module skeleton: a docstring naming it as Gate 125 and stating its purpose (mirroring `.github/scripts/verify-concurrency-guarantee-statement.py`'s header shape), `REPO_ROOT`-relative path constants for the four inputs (`.claude/skills/spec-cross-reference/SKILL.md`, `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`, `.github/workflows/board-loop.yml`, `.github/scripts/skill-example-drift-waivers.json`), and a `--self-test` argparse flag with `run()`/`main()` stubs (contracts/skill-drift-gate.md "Inputs"). Note for whoever executes this task: 125 is the next free gate number as of this plan (research.md D1); if another spec's PR has claimed it first by the time this task runs, use the next free number instead and update this file's own docstring and the cross-references in SKILL.md (T009/T015) accordingly — a rebase mechanic, not a design change.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The extraction-and-comparison engine every user story depends on. No story's independent test can pass without this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`, implement `SkillClaim` extraction from `.claude/skills/spec-cross-reference/SKILL.md`: a bounded scan from the Over-rated example's anchor phrase to the next paragraph break, pulling the backtick-quoted `job_range_start`/`job_range_end` from the "`` `X` `` through `` `Y` ``"-shaped phrase (expected `select`/`readiness`), the `ordinary_group` token (expected `` `wing-commander-board-loop` ``), and the `directed_group` token (expected `` `wing-commander-board-loop-directed-proof` ``); a missing anchor or any missing token records a `subject-missing` `DriftFinding` rather than raising (data-model.md SkillClaim, research.md D3, contracts/skill-example-claim.md "Verification")
- [x] T004 In the same file, implement `JobClassification` extraction from `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`'s "Groups, per job" table: per row, `job`, `can_select_or_open_fix_pr`, `expected_group_ordinary`, `expected_group_directed` (or null where the table says "n/a"), `expected_cancel_in_progress` (always `false`); the table is read as-is, never re-derived from `board-loop.yml`'s own job names (data-model.md JobClassification, research.md D4)
- [x] T005 In the same file, implement `WorkflowConcurrencyFact` extraction from `.github/workflows/board-loop.yml`'s real `concurrency:` blocks (not the preceding comments, which Gate 101 already owns): per job, `group_literal`, `group_expression` (for `prove-gate`/`prove`'s conditional, matched structurally against the known `${{ (... directed-stage != '') && '...-directed-proof' || '...' }}` shape rather than a generic expression evaluator), `cancel_in_progress` (`null` when the job has no `concurrency:` block at all) (data-model.md WorkflowConcurrencyFact, research.md D5)
- [x] T006 In the same file, implement the `DriftFinding` comparison (contracts/skill-drift-gate.md "Algorithm" steps 4-6): for every select/fix-PR-capable `JobClassification` row, compare its `WorkflowConcurrencyFact` against the expected group and `cancel_in_progress`, emitting `job-missing-from-group`, `cancel-in-progress-mismatch`, or `directed-group-mismatch` per mismatch; for every non-capable job (including any job the table does not mention, e.g. `resolve-model`), confirm it sits in neither `SkillClaim.ordinary_group` nor `SkillClaim.directed_group`, emitting `unexpected-job-in-group` on a hit; compare `SkillClaim.job_range_start`/`job_range_end` against the actual first/last capable job in `board-loop.yml`'s own job order, emitting `job-range-mismatch` on any difference

**Checkpoint**: The script can compute the full `DriftFinding` set for the real tree in memory. No CLI output or exit-code wiring yet — that starts in US1.

---

## Phase 3: User Story 1 - The reviewer refutes a race with a rule that still exists (Priority: P1) 🎯 MVP

**Goal**: A reviewer following the Over-rated example reaches the verdict that matches `board-loop.yml`'s actual shape, on both the current tree and a mutated one.

**Independent Test**: Run the gate against `main`'s tree (passes) and against a scratch mutation of `board-loop.yml` that removes a selecting job's `concurrency:` block (fails, naming the job) — quickstart.md §2.

### Implementation for User Story 1

- [x] T007 [US1] In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`, format each `DriftFinding` into the FR-006 failure message shape (contracts/skill-drift-gate.md "Failure message shape"): names the `<property>`, the `<job>`, both `SKILL.md:<line>` and `board-loop.yml:<line>` locations, `<expected>`/`<actual>`, and the waive-or-fix instruction
- [x] T008 [US1] In the same file, wire `run()`/`main()` to read the three source files (SKILL.md, concurrency-groups.md, board-loop.yml) via T003-T005, compute the `DriftFinding` set via T006, print each failure line via T007, print an `[ok]` line per currently-passing checked property, and exit non-zero iff any finding remains (waiver filtering is out of scope here — added in US2's T011); any of the three files being missing or unreadable is itself a loud `subject-missing` finding, never a silent skip (contracts/skill-drift-gate.md "Algorithm" step 8 minus waivers, and "Inputs")
- [ ] T009 [US1] BLOCKED (implement-stage cycle 1, #489/#675): the implement-stage agent's write permission does not extend to `.claude/`, confirmed by two denied Edit attempts against `.claude/skills/spec-cross-reference/SKILL.md` this cycle — same restriction FR-013 already documents for the board-loop.yml drift case, here blocking a wording *addition* rather than a drift fix, so the waiver file does not apply (nothing in the gate's own checked properties currently diverges over this). Needs a human session with `.claude/` write access. In `.claude/skills/spec-cross-reference/SKILL.md`, add the queuing/non-cancelling clause to the Over-rated example's existing paragraph (research.md D6, contracts/skill-example-claim.md item 4): state that a second run in the same group queues rather than racing or cancelling — a `queue`/`cancel` word in the same paragraph as the existing three backtick group/job tokens — without restating `concurrency-groups.md`'s full per-job table
- [x] T010 [US1] Run `python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py` against the real tree (expect pass) and then, on a scratch branch, against `.github/workflows/board-loop.yml` with one selecting job's (e.g. `review`'s) `concurrency:` block removed (expect fail, naming the job and both file locations), per quickstart.md §2; revert the scratch mutation afterward

**Checkpoint**: User Story 1 is independently functional — a reviewer or triager can invoke Gate 125 directly and get a trustworthy pass/fail against whatever `board-loop.yml` is checked out.

---

## Phase 4: User Story 2 - Changing the workflow surfaces the doc it invalidates (Priority: P2)

**Goal**: The PR-time gate suite blocks a `board-loop.yml` concurrency change that outdates the skill's claim, unless covered by a waiver — and the waiver itself is stale-checked in both directions.

**Independent Test**: Mutate `board-loop.yml`'s concurrency block on a scratch branch, run the local gate suite, observe a failure naming both the skill line and the workflow line; add a waiver entry and observe a pass; close the divergence and observe the same waiver entry now fail as stale — quickstart.md §3.

### Implementation for User Story 2

- [ ] T011 [US2] In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`, implement `WaiverEntry` loading and the stale-check pass (contracts/skill-drift-gate.md "Algorithm" step 7, data-model.md WaiverEntry, research.md D7): read `.github/scripts/skill-example-drift-waivers.json`, mark any `DriftFinding` whose `{property, job}` pair matches a `WaiverEntry` as waived (still printed, as `waived: <property> (<job>), see #<issue>`, not counted toward the exit code), and emit a blocking stale-waiver failure for any `WaiverEntry` whose `{property, job}` pair matches no current finding
- [ ] T012 [US2] Register Gate 125 in `.github/workflows/lint-workflows.yml`'s existing PR-time lint job, immediately after Gate 124's block: a `Gate 125` step (`python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py`) and a `Gate 125 self-test` step (same command plus `--self-test`), both `if: "!cancelled()"` (contracts/skill-drift-gate.md "Wiring", FR-010)
- [ ] T013 [US2] In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`, implement `--self-test` fixtures for the waiver stale-check in both directions (research.md D9's waiver bullet, contracts/skill-drift-gate.md "Waiver interaction"): a synthetic fixture with `fix` missing from the ordinary group and an empty waiver set fails; the same fixture plus a matching `WaiverEntry{property: "job-missing-from-group", job: "fix", issue: "#1"}` passes and prints the `waived:` line; reverting the fixture to match while leaving that same entry in place fails, naming the entry as stale
- [ ] T014 [US2] On a scratch branch, run quickstart.md §3 end-to-end against the real tree: remove `review`'s `concurrency:` block from `.github/workflows/board-loop.yml`, confirm `python .github/scripts/run-local-gates.py` fails naming both `SKILL.md` and `board-loop.yml`; add a matching entry to `.github/scripts/skill-example-drift-waivers.json`, confirm the suite passes; restore `review`'s block with the waiver entry still present, confirm the suite now fails on the stale entry; discard the scratch mutation and the waiver entry afterward

**Checkpoint**: User Stories 1 and 2 both independently functional — an ordinary PR is blocked by real drift, and a PR that cannot edit `.claude/` (the implement-stage case, FR-013) can still land behind a waiver.

---

## Phase 5: User Story 3 - A triager can date the claim (Priority: P3)

**Goal**: Someone meeting a "the skill is stale" report settles it in one command, with no history of spec 060.

**Independent Test**: Run Gate 125 bare, with no other file read. A clean exit with `[ok]` lines per checked property is "current"; a non-zero exit with the FR-006 message is "stale, here is exactly what diverged" — quickstart.md §4.

### Implementation for User Story 3

- [ ] T015 [US3] In `.claude/skills/spec-cross-reference/SKILL.md`, add the Gate-125-naming pointer sentence immediately after the Over-rated example's paragraph (research.md D8 item 1, contracts/skill-example-claim.md item 5): names the script's literal path `.github/scripts/verify-skill-board-loop-concurrency-claim.py` within two paragraphs of the anchor, and tells the reader to run it to settle currency before trusting the example to downgrade a finding
- [ ] T016 [US3] In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`, extend the `[ok]` pass output (built in T008) to name each property it checked and that it currently holds, mirroring `verify-concurrency-guarantee-statement.py`'s `[ok] ...` lines (research.md D8 item 2), so a triager reads which properties were verified without reading the script's source
- [ ] T017 [US3] Run quickstart.md §4 against both the real tree and one of US2's scratch mutation states (T014's setup, reproduced and reverted again), confirming the command's output alone settles staleness with no other file or issue history read

**Checkpoint**: All three user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Whole-suite and whole-feature validation spanning all three stories.

- [ ] T018 [P] Run `python .github/scripts/run-local-gates.py` and confirm a fully green suite, including Gate 125's bare run and its `--self-test` step, against the real tree (SC-005, quickstart.md §1)
- [ ] T019 [P] Confirm SC-006 (no second tracked copy of the claim): grep the tree for the four backtick tokens and the queuing-clause wording added in T009, and confirm they appear only in `.claude/skills/spec-cross-reference/SKILL.md`, never duplicated into `.github/scripts/verify-skill-board-loop-concurrency-claim.py`'s own comments or elsewhere
- [ ] T020 Walk quickstart.md §5's edge cases against `.github/scripts/verify-skill-board-loop-concurrency-claim.py`: point the script's `board-loop.yml` constant at a nonexistent path on a scratch branch → fails with `subject-missing`, never a silent pass; reflow the Over-rated paragraph's prose or fix a typo in `.claude/skills/spec-cross-reference/SKILL.md` without touching any backtick token or the queuing clause → still passes (FR-009); confirm the untracked `.wing-commander-pipeline/` checkout (if present locally) is never opened by the script

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001 and T002 touch different files and can run in parallel.
- **Foundational (Phase 2)**: Depends on T002 (the script must exist to extend). T003-T006 all edit the same file sequentially (each function builds on the last existing in the module) — BLOCKS every user story.
- **User Stories (Phase 3-5)**: All depend on Foundational (Phase 2) completion.
  - US1 (T007-T010) can start immediately after Foundational.
  - US2 (T011-T014) can start immediately after Foundational, but T012's wiring step is most meaningfully tested once T008's bare-invocation exit code (US1) exists — sequence US1 before US2 in practice even though nothing but the shared files strictly forces it.
  - US3 (T015-T017) depends on T009 (US1's queuing clause) already being present in SKILL.md, since T015's pointer sentence is added to the same paragraph — sequence US1 before US3.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Each User Story

- US1: T007 and T008 are sequential (same file, T008 calls T007's formatter). T009 (SKILL.md) has no code dependency on T007/T008 and could be done in either order, but is listed after them for narrative continuity with T010, which exercises the finished script. T010 depends on T008.
- US2: T011 depends on Foundational's T006 (needs a `DriftFinding` set to filter). T012 depends on T008 (needs a working bare invocation to wire into CI) and T011 (the wired self-test step must find waiver logic to exercise). T013 depends on T011. T014 depends on T011-T013.
- US3: T015 depends on T009 (same SKILL.md paragraph). T016 depends on T008 (extends its `[ok]` output). T017 depends on T015 and T016.

### Same-File Sequencing (overrides any apparent [P] opportunity)

- `.github/scripts/verify-skill-board-loop-concurrency-claim.py`: T002 → T003 → T004 → T005 → T006 → T007 → T008 → T011 → T013 → T016, strictly sequential.
- `.claude/skills/spec-cross-reference/SKILL.md`: T009 → T015, strictly sequential.

### Parallel Opportunities

- T001 and T002 (different files, Setup).
- T018 and T019 (both read-only verification against the finished tree, no shared mutation).

---

## Parallel Example: Setup

```bash
# Launch both Setup tasks together — different files, no dependency:
Task: "Create .github/scripts/skill-example-drift-waivers.json shipping an empty waivers array"
Task: "Create .github/scripts/verify-skill-board-loop-concurrency-claim.py module skeleton"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002).
2. Complete Phase 2: Foundational (T003-T006) — CRITICAL, blocks every story.
3. Complete Phase 3: User Story 1 (T007-T010).
4. **STOP and VALIDATE**: Gate 125 runs by hand, passes against `main`, fails against a scratch mutation naming the right job and both file locations. This alone satisfies the skill's "whole purpose" (spec.md's own framing of P1).

### Incremental Delivery

1. Setup + Foundational → the extraction/comparison engine exists but is silent.
2. Add User Story 1 → a reviewer can run Gate 125 by hand and trust its verdict (MVP).
3. Add User Story 2 → the same check becomes CI-blocking, with a waiver escape hatch for the implement-stage case.
4. Add User Story 3 → a triager settles staleness in one command with no spec-060 history.
5. Polish → whole-suite green, no duplicated claim, edge cases demonstrated.

### Parallel Team Strategy

Because nearly every task shares one of two files (the gate script or SKILL.md), this feature does not parallelize well across multiple implementers beyond the two Setup tasks and the two Polish read-only checks — a single implementer working the phases in order is the realistic path, not a team split.
