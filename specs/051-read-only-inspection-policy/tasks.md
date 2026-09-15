---

description: "Task list for One read-only inspection policy for stage tool allowlists"
---

# Tasks: One read-only inspection policy for stage tool allowlists

**Input**: Design documents from `/specs/051-read-only-inspection-policy/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/inspection-policy.md, contracts/gate-extensions.md, quickstart.md

**Tests**: Not requested as a separate TDD pass — this feature's own "tests" are the two gate scripts' mutation self-tests (FR-014/FR-015/SC-003), which are load-bearing implementation tasks (T012, T023) rather than an optional addition, mirroring how spec 037 treated its own gate work.

**Organization**: Tasks are grouped by the spec's three user stories (P1/P2/P3), each a distinct shape behind the nine #266 occurrences. The policy prose itself (research.md D1) lands once, in Foundational, because it is one contiguous markdown section whose paragraphs serve all three stories at once (the inspection-set/compound-rule/read-capable-definition paragraphs serve US1, the `gh api` paragraph serves US2, the gate-suite paragraph serves US3) — splitting it across three tasks would have three tasks racing to insert at the same point in the same file for no benefit, exactly the failure mode spec 037's own Foundational-render rationale warns against. FR-011/FR-012/FR-013 ("deterministic leftovers," per the spec's own section heading) map to no single priority story — they resolve occurrences 5/6 (printenv) and part of the plan/tasks `gh auth status` grant, none of which the three stories' own Independent Tests exercise — so they land in Polish alongside the final gate sweep.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (one contract doc, one composite action, two gate scripts, five workflow files, one repo-root guidance file), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative. Line numbers cited are current as of this tasks-generation pass against `spec/051-read-only-inspection-policy` (plan commit `eac3e78`); T001 re-confirms them before editing.

---

## Phase 1: Setup

**Purpose**: Confirm the anchor lines this feature edits have not drifted since research.md/data-model.md/contracts were written.

- [ ] T001 Run `grep -n "default-allowed-tools:\|Shell constraints in this headless run\|gh auth status\|shell_commands=" .github/workflows/intake.yml .github/workflows/clarify.yml .github/workflows/plan.yml .github/workflows/tasks.yml .github/workflows/implement.yml .github/actions/wing-commander-tool-args/action.yml` and `grep -n "^## Before pushing" CLAUDE.md` and `grep -n "^## Per-stage default tool lists" specs/010-reusable-pipeline/contracts/stage-interfaces.md`, and reconcile the output against the line numbers cited in T002 onward. Record any drift found (there was none as of this tasks pass: intake.yml default-allowed-tools at line 572, its Shell constraints block at 692-725; clarify.yml default-allowed-tools at 479; plan.direct-commit at 631, plan.pr at 798, each with their Shell constraints block and `gh auth status` bullet; tasks.direct-commit at 632, tasks.pr at 781, same shape; implement.cycle at 687, implement.retry at 1117, `Install actionlint for the agent` at 660; the composite's `shell_commands` assignments span action.yml lines 283-357; CLAUDE.md's `## Before pushing` at line 3; stage-interfaces.md's `## Per-stage default tool lists` at line 250).

**Checkpoint**: Every line number cited below is confirmed current (or corrected) before any edit begins.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: FR-001 requires one written policy, in the record that already owns the per-stage lists, that every other mention points at rather than restates. Every later phase's table/prompt/gate edit is described relative to this section, so it must exist first.

- [ ] T002 In `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, insert a new `## Read-only inspection policy` section immediately before `## Per-stage default tool lists` (currently line 250), landing the "Policy text" block from `specs/051-read-only-inspection-policy/contracts/inspection-policy.md` verbatim (its six paragraphs: the opening "nine occurrences shared one cause" statement; **The inspection primitive set**; **Compound, piped, and redirected commands**; **Read-capable stage, defined**; **`gh api`**; **The gate suite**; and the closing pointer to this feature's occurrence-disposition table at `specs/051-read-only-inspection-policy/contracts/inspection-policy.md`). This is one atomic insertion, not four, because the paragraphs serve US1 (primitive set + compound rule + read-capable definition), US2 (`gh api` routing, including the FR-008 "pre-existing and untouched" sentence for `watchdog.diagnose`), and US3 (gate-suite scoping) simultaneously in one contiguous section — every later phase edits a *different* file and cites back to this one.

**Checkpoint**: The policy has one home; every later table row, prompt sentence, and gate error message can now point at it instead of restating it.

---

## Phase 3: User Story 1 - A read-only inspection succeeds in the shape the agent was taught (Priority: P1) 🎯 MVP

**Goal**: Every read-capable stage's default allowed list carries the seven-primitive inspection set, and the rendered tooling statement every stage prompt embeds states the compound/pipe/redirect rule once, from its one existing home, so a piped or chained inspection is either permitted or pre-empted by name.

**Independent Test**: Replay `cd .github/workflows && for …`, `grep … | sort | tail`, `ls … | grep`, and `git stash; actionlint … ; git stash pop` against each stage's composed allowed list and rendered prompt; each is either permitted or covered by a prompt sentence naming the permitted alternative (occurrence-disposition rows 1, 2, 10).

### Implementation for User Story 1

- [ ] T003 [P] [US1] In `.github/actions/wing-commander-tool-args/action.yml`'s `Compose tool args` step, add a `STATIC_SUFFIX` string per `contracts/gate-extensions.md`'s Gate 21 section — `" Each command in a pipeline or `;`/`&&` chain is checked separately, and a `>`/`>>` redirect or a `cd … &&` prefix is denied regardless of this list — use the Read/Grep/Glob tools, or a single command, for anything multi-step."` — and append it to `shell_commands` once, after every branch of the if/else that sets it has run (immediately before the "5. Emit" comment / `echo "allowed-tools=$effective_allowed"` line, currently line 354), so it lands in the `UNRESTRICTED`, `UNRESTRICTED_EXCEPT`, `EMPTY`, and `ENUMERATED` templates alike (research.md D3).
- [ ] T004 [US1] In `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s per-stage table, add the seven-primitive inspection set (`Bash(grep:*),Bash(head:*),Bash(tail:*),Bash(sort:*),Bash(uniq:*),Bash(wc:*),Bash(cut:*)`) to the `intake`, `clarify`, and `implement.cycle` rows' Default allowed cell, inserted immediately after `Bash(cat:*)` — the same position `plan.*`/`tasks.*` already use — so the literal-cell order match Gate 27's `compare()` enforces still holds. `implement.retry`'s row already reads "same as `implement.cycle` plus …" and needs no separate edit (the relative-row set comparison inherits `implement.cycle`'s addition automatically).
- [ ] T005 [P] [US1] In `.github/workflows/intake.yml`'s `default-allowed-tools` literal (line 572), insert `Bash(grep:*),Bash(head:*),Bash(tail:*),Bash(sort:*),Bash(uniq:*),Bash(wc:*),Bash(cut:*)` immediately after `Bash(cat:*)`, matching T004's table order exactly.
- [ ] T006 [P] [US1] In `.github/workflows/clarify.yml`'s `default-allowed-tools` literal (line 479), insert `Bash(grep:*),Bash(head:*),Bash(tail:*),Bash(sort:*),Bash(uniq:*),Bash(wc:*),Bash(cut:*)` immediately after `Bash(cat:*)`, matching T004's table order exactly.
- [ ] T007 [P] [US1] In `.github/workflows/implement.yml`, insert `Bash(grep:*),Bash(head:*),Bash(tail:*),Bash(sort:*),Bash(uniq:*),Bash(wc:*),Bash(cut:*)` immediately after `Bash(cat:*)` in **both** the `implement.cycle` `default-allowed-tools` literal (line 687) and the `implement.retry` `default-allowed-tools` literal (line 1117), matching T004's table order exactly in each.
- [ ] T008 [P] [US1] In `.github/workflows/intake.yml`'s "Shell constraints in this headless run" block (lines 692-725), delete the bullets that duplicate T003's new rendered sentence: the "Every part of a compound command must be separately allowed…" bullet, the "No output redirection (`>`, `>>`)…" bullet, and the "To search or inspect many files at once use the Grep and Glob tools…" bullet; from the "Use bare git verbs from the repo root…" bullet, remove only the "and `cd <path> && ...` are denied" clause, keeping the `git -C <path> ...` prohibition (a fact T003's sentence does not state). Leave the variable-expansion-rejection, environment-assignment-prefix, `.specify`-scripts-not-executable, `gh auth status`-uninformativeness, and "a denial is not a hint to retry" bullets untouched (research.md D4).
- [ ] T009 [P] [US1] Apply the identical deletion described in T008 to both copies of the "Shell constraints" block in `.github/workflows/plan.yml` (the `plan.direct-commit` prompt around lines 724-757 and the `plan.pr` prompt around lines 886-919).
- [ ] T010 [P] [US1] Apply the identical deletion described in T008 to both copies of the "Shell constraints" block in `.github/workflows/tasks.yml` (the `tasks.direct-commit` and `tasks.pr` prompts).
- [ ] T011 [P] [US1] Apply the identical deletion described in T008 to both copies of the "Shell constraints" block in `.github/workflows/implement.yml` (the `implement.cycle` prompt around lines 785-818 and the `implement.retry` prompt around lines 1239-1272).
- [ ] T012 [US1] In `.github/scripts/verify-stage-tool-lists.py`, add Check A (inspection-set completeness) per `contracts/gate-extensions.md`: the `INSPECTION_SET` and `READ_CAPABLE_LABELS` constants (near the existing `TABLE_DOC`/`WORKFLOW_DIR`/`COMPOSITE` constants), a `check_inspection_set(table)` function returning one failure per read-capable label missing a primitive with no recorded exception, wired into `run()` after the existing `compare()` call so its failures append to the same list, and the two self-test mutations described in the contract (drop `Bash(cut:*)` from `plan.direct-commit` → expect the "omits" failure; confirm no failure fires for a non-read-capable row like `finalize` missing the whole set) added to `_mutations()`. Depends on T004 landing the table rows Check A reads.
- [ ] T013 [US1] In `.github/scripts/verify-tooling-statement.py`, add T003's `STATIC_SUFFIX` as a literal constant, append it to every existing `CASES` entry's `want_shell_commands` argument (twelve call sites), and add the one new `MUTATIONS` entry from `contracts/gate-extensions.md` that strips the suffix from a scratch copy of the shipped script and asserts every one of the twelve cases turns red. Depends on T003 (the shipped script's literal text must match).
- [ ] T014 [US1] Validate this phase against `quickstart.md` steps 1-4 and `contracts/inspection-policy.md`'s occurrence rows 1, 2, and 10: run `python3 .github/scripts/verify-stage-tool-lists.py --self-test` and `python3 .github/scripts/verify-tooling-statement.py`, confirm both exit 0 with the expected mutation-caught lines, and desk-check that the `cd .github/workflows && for …` and `git stash; actionlint … ; git stash pop` shapes are now named as denied-whole by the rendered `Tooling: …` sentence in each affected stage's prompt.

**Checkpoint**: User Story 1 is fully functional and independently testable — every read-capable stage carries the inspection set, the rendered statement states the compound/pipe/redirect rule from its one home, and both gates catch a regression of either guarantee.

---

## Phase 4: User Story 2 - The reads that drove `gh api` have a sanctioned route (Priority: P2)

**Goal**: `clarify` and `plan` never need `gh api` — the reads that drove agents to it are named, by the prompt itself, as already satisfied another way.

**Independent Test**: For each recorded `gh api` denial, confirm the field it was after is obtainable through a route that stage's own prompt names, and that `gh api` is absent from every stage's composed allowed list except `watchdog.diagnose`'s pre-existing, untouched `Bash(gh:*)` (occurrence-disposition rows 3, 8, 9).

### Implementation for User Story 2

- [ ] T015 [P] [US2] In `.github/workflows/clarify.yml`'s prompt, add one sentence after the existing "A reply to the clarification questions was posted. It is at /tmp/wing-commander/clarification-answer.md…" paragraph (lines 527-529) stating that `gh api`/`gh issue view --json comments` are not needed and not granted for this — the reply body and author are already staged in the two named files, so the agent never has cause to fetch the comment itself (FR-007, closes occurrence 8's `gh issue view … --jq … > /tmp/q.md` and occurrence 9's `gh api … --jq '.body'`).
- [ ] T016 [P] [US2] In `.github/workflows/plan.yml`, replace the existing generic sentence "`gh api` is not granted in this run; read PRs and issues with whichever `gh pr ...` / `gh issue ...` verbs this run permits." with one naming the specific sanctioned route for a PR's raw JSON: "`gh api` is not granted in this run and is never needed for a PR read — use `gh pr view <number> --json <fields>`, which this run already permits." Apply identically to **both** copies (`plan.direct-commit`'s prompt around lines 749-753, and `plan.pr`'s prompt around lines 911-915) (FR-007, closes occurrence 3's `gh api repos/{owner}/{repo}/pulls/224`).
- [ ] T017 [US2] Validate this phase against `quickstart.md` step 5 and occurrence rows 3, 8, 9: run `grep -n 'default-allowed-tools:.*gh api' .github/workflows/*.yml` and confirm zero matches; confirm `watchdog.diagnose`'s `Bash(gh:*)` (a different literal, unaffected by this feature) is recorded as pre-existing-and-untouched in T002's landed policy text; re-read T015/T016's prompt sentences alongside the deterministic staging steps they point at (`clarify.yml`'s "Stage the answer as a data file" step, `plan.yml`'s existing `Bash(gh pr view:*)` grant) to confirm each route is real, not aspirational.

**Checkpoint**: User Stories 1 and 2 both hold — no stage's write surface widened (FR-008), and every `gh api` denial has a named, real alternative in the prompt that hit it.

---

## Phase 5: User Story 3 - No agent is instructed to run what its allowlist forbids (Priority: P3)

**Goal**: `CLAUDE.md`'s "Before pushing" gate-suite instruction addresses only the implement stage agent and human/local sessions; the implement stage agent is now actually permitted to run it, under a timeout, behind a preflight that degrades instead of denying or failing.

**Independent Test**: Enumerate the commands repository guidance mandates for a pipeline agent, resolve each against every stage whose agent reads that guidance, and confirm no instruction/permission mismatch remains; confirm the gate-suite run completes within its timeout or leaves a summary note under both prerequisite states (occurrence-disposition row 7, SC-008).

### Implementation for User Story 3

- [ ] T018 [US3] In `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s per-stage table, add `Bash(python .github/scripts/run-local-gates.py:*)` to the `implement.cycle` row's Default allowed cell (append at the end, after `Bash(git rm:*)`). `implement.retry`'s relative row inherits it automatically.
- [ ] T019 [US3] In `.github/workflows/implement.yml`, append `,Bash(python .github/scripts/run-local-gates.py:*)` to the end of **both** the `implement.cycle` `default-allowed-tools` literal (line 687, after `Bash(git rm:*)`) and the `implement.retry` `default-allowed-tools` literal (line 1117).
- [ ] T020 [US3] In `.github/workflows/implement.yml`'s `implement` job, add a preflight step named `Preflight: gate-suite prerequisites (cycle)` immediately after `Install actionlint for the agent` (line 660) and before `Compose tool args (cycle)` (line 676), sharing the same `if:` guard as its neighboring steps. It checks `python3 -c "import yaml"` (pyyaml), `command -v jq`, and `command -v actionlint` (already installed by the preceding step, so this leg only confirms, never (re)installs); on any failure it appends a line naming the missing tool to `$GITHUB_STEP_SUMMARY` and sets a `ready=false` step output (default `ready=true` when all three are present) — it never exits non-zero (FR-009a). Add the mirrored step `Preflight: gate-suite prerequisites (retry)` immediately before `Compose tool args (implement.retry)` (line 1111), identical apart from its `id`.
- [ ] T021 [US3] In `.github/workflows/implement.yml`, add a step named `Run local gate suite (cycle)` immediately after T020's cycle preflight (and before `Compose tool args (cycle)`), gated on `steps.<preflight-id>.outputs.ready == 'true'` in addition to the job's existing guards, with `timeout-minutes: 10`, running `python .github/scripts/run-local-gates.py` with its default (parallel) `--jobs` (research.md D5). Add the mirrored step `Run local gate suite (retry)` immediately after T020's retry preflight.
- [ ] T022 [US3] In `CLAUDE.md`, add one leading sentence under the `## Before pushing` heading (line 3) naming its audience explicitly — the implement stage agent and human/local sessions — and stating that the intake, clarify, plan, and tasks stage agents are not addressed by this section, before the existing "Run the full PR-time gate suite locally…" paragraph (FR-009b).
- [ ] T023 [US3] In `.github/scripts/verify-stage-tool-lists.py`, add Check B (repository-guidance reconciliation) per `contracts/gate-extensions.md`: the `MANDATED_COMMANDS` constant (`{"Bash(python .github/scripts/run-local-gates.py:*)": {"implement.cycle", "implement.retry"}}`), a `check_mandated_commands(table)` function, wired into `run()` alongside Check A, and the self-test mutation that removes the gate-suite command from `implement.cycle`'s table row and expects the "is told by CLAUDE.md... but its default allowed list does not permit it" failure. Depends on T018 landing the table entry Check B reads.
- [ ] T024 [US3] Validate this phase against `quickstart.md` steps 6-7 and occurrence row 7: run `timeout 600 python3 .github/scripts/run-local-gates.py` directly to confirm it completes well inside 10 minutes; then simulate the prerequisite-absent path by reading T020's preflight step and confirming its `if` guard on T021 and its `$GITHUB_STEP_SUMMARY` note, matching FR-009a/SC-008's "never a denial, never a failed stage" requirement; run `sed -n '/## Before pushing/,/^## /p' CLAUDE.md | head -20` and confirm the audience sentence precedes the gate-suite command.

**Checkpoint**: All three user stories hold independently — the implement agent can run the gate suite it is now the only agent told to run, under a timeout, degrading instead of failing when its container has drifted.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: FR-011/FR-012/FR-013's deterministic leftovers (occurrences 5, 6, and part of 4), plus the final proof that every occurrence has a disposition and the whole suite still passes.

- [ ] T025 In `.github/workflows/intake.yml`'s `default-allowed-tools` literal (line 572) and `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s `intake` row, add `Bash(printenv SPECIFY_FEATURE_DIRECTORY)`, matching `plan.*`/`tasks.*`'s existing grant literally (FR-011, closes occurrence 6).
- [ ] T026 In `.github/workflows/intake.yml`'s "Shell constraints" block (post-T008), edit the environment-assignment-prefix bullet to remove the clause "the variable is already exported for you, so just run the script" — intake computes its spec directory only during the agent's own run and exports nothing before it starts, unlike plan/tasks/implement (FR-012, research.md D6). Keep the rest of the bullet (the environment-assignment-prefix rejection itself) intact.
- [ ] T027 [P] Remove `Bash(gh auth status)` from all four literals — `.github/workflows/plan.yml`'s `plan.direct-commit` (line 631) and `plan.pr` (line 798), `.github/workflows/tasks.yml`'s `tasks.direct-commit` (line 632) and `tasks.pr` (line 781) — and from the corresponding `plan.direct-commit`/`tasks.direct-commit` rows in `specs/010-reusable-pipeline/contracts/stage-interfaces.md` (the `plan.pr`/`tasks.pr` relative rows inherit the removal automatically). Leave each prompt's existing "`gh auth status`... will not explain [a denial]" sentence unchanged — it remains true whether or not the command is granted (FR-013, closes the `gh auth status` half of occurrence 4).
- [ ] T028 [P] Run `actionlint` and `yamllint` (per spec 025's existing CI gate) across every workflow this feature touched (`intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`) and confirm zero new errors; validate `.github/actions/wing-commander-tool-args/action.yml`'s edited `run:` block the way spec 037's own Polish phase did — via `bash -e` execution through `verify-tooling-statement.py`'s suite rather than `actionlint` (which cannot parse composite-action files structurally).
- [ ] T029 Run `python .github/scripts/run-local-gates.py` (the same command `CLAUDE.md` now scopes to this stage) and confirm a clean pass, including Gate 27's and Gate 21's extended self-tests (SC-003). Then walk `contracts/inspection-policy.md`'s ten-row occurrence-disposition table and confirm every row's Disposition cell is non-blank and matches what T003-T027 actually shipped (SC-001) — this is the evidence a maintainer quotes when closing #266 (SC-007); closing the issue itself is a follow-up action outside this feature's file edits.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup's line-number confirmation only loosely — BLOCKS every user story phase, since T002 lands the prose every later table row and prompt sentence points at.
- **User Story 1 (Phase 3)**: Depends on Foundational. T004-T011 can proceed in any order relative to each other (disjoint files, or disjoint line ranges within stage-interfaces.md's single table for T004); T012 depends on T004; T013 depends on T003.
- **User Story 2 (Phase 4)**: Depends on Foundational only; independent of User Story 1's tasks.
- **User Story 3 (Phase 5)**: Depends on Foundational only; independent of User Stories 1/2. T019/T023 depend on T018; T021 depends on T020.
- **Polish (Phase 6)**: T025/T026 touch `intake.yml` (different line ranges from each other and from T005/T008); T027 touches `plan.yml`/`tasks.yml` (after T009/T010 land, to avoid two tasks racing on the same Shell-constraints edit region — sequence T027 after Phase 3's T009/T010 complete). T028/T029 depend on every prior phase.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on another story's tasks beyond Foundational.
- **User Story 2 (P2)**: No dependency on another story's tasks beyond Foundational; independently testable in parallel with User Story 1.
- **User Story 3 (P3)**: No dependency on another story's tasks beyond Foundational; independently testable in parallel with User Stories 1/2.

### Parallel Opportunities

- T005, T006, T007 (User Story 1's per-workflow inspection-set grants) touch three disjoint workflow files and can run in parallel once T004 fixes the shared order convention.
- T008, T009, T010, T011 (the Shell-constraints deletions) touch four disjoint workflow files and can all run in parallel.
- T015 and T016 (User Story 2's two prompt edits) touch disjoint files (`clarify.yml`, `plan.yml`) and can run in parallel.
- User Story 1, User Story 2, and User Story 3's implementation tasks (T003-T014, T015-T017, T018-T024) can proceed in parallel once Foundational (T002) lands, since no story's tasks edit a file another story's tasks also edit (the one shared file, `stage-interfaces.md`, is touched by T004/T018/T025/T027 at disjoint rows — sequence these four sequentially against that one file even though their surrounding phases run in parallel).
- T027 and T028 can run in parallel once their file-level prerequisites (T009/T010 for T027; every prior phase for T028) are met.

---

## Parallel Example: User Story 1's per-file edits

```bash
# Launch together — three different workflow files, all adding the same
# seven-primitive set at the same relative position once T004 fixes the order:
Task: "Add inspection set to intake.yml's default-allowed-tools (line 572)"
Task: "Add inspection set to clarify.yml's default-allowed-tools (line 479)"
Task: "Add inspection set to implement.yml's cycle and retry default-allowed-tools"

# Launch together — four different workflow files, each losing the same
# three redundant Shell-constraints bullets:
Task: "Delete redundant compound/pipe/redirect bullets in intake.yml"
Task: "Delete redundant compound/pipe/redirect bullets in plan.yml (both copies)"
Task: "Delete redundant compound/pipe/redirect bullets in tasks.yml (both copies)"
Task: "Delete redundant compound/pipe/redirect bullets in implement.yml (both copies)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm line anchors)
2. Complete Phase 2: Foundational (the policy document, landed once)
3. Complete Phase 3: User Story 1 (inspection set standardized, compound-rule sentence rendered, both gates extended)
4. **STOP and VALIDATE**: Run `quickstart.md` steps 1-4 against the finished render and table
5. This alone resolves the majority of #266's occurrences (the 23-denial run is almost entirely this shape) — User Stories 2 and 3 close the two remaining shapes independently

### Incremental Delivery

1. Setup + Foundational → the policy has one home
2. Add User Story 1 → inspection set + compound-rule guidance ship, both gates catch a regression → mergeable increment (closes occurrences 1, 2, 10)
3. Add User Story 2 → `gh api` routes named in the prompts that hit it → mergeable increment (closes occurrences 3, 8, 9)
4. Add User Story 3 → gate suite scoped to implement, preflight-gated, timed out → mergeable increment (closes occurrence 7)
5. Polish → the two remaining deterministic leftovers (occurrences 5, 6, and the `gh auth status` half of 4), full gate sweep, occurrence table walk closing SC-001

### Why the policy document (Foundational) is one task, not three

`contracts/inspection-policy.md`'s "Policy text" block is one contiguous `## Read-only inspection policy` section whose paragraphs are read together — a stage prompt or a gate error message points at the section, not at "the US1 half of the section" — so there is no intermediate state a partial insertion could safely leave (a policy document missing its `gh api` paragraph mid-implementation would contradict FR-001's "one written policy" the moment any other task tried to cite it). Landing it once in Foundational matches how spec 037's own render landed once, and every later phase's task either edits a genuinely different file (a workflow, a gate script, `CLAUDE.md`) or extends a genuinely independent piece of that one document (a different table row), never a partial re-authoring of the policy prose itself.
