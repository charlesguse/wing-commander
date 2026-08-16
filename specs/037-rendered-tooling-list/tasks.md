---

description: "Task list for The Prompt's Tooling List States What the Run Actually Permits"
---

# Tasks: The Prompt's Tooling List States What the Run Actually Permits

**Input**: Design documents from `/specs/037-rendered-tooling-list/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/tooling-statement-render.md, contracts/contract-agreement-check.md, quickstart.md

**Tests**: Requested explicitly — unlike most prior specs in this repository (no automated coverage exists for workflow YAML by default), User Story 4/FR-014/FR-015 make executable coverage a first-class requirement here: two new gate scripts, each with an inline mutation-based self-test proving it can fail. T011 and T013/T014 below are that coverage, not an optional addition.

**Organization**: The render fix itself (research.md D1-D5) is one atomic edit to one shell step — `contracts/tooling-statement-render.md` specifies it as a single algorithm, not four independently-shippable pieces — so it lands once, in Foundational, exactly as spec 026's composite action landed once in that feature's own Foundational phase. Every later phase either extends that render to its real consumer (US1's prompt rewrite), validates a distinct slice of it against `quickstart.md` (US1/US2's own Independent Tests), or builds the governance around it that didn't exist before (US3's declared contract, US4's executable coverage, US5's run-record visibility). Phases follow the spec's own priority order: US1-US4 are all P1 and appear in spec.md's own sequence; US5 (P3) is diagnostic only and follows.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (one existing composite action's render step corrected, one existing workflow's two prompt sites rewritten, two new gate scripts, five existing docs corrected), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the exact gate numbers this feature's two new checks will register under, since `lint-workflows.yml`'s existing numbering may have shifted since research.md was written (research.md's own caveat: "the number is cosmetic, not part of any contract").

- [ ] T001 Run `grep -n "Gate [0-9]* —" .github/workflows/lint-workflows.yml` to find the highest-numbered existing gate, and record the next two free numbers for use in T012 and T015 below (research.md recorded 18/19 as placeholders as of plan time; re-confirm against the current file rather than assuming they are still free).

**Checkpoint**: Gate numbers for T012/T015 are confirmed current.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The corrected render is the single piece of logic every user story either extends, validates, or governs. It must be correct before any later phase can meaningfully proceed.

- [ ] T002 Rewrite the `shell_commands` render in the `Compose tool args` step of `.github/actions/wing-commander-tool-args/action.yml` (replacing the existing step-4 comment block and loop, lines 180-208) per `contracts/tooling-statement-render.md`: (1) classify each `effective_allowed`/`effective_disallowed` entry as `ANY` (bare `Bash`), `PREFIX(cmd)` (`Bash(cmd:*)`/`Bash(cmd *)`), `EXACT(cmd)` (`Bash(cmd)`), or `NOT_SHELL` (anything else — excluded from every later step, research.md D1); (2) for each allow grant, determine whether a disallowed grant covers it per D2's table (`ANY` deny covers everything; `PREFIX(cmd)` deny covers `EXACT(cmd)`/`PREFIX(cmd)` allows for the same command; `EXACT(cmd)` deny covers only `EXACT(cmd)` allow for the same command; a disallowed grant for a different command never covers), dropping covered allow grants from the render only — `effective_allowed`/`effective_disallowed` themselves are never rewritten (FR-003); (3) for a surviving `ANY` allow, name any surviving command-specific disallowed grants as exceptions rather than dropping the whole grant (D3); (4) group surviving `PREFIX`/`EXACT` allow grants by command — a command with any surviving `PREFIX` grant renders as `PREFIX` (bare backticked text), a command with only surviving `EXACT` grant(s) renders as `EXACT` (with a trailing `(exact command only)` qualifier) — each command appears once (D4); (5) emit one of D5's four complete-sentence templates as the new `shell_commands` value: `EMPTY` → `` This run permits no shell command. ``, `UNRESTRICTED` → `` This run permits any shell command. ``, `UNRESTRICTED_EXCEPT` → `` This run permits any shell command except: `cmd1`, `cmd2`. ``, `ENUMERATED` → `` This run permits these shell commands: `cmd1`, `cmd2`. ``, commands joined in first-seen order. Keep the existing `echo "shell-commands=$shell_commands" >> "$GITHUB_OUTPUT"` line (line 213) unchanged in shape — only `shell_commands`'s computed value changes. Also correct the `shell-commands` output's `description:` (lines 61-70) to describe the corrected sentence-shaped value (a complete sentence, subtraction applied, unrestricted/exact/prefix distinguished) rather than the old comma-joined-fragment description.

**Checkpoint**: The composite's `shell-commands` render is correct in isolation for every legal configuration — ready for its consumer and for governance to build on.

---

## Phase 3: User Story 1 - The agent is told the truth about what it can run (Priority: P1) 🎯 MVP

**Goal**: `implement.yml`'s prompt states its shell tooling as a statement that agrees with what the run's composed lists actually enforce — no denied command named, and the statement narrows correctly when a consumer's configuration narrows the allow list.

**Independent Test**: Drive the shipped composition with a configuration that denies a shell command the stage allows by default, and confirm that command is absent from the statement handed to the agent while the enforced lists themselves are unchanged; then drive it with no configuration at all and confirm the statement names exactly the stage's default shell commands.

### Implementation for User Story 1

- [ ] T003 [US1] In `.github/workflows/implement.yml`, rewrite both tooling paragraphs per research.md D6 — the `cycle` step (lines 577-591, reading `steps.tool-args-cycle.outputs.shell-commands`) and the `retry` step (lines 792-806, reading `steps.tool-args-retry.outputs.shell-commands`), byte-identical apart from the step-id reference: drop the phrase "are exactly ... — that list is rendered from this step's own --allowedTools, so it is authoritative", and instead embed the now-complete `shell-commands` sentence directly, followed by "That statement is derived from this run's own composed allowed and disallowed tool lists, so a command's presence or absence here matches what this run actually permits." Keep the rest of the existing operational guidance (auto-denial burns turns; note missing commands for the human instead of retrying variants; use the Grep tool, not shell `grep`; lint-tool conditioning on list membership) unchanged in substance — this task changes only the overclaiming phrase and its replacement (FR-009).
- [ ] T004 [US1] Validate T002/T003 against `quickstart.md`'s static-validation bullets 1-4 (spec.md Acceptance Scenarios 1.1-1.5): invoke the composite's extracted `run:` block (by hand, or a throwaway script) with no consumer configuration at all and confirm the statement names exactly the step's hard-coded default shell commands (SC-003); with `extra-disallowed-tools` denying — exactly or by prefix — a shell command the defaults allow, and confirm that command is absent from the statement while the composed `allowed-tools`/`disallowed-tools` outputs are byte-identical to the no-subtraction case; with `allowed-tools-override` replacing the allowed list wholesale, and confirm the statement is derived from the replacement, not the defaults; with a command denied via `extra-disallowed-tools` and separately re-allowed via `extra-allowed-tools` (spec 026's explicit-allow-beats-default-deny), and confirm the statement names it as permitted, agreeing with the enforced outcome rather than either input alone.

**Checkpoint**: User Story 1 is fully functional and independently testable — the statement agrees with the enforced outcome for every subtraction scenario, and `implement.yml`'s real prompt reflects it.

---

## Phase 4: User Story 2 - The statement is well-formed for every legal configuration (Priority: P1)

**Goal**: Every legal tool-list shape — unrestricted, empty, exact-only, prefix, both forms together — produces a complete, grammatical sentence whose content matches what that grant actually permits.

**Independent Test**: Drive the shipped composition once per legal configuration shape — unrestricted shell grant, no shell grant, exact-command grant, prefix grant, the same command granted in both forms — and confirm each produces a complete sentence whose content matches what that grant actually permits.

### Implementation for User Story 2

- [ ] T005 [US2] Validate T002 against `quickstart.md`'s static-validation bullets 5-11 (spec.md Acceptance Scenarios 2.1-2.6 and the partial-overlap edge case): a bare `Bash` allow with no matching deny renders `` This run permits any shell command. ``; a bare `Bash` allow plus one command-specific deny renders `` This run permits any shell command except: `cmd`. ``; an allowed list with no `Bash`/`Bash(...)` entry at all but other tools present renders `` This run permits no shell command. `` as a complete sentence with those other tools untouched; `Bash(cmd)` granted with no `:*` renders `` `cmd` (exact command only) `` distinguishing it from the any-arguments form; both `Bash(cmd)` and `Bash(cmd:*)` granted together render `cmd` once, in the `PREFIX` form; a deny that only partially overlaps an allow (`Bash(cmd)` denied while `Bash(cmd:*)` is allowed) leaves `cmd` stated. Confirm every case above (plus T004's cases) ends in a period with no unresolved template text, dangling connective, or empty enumeration (SC-002).

**Checkpoint**: User Stories 1 AND 2 both hold — the render is correct under subtraction and grammatically complete for every legal shape.

---

## Phase 5: User Story 3 - An adopter can see every output the composite emits (Priority: P1)

**Goal**: The composite's published interface documents `shell-commands` accurately and completely, and a machine check holds the declared and emitted output sets in agreement in both directions.

**Independent Test**: Read the composite's published interface and confirm that the set of outputs it documents is exactly the set the action emits; then add an output to the action without documenting it and confirm a check fails.

### Implementation for User Story 3

- [ ] T006 [P] [US3] Replace the "Caveats as shipped" block (lines 64-90) in `specs/026-configurable-tool-lists/contracts/tool-composition-action.md` with the corrected render contract, carried over from `specs/037-rendered-tooling-list/contracts/tooling-statement-render.md` (research.md D10) — the four former divergences become the guarantees D2/D3/D5 now hold, described as guarantees rather than caveats; keep the surrounding Outputs table's row structure and the three existing output names unchanged.
- [ ] T007 [P] [US3] In `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, rewrite the "What the agent is *told*" paragraph (lines 57-72): drop the "Four divergences... are known and being fixed under specs/037-rendered-tooling-list" sentence and state the corrected behavior directly — the statement excludes every fully-denied command, states unrestricted grants as permitting any command (with named exceptions when a partial deny applies), and distinguishes exact-only from any-arguments grants — keeping the existing pointer to `tool-composition-action.md#outputs`.
- [ ] T008 [P] [US3] In `docs/architecture.md`, correct the Security section paragraph describing `shell-commands` (lines 216-230) to match the corrected render — note the subtraction against the disallowed list, rather than describing the statement as derived from the allowed list alone.
- [ ] T009 [P] [US3] Add a one-line pointer to `tool-composition-action.md#outputs` in `specs/026-configurable-tool-lists/contracts/tool-list-inputs.md`, noting that the composed lists also drive a stage's stated-tooling output where one exists (FR-013).
- [ ] T010 [P] [US3] Add one sentence to the existing "Tool-list inputs" bullet (lines 801-815) in `docs/adoption.md`, noting the composed lists also drive the stage's own stated-tooling prompt where one exists, pointing to `tool-composition-action.md#outputs`.
- [ ] T011 [US3] Create `.github/scripts/verify-tool-args-contract.py` per `contracts/contract-agreement-check.md` (research.md D9): extract the `Compose tool args` step's `run:` block from `.github/actions/wing-commander-tool-args/action.yml` (same extraction the T013 harness uses, so the two scripts share one parser rather than each maintaining its own YAML-parsing logic); collect three name sets — `action.yml`'s `outputs:` keys, every `<name>` emitted via `echo "<name>=<value>" >> "$GITHUB_OUTPUT"` in the extracted block, and the first-column entries of `tool-composition-action.md`'s `## Outputs` table (as corrected by T006); fail (matching the existing `::error::` + `GITHUB_STEP_SUMMARY` gate convention, non-zero exit) naming the specific output and which set(s) it is missing from whenever the three sets disagree in any direction; add a self-test phase running the same check against two scratch fixtures — a copy of `action.yml` with a fourth `outputs:` entry added but never emitted (expect "declared but not emitted"), and a copy with the `shell-commands` entry deleted from `outputs:` while the `run:` block still emits it (expect "emitted but not declared", reproducing this spec's own motivating defect as a regression fixture) — asserting both fixtures fail for the expected reason and the real, unmodified files pass.
- [ ] T012 [US3] Register `verify-tool-args-contract.py` in `.github/workflows/lint-workflows.yml` as `- name: Gate <N> — every output the tool-args composite emits is declared, and every declared output is emitted` / `run: python3 .github/scripts/verify-tool-args-contract.py`, using the first gate number confirmed in T001.

**Checkpoint**: An adopter can predict `shell-commands`'s content from documentation alone, and an undeclared or removed output fails a check before merge.

---

## Phase 6: User Story 4 - The behavior cannot regress silently (Priority: P1)

**Goal**: Every guarantee from User Stories 1 and 2 is exercised by an executable test against the shipped composition, and reverting any one of them fails a distinct test.

**Independent Test**: Break each guarantee in turn — remove the subtraction, remove the unrestricted-shell case, remove the empty-list fallback, remove the deduplication — and confirm a distinct test fails for each; then confirm the whole suite passes on the finished implementation.

### Implementation for User Story 4

- [ ] T013 [US4] Create `.github/scripts/verify-tooling-statement.py` per research.md D8: extract the `Compose tool args` step's `run:` block from `.github/actions/wing-commander-tool-args/action.yml` (mirroring `verify-metrics-turn-accounting.py`'s `shipped_script()` pattern), drive it via `wc_shell_harness.run_step()` once per representative configuration — no consumer configuration at all; a default-covering deny; a wholesale allow replacement; a denied-then-re-allowed command; a bare `Bash` allow with no deny; a bare `Bash` allow with one command-specific deny; an allowed list with no `Bash` entry but other tools present; `Bash(cmd)` only; `Bash(cmd)` and `Bash(cmd:*)` both granted; a partial-overlap deny; a non-shell-only allowed list — and assert the `shell-commands` line in `$GITHUB_OUTPUT` matches the expected sentence for each case, and that `allowed-tools`/`disallowed-tools` are byte-identical to the no-subtraction values in the subtraction cases.
- [ ] T014 [US4] Add a `MUTATIONS`-style self-test phase to `verify-tooling-statement.py`, following Gate 11's pattern (`verify-metrics-turn-accounting.py`): revert the subtraction (D2), the unrestricted-shell case (D3/D5's `UNRESTRICTED`/`UNRESTRICTED_EXCEPT` templates), the empty-list fallback (D5's `EMPTY` template), and the deduplication (D4) one at a time against a scratch copy of the extracted script, re-run the full suite against each mutated copy, and assert every mutation turns at least one *distinct* named case red (User Story 4 Acceptance Scenario 2, FR-015).
- [ ] T015 [US4] Register `verify-tooling-statement.py` in `.github/workflows/lint-workflows.yml` as `- name: Gate <N+1> — the tooling statement matches what the run actually permits` / `run: python3 .github/scripts/verify-tooling-statement.py`, using the second gate number confirmed in T001.
- [ ] T016 [US4] Run `verify-gate-wiring.py` (Gate 10) locally and confirm it auto-detects both `verify-tooling-statement.py` and `verify-tool-args-contract.py` as wired with no manifest edit needed; then run the full `lint-workflows.yml` gate suite, including both new gates, and confirm it passes against the finished implementation (User Story 4 Acceptance Scenarios 1 and 3).

**Checkpoint**: Every guarantee from User Stories 1-3 is now covered by an executable, self-testing check registered in the gate suite — reverting any one of them fails before merge.

---

## Phase 7: User Story 5 - A maintainer can see what the agent was told (Priority: P3)

**Goal**: A maintainer reading a completed run's own record can see the tooling statement that run handed to its agent, without reading the workflow source.

**Independent Test**: Complete a run and confirm the statement it handed to its agent is recoverable from the run's own record without reading the workflow source.

### Implementation for User Story 5

- [ ] T017 [US5] In the `Compose tool args` step's `run:` block (`.github/actions/wing-commander-tool-args/action.yml`), append a `**Tooling statement**: <value>` line to `$GITHUB_STEP_SUMMARY` (research.md D7), carrying the literal rendered `shell_commands` sentence, alongside — not replacing — the existing `✅ wing-commander-tool-args (...): composed tool lists.` line.
- [ ] T018 [US5] Validate `quickstart.md`'s end-to-end scenario check: trigger `implement.yml`'s dogfood wrapper (or a direct `workflow_call`) with `extra-disallowed-tools` set to one command in the `implement.cycle` step's default allowed list, and confirm — from the run's own `$GITHUB_STEP_SUMMARY` alone, no workflow source read required — that the `wing-commander-tool-args` step's summary carries the `**Tooling statement**:` line naming the run's actual permitted commands and omitting the one just denied (SC-009, SC-010), and that the same sentence appears in the `Implement and converge (cycle)` step's own prompt log rather than the old "are exactly ... — that list is ... authoritative" phrasing.

**Checkpoint**: All five user stories hold independently — correctness (US1/US2), governance (US3), regression-safety (US4), and diagnosability (US5).

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Static validation across every changed file and a full walk of `quickstart.md`.

- [ ] T019 [P] Run `actionlint` and `yamllint` (per spec 025's existing CI gate) across `.github/actions/wing-commander-tool-args/action.yml`, `.github/workflows/implement.yml`, and `.github/workflows/lint-workflows.yml`, confirming zero errors.
- [ ] T020 Walk `quickstart.md`'s full scenario set end-to-end against the finished implementation (static validation, self-test verification, contract-agreement check, end-to-end scenario check, documentation check, regression check), recording in the PR body which were exercised via a live/dogfooded run versus desk-checked only.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup only loosely (T001's gate numbers aren't needed until T012/T015) — BLOCKS every user story phase, since T002 is the render every later phase extends, validates, or governs.
- **User Story 1 (Phase 3)**: Depends on Foundational (T003 embeds T002's corrected output; T004 validates T002/T003 together).
- **User Story 2 (Phase 4)**: Depends on Foundational (T005 validates T002 directly); independent of User Story 1's own tasks.
- **User Story 3 (Phase 5)**: Depends on Foundational (T006-T011 describe/check the render T002 produces); T012 depends on T001 (gate number) and T011 (script must exist).
- **User Story 4 (Phase 6)**: Depends on Foundational (T013 drives T002's shipped script); T015 depends on T001 and T013/T014; T016 depends on T012 and T015 both being registered.
- **User Story 5 (Phase 7)**: Depends on Foundational (T017 extends the same step T002 rewrote).
- **Polish (Phase 8)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on another story's tasks beyond Foundational.
- **User Story 2 (P1)**: No dependency on another story's tasks beyond Foundational; independently testable in parallel with User Story 1.
- **User Story 3 (P1)**: No dependency on another story's tasks beyond Foundational; independently testable in parallel with User Stories 1/2.
- **User Story 4 (P1)**: No dependency on another story's tasks beyond Foundational (T011 from User Story 3 and T013 from User Story 4 share an extraction approach but are independently written and independently useful).
- **User Story 5 (P3)**: No dependency on another story's tasks beyond Foundational.

### Parallel Opportunities

- T006, T007, T008, T009, T010 (User Story 3's documentation tasks) touch five disjoint files and can all run in parallel once Foundational (T002) is complete.
- T011 (User Story 3's contract-agreement script) and T013 (User Story 4's render-correctness script) touch disjoint new files and depend only on Foundational — they can be written in parallel even though they appear in sequential phases above.
- T004 (User Story 1) and T005 (User Story 2) both validate T002's already-finished render and touch no files — they can run in parallel with each other once T002 (and, for T004, T003) completes.
- T019 (Polish lint) can run in parallel with T020 (Polish quickstart walk) once every prior phase is complete.

---

## Parallel Example: User Story 3 documentation

```bash
# Launch together — five different files, all correcting the same
# render's documentation once T002 has landed:
Task: "Replace 'Caveats as shipped' in specs/026-configurable-tool-lists/contracts/tool-composition-action.md"
Task: "Correct 'What the agent is told' paragraph in specs/010-reusable-pipeline/contracts/stage-interfaces.md"
Task: "Correct Security section paragraph in docs/architecture.md"
Task: "Add pointer to tool-composition-action.md#outputs in specs/026-configurable-tool-lists/contracts/tool-list-inputs.md"
Task: "Add one sentence to the Tool-list inputs bullet in docs/adoption.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm gate numbers)
2. Complete Phase 2: Foundational (the corrected render, proven in isolation)
3. Complete Phase 3: User Story 1 (the real prompt in `implement.yml` rewritten, and T004's subtraction scenarios validated)
4. **STOP and VALIDATE**: Run `quickstart.md`'s static-validation bullets 1-4 against the finished render
5. This alone closes the failure the feature exists to close (spec 036's four unrun tasks) — every remaining phase either proves an additional property of the same render (US2), builds the governance around it (US3, US4), or adds diagnosability (US5)

### Incremental Delivery

1. Setup + Foundational → the corrected render exists and is proven standalone
2. Add User Story 1 → validate subtraction scenarios, `implement.yml`'s real prompt is fixed → mergeable increment (MVP — the failure mode that cost spec 036 is closed)
3. Add User Story 2 → validate grammar/template scenarios on the same render → mergeable increment (well-formedness confidence)
4. Add User Story 3 → documentation corrected, contract-agreement gate registered → mergeable increment (the published-contract half of the feature)
5. Add User Story 4 → render-correctness gate with mutation self-test registered → mergeable increment (regression-proof)
6. Add User Story 5 → step-summary line added → mergeable increment (diagnosability)
7. Polish → lint every changed file, full quickstart sweep

### Why the render (Foundational) is one task, not four

`contracts/tooling-statement-render.md` specifies classification (D1), subtraction (D2), the unrestricted-exception case (D3), broadening/dedup (D4), and the four sentence templates (D5) as one algorithm operating on one shell step's already-composed inputs — there is no intermediate state a partial implementation could safely emit (e.g. subtraction without templates would still hit the old dangling-em-dash defect on empty input). Landing it as a single Foundational task matches how spec 026's own composite action landed once, and every later phase's story-scoped task is either a real extension to a different file (US1's `implement.yml` prompt, US5's step-summary line) or a validation/governance task against the one finished render, never a partial reimplementation of it.
