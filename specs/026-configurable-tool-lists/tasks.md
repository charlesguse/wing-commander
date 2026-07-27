---

description: "Task list for Configurable Allowed/Disallowed Tool Lists Across Pipeline Stages"
---

# Tasks: Configurable Allowed/Disallowed Tool Lists Across Pipeline Stages

**Input**: Design documents from `/specs/026-configurable-tool-lists/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/tool-list-inputs.md, contracts/tool-composition-action.md, contracts/stage-default-tool-lists.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for workflow YAML in this repository (plan.md's Testing note; consistent with specs 014/016/017/018/025). Validation is `quickstart.md`'s static-validation bullets and end-to-end scenario checks, folded into each phase's checkpoint below.

**Organization**: Unlike spec 018 (where branch-prefix wiring was asymmetric per CREATE/LOCATE stage and had to land as one bundled change), this feature's wiring is mechanically identical at every call site (research.md D1/D2/D5: one composite action, four uniform inputs, one call per internal agent step) — the only per-stage variable is which literal default list that step already ships with. That uniformity means the mechanism can be proven on a single representative stage before paying to wire the other eight, so the phases below follow the spec's own priorities literally: Foundational builds the shared composite action once; User Story 1 (P1) wires exactly one stage (`clarify.yml` — the same stage `contracts/tool-list-inputs.md`'s own example uses) and proves append-allowed; User Story 2 (P1) proves append-disallowed against that same wiring; User Story 3 (P2) proves replace and the FR-010 conflict on that same wiring; User Story 4 (P2) extends the identical pattern to the remaining eight stages and audits 100% coverage (SC-004). Each phase after Foundational is independently checkpointable and shippable, matching the tasks-template's incremental-delivery model.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (GitHub Actions reusable workflows + one new shared composite action + normative contract doc + `docs/` updates), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the exact literal `--allowedTools`/`--disallowedTools` values this feature will move out of inline `claude_args:` and into composite-action call sites, since `contracts/stage-default-tool-lists.md` captured them during planning and the 9 stage files may have shifted since.

- [X] T001 Re-grep every `claude_args:` block across `.github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase,watchdog}.yml` (14 agent steps total) for their current literal `--allowedTools`/`--disallowedTools` values and confirm each still matches `contracts/stage-default-tool-lists.md`'s table exactly, entry for entry. If any literal has moved or changed, update the working inventory before T002 begins — every task below assumes this table is exhaustive and current. **Drift found**: `watchdog.diagnose`'s current disallowed list is `WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*)` — missing `ScheduleWakeup,Monitor,SendMessage` that the contract table claims. T016 uses the actual current literal (not the contract's) so SC-005's byte-identical-when-unset invariant holds for that step. Every other stage's literals match the contract exactly.

**Checkpoint**: The default-tool-list inventory is confirmed current — composing against it can proceed without re-deriving it mid-task.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The new `wing-commander-tool-args` composite action (research.md D1) is the single place FR-001–FR-004, FR-007–FR-012's composition/precedence/validation rule is implemented. Every stage in every later phase calls it, so it must exist and be proven correct in isolation first.

- [X] T002 Create `.github/actions/wing-commander-tool-args/action.yml` per `contracts/tool-composition-action.md`: inputs `default-allowed-tools` (required), `default-disallowed-tools` (required), `extra-allowed-tools` (optional, default `""`), `extra-disallowed-tools` (optional, default `""`), `allowed-tools-override` (optional, default `"__unset__"`), `disallowed-tools-override` (optional, default `"__unset__"`), `step-label` (required); outputs `allowed-tools`, `disallowed-tools`. Single `composite`/`shell: bash` run step implementing, in order: (1) FR-010 validation — for each direction independently, fail via a `fail()` helper mirroring `wing-commander-preflight/action.yml`'s convention (`::error::` + `$GITHUB_STEP_SUMMARY` line, `exit 1`) naming `step-label`, the direction, and both values, when that direction's `extra-*` input is non-empty AND its `*-override` input is not the literal string `__unset__`; (2) research.md D4's composition — `effective_allowed = allowed-tools-override if provided (non-sentinel) else split(default-allowed-tools) ∪ split(extra-allowed-tools)`, `effective_disallowed = (disallowed-tools-override if provided else split(default-disallowed-tools) ∪ split(extra-disallowed-tools)) − explicit_allow`, where `explicit_allow` is `split(extra-allowed-tools)` in append mode or the full override-allowed list in override mode (never `default-allowed-tools`); (3) deduplicate each composed set on `,`, trimming whitespace, preserving first-seen order; (4) emit `allowed-tools`/`disallowed-tools` via `$GITHUB_OUTPUT`, comma-joined, consistent with `wing-commander-context/action.yml`'s output style.
- [X] T003 Standalone-validate T002's composite action against every bullet in `quickstart.md`'s "Static validation" section (no unset inputs → outputs equal `default-*` inputs exactly; `extra-allowed-tools` only → default list plus the one entry; `allowed-tools-override=""` → empty output, distinct from the unset case; both `extra-allowed-tools` and a non-sentinel `allowed-tools-override` set → non-zero exit with `::error::` naming both; `extra-allowed-tools` naming a tool also in `default-disallowed-tools` → that tool present in `allowed-tools` output and absent from `disallowed-tools` output (FR-011); `extra-disallowed-tools` naming a tool also in `default-allowed-tools` → tool present in both outputs; duplicate entry across default and extra → collapses to one). Invoke by extracting the action's `run:` block into a standalone script with representative env vars, or via a throwaway `workflow_dispatch` test workflow — either is acceptable, record which was used.

**Checkpoint**: `wing-commander-tool-args` composes and validates correctly in isolation — ready for any stage to call.

---

## Phase 3: User Story 1 - Append extra allowed tools to a stage (Priority: P1) 🎯 MVP

**Goal**: A downstream consumer can add one or two tools to a stage's allowed list without restating the stage's defaults, proven on one representative stage.

**Independent Test**: Configure `clarify.yml` with one additional allowed tool, run the stage, and confirm the agent has both the additional tool and the pipeline's normal default tools without the consumer restating them (spec.md User Story 1's own Independent Test).

### Implementation for User Story 1

- [X] T004 [US1] In `.github/workflows/clarify.yml`: add four new `workflow_call` inputs per `contracts/tool-list-inputs.md` — `extra-allowed-tools` (string, default `""`), `extra-disallowed-tools` (string, default `""`), `allowed-tools-override` (string, default `"__unset__"`), `disallowed-tools-override` (string, default `"__unset__"`); add a `Compose tool args (clarify)` step (`id: tool-args-clarify`) calling `./.github/actions/wing-commander-tool-args` immediately before the stage's existing `anthropics/claude-code-action@v1` step, with `default-allowed-tools: "Read,Edit,Write,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(cat:*),Bash(gh issue view:*),Bash(gh issue comment:*),Bash(gh pr list:*),Bash(gh pr view:*),Bash(gh pr edit:*)"`, `default-disallowed-tools: "WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage"`, the four `extra-*`/`*-override` inputs passed through from `inputs.*`, and `step-label: "clarify"`; replace that agent step's inline `--allowedTools "..."`/`--disallowedTools "..."` literals in `claude_args:` with `--allowedTools "${{ steps.tool-args-clarify.outputs.allowed-tools }}"`/`--disallowedTools "${{ steps.tool-args-clarify.outputs.disallowed-tools }}"`, guarding the step with `if: steps.tool-args-clarify.outputs.allowed-tools != ''` per `contracts/tool-composition-action.md`'s documented call-site shape.
- [X] T005 [US1] Desk-check (dogfood run optional) `clarify.yml`'s finished wiring from T004 against `quickstart.md`'s end-to-end checks 1 and 2: with `extra-allowed-tools` set to one tool not in clarify's default list (e.g. `Bash(npm run lint:*)`), confirm the composed `allowed-tools` output is the default list plus that one entry, and every default tool is still present; with none of the four inputs set, confirm the composed `--allowedTools`/`--disallowedTools` values are byte-for-byte identical to the pre-T004 literal strings recorded in T001's inventory (SC-005, spec.md User Story 1 Acceptance Scenario 2).

**Checkpoint**: User Story 1 is fully functional and independently testable on `clarify.yml` — the append-allowed capability and zero-change-when-unset invariant both hold.

---

## Phase 4: User Story 2 - Append extra disallowed tools to a stage (Priority: P1)

**Goal**: A consumer can further restrict a stage by denying one additional tool while every default restriction (and default allowance) stays in place, proven on the same wired stage.

**Independent Test**: Configure `clarify.yml` with one additional disallowed tool, run the stage, and confirm that tool is denied while the pipeline's normal defaults (both allowed and disallowed) still apply (spec.md User Story 2's own Independent Test).

### Implementation for User Story 2

- [X] T006 [US2] Desk-check (dogfood run optional) `clarify.yml`'s finished wiring from T004 against `quickstart.md`'s end-to-end check 3: with `extra-disallowed-tools` set to one tool that is in clarify's default allowed list (e.g. `Bash(gh pr edit:*)`), confirm the composed `disallowed-tools` output contains it in addition to the pipeline's default disallowed entries (spec.md User Story 2 Acceptance Scenario 1), and confirm the composed `allowed-tools` output still nominally contains that tool too (unions don't subtract defaults) while the disallowed-tools composition takes precedence downstream (research.md D4 — "explicit deny beats default allow", spec.md User Story 2 Acceptance Scenario 2).

**Checkpoint**: User Stories 1 AND 2 both hold on `clarify.yml` — append works symmetrically for both directions.

---

## Phase 5: User Story 3 - Replace the entire allowed or disallowed list for a stage (Priority: P2)

**Goal**: A consumer with a substantially different use case can supply a wholesale replacement list instead of layering on top of defaults, and a conflicting append+replace configuration fails before any agent runs.

**Independent Test**: Configure `clarify.yml` with a full replacement allowed list, run the stage, and confirm the agent has exactly the replacement tools and none of the discarded defaults (spec.md User Story 3's own Independent Test).

### Implementation for User Story 3

- [X] T007 [US3] Desk-check (dogfood run optional) `clarify.yml`'s finished wiring from T004 against `quickstart.md`'s end-to-end check 4: with `allowed-tools-override` set to a small custom list that still covers what the `clarify` step needs to complete its lifecycle bookkeeping (e.g. `"Read,Edit,Write,Bash(git commit:*),Bash(git push:*),Bash(gh issue comment:*)"`), confirm the composed `allowed-tools` output is exactly that list — no defaults beyond it (spec.md User Story 3 Acceptance Scenario 1); repeat for `disallowed-tools-override` set to a small custom list, confirming the composed `disallowed-tools` output is exactly that list (spec.md User Story 3 Acceptance Scenario 2).
- [X] T008 [US3] Desk-check (dogfood run optional) `clarify.yml`'s finished wiring from T004 against `quickstart.md`'s end-to-end check 5 (FR-010): with both `extra-allowed-tools` and a non-sentinel `allowed-tools-override` set simultaneously, confirm the `Compose tool args (clarify)` step fails (non-zero exit, `::error::` naming both supplied values) before the `anthropics/claude-code-action@v1` step runs — i.e. the job log shows no Claude credential/cost was exercised.

**Checkpoint**: All three of User Stories 1–3 hold independently on `clarify.yml` — append (both directions), replace (both directions), and the FR-010 conflict guard all behave per spec.

---

## Phase 6: User Story 4 - Configure tool lists consistently across every stage (Priority: P2)

**Goal**: The identical four-input/composite-action pattern proven on `clarify.yml` is extended to every other agent-running stage, reaching 100% coverage (SC-004).

**Independent Test**: Apply an append configuration to each of the remaining agent-running stages and confirm each honors it identically to `clarify.yml`'s behavior from User Story 1 (spec.md User Story 4's own Independent Test).

### Implementation for User Story 4

- [ ] T009 [P] [US4] In `.github/workflows/intake.yml`: add the same four `workflow_call` inputs as T004; add a `Compose tool args (intake)` step calling `./.github/actions/wing-commander-tool-args` immediately before the stage's agent step, with `default-allowed-tools: "Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git checkout:*),Bash(git switch:*),Bash(git push:*),Bash(git branch:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(echo:*),Bash(ls:*),Bash(mkdir:*),Bash(cat:*),Bash(gh issue view:*),Bash(gh issue edit:*),Bash(gh issue comment:*),Bash(gh pr create:*),Bash(gh label create:*)"`, `default-disallowed-tools: "WebFetch,ScheduleWakeup,Monitor,SendMessage"`, `step-label: "intake"`; splice the outputs into `claude_args:` and guard the agent step, exactly as T004 did for `clarify.yml`.
- [ ] T010 [P] [US4] In `.github/workflows/plan.yml`: add the same four `workflow_call` inputs; add two `Compose tool args` steps, one per internal agent step — `tool-args-plan-direct-commit` (`step-label: "plan.direct-commit"`, `default-allowed-tools: "Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(ls:*),Bash(mkdir:*),Bash(cat:*),Bash(.specify/scripts/bash/setup-plan.sh:*),Bash(bash .specify/scripts/bash/setup-plan.sh:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(.specify/scripts/bash/update-agent-context.sh:*),Bash(bash .specify/scripts/bash/update-agent-context.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*)"`) and `tool-args-plan-pr` (`step-label: "plan.pr"`, same default-allowed-tools plus `,Bash(git checkout:*),Bash(git switch:*),Bash(gh pr create:*),Bash(gh pr list:*)`); both steps use `default-disallowed-tools: "WebFetch,ScheduleWakeup,Monitor,SendMessage"` and the same four passthrough inputs; splice each step's own outputs into its corresponding agent step's `claude_args:`, guarded as in T004.
- [ ] T011 [P] [US4] In `.github/workflows/tasks.yml`: add the same four `workflow_call` inputs; add two `Compose tool args` steps — `tool-args-tasks-direct-commit` (`step-label: "tasks.direct-commit"`, `default-allowed-tools: "Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(ls:*),Bash(cat:*),Bash(.specify/scripts/bash/setup-tasks.sh:*),Bash(bash .specify/scripts/bash/setup-tasks.sh:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*)"`) and `tool-args-tasks-pr` (`step-label: "tasks.pr"`, same default-allowed-tools plus `,Bash(git checkout:*),Bash(git switch:*),Bash(gh pr create:*),Bash(gh pr list:*)`); both use `default-disallowed-tools: "WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage"` and the same four passthrough inputs; splice outputs and guard as in T004.
- [ ] T012 [P] [US4] In `.github/workflows/implement.yml`: add the same four `workflow_call` inputs; add three `Compose tool args` steps — `tool-args-cycle` (`step-label: "implement.cycle"`, `default-allowed-tools: "Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(git show:*),Bash(ls:*),Bash(cat:*),Bash(yamllint:*),Bash(actionlint:*),Bash(shellcheck:*),Bash(jq:*),Bash(mkdir:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*),Bash(gh run view:*),Bash(gh run list:*)"`), `tool-args-retry` (`step-label: "implement.retry"`, same default-allowed-tools plus `,Bash(git pull:*),Bash(git fetch:*),Bash(git reset:*)`), and `tool-args-post-progress-comment` (`step-label: "implement.post-progress-comment"`, `default-allowed-tools: "Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(gh issue comment:*)"`); all three use `default-disallowed-tools: "WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage"` and the same four passthrough inputs (D5 — one stage-level input set, three call sites); splice each step's own outputs into its corresponding agent step's `claude_args:`, guarded as in T004.
- [ ] T013 [P] [US4] In `.github/workflows/finalize.yml`: add the same four `workflow_call` inputs; add a `Compose tool args (finalize)` step with `default-allowed-tools: "Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write"`, `default-disallowed-tools: "WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage"`, `step-label: "finalize"`; splice outputs and guard as in T004.
- [ ] T014 [P] [US4] In `.github/workflows/cleanup.yml`: add the same four `workflow_call` inputs; add a `Compose tool args (cleanup)` step with `default-allowed-tools: "Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write"`, `default-disallowed-tools: "WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage"`, `step-label: "cleanup"`; splice outputs and guard as in T004.
- [ ] T015 [P] [US4] In `.github/workflows/rebase.yml`: add the same four `workflow_call` inputs; add a `Compose tool args (rebase)` step with `default-allowed-tools: "Read,Edit,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git add:*),Bash(git rebase --continue:*),Bash(git rebase --abort:*)"`, `default-disallowed-tools: "WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage"`, `step-label: "rebase"`; splice outputs and guard as in T004.
- [ ] T016 [P] [US4] In `.github/workflows/watchdog.yml`: add the same four `workflow_call` inputs; add two `Compose tool args` steps — `tool-args-diagnose` (`step-label: "watchdog.diagnose"`, `default-allowed-tools: "Read,Grep,Bash(gh:*),Bash(git log:*),Bash(git diff:*)"`, `default-disallowed-tools: "WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*),ScheduleWakeup,Monitor,SendMessage"`) and `tool-args-propose-fix` (`step-label: "watchdog.propose-fix"`, `default-allowed-tools: "Read,Grep,Glob,Edit,Write"`, `default-disallowed-tools: "WebSearch,WebFetch,Bash,ScheduleWakeup,Monitor,SendMessage"`); splice each step's own outputs into its corresponding agent step's `claude_args:`, guarded as in T004.
- [ ] T017 [US4] Audit all 9 stage workflow files (`clarify.yml` from T004; `intake.yml`, `plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`, `cleanup.yml`, `rebase.yml`, `watchdog.yml` from T009–T016) against `contracts/tool-list-inputs.md`: confirm every file declares the same four inputs with identical names, types, and defaults; confirm every one of the 14 internal agent steps (per `contracts/stage-default-tool-lists.md`'s "Internal step" column) has its own `Compose tool args` call with a distinct, correctly-labeled `step-label` immediately before its `anthropics/claude-code-action@v1` step; confirm none of the 9 files still has an inline literal `--allowedTools`/`--disallowedTools` value in `claude_args:` (SC-004, 100% coverage — `quickstart.md` end-to-end check 6).

**Checkpoint**: All four user stories are independently functional — every agent-running stage supports append (both directions), replace (both directions), and the FR-010 conflict guard, matching `clarify.yml`'s proven behavior.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation (FR-013, SC-006) and static validation across the whole feature.

- [ ] T018 [P] Extend `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Common inputs" table with the four new inputs, carried over verbatim from `contracts/tool-list-inputs.md` (research.md D7), including the sentinel-default rationale for the two override inputs.
- [ ] T019 [P] Add a new per-stage default tool list reference section/table to `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, carried over verbatim from `contracts/stage-default-tool-lists.md` (research.md D7), reflecting the finished defaults confirmed in T001 and wired in T004/T009–T016.
- [ ] T020 [P] In `docs/architecture.md`, add a pointer to `stage-interfaces.md`'s new tool-list section (T018/T019) and a short append-vs-replace explainer (FR-013).
- [ ] T021 [P] In `docs/adoption.md`, add a pointer to the same reference alongside the existing per-stage prerequisites table, with the same short append-vs-replace explainer, and a note that `allowed-tools-override`/`disallowed-tools-override` on `implement.yml` (or any multi-step stage) apply identically to every internal step (research.md D5's documented consequence).
- [ ] T022 Run `actionlint` and `yamllint` (per spec 025's CI gate) across every changed workflow file (`intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`, `cleanup.yml`, `rebase.yml`, `watchdog.yml`) and the new `.github/actions/wing-commander-tool-args/action.yml`, confirming zero errors.
- [ ] T023 Walk `specs/026-configurable-tool-lists/quickstart.md`'s full scenario set (Static validation bullets, end-to-end checks 1–6, Documentation check) end-to-end against the finished implementation, recording in the PR body which were exercised via a live/dogfooded run versus desk-checked only.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001 confirms the literal defaults T002/T003 and every later phase compose against) — BLOCKS every user story phase.
- **User Story 1 (Phase 3)**: Depends on Foundational (T004 calls the action T002/T003 produced).
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T006 validates against the wiring T004 produced).
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T007/T008 validate against the same T004 wiring); independent of User Story 2.
- **User Story 4 (Phase 6)**: Depends on Foundational directly for T009–T016 (each wires a different stage against T002/T003, independent of `clarify.yml`); T017's audit depends on T004 and T009–T016 all being complete.
- **Polish (Phase 7)**: Depends on all prior phases (T018/T019 document the finished defaults; T022 lints every changed file; T023 walks the full scenario set).

### User Story Dependencies

- **User Story 1 (P1)**: The only story with no dependency on another story's tasks (beyond the Foundational phase).
- **User Story 2 (P1)**: Validates behavior on User Story 1's wiring; independently testable once its own phase completes.
- **User Story 3 (P2)**: Validates behavior on User Story 1's wiring; independently testable once its own phase completes; independent of User Story 2.
- **User Story 4 (P2)**: Extends User Story 1's pattern to the remaining stages; each of T009–T016 is independently testable the moment its own task completes, without waiting for the others.

### Parallel Opportunities

- T009–T016 (all eight remaining stages) touch disjoint files, depend only on Foundational (not on each other or on T004), and can all run in parallel.
- T018, T019, T020, T021 (documentation) touch disjoint files and can all run in parallel once T001/T004/T009–T016 have fixed the final defaults and input shapes they document.
- T005 (US1) and T006 (US2) both validate `clarify.yml`'s already-finished wiring and touch no files — they can run in parallel with each other once T004 completes.
- T007 and T008 (US3) likewise touch no files and can run in parallel with each other once T004 completes.

---

## Parallel Example: User Story 4 (after Foundational + User Story 1 complete)

```bash
# Launch together — eight different files, same mechanical pattern proven on clarify.yml:
Task: "Add 4 tool-list inputs + 1 compose-tool-args call to .github/workflows/intake.yml"
Task: "Add 4 tool-list inputs + 2 compose-tool-args calls to .github/workflows/plan.yml"
Task: "Add 4 tool-list inputs + 2 compose-tool-args calls to .github/workflows/tasks.yml"
Task: "Add 4 tool-list inputs + 3 compose-tool-args calls to .github/workflows/implement.yml"
Task: "Add 4 tool-list inputs + 1 compose-tool-args call to .github/workflows/finalize.yml"
Task: "Add 4 tool-list inputs + 1 compose-tool-args call to .github/workflows/cleanup.yml"
Task: "Add 4 tool-list inputs + 1 compose-tool-args call to .github/workflows/rebase.yml"
Task: "Add 4 tool-list inputs + 2 compose-tool-args calls to .github/workflows/watchdog.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the literal default-tool-list inventory)
2. Complete Phase 2: Foundational (`wing-commander-tool-args` composite action, proven standalone)
3. Complete Phase 3: User Story 1 (`clarify.yml` wired end to end)
4. **STOP and VALIDATE**: Run `quickstart.md` end-to-end checks 1 and 2 against `clarify.yml`
5. This alone proves the entire feature's mechanism on one stage — every remaining phase either validates another property of the same mechanism (US2, US3) or replicates it mechanically to the other eight stages (US4)

### Incremental Delivery

1. Setup + Foundational → composite action ready and unit-proven
2. Add User Story 1 → validate checks 1/2 on `clarify.yml` → mergeable increment (MVP, append-allowed proven end to end)
3. Add User Story 2 → validate check 3 on the same wiring → mergeable increment (append-disallowed confidence)
4. Add User Story 3 → validate checks 4/5 on the same wiring → mergeable increment (replace + FR-010 conflict confidence)
5. Add User Story 4 → wire the remaining 8 stages, audit 100% coverage (SC-004) → mergeable increment (uniform availability, FR-006)
6. Polish → documentation (FR-013/SC-006), lint gate, full quickstart sweep

### Why User Story 1 alone proves the mechanism

Because research.md D1/D2/D5 force every stage's wiring to be mechanically identical (same four inputs, same composite action, same call-site shape — only the literal default lists and `step-label`s differ), proving append-allowed on one stage (`clarify.yml`) exercises the exact same composition/precedence/validation code path (`wing-commander-tool-args`, Phase 2) that every other stage and every other capability (append-disallowed, replace, the FR-010 conflict) will also exercise. User Stories 2 and 3 therefore need no new implementation — only new assertions against `clarify.yml`'s existing wiring — and User Story 4 is a mechanical repetition of User Story 1's own task (T004) across the remaining eight files, not new design.
