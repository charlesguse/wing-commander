---

description: "Task list for Parameterize Hardcoded Models"
---

# Tasks: Parameterize Hardcoded Models

**Input**: Design documents from `/specs/017-parameterize-hardcoded-models/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/model-override-points.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for workflow YAML in this repository (research.md's Testing note; consistent with spec 016). Validation is `quickstart.md`'s six scenarios, folded into each phase's checkpoint below.

**Organization**: This feature closes the one remaining gap left by spec 016: seven hardcoded `claude-*` literals in `implement.yml` and four missing repository-variable knobs across the wrapper layer. User Story 1 (P1) is the full fix — it both parameterizes `implement.yml`'s literals and wires every wrapper file to a repository variable, because a partial fix (inputs without variable wiring, or variables without inputs to land in) leaves a Bedrock consumer just as stuck as today (spec.md's own framing: "a partially-overridable pipeline is as broken... as a fully hardcoded one"). User Story 2 (P2) and User Story 3 (P3) validate properties of that same change — default-reproduction and completeness — rather than adding new code paths, matching how spec 016's User Story 2 validated User Story 1's output.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Setup and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (GitHub Actions reusable workflows + repository-variable wiring), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the exact literal locations this feature edits, since research.md D1's line numbers were captured during planning and `implement.yml` may have shifted since.

- [X] T001 Re-grep `.github/workflows/implement.yml` for `claude-opus-4-8` and `claude-haiku-4-5` and confirm the seven hits still match research.md D1's inventory (retry guard, retry `--model`, retry metrics-summary `model:`, retry step-summary text, outcome-consolidation `tier=`, progress-comment `--model`, progress-comment metrics-summary `model:`). If any line has moved or a new literal has appeared, update the working inventory before T002 begins — every task below assumes this list is exhaustive and current.

**Checkpoint**: The literal inventory is confirmed current — editing can proceed without re-deriving it mid-task.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: N/A for this feature. Unlike spec 016 (which needed a new shared composite action and an extended preflight branch that every stage depended on), this feature's changes are independent, per-file edits with no shared artifact in between. User Story 1 below is where the actual (and only) blocking work begins.

**Checkpoint**: Skipped — proceed directly to User Story 1.

---

## Phase 3: User Story 1 - Bedrock consumer overrides every model the pipeline uses (Priority: P1) 🎯 MVP

**Goal**: Every model selection the pipeline makes — including `implement.yml`'s retry/escalation and progress-comment paths — resolves through a configurable override point, and every one of those override points is reachable from a repository variable in the consuming repository.

**Independent Test**: Configure all five repository variables (`WING_COMMANDER_SPEC_MODEL`, `WING_COMMANDER_PLAN_MODEL`, `WING_COMMANDER_SUMMARY_MODEL`, `WING_COMMANDER_IMPLEMENT_MODEL`, `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL`) with sentinel values, run each stage (including `implement.yml`'s retry path and `watchdog.yml`'s propose-fix path), and confirm no stage ever invokes a model identifier the operator did not supply — quickstart.md Scenario 2.

### Implementation for User Story 1

- [X] T002 [US1] In `.github/workflows/implement.yml`, add two `workflow_call` inputs — `escalation-model` (`type: string`, `required: false`, `default: claude-opus-4-8`) and `summary-model` (`type: string`, `required: false`, `default: claude-haiku-4-5`) — and replace all seven literals confirmed in T001 (research.md D1, D2): the retry guard becomes `inputs.model != inputs.escalation-model` (was `!= 'claude-opus-4-8'`); the retry step's `--model claude-opus-4-8` becomes `--model ${{ inputs.escalation-model }}`; the retry `wing-commander-metrics-summary` call's `model: claude-opus-4-8` becomes `model: ${{ inputs.escalation-model }}`; the retry step-summary text ("Retry attempt (claude-opus-4-8) also failed...") interpolates `${{ inputs.escalation-model }}`; the outcome-consolidation `tier="claude-opus-4-8"` becomes `tier="${{ inputs.escalation-model }}"`; the progress-comment step's `--model claude-haiku-4-5` becomes `--model ${{ inputs.summary-model }}`; the progress-comment `wing-commander-metrics-summary` call's `model: claude-haiku-4-5` becomes `model: ${{ inputs.summary-model }}`.
- [X] T003 [P] [US1] Wire `.github/workflows/wing-commander-1-intake.yml` to pass `model: ${{ vars.WING_COMMANDER_SPEC_MODEL || 'claude-opus-4-8' }}` into its call to `intake.yml` (contracts/model-override-points.md Layer 2, `WING_COMMANDER_SPEC_MODEL` row).
- [X] T004 [P] [US1] Wire `.github/workflows/wing-commander-2-clarify.yml` to pass `model: ${{ vars.WING_COMMANDER_SPEC_MODEL || 'claude-opus-4-8' }}` into its call to `clarify.yml` (same variable as T003 — `spec/clarify` is one tier).
- [X] T005 [P] [US1] Wire `.github/workflows/wing-commander-3-plan.yml` to pass `model: ${{ vars.WING_COMMANDER_PLAN_MODEL || 'claude-sonnet-5' }}` into its call to `plan.yml`.
- [X] T006 [P] [US1] Wire `.github/workflows/wing-commander-4-tasks.yml` to pass `model: ${{ vars.WING_COMMANDER_PLAN_MODEL || 'claude-sonnet-5' }}` into its call to `tasks.yml` (same variable as T005 — `plan/tasks` is one tier).
- [X] T007 [P] [US1] Wire `.github/workflows/wing-commander-rebase.yml` to pass `model: ${{ vars.WING_COMMANDER_PLAN_MODEL || 'claude-sonnet-5' }}` into its call to `rebase.yml` (same variable as T005/T006 — `rebase` is a `plan/tasks`-tier member location per data-model.md).
- [X] T008 [P] [US1] Extend `.github/workflows/wing-commander-5-implement.yml`'s existing `resolve-model` job with two new outputs — `escalation-model: ${{ vars.WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL || 'claude-opus-4-8' }}` and `summary-model: ${{ vars.WING_COMMANDER_SUMMARY_MODEL || 'claude-haiku-4-5' }}` — and pass both into its call to `implement.yml` alongside the existing `model` output (which consumes `WING_COMMANDER_IMPLEMENT_MODEL`, unchanged), landing on the two new inputs T002 declares.
- [X] T009 [P] [US1] Wire `.github/workflows/wing-commander-6-finalize.yml` to pass `summary-model: ${{ vars.WING_COMMANDER_SUMMARY_MODEL || 'claude-haiku-4-5' }}` into its call to `finalize.yml`.
- [X] T010 [P] [US1] Wire `.github/workflows/wing-commander-7-cleanup.yml` to pass `summary-model: ${{ vars.WING_COMMANDER_SUMMARY_MODEL || 'claude-haiku-4-5' }}` into its call to `cleanup.yml` (same variable as T009 — `triage/summary` is one tier).
- [X] T011 [US1] In `.github/workflows/watchdog.yml`, add two direct `vars.*` reads mirroring its existing `vars.WING_COMMANDER_WATCHDOG_PAUSED`/`vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` pattern (research.md D4 — this file is `release.yml` Gate 1b's documented exception, so no wrapper-side `resolve-model` job is needed): the `diagnose` step's `diagnose-model` input resolves `${{ vars.WING_COMMANDER_SUMMARY_MODEL || 'claude-haiku-4-5' }}`, and the existing `propose-fix-model` input resolves `${{ vars.WING_COMMANDER_IMPLEMENT_MODEL || 'claude-sonnet-5' }}` (newly wired to the existing implement-tier variable, no `model:opus` label logic — that label only applies to `implement.yml`'s own primary attempt).
- [X] T012 [US1] Add four new rows to `docs/setup.md`'s "3. Repository variables" table, placed adjacent to the existing `WING_COMMANDER_IMPLEMENT_MODEL` row (research.md D6): `WING_COMMANDER_SPEC_MODEL` (default `claude-opus-4-8`), `WING_COMMANDER_PLAN_MODEL` (default `claude-sonnet-5`), `WING_COMMANDER_SUMMARY_MODEL` (default `claude-haiku-4-5`), `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` (default `claude-opus-4-8`), each with a one-line "Meaning" matching its tier from data-model.md.

**Checkpoint**: User Story 1 is fully functional — quickstart.md Scenario 2 (full override) and Scenario 3 (partial override / independence) both pass; every model selection in the pipeline, including retry/escalation and watchdog's propose-fix path, resolves through a repository variable.

---

## Phase 4: User Story 2 - Existing consumer keeps current behavior with no configuration (Priority: P2)

**Goal**: Confirm that with no repository variables set, every stage — including `implement.yml`'s retry and progress-comment paths — selects exactly the model it selects today.

**Independent Test**: Run every stage with no overrides supplied and confirm each model invocation matches the model that stage invokes in the current pipeline, including on retry/escalation paths — quickstart.md Scenario 1.

### Implementation for User Story 2

- [ ] T013 [US2] Desk-check T002's new inputs against research.md D1's literal inventory: confirm `escalation-model`'s `default: claude-opus-4-8` and `summary-model`'s `default: claude-haiku-4-5` reproduce the exact values every one of the seven replaced literals held, and confirm no other reusable stage workflow's existing `model`/`summary-model`/`diagnose-model`/`propose-fix-model` input default changed as a side effect of T003–T011 (quickstart.md Scenario 1, first half).
- [ ] T014 [US2] Desk-check T003–T011's `vars.X || 'default'` (and, for `watchdog.yml`, `${VAR:-default}`-equivalent) expressions against contracts/model-override-points.md Layer 2: confirm each of the five variables' documented default is what actually resolves when the variable is unset, and separately confirm an explicitly-blank value (`gh variable set ... --body ""`) resolves identically, since GitHub Actions `||` and bash parameter expansion both treat `''` as falsy (FR-009; quickstart.md Scenario 4).

**Checkpoint**: User Stories 1 AND 2 both hold — quickstart.md Scenarios 1–4 pass.

---

## Phase 5: User Story 3 - Maintainer can confirm no model remains hardcoded (Priority: P3)

**Goal**: Confirm no executable model selection remains embedded in pipeline logic anywhere in `.github/workflows/`.

**Independent Test**: Audit the pipeline's executable logic and confirm every model selection resolves to a configurable override point with a default, with no model identifier embedded directly in the selection logic — quickstart.md Scenario 6.

### Implementation for User Story 3

- [ ] T015 [US3] Run quickstart.md Scenario 6's grep audit — `grep -rn "claude-opus-4-8\|claude-haiku-4-5\|claude-sonnet-5\|claude-fable-5" .github/workflows/*.yml` filtered to exclude `default:` lines and prose comments — and confirm zero remaining matches where a `claude-*` string is used directly as a `--model` flag value, a `model:`/`diagnose-model:`/`propose-fix-model:`/`summary-model:` field value, or a bash variable assignment outside an input's own `default:` (SC-001).

**Checkpoint**: All three user stories are independently functional — the full quickstart.md scenario set (1–6) passes.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Static validation and a full scenario walkthrough across the whole feature.

- [ ] T016 [P] Validate every workflow file touched by T002–T011 parses as valid YAML and, where applicable, embedded `run:` scripts pass `bash -n`, matching `.github/workflows/lint-workflows.yml`'s own CI checks — run locally or trigger `lint-workflows.yml` itself.
- [ ] T017 Confirm `release.yml` Gate 1b's `vars\.` grep scope (research.md D5) is unaffected: the eight gated files (`intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`, `cleanup.yml`, `rebase.yml`) contain zero `vars.*` reads after T002–T012 — every new `vars.*` read landed either in a `wing-commander-*.yml` wrapper file (outside Gate 1b's scope) or in `watchdog.yml` (T011, already excluded). Also confirm the "every agent step declares `--model` and `--max-turns`" sub-check still holds for `implement.yml`'s retry and progress-comment steps after T002 (same flag count, different right-hand side).
- [ ] T018 Walk `specs/017-parameterize-hardcoded-models/quickstart.md`'s full scenario set (1–6) end-to-end against the finished workflow files, recording in the PR body which were exercised live (e.g. via a scratch repository or throwaway test issue) versus desk-checked only.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Skipped — no shared prerequisite artifact.
- **User Story 1 (Phase 3)**: Depends on Setup (T001 confirms the exact literals T002 edits). T003–T011 do not depend on T002 (different files) and may proceed in parallel with it; T012 documents the variable names/defaults already fixed by contracts/model-override-points.md, so it may also run in parallel, though it reads most naturally as the last task in the phase.
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T013/T014 desk-check the exact wiring T002–T011 produced).
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T015's audit is only meaningful once T002's literals are actually replaced).
- **Polish (Phase 6)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: Independently implementable and testable after Setup — the only story with no dependency on another story's tasks.
- **User Story 2 (P2)**: Validates User Story 1's output; independently testable once its own phase completes (quickstart.md Scenarios 1 and 4).
- **User Story 3 (P3)**: Audits User Story 1's output for completeness; independently testable once its own phase completes (quickstart.md Scenario 6).

### Within User Story 1

- T002 (the `implement.yml` inputs) and T003–T011 (wrapper wiring) touch disjoint files and have no ordering requirement between them.
- T008 (the `implement` wrapper's new outputs) is easiest to reason about once T002's input names are settled, but nothing prevents writing it first — both are fixed by contracts/model-override-points.md before either task starts.
- T012 (docs) is safest last, since it's the one task that summarizes every variable name from T003–T011.

### Parallel Opportunities

- T003 through T011 each touch a distinct workflow file and can all run in parallel with each other and with T002.
- T013 and T014 (User Story 2) touch no files (desk-check only) and can run in parallel with each other.
- T016 (lint validation) is parallel-safe with T017/T018 (desk-check/scenario walkthrough) since it only reads the finished files.

---

## Parallel Example: User Story 1 wrapper wiring

```bash
# Launch together — nine different files, same mechanical pattern:
Task: "Wire .github/workflows/implement.yml with escalation-model/summary-model inputs, replacing 7 literals"
Task: "Wire .github/workflows/wing-commander-1-intake.yml with WING_COMMANDER_SPEC_MODEL"
Task: "Wire .github/workflows/wing-commander-2-clarify.yml with WING_COMMANDER_SPEC_MODEL"
Task: "Wire .github/workflows/wing-commander-3-plan.yml with WING_COMMANDER_PLAN_MODEL"
Task: "Wire .github/workflows/wing-commander-4-tasks.yml with WING_COMMANDER_PLAN_MODEL"
Task: "Wire .github/workflows/wing-commander-rebase.yml with WING_COMMANDER_PLAN_MODEL"
Task: "Extend wing-commander-5-implement.yml's resolve-model job with escalation-model/summary-model outputs"
Task: "Wire .github/workflows/wing-commander-6-finalize.yml with WING_COMMANDER_SUMMARY_MODEL"
Task: "Wire .github/workflows/wing-commander-7-cleanup.yml with WING_COMMANDER_SUMMARY_MODEL"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the literal inventory)
2. Complete Phase 3: User Story 1 (all seven literals parameterized, all five variables wired end-to-end)
3. **STOP and VALIDATE**: Run quickstart.md Scenarios 2 and 3 against the finished wiring
4. This alone delivers the entire feature's user-facing value — every remaining phase validates properties of this one change rather than adding new override points

### Incremental Delivery

1. Setup → literal inventory confirmed
2. Add User Story 1 → validate Scenarios 2/3 → mergeable increment (MVP, full Bedrock override coverage)
3. Add User Story 2 → validate Scenarios 1/4 explicitly (no regression for existing consumers) → mergeable increment (confidence before merge)
4. Add User Story 3 → validate Scenario 6 (completeness audit) → mergeable increment (maintainer sign-off surface)
5. Polish → validate the full Scenario 1–6 sweep together, plus lint and the Gate 1b desk-check

### Why User Story 1 alone is the complete fix, unlike spec 016

Spec 016 could stage its rollout because "prove the mechanism on one stage" (US1) and "extend to every stage" (US3) were genuinely separable — an adopter got real, if partial, value from `intake.yml` alone. This feature has no such seam: FR-001 and FR-006 require every override point to exist *and* be independently reachable, and spec.md's own priority rationale is explicit that "a partially-overridable pipeline is as broken for [a Bedrock consumer] as a fully hardcoded one." Splitting the seven-literal fix from the four-variable wiring would leave input-only or variable-only half-states that satisfy neither. User Story 1 therefore includes both; User Story 2 and User Story 3 are verification passes over that one change, not additional functionality.
