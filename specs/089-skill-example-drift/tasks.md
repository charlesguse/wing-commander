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
- [x] T002 [P] Create `.github/scripts/verify-skill-board-loop-concurrency-claim.py` as a module skeleton: a docstring naming it as Gate 129 and stating its purpose (mirroring `.github/scripts/verify-concurrency-guarantee-statement.py`'s header shape), `REPO_ROOT`-relative path constants for the four inputs (`.claude/skills/spec-cross-reference/SKILL.md`, `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`, `.github/workflows/board-loop.yml`, `.github/scripts/skill-example-drift-waivers.json`), and a `--self-test` argparse flag with `run()`/`main()` stubs (contracts/skill-drift-gate.md "Inputs"). Note for whoever executes this task: 125 is the next free gate number as of this plan (research.md D1); if another spec's PR has claimed it first by the time this task runs, use the next free number instead and update this file's own docstring and the cross-references in SKILL.md (T009/T015) accordingly — a rebase mechanic, not a design change.

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
- [x] T009 [US1] DONE by hand in a maintainer commit (was BLOCKED in implement-stage cycle 1, #489/#675): the implement-stage agent's write permission does not extend to `.claude/`, confirmed by two denied Edit attempts against `.claude/skills/spec-cross-reference/SKILL.md` this cycle — same restriction FR-013 already documents for the board-loop.yml drift case, here blocking a wording *addition* rather than a drift fix, so the waiver file does not apply (nothing in the gate's own checked properties currently diverges over this). Needs a human session with `.claude/` write access. In `.claude/skills/spec-cross-reference/SKILL.md`, add the queuing/non-cancelling clause to the Over-rated example's existing paragraph (research.md D6, contracts/skill-example-claim.md item 4): state that a second run in the same group queues rather than racing or cancelling — a `queue`/`cancel` word in the same paragraph as the existing three backtick group/job tokens — without restating `concurrency-groups.md`'s full per-job table
- [x] T010 [US1] Run `python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py` against the real tree (expect pass) and then, on a scratch branch, against `.github/workflows/board-loop.yml` with one selecting job's (e.g. `review`'s) `concurrency:` block removed (expect fail, naming the job and both file locations), per quickstart.md §2; revert the scratch mutation afterward

**Checkpoint**: User Story 1 is independently functional — a reviewer or triager can invoke Gate 125 directly and get a trustworthy pass/fail against whatever `board-loop.yml` is checked out.

---

## Phase 4: User Story 2 - Changing the workflow surfaces the doc it invalidates (Priority: P2)

**Goal**: The PR-time gate suite blocks a `board-loop.yml` concurrency change that outdates the skill's claim, unless covered by a waiver — and the waiver itself is stale-checked in both directions.

**Independent Test**: Mutate `board-loop.yml`'s concurrency block on a scratch branch, run the local gate suite, observe a failure naming both the skill line and the workflow line; add a waiver entry and observe a pass; close the divergence and observe the same waiver entry now fail as stale — quickstart.md §3.

### Implementation for User Story 2

- [x] T011 [US2] In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`, implement `WaiverEntry` loading and the stale-check pass (contracts/skill-drift-gate.md "Algorithm" step 7, data-model.md WaiverEntry, research.md D7): read `.github/scripts/skill-example-drift-waivers.json`, mark any `DriftFinding` whose `{property, job}` pair matches a `WaiverEntry` as waived (still printed, as `waived: <property> (<job>), see #<issue>`, not counted toward the exit code), and emit a blocking stale-waiver failure for any `WaiverEntry` whose `{property, job}` pair matches no current finding
- [x] T012 [US2] Register Gate 125 in `.github/workflows/lint-workflows.yml`'s existing PR-time lint job, immediately after Gate 124's block: a `Gate 125` step (`python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py`) and a `Gate 125 self-test` step (same command plus `--self-test`), both `if: "!cancelled()"` (contracts/skill-drift-gate.md "Wiring", FR-010)
- [x] T013 [US2] In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`, implement `--self-test` fixtures for the waiver stale-check in both directions (research.md D9's waiver bullet, contracts/skill-drift-gate.md "Waiver interaction"): a synthetic fixture with `fix` missing from the ordinary group and an empty waiver set fails; the same fixture plus a matching `WaiverEntry{property: "job-missing-from-group", job: "fix", issue: "#1"}` passes and prints the `waived:` line; reverting the fixture to match while leaving that same entry in place fails, naming the entry as stale
- [x] T014 [US2] On a scratch branch, run quickstart.md §3 end-to-end against the real tree: remove `review`'s `concurrency:` block from `.github/workflows/board-loop.yml`, confirm `python .github/scripts/run-local-gates.py` fails naming both `SKILL.md` and `board-loop.yml`; add a matching entry to `.github/scripts/skill-example-drift-waivers.json`, confirm the suite passes; restore `review`'s block with the waiver entry still present, confirm the suite now fails on the stale entry; discard the scratch mutation and the waiver entry afterward

**Checkpoint**: User Stories 1 and 2 both independently functional — an ordinary PR is blocked by real drift, and a PR that cannot edit `.claude/` (the implement-stage case, FR-013) can still land behind a waiver.

---

## Phase 5: User Story 3 - A triager can date the claim (Priority: P3)

**Goal**: Someone meeting a "the skill is stale" report settles it in one command, with no history of spec 060.

**Independent Test**: Run Gate 125 bare, with no other file read. A clean exit with `[ok]` lines per checked property is "current"; a non-zero exit with the FR-006 message is "stale, here is exactly what diverged" — quickstart.md §4.

### Implementation for User Story 3

- [x] T015 [US3] DONE by hand in a maintainer commit (was BLOCKED in implement-stage cycle 1, #489/#675): same `.claude/` write restriction as T009 (confirmed again this cycle) — needs a human session. In `.claude/skills/spec-cross-reference/SKILL.md`, add the Gate-129-naming pointer sentence immediately after the Over-rated example's paragraph (research.md D8 item 1, contracts/skill-example-claim.md item 5): names the script's literal path `.github/scripts/verify-skill-board-loop-concurrency-claim.py` within two paragraphs of the anchor, and tells the reader to run it to settle currency before trusting the example to downgrade a finding
- [x] T016 [US3] In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`, extend the `[ok]` pass output (built in T008) to name each property it checked and that it currently holds, mirroring `verify-concurrency-guarantee-statement.py`'s `[ok] ...` lines (research.md D8 item 2), so a triager reads which properties were verified without reading the script's source
- [x] T017 [US3] DONE (the pointer sentence landed with T015; the gate passes on the real tree after that edit) (was PARTIAL in implement-stage cycle 1): the command's own output was verified this cycle to settle staleness alone in both the real-tree (pass, `[ok]` lines) and a scratch-mutated state (fail naming the job and both locations) — the one part not verifiable this cycle is "the skill itself points at the check" (T015's pointer sentence), since T015 is blocked. Re-run once T015 lands. Run quickstart.md §4 against both the real tree and one of US2's scratch mutation states (T014's setup, reproduced and reverted again), confirming the command's output alone settles staleness with no other file or issue history read

**Checkpoint**: All three user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Whole-suite and whole-feature validation spanning all three stories.

- [x] T018 [P] Ran the full suite: 179/181 passed. Gate 125 (bare + `--self-test`) both PASS. The only 2 failures (`verify-agent-push-credential-helper.py` bare and `--self-test`) are pre-existing and unrelated to this feature -- confirmed cause is a false positive: that gate's `check_no_jwt_construction` walks the untracked `.wing-commander-pipeline/` checkout, which carries a nested copy of the same script whose own self-test fixture string contains the JWT shape the gate flags. Filed as a `wing-commander-findings` entry rather than fixed here (out of this feature's scope). Run `python .github/scripts/run-local-gates.py` and confirm a fully green suite, including Gate 125's bare run and its `--self-test` step, against the real tree (SC-005, quickstart.md §1)
- [x] T019 [P] Confirm SC-006 (no second tracked copy of the claim): grep the tree for the four backtick tokens and the queuing-clause wording added in T009, and confirm they appear only in `.claude/skills/spec-cross-reference/SKILL.md`, never duplicated into `.github/scripts/verify-skill-board-loop-concurrency-claim.py`'s own comments or elsewhere
- [x] T020 Walk quickstart.md §5's edge cases: (1) pointed the script's `board-loop.yml` constant at a nonexistent path on a scratch edit → failed with `subject-missing`, naming the missing file, never a silent pass; reverted. (2) The reflow/typo-fix sub-case is BLOCKED this cycle -- same `.claude/` write restriction as T009/T015; by construction, though, `extract_skill_claim`'s regex only anchors on the four backtick tokens and collapses whitespace first, so a reflow or typo elsewhere in the paragraph cannot change the match (verifiable by inspection; not exercised against a live edit this cycle). (3) Confirmed by inspection: every path the script opens (`SKILL_MD`, `CONCURRENCY_GROUPS_MD`, `BOARD_LOOP_YML`, `DRIFT_WAIVERS_PATH`) is a fixed `REPO_ROOT`-joined literal, no glob or `os.walk`, so `.wing-commander-pipeline/` is never reachable.

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

---

## Phase 7: Convergence

- [x] T021 Extend `.github/scripts/verify-skill-board-loop-concurrency-claim.py`'s `--self-test` mode with synthetic SKILL.md/concurrency-groups.md/board-loop.yml-shaped text fixtures that exercise `extract_skill_claim`, `extract_job_classifications`, `extract_workflow_concurrency_facts`, and `compute_drift_findings` directly (not just `apply_waivers`), covering each of the five `DriftFinding` properties (`job-missing-from-group`, `cancel-in-progress-mismatch`, `unexpected-job-in-group`, `job-range-mismatch`, `directed-group-mismatch`) and `subject-missing` in both a failing and a passing direction, plus one fixture proving a reflow/typo-only change leaves extraction unaffected (FR-009) — the self-test currently only exercises the waiver stale-check, so a regression in any of these functions has no checked-in fixture catching it, only the real-tree manual demonstrations this cycle recorded in T010/T014/T020, which Constitution Principle VIII names as "evidence for that reviewer, not coverage for the next one" (CRITICAL, contradicts)


## Phase 8: Maintainer Feedback (PR #813 Review)

**Purpose**: The `DriftFinding` comparison built in T006 checks that `SkillClaim.ordinary_group`/`SkillClaim.directed_group` are used to spot non-capable jobs wrongly joining a group, but never checks whether those claimed group names themselves still match what `concurrency-groups.md` and `board-loop.yml` actually use for capable jobs — so a consistent rename of the group (e.g. `wing-commander-board-loop` → something else) across the workflow and the contract table would pass Gate 125 even though `SKILL.md`'s claim is now stale.

- [x] T022 In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`'s `DriftFinding` comparison (around `verify-skill-board-loop-concurrency-claim.py:254,275`), fail when `SkillClaim.ordinary_group`/`SkillClaim.directed_group` differ from the group names actually present in both `concurrency-groups.md`'s table and `board-loop.yml`'s real `concurrency:` blocks for capable jobs — today `ordinary_group`/`directed_group` are used only to spot non-capable jobs joining a group, never to check whether the claimed group names themselves still match (FR-001, FR-012, SC-001). Added two new `DriftFinding` properties, `ordinary-group-name-mismatch`/`directed-group-name-mismatch` (also recorded in data-model.md's property vocabulary). Note: the directed-name source had to be read from the jobs that actually carry a conditional `group:` expression in `board-loop.yml` (`prove-gate`/`prove`), not from `concurrency-groups.md`'s other capable-job rows, whose own "directed" column cell carries directed-*reachability* footnote tokens (e.g. `` `triage` ``/`` `review` ``/`` `readiness` ``) rather than the directed group's own name — taking the first backtick token from those rows would have picked the wrong value.
- [x] T023 [P] Update `contracts/skill-drift-gate.md`'s Algorithm steps 4-6 to document the new group-name comparison
- [x] T024 Add a `--self-test` fixture that renames `wing-commander-board-loop` consistently across a synthetic `board-loop.yml` and `concurrency-groups.md` while leaving `SKILL.md`'s claim unchanged, demonstrating the gate now fails on the stale skill claim (depends on T022; same file as T022, sequential). Two fixtures added (ordinary and directed rename), plus verified bare + `--self-test` pass against the real tree with the new `[ok]` lines.

**Checkpoint**: Gate 125 now also fails when the claimed group names drift from the workflow/contract, not just when membership drifts — closing the gap PR #813's review identified.


## Phase 9: Maintainer Feedback (PR #813 Review) — Gate Number Reassignment

**Purpose**: This feature's Gate 125 collides with a coordinated cross-spec gate renumbering (spec 091 keeps 126/127, spec 074 takes 128, spec 108 takes 130/131, spec 109 takes 132); this feature's gate moves to Gate 129 to fit that scheme.

- [x] T025 In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`'s docstring, renumber this feature's gate from Gate 125 to Gate 129 per the coordinated cross-spec numbering (spec 091 keeps 126/127, spec 074 takes 128, spec 108 takes 130/131, spec 109 takes 132). Note: the docstring and lint-workflows.yml step names were already at "Gate 126" (an earlier, separate rebase renumbering, commit 95f17fe) rather than "Gate 125" — renumbered straight from 126 to 129.
- [x] T026 [P] Update the corresponding step name(s) in `.github/workflows/lint-workflows.yml` from "Gate 125" to "Gate 129". Also updated the step's load-bearing explanatory comment (126, not 125, was the starting number in this tree) to record both renumbering events.
- [x] T027 [P] Fix stale "Gate 125" references in `tasks.md` (T002, T015) and in `contracts/skill-drift-gate.md` to read "Gate 129". Scoped exactly to T002 and T015 as this task item specifies; the many other "Gate 125" mentions elsewhere in this file are historical task narrative (already-completed task descriptions, checkpoints) outside this item's named scope — see the `wing-commander-findings` note on Phase 9's own Checkpoint text, which claims a broader scope than T027 actually specifies.
- [ ] T028 BLOCKED this cycle: updating the PR body/description needs a `gh pr edit`-family command, which this run's tool allowlist does not grant (only `gh issue view`/`gh issue comment` are permitted, no `gh pr *`). Needs a session with PR-edit access, or the maintainer, to set the PR body to reference Gate 129 and note that this resolves #812.

**Checkpoint**: Gate 129 is the feature's only remaining gate number — no "Gate 125" reference survives in the script, the workflow, this file, or the contract — and the coordinated cross-spec renumbering lands without collision.


## Phase 10: Convergence

**Purpose**: `contracts/skill-example-claim.md`'s Verification section documents two checks Gate 129's own extraction never performs, and `data-model.md`'s `SkillClaim` entity carries a field the code never populates.

- [x] T029 Extend `extract_skill_claim` in `.github/scripts/verify-skill-board-loop-concurrency-claim.py` to test the two properties `contracts/skill-example-claim.md`'s Verification section already documents as gate-checked but the current extraction (which only pulls the three backtick tokens) never tests: a queuing/cancellation word (`queue`/`cancel`) present in the Over-rated paragraph (contract item 4), and the literal script path `verify-skill-board-loop-concurrency-claim.py` present within two paragraphs of the anchor (contract item 5); record the queuing result as `SkillClaim.queues_not_cancels`, the field `data-model.md`'s SkillClaim table already names but the code has never populated; emit `subject-missing` when either is absent, so an edit that drops the queuing clause or the Gate pointer sentence T009/T015 added is caught by the gate rather than silently passing (FR-003, FR-005, FR-008, SC-003, SC-004; contracts/skill-example-claim.md "Verification")
- [x] T030 Add `--self-test` fixtures demonstrating T029's two new checks: a paragraph missing the queuing word fails as `subject-missing`, a paragraph missing the Gate pointer sentence fails as `subject-missing`, and a paragraph carrying both passes, per FR-007/SC-005

**Checkpoint**: `extract_skill_claim` enforces every property `contracts/skill-example-claim.md` documents as gate-checked, and `SkillClaim`'s shape matches `data-model.md` exactly.

## Phase 11: Maintainer Feedback (PR #813 Review — Message Formatting)

**Purpose**: The `ordinary-group-name-mismatch`/`directed-group-name-mismatch` `DriftFinding`s (verify-skill-board-loop-concurrency-claim.py:297-298, 315-316) set `expected` to the name `concurrency-groups.md`/`board-loop.yml` actually use and `actual` to `SKILL.md`'s claimed token — the reverse of every other finding property (e.g. `job-range-mismatch`) and of `format_finding`'s "SKILL.md claims {expected}; board-loop.yml (...) has {actual}" template, so the rendered message states the disagreement backwards and labels the `concurrency-groups.md` location as `board-loop.yml`. FR-006 requires the message to name the skill location and the workflow location that disagree; SC-004 requires a triager to settle staleness from the output alone.

- [x] T031 In `.github/scripts/verify-skill-board-loop-concurrency-claim.py`'s group-name comparison (lines 291-316), swap `expected`/`actual` for both `ordinary-group-name-mismatch` and `directed-group-name-mismatch` so `expected` carries `SKILL.md`'s claimed token (`claim.ordinary_group`/`claim.directed_group`) and `actual` carries the name `concurrency-groups.md`/`board-loop.yml` actually use (`real_ordinary`/`real_directed`), matching the convention every other `DriftFinding` property already follows (FR-006, SC-004).
- [x] T032 Extend the two rename `--self-test` fixtures (lines ~737-740, ~754-757) to assert on the rendered `format_finding(...)` message text (e.g. that it reads "claims `wing-commander-board-loop`" and "has `renamed-ordinary-group`", not the reverse), not only `[f.property for f in ...]`, so a future swap of `expected`/`actual` fails a checked-in fixture instead of passing silently (Constitution Principle VIII). Note: the assertions use the self-test's own fixture tokens (`ordinary-group`/`renamed-ordinary-group`, `directed-group`/`renamed-directed-group`), not the task item's illustrative `wing-commander-board-loop` example, which belongs to the real tree, not the synthetic fixture.

## Phase 12: Maintainer Feedback (PR #813 Review — Stale Gate Numbers, #812)

**Purpose**: T027 scoped its renumbering to `tasks.md` (T002, T015) and `contracts/skill-drift-gate.md` only. Issue #812 names `contracts/skill-example-claim.md` explicitly, and that file still reads "Gate 125" at lines 32, 34, 45, 51, 66; `.github/scripts/skill-example-drift-waivers.json`'s live `$comment` at lines 3 and 19 still reads "Gate 126". #812 is therefore still open.

- [x] T033 Update the remaining stale gate-number references to "Gate 129": `contracts/skill-example-claim.md` (lines 32, 34, 45, 51, 66 — the file #812 names explicitly) and `.github/scripts/skill-example-drift-waivers.json`'s `$comment` (lines 3, 19). Optionally also update `data-model.md`, `plan.md`, `quickstart.md`, and `research.md`, which still say "Gate 125" throughout, for consistency. Did the two named-in-#812 files (verified: grep finds zero remaining "Gate 125"/"Gate 126" in either). Left the optional four alone: `research.md`'s D1 decision record in particular narrates *why* 125 was picked ("the next free number; none of 1-124 is unused") — renumbering that prose in place would misstate the historical rationale rather than just relabel it, the same hazard T027 already flagged for its own narrower scope.

## Phase 13: Maintainer Feedback (PR #813 Review — Convergence Gap, T029/T030)

**Purpose**: Confirms Phase 10's existing gap is still open and blocking convergence: `contracts/skill-example-claim.md`'s Verification section documents items 4 (a queuing/cancellation word in the Over-rated paragraph) and 5 (the script path within two paragraphs of the anchor) as gate-checked, but `extract_skill_claim` only pulls the three backtick tokens, so deleting either sentence from `SKILL.md` still passes the gate. FR-008 is unenforced as documented.

- [x] T034 Either complete T029/T030 as already specified in Phase 10, or — if that scope is rejected for this PR — revise `contracts/skill-example-claim.md`'s Verification section so it no longer documents items 4 and 5 as mechanically gate-checked. This PR is not converged while either remains undone (FR-003, FR-005, FR-008, SC-003, SC-004). Done via the first branch: T029/T030 landed this cycle. Confirmed against the real tree: bare run and `--self-test` both pass (`[ok]` lines for all seven `DriftFinding` properties, plus the new queuing-word/script-pointer self-test fixtures). Could not additionally demonstrate the failing direction against the live `SKILL.md` itself (a scratch removal of the queuing clause, then revert) — the implement-stage agent's write permission does not extend to `.claude/`, confirmed again this cycle by a denied Edit attempt, same restriction T009/T015/T020 already document. The synthetic `--self-test` fixtures added in T030 (missing-queue-word and missing-pointer-sentence, both asserting `subject-missing`) demonstrate the same code path this scratch mutation would have exercised.

## Phase 14: Convergence

**Purpose**: `format_finding` hardcodes the literal text `"board-loop.yml"` as the workflow-location label for every `DriftFinding`'s rendered message, but `ordinary-group-name-mismatch`/`directed-group-name-mismatch` (added in Phase 8/T022) set `workflow_location` to `(CONCURRENCY_GROUPS_MD, None)`, not `board-loop.yml` — so the rendered failure message reads `"board-loop.yml (specs/060-self-redrive-concurrency/contracts/concurrency-groups.md) has ordinary group \`...\`"`, naming the wrong file by its fixed label even though the actual path shown in parentheses is correct. FR-006 requires the message to name the workflow location that disagrees; a triager who reads the label before the path is misdirected to `board-loop.yml` when the actual disagreement is in `concurrency-groups.md`.

- [ ] T035 In `format_finding` (`.github/scripts/verify-skill-board-loop-concurrency-claim.py`), derive the workflow-location label from `finding.workflow_location`'s own path (e.g. its basename) instead of the hardcoded literal `"board-loop.yml"`, so the rendered message correctly names `concurrency-groups.md` for the two group-name-mismatch properties while continuing to name `board-loop.yml` for every other property; extend the two rename `--self-test` fixtures (already asserting on `format_finding`'s output per T032) to also assert the corrected label per FR-006 (partial)

## Phase 15: Maintainer Feedback (PR #813 Review — Contract Doc for T035)

**Purpose**: T035 (Phase 14) fixes `format_finding` so it derives the workflow-location label from each finding's actual `workflow_location` path instead of hardcoding `"board-loop.yml"`. `contracts/skill-drift-gate.md`'s "Failure message shape" section and its rename-example text still document the old, wrong behavior — the same hardcoded `board-loop.yml` label — so the contract no longer matches the gate it specifies (FR-006, SC-004).

- [ ] T036 Update `specs/089-skill-example-drift/contracts/skill-drift-gate.md`'s "Failure message shape" section and its rename-example text to match T035's fix: the workflow-location label must be derived from each finding's actual `workflow_location` path (e.g. `concurrency-groups.md` for `ordinary-group-name-mismatch`/`directed-group-name-mismatch`, not a hardcoded `board-loop.yml` literal). The contract currently documents the same wrong label `format_finding` (verify-skill-board-loop-concurrency-claim.py:380) still renders (FR-006, SC-004; PR #813 review item 1).


## Phase 16: Maintainer Feedback (PR #813 Review — subject-missing Message for SKILL.md-internal Findings)

**Purpose**: `extract_skill_claim` (verify-skill-board-loop-concurrency-claim.py:129-135) emits a `subject-missing` `DriftFinding` when a SKILL.md-internal element — the queuing/cancellation word, the script pointer sentence, or a job-range/group backtick token — cannot be found in the Over-rated example's paragraph. For all of these, the finding's `workflow_location` is set to `(BOARD_LOOP_YML, None)`, which is wrong: the disagreement is entirely within `SKILL.md` itself, not between `SKILL.md` and `board-loop.yml`. `format_finding`'s generic template then renders this as "board-loop.yml (.github/workflows/board-loop.yml) has not found in that paragraph" — naming the wrong file, in some cases embedding an absolute path instead of a repo-relative one, and producing text that does not read as a sentence. FR-006 requires the message to name the location that actually disagrees; SC-004 requires a triager to settle staleness from the output alone.

- [ ] T037 Fix the `subject-missing` `DriftFinding` `extract_skill_claim` emits when a SKILL.md-internal element (queuing word, script pointer, job-range/group tokens) is missing (verify-skill-board-loop-concurrency-claim.py:129-135): it currently sets `workflow_location=(BOARD_LOOP_YML, None)`, so `format_finding`'s generic template renders "board-loop.yml (.github/workflows/board-loop.yml) has not found in that paragraph" — naming the wrong file, embedding an absolute path in other cases, and not reading as a sentence. Name SKILL.md as the source of the disagreement, run the path through `os.path.relpath`, and phrase `actual` as a readable clause (e.g. "a paragraph without it") (FR-006, FR-008, SC-004; PR #813 review item 2).

## Maintainer Feedback (PR #813 Review — Self-Test Crash on Empty Findings)

- [ ] T038 Fix `run_selftest`'s rename-fixture assertions (verify-skill-board-loop-concurrency-claim.py:821, 843): `format_finding(renamed_ordinary_findings[0])` and `format_finding(renamed_directed_findings[0])` raise `IndexError` when the group-name check is removed or broken and the list is empty, aborting the self-test before it prints every later check or the summary line. Guard each access so an empty list is recorded as a failed `check(...)` instead of raising (Constitution Principle VIII; PR #813 review item 3).

## Maintainer Feedback (PR #813 Review — Tautological Self-Test Check)

- [ ] T039 Fix the tautological self-test check at verify-skill-board-loop-concurrency-claim.py:652-654 ("a paragraph carrying both the queuing word and the Gate pointer sentence extracts queues_not_cancels=True"): since `extract_skill_claim` only returns a non-None `SkillClaim` when `has_queue_word` already held (line 113, 123-125), `claim.queues_not_cancels` is `True` on every code path that reaches this assertion, so it cannot fail on its own. Delete it or replace it with an assertion that distinguishes a real regression (Constitution Principle VIII; PR #813 review item 4).
