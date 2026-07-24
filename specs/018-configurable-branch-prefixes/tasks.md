---

description: "Task list for Configurable Branch Prefixes & Consumer-Modifiable Naming"
---

# Tasks: Configurable Branch Prefixes & Consumer-Modifiable Naming

**Input**: Design documents from `/specs/018-configurable-branch-prefixes/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/branch-prefix-override-points.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for workflow YAML in this repository (plan.md's Testing note; consistent with specs 014/016/017). Validation is `quickstart.md`'s seven scenarios, folded into each phase's checkpoint below.

**Organization**: FR-001–FR-010 require every one of the five branch-type prefixes (`spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`) to become overridable *and* independently reachable from a repository variable, with a fail-closed validation check before any branch is created. User Story 1 (P1) is that whole mechanism — Layer 1 (`workflow_call` inputs on the nine reusable/watchdog workflows), Layer 2 (repository-variable wiring in the eight wrapper files), and Layer 3 (the `wing-commander-preflight` validation check) — because a partial wiring (inputs without variables, or variables without the validation that makes FR-010 true) leaves the feature unusable, mirroring how spec 017's User Story 1 bundled its own override points end to end. User Story 2 (P1, equal priority) verifies that same change reproduces today's behavior exactly when unconfigured. User Story 3 (P2) makes the resulting surface discoverable in documentation. Phase 2 (Foundational) exists this time — unlike spec 017 — because the new `wing-commander-preflight` validation check (Layer 3) is a genuine shared prerequisite the three CREATE-capable stages in User Story 1 all depend on.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (GitHub Actions reusable workflows + a shared composite action + repository-variable wiring + documentation), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the exact literal locations this feature edits, since `research.md` and `contracts/branch-prefix-override-points.md` captured line-level detail during planning and the nine workflow files may have shifted since.

- [X] T001 Re-grep `.github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase,watchdog}.yml`, `.github/workflows/wing-commander-{1-intake,2-clarify,3-plan,4-tasks,5-implement,6-finalize,7-cleanup,rebase}.yml`, and `.github/actions/wing-commander-preflight/action.yml` for the literals `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/` (including the two `startsWith(github.event.pull_request.head.ref, ...)` trigger guards in `wing-commander-3-plan.yml` and `wing-commander-4-tasks.yml` — plan.md's Summary explicitly names these as hardcoded LOCATE sites in scope) and confirm every hit still matches `contracts/branch-prefix-override-points.md`'s Layer 1/Layer 2 tables. If any line has moved or a new literal has appeared, update the working inventory before T002 begins — every task below assumes this list is exhaustive and current.

**Checkpoint**: The literal inventory is confirmed current — editing can proceed without re-deriving it mid-task.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `wing-commander-preflight`'s new `branch-prefixes` check (Layer 3, research.md D4) is a genuine shared prerequisite: the three CREATE-capable stages in User Story 1 (`intake.yml`, `plan.yml`, `tasks.yml`) each need this check to exist before their own tasks can wire a `branch-prefixes:` value into it.

- [X] T002 In `.github/actions/wing-commander-preflight/action.yml`, add a new optional input `branch-prefixes` (`type: string`, `required: false`, `default: ""`) and a new check block (numbered after the existing five) in the composite's single `run:` step that, only when `$BRANCH_PREFIXES` is non-empty: (1) parses it as newline-separated `type=value` pairs; (2) fails via the existing `fail()` helper naming the offending `type` if any `value` is empty; (3) fails naming the offending `type`/`value` if the portion before the value's single trailing `/` does not match `^[A-Za-z0-9][A-Za-z0-9._-]*$` or the value does not end in exactly one `/`; (4) fails naming both offending `type`s if any two of the supplied values are equal or one is a literal string-prefix of the other (research.md D4's collision rule — e.g. `spec/` and `spec/sub/` collide). Empty/unset `branch-prefixes` performs no check, so every other call site that doesn't pass it (`clarify`, `finalize`, `rebase`, `implement`, `cleanup`) is unaffected.

**Checkpoint**: `wing-commander-preflight` can validate a full five-value prefix set and fails closed with `::error::` + `$GITHUB_STEP_SUMMARY` on any violation — ready for the three CREATE stages to wire into it.

---

## Phase 3: User Story 1 - Customize branch prefixes for the pipeline (Priority: P1) 🎯 MVP

**Goal**: Every CREATE and LOCATE site across the nine branch-owning workflows (`intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase`, `watchdog`) resolves its branch-type prefix from a declared override point instead of a literal, every override point is reachable from a repository variable via this repo's own wrapper wiring, and an invalid/colliding configured value fails the run before any branch is created.

**Independent Test**: Configure a custom prefix for at least one pipeline-created branch type, run the corresponding stage, and confirm the branch is created with the configured prefix while every downstream stage still finds and operates on that branch (quickstart.md Scenario 2/3).

### Implementation for User Story 1 — Layer 1 (reusable-workflow inputs) + Layer 3 wiring

- [X] T003 [P] [US1] In `.github/workflows/intake.yml`, add five `workflow_call` inputs — `spec-draft-prefix` (`default: spec-draft/`, CREATE) and `spec-prefix`, `plan-prefix`, `tasks-prefix`, `impl-prefix` (defaults `spec/`, `plan/`, `tasks/`, `impl/`, validation-only) — replace the literal `spec-draft/` in the "Allocate feature number" step's `git ls-remote` glob, the agent prompt's branch-create/PR-create instructions (steps 5–6), the "Resolve created spec" step, and the "Label spec PR to match the issue" step with `${{ inputs.spec-draft-prefix }}`; and pass all five resolved values as a newline-separated `type=value` list into the existing "Preflight" step's `branch-prefixes:` input (T002) so an invalid/colliding value fails before "Allocate feature number" runs (FR-010).
- [X] T004 [P] [US1] In `.github/workflows/clarify.yml`, add a `spec-draft-prefix` `workflow_call` input (`default: spec-draft/`) and replace the literal in the `ref: spec-draft/${{ steps.ctx.outputs.spec-slug }}` checkout step (line ~205) with `ref: ${{ inputs.spec-draft-prefix }}${{ steps.ctx.outputs.spec-slug }}`.
- [X] T005 [US1] In `.github/workflows/plan.yml`, add five `workflow_call` inputs — `spec-draft-prefix` (`default: spec-draft/`, LOCATE — slug derivation from `HEAD_REF`), `spec-prefix`, `plan-prefix` (defaults `spec/`, `plan/`, CREATE), `tasks-prefix`, `impl-prefix` (defaults `tasks/`, `impl/`, validation-only) — replace the literal `spec-draft/` in the `HEAD_REF#spec-draft/` slug-derivation line (~149), the literal `spec/` in the branch-create/reuse block, `spec_branch` field, and PR-head/verification steps (~295–299, 397, 434, 444, 519, 588–597, 632), and the literal `plan/` in the branch-create block, duplicate-guard `ls-remote`, and `gh pr list --head` (~302–312, 508–541, 559–561) with the corresponding input reference; and pass all five resolved values into the existing "Preflight" step's `branch-prefixes:` input (FR-010, before the `spec/`/`plan/` branch-create steps run).
- [X] T006 [US1] In `.github/workflows/tasks.yml`, add five `workflow_call` inputs — `spec-prefix`, `plan-prefix` (defaults `spec/`, `plan/`, LOCATE — `resolve-spec`'s mode-based `prefix="tasks/"`/`prefix="plan/"` selection at line ~161–163 and the `origin/spec/$SLUG` references at ~500–505), `tasks-prefix` (default `tasks/`, CREATE+LOCATE — branch-create, `ls-remote` duplicate guard, `gh pr list --head`, and the mode-based prefix selection), `spec-draft-prefix`, `impl-prefix` (defaults `spec-draft/`, `impl/`, validation-only) — replace every literal identified in T001's inventory (~161–163, 344–346, 447–467, 500–524, 564) with the corresponding input reference in both the `resolve-spec` job (shared by `mode: generate` and `mode: approved`) and the `tasks` job; and pass all five resolved values into the existing "Preflight" step's `branch-prefixes:` input (FR-010, before `git checkout -b tasks/...` runs).
- [X] T007 [P] [US1] In `.github/workflows/implement.yml`, add a `spec-prefix` `workflow_call` input (`default: spec/`, LOCATE only — no branch-topology change, research.md "No change to implement.yml's branch behavior") and replace every literal `origin/spec/$SLUG` reference (~505, 509–510, 514, 528, 660, 664–665, 669, 684) with `origin/${{ inputs.spec-prefix }}$SLUG` via a resolved shell variable.
- [X] T008 [P] [US1] In `.github/workflows/finalize.yml`, add a `spec-prefix` `workflow_call` input (`default: spec/`, LOCATE — `gh pr list --head`/`gh pr create --head`) and replace every literal `spec/$SLUG` reference (~260–294, 472–495) with the resolved input value via a shell variable.
- [X] T009 [P] [US1] In `.github/workflows/rebase.yml`, add a `spec-prefix` `workflow_call` input (`default: spec/`, LOCATE — `git ls-remote --heads origin 'spec/*'` discovery) and replace the literal glob at line ~258 and every downstream `spec/$SLUG` reference used as an actual git ref (the `git push --force-with-lease origin "HEAD:refs/heads/spec/$SLUG"` destination at ~586, plus the step-summary/log interpolations at ~410–652 that name the same branch) with the resolved input value via a shell variable.
- [X] T010 [US1] In `.github/workflows/cleanup.yml`, add all five `workflow_call` inputs (`spec-draft-prefix`, `spec-prefix`, `plan-prefix`, `tasks-prefix`, `impl-prefix`, all five defaults — LOCATE + DELETE, full-lifecycle teardown) and replace every literal in the PR-outcome classifier `case` blocks (~158–163, 705–726), the `delete_branch` calls and `impl/$SLUG-iter*` glob (~445–449), the slug-stripping sites (~525, 540, 612–615, 726), and the manual-cleanup instructions printed on the mark-stalled path (~828, 842–845) with the corresponding input reference.
- [X] T011 [US1] In `.github/workflows/watchdog.yml`, add five direct `vars.WING_COMMANDER_*_PREFIX` reads (mirroring its existing `vars.WING_COMMANDER_SUMMARY_MODEL` exception — this file is `release.yml` Gate 1b's documented exception, not one of the eight gated stages) with bash `${VAR:-default}` fallback, and replace the literal `case "$HEAD_BRANCH"` slug-recovery block (~240–245: `spec-draft/*`, `spec/*`, `plan/*`, `tasks/*`, `impl/*`) with the five resolved shell variables as `case` patterns.

### Implementation for User Story 1 — Layer 2 (repository-variable wrapper wiring)

- [X] T012 [P] [US1] In `.github/workflows/wing-commander-1-intake.yml`, wire all five `WING_COMMANDER_{SPEC_DRAFT,SPEC,PLAN,TASKS,IMPL}_PREFIX` variables (`||` defaults `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`) into its call to `intake.yml`'s five new inputs from T003.
- [X] T013 [P] [US1] In `.github/workflows/wing-commander-2-clarify.yml`, wire `spec-draft-prefix: ${{ vars.WING_COMMANDER_SPEC_DRAFT_PREFIX || 'spec-draft/' }}` into its call to `clarify.yml`'s new input from T004.
- [X] T014 [US1] In `.github/workflows/wing-commander-3-plan.yml`, wire all five `WING_COMMANDER_*_PREFIX` variables into its call to `plan.yml`'s five new inputs from T005, AND parameterize the job's own `startsWith(github.event.pull_request.head.ref, 'spec-draft/')` trigger guard to `startsWith(github.event.pull_request.head.ref, vars.WING_COMMANDER_SPEC_DRAFT_PREFIX || 'spec-draft/')` (plan.md Summary names this trigger guard as a hardcoded LOCATE site in scope for this feature — FR-003 requires it to resolve from the same configured value as the rest of the spec-draft branch type).
- [X] T015 [US1] In `.github/workflows/wing-commander-4-tasks.yml`, wire all five `WING_COMMANDER_*_PREFIX` variables into both the `tasks` job's call to `tasks.yml` (`mode: generate`) and the `tasks-approved` job's call (`mode: approved`), AND parameterize both jobs' own trigger guards — the `tasks` job's `startsWith(..., 'plan/')` to `startsWith(..., vars.WING_COMMANDER_PLAN_PREFIX || 'plan/')`, and the `tasks-approved` job's `startsWith(..., 'tasks/')` to `startsWith(..., vars.WING_COMMANDER_TASKS_PREFIX || 'tasks/')`.
- [X] T016 [P] [US1] In `.github/workflows/wing-commander-5-implement.yml`, wire `spec-prefix: ${{ vars.WING_COMMANDER_SPEC_PREFIX || 'spec/' }}` into its call to `implement.yml`'s new input from T007.
- [X] T017 [P] [US1] In `.github/workflows/wing-commander-6-finalize.yml`, wire `spec-prefix: ${{ vars.WING_COMMANDER_SPEC_PREFIX || 'spec/' }}` into its call to `finalize.yml`'s new input from T008.
- [X] T018 [P] [US1] In `.github/workflows/wing-commander-7-cleanup.yml`, wire all five `WING_COMMANDER_*_PREFIX` variables into its call to `cleanup.yml`'s five new inputs from T010.
- [X] T019 [P] [US1] In `.github/workflows/wing-commander-rebase.yml`, wire `spec-prefix: ${{ vars.WING_COMMANDER_SPEC_PREFIX || 'spec/' }}` into its call to `rebase.yml`'s new input from T009.

**Checkpoint**: User Story 1 is fully functional — quickstart.md Scenario 2 (full override) and Scenario 3 (partial override / independence) both pass; every branch-prefix CREATE and LOCATE site in the pipeline resolves through a configurable override point reachable from a repository variable, and Scenario 5 (invalid/colliding override) fails closed before any branch is created.

---

## Phase 4: User Story 2 - Sensible defaults require zero configuration (Priority: P1)

**Goal**: Confirm that with no naming configuration present, every stage produces identical branch names, PRs, and labels to the pre-feature pipeline.

**Independent Test**: Run the full pipeline in a repository with no naming configuration present and confirm behavior is identical to the current pipeline (quickstart.md Scenario 1).

### Implementation for User Story 2

- [ ] T020 [US2] Desk-check every new input's `default:` added in T003–T011 against `contracts/branch-prefix-override-points.md` Layer 1: confirm each of the five defaults (`spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`) exactly reproduces the literal it replaced, with no other existing input's default changed as a side effect (quickstart.md Scenario 1).
- [ ] T021 [US2] Desk-check every `vars.X || 'default'` expression wired in T012–T019 (and `watchdog.yml`'s bash `${VAR:-default}` equivalent from T011) against `contracts/branch-prefix-override-points.md` Layer 2: confirm each variable's documented default resolves when unset, and confirm an explicitly-blank value (`gh variable set ... --body ""`) resolves identically to unset, since GitHub Actions `||` and bash parameter expansion both treat `''` as falsy (FR-004; quickstart.md Scenario 4).

**Checkpoint**: User Stories 1 AND 2 both hold — quickstart.md Scenarios 1–5 pass.

---

## Phase 5: User Story 3 - Discover and configure all customizable naming in one place (Priority: P2)

**Goal**: An adopter can enumerate every consumer-modifiable branch prefix, its default, and its effect from a single documented location, without reading stage internals.

**Independent Test**: From the documentation and a single configuration location, an adopter can identify every consumer-modifiable naming value and its default, and change any of them without reading stage internals (quickstart.md Scenario 6).

### Implementation for User Story 3

- [ ] T022 [P] [US3] Add five new rows to `docs/setup.md` §3 "Repository variables" table, adjacent to the existing model/gate-mode rows: `WING_COMMANDER_SPEC_DRAFT_PREFIX` (`spec-draft/`), `WING_COMMANDER_SPEC_PREFIX` (`spec/`), `WING_COMMANDER_PLAN_PREFIX` (`plan/`), `WING_COMMANDER_TASKS_PREFIX` (`tasks/`), `WING_COMMANDER_IMPL_PREFIX` (`impl/`), each with a one-line "Meaning" naming its branch type and default (FR-007, SC-004).
- [ ] T023 [P] [US3] In `docs/adoption.md`, reword the "Side effects land in your repository only" bullet's sentence "The branch *prefixes* `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`... are the shared artifact contract" (~line 661) to state each prefix is configurable via its repository variable with the literal shown as its default, and reword the `intake`/`clarify`/`plan`/`tasks`/`cleanup` stage-reference tables' `Side effects`/`Preconditions` cells that name a literal prefix (~681, 711, 723) the same way.
- [ ] T024 [P] [US3] In `docs/architecture.md`, reword the "No branch-name assumptions" bullet's clause "only the `spec-draft/ spec/ plan/ tasks/ impl/` *prefixes* are contract" (~line 60) and the "Branches" bullet's three sub-bullets (~89–92) to state each prefix is configurable-with-default, and apply the same treatment to the cleanup/watchdog sections' literal-prefix mentions (~264–272).
- [ ] T025 [P] [US3] In `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, reword the Universal Behavior bullet's "The `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/` branch *prefixes* remain part of the shared artifact contract" (~lines 43–45) to describe them as configurable-with-defaults, and add a new row to the Common Inputs table (~lines 20–28) documenting the prefix inputs newly common across the CREATE-capable stages.
- [ ] T026 [US3] In `.specify/memory/constitution.md`, reword the Operational Constraints "Branch conventions" line (~line 42) — which currently omits `tasks/` — to name all five prefixes as "the pipeline's default branch prefixes... (consumer-configurable via repository variables — see docs/setup.md)", and add a new Sync Impact Report header at the top of the file documenting the PATCH-level version bump (1.2.0 → 1.2.1) per the Governance section's semver rule, matching the style of the existing 1.1.0→1.2.0 report.

**Checkpoint**: All three user stories are independently functional — the full quickstart.md scenario set (1–7) passes.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Static validation and a full scenario walkthrough across the whole feature.

- [ ] T027 [P] Validate every workflow/action file touched by T002–T019 parses as valid YAML and, where applicable, embedded `run:` scripts pass `bash -n`, matching `.github/workflows/lint-workflows.yml`'s own CI checks — run locally or trigger `lint-workflows.yml` itself.
- [ ] T028 Confirm `release.yml` Gate 1b's `vars\.` grep scope is unaffected: the eight gated files (`intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`, `cleanup.yml`, `rebase.yml`) contain zero `vars.*` reads after T003–T011 — every new `vars.*` read landed either in a `wing-commander-*.yml` wrapper file (T012–T019, outside Gate 1b's scope) or in `watchdog.yml` (T011, already excluded).
- [ ] T029 Run quickstart.md Scenario 7's maintainer-audit grep across `.github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase,watchdog}.yml` and confirm every remaining `spec-draft/|plan/|tasks/|impl/` match is either a `default:` line, a wrapper's `vars.X || 'default'` expression, or a prose comment — zero matches where a literal prefix is used directly in a `git checkout -b`, `git ls-remote`, `gh pr list --head`, `${VAR#prefix}`, or `case prefix/*)` construct (SC-001, User Story 3).
- [ ] T030 Run quickstart.md Scenario 5 (both Setup A — invalid characters — and Setup B — collision) against the finished `wing-commander-preflight` check from T002, confirming the run fails at the Preflight step with an `::error::` naming the offending variable(s)/value(s) before any `git checkout -b`/push step runs, and that `$GITHUB_STEP_SUMMARY` carries the same message (FR-010).
- [ ] T031 Walk `specs/018-configurable-branch-prefixes/quickstart.md`'s full scenario set (1–7) end-to-end against the finished workflow files, recording in the PR body which were exercised via a live/dogfooded run versus desk-checked only.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001 confirms `wing-commander-preflight`'s current structure before T002 edits it) — BLOCKS User Story 1's T003, T005, T006 (the three CREATE stages each pass `branch-prefixes:` into the check T002 adds).
- **User Story 1 (Phase 3)**: Depends on Foundational. T003, T005, T006 (CREATE stages) depend on T002; T004, T007–T011 (LOCATE-only/watchdog stages) do not depend on T002 and may proceed in parallel with it. T012–T019 (Layer 2 wrapper wiring) depend on their corresponding Layer 1 task (e.g. T012 depends on T003; T014 depends on T005) since each wrapper wires into input names its Layer 1 task declares.
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T020/T021 desk-check the exact wiring T003–T019 produced).
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T022–T026 document the variable names/defaults T003–T019 already fixed; independent of User Story 2).
- **Polish (Phase 6)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: The only story with no dependency on another story's tasks (beyond the Foundational phase).
- **User Story 2 (P1)**: Validates User Story 1's output; independently testable once its own phase completes (quickstart.md Scenarios 1 and 4).
- **User Story 3 (P2)**: Documents User Story 1's output; independently testable once its own phase completes (quickstart.md Scenario 6).

### Within User Story 1

- T003, T005, T006 (the three CREATE stages) each depend on T002 (Foundational) for their `branch-prefixes:` wiring, but not on each other — different files.
- T004, T007, T008, T009 touch disjoint files from T003/T005/T006/T010/T011 and have no ordering requirement against them.
- T010 (cleanup) and T011 (watchdog) do not depend on T002 (neither forwards into `wing-commander-preflight` — full-lifecycle teardown/diagnosis stages read all five prefixes operationally, not for validation).
- Each Layer 2 task (T012–T019) depends only on its own corresponding Layer 1 task(s), not on the other Layer 2 tasks.

### Parallel Opportunities

- T004 and T007–T011 (LOCATE-only/watchdog/cleanup stages) can run in parallel with each other and with T002's foundational work.
- T003, T005, T006 can run in parallel with each other once T002 completes.
- T012, T013, T016, T017, T018, T019 each touch a distinct wrapper file with no cross-dependency and can run in parallel once their respective Layer 1 task completes; T014 and T015 are not marked [P] because each also edits its file's own trigger-guard `if:` condition, which is easiest to reason about as a single sequential edit alongside that file's `with:` wiring.
- T020 and T021 (User Story 2) touch no files (desk-check only) and can run in parallel with each other.
- T022–T025 (User Story 3 docs) touch disjoint files and can all run in parallel; T026 (constitution) is safest run after them since its Sync Impact Report references the same rewording.
- T027 (lint validation) is parallel-safe with T028/T029 (desk-check/grep audit) since it only reads the finished files.

---

## Parallel Example: User Story 1 Layer 1 (after Foundational completes)

```bash
# Launch together — nine different files, same mechanical pattern:
Task: "Add 5 prefix inputs to .github/workflows/intake.yml, wire branch-prefixes into Preflight"
Task: "Add spec-draft-prefix input to .github/workflows/clarify.yml"
Task: "Add 5 prefix inputs to .github/workflows/plan.yml, wire branch-prefixes into Preflight"
Task: "Add 5 prefix inputs to .github/workflows/tasks.yml, wire branch-prefixes into Preflight"
Task: "Add spec-prefix input to .github/workflows/implement.yml"
Task: "Add spec-prefix input to .github/workflows/finalize.yml"
Task: "Add spec-prefix input to .github/workflows/rebase.yml"
Task: "Add all 5 prefix inputs to .github/workflows/cleanup.yml"
Task: "Add direct vars.* prefix reads to .github/workflows/watchdog.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the literal inventory)
2. Complete Phase 2: Foundational (`wing-commander-preflight`'s `branch-prefixes` check)
3. Complete Phase 3: User Story 1 (all nine workflow/watchdog files parameterized, all eight wrapper files wired)
4. **STOP and VALIDATE**: Run quickstart.md Scenarios 2, 3, and 5 against the finished wiring
5. This alone delivers the entire feature's user-facing value — every remaining phase validates or documents properties of this one change rather than adding new override points

### Incremental Delivery

1. Setup + Foundational → literal inventory confirmed, validation check ready
2. Add User Story 1 → validate Scenarios 2/3/5 → mergeable increment (MVP, full prefix override coverage with fail-closed validation)
3. Add User Story 2 → validate Scenarios 1/4 explicitly (no regression for existing consumers) → mergeable increment (confidence before merge)
4. Add User Story 3 → validate Scenario 6 (discoverability) → mergeable increment (adoption-friction reduction)
5. Polish → validate the full Scenario 1–7 sweep together, plus lint and the Gate 1b desk-check

### Why User Story 1 alone is the complete fix

FR-001/FR-003/FR-006/FR-010 together require every override point to exist, be independently reachable, and fail closed on an invalid value — spec.md's own priority rationale is explicit that a customization feature that regresses the default experience "is not shippable," and a half-wired override point (an input with no variable path to it, or a variable with no validation) leaves User Story 1's own acceptance scenarios unmet. User Story 1 therefore includes all three layers (inputs, wrapper wiring, validation); User Story 2 and User Story 3 are verification and documentation passes over that one change, not additional functionality.
