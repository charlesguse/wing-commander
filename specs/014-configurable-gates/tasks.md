# Tasks: Configurable Human Review Gates

**Input**: Design documents from `/specs/014-configurable-gates/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/plan-workflow.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for these workflows (plan.md's Testing section); `lint-workflows.yml` (YAML parse + `bash -n`) is the only CI-enforced check, and feature validation is manual via `quickstart.md`. No test tasks are generated.

**Organization**: Tasks are grouped by user story. Almost every task edits the same file (`.github/workflows/plan.yml`), so within-file tasks are ordered sequentially (same pattern as `specs/003-tasks-stage/tasks.md`, the precedent this feature mirrors); only the wrapper and docs tasks are separate files and can run in parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Phase 1: Setup

**Purpose**: Confirm the ground the implementation builds on.

- [ ] T001 Re-read `.github/workflows/plan.yml` (current steps: `resolve-spec` job; `plan` job's `Ensure persistent spec branch` → `Check for a prior planning attempt` (id: `dupe`) → `Create lifecycle issue if missing` (id: `newissue`) → `Report run started on lifecycle issue` → `Checkout spec branch as wing-commander-bot` → `Generate implementation plan` (id: `agent`) → `Verify plan PR and flip stage label` → `Upload Claude execution log` → `Agent run metrics summary`) and `.github/workflows/tasks.yml`'s equivalent `tasks-review`/`agent-auto`/`agent-pr`/`next-workflow` pattern (lines ~288-538) side by side; confirm both match this feature's `contracts/plan-workflow.md` before editing either file.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The new declared inputs, permission grant, and mode-resolution step every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 Add two new `workflow_call` inputs to `.github/workflows/plan.yml`'s `on.workflow_call.inputs` block: `plan-review` (string, default `pr`, description per `contracts/plan-workflow.md`) and `next-workflow` (string, default `""`, description mirroring `tasks.yml`'s existing `next-workflow` input) — placed alongside the existing `model`/`max-turns` inputs.
- [ ] T003 Add `actions: write` to the `plan` job's `permissions:` block in `.github/workflows/plan.yml` (alongside the existing `contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`), needed for the auto-mode dispatch step (permissions contract addendum).
- [ ] T004 Add a "Resolve review mode" step (id: `mode`) to the `plan` job in `.github/workflows/plan.yml`, positioned after "Report run started on lifecycle issue" and before "Checkout spec branch as wing-commander-bot", gated `if: steps.dupe.outputs.skip != 'true'`: read `inputs.plan-review`; unset/empty → `mode=pr`; `pr` → `mode=pr`; `auto` → `mode=auto`; any other non-empty value → `mode=pr` (fails open, never to `auto`) and set an `invalid=true` output carrying the bad value (surfacing wired in Phase 4, US2) — per `contracts/plan-workflow.md`'s resolution table.

**Checkpoint**: `plan.yml` can resolve a review mode and has the permissions/inputs the rest of this feature needs — user story work can begin.

---

## Phase 3: User Story 1 - Skip the plan review gate (Priority: P1) 🎯 MVP

**Goal**: With `plan-review: auto`, after the spec PR merges, the plan is committed directly to `spec/NNN-slug` (no `plan/NNN-slug` branch or PR) and the tasks stage is dispatched automatically — zero human action on the plan artifact.

**Independent Test**: `quickstart.md` Scenario 2 — set `WING_COMMANDER_PLAN_REVIEW=auto`, merge a spec-draft PR, confirm `plan.md` lands on `spec/NNN-slug`, `spec-meta.json` reads `stage: "plan"`, the lifecycle issue records the automatic advance, and `wing-commander-4-tasks.yml` is dispatched — with no `plan/NNN-slug` branch or PR ever created.

### Implementation for User Story 1

- [ ] T005 [US1] Add a "Generate implementation plan (direct commit)" step (id: `agent-auto`) to the `plan` job in `.github/workflows/plan.yml`, `if: steps.dupe.outputs.skip != 'true' && steps.mode.outputs.mode == 'auto'`: same `anthropics/claude-code-action@v1` shape as the existing agent step (`claude_code_oauth_token`, `anthropic_api_key`, `github_token` from `ctx`, `allowed_bots: "github-actions"`, `SPECIFY_FEATURE_DIRECTORY` + `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` env), but the prompt: (1) stays on `spec/${{ needs.resolve-spec.outputs.slug }}` — no `git checkout -b plan/...`; (2) runs `/speckit-plan` (same CI deviations: never wait for input, proceed past `[NEEDS CLARIFICATION]` markers); (3) updates `spec-meta.json` (`stage: "plan"`, `spec_branch`, `issue`); (4) commits `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, `spec-meta.json` (and the agent context file if touched) together as `plan: <slug> (#<issue>)` directly on `spec/<slug>` and pushes — opens no PR; (5) comments on the lifecycle issue (FR-005 text wired in T012). Constraints: edit only inside the spec dir; push only to `spec/<slug>`; open no PR; never merge/approve. `--allowedTools` drops `git checkout/switch/branch` and `gh pr create/list` from the existing agent step's list (data-model.md, plan-workflow.md).
- [ ] T006 [US1] Rename the existing "Generate implementation plan" step's id from `agent` to `agent-pr` in `.github/workflows/plan.yml` and change its `if:` to `steps.dupe.outputs.skip != 'true' && steps.mode.outputs.mode == 'pr'` — no other behavior change (this is today's unmodified `pr`-mode path).
- [ ] T007 [US1] Update the "Agent run metrics summary" step's `if:` in `.github/workflows/plan.yml` from `steps.agent.outcome != 'skipped'` to `(steps.agent-pr.outcome != 'skipped' || steps.agent-auto.outcome != 'skipped')`, mirroring `tasks.yml`'s equivalent step.
- [ ] T008 [US1] Add a "Verify plan committed (auto)" deterministic step to `.github/workflows/plan.yml`, `if: steps.dupe.outputs.skip != 'true' && steps.mode.outputs.mode == 'auto'`: `git fetch origin` the spec branch, confirm `specs/<slug>/plan.md` exists and is non-empty on `origin/spec/<slug>`, and that `spec-meta.json`'s `stage` field there reads exactly `"plan"`; `::error::` + `exit 1` otherwise, mirroring `tasks.yml`'s "Verify tasks committed (auto)" step (FR-007, verification contract).
- [ ] T009 [US1] Change the existing "Verify plan PR and flip stage label" step's `if:` in `.github/workflows/plan.yml` to add `&& steps.mode.outputs.mode == 'pr'` (it stays otherwise unchanged — it only makes sense when a plan PR was opened).
- [ ] T010 [US1] Add a "Flip stage label (auto)" step to `.github/workflows/plan.yml`, `if: steps.dupe.outputs.skip != 'true' && steps.mode.outputs.mode == 'auto'`, running after T008's verification: `gh label create "stage:plan" --force` (same color/description as the existing pr-mode flip), `gh issue edit --add-label "stage:plan"`, `--remove-label "stage:spec"` / `--remove-label "stage:clarify"` (`|| true`) — no PR-labeling step since auto mode opens no PR.
- [ ] T011 [US1] Add a "Dispatch tasks stage (auto)" step to `.github/workflows/plan.yml`, `if: steps.dupe.outputs.skip != 'true' && steps.mode.outputs.mode == 'auto'`, running after T010: when `inputs.next-workflow` is empty, log a standalone-mode note to `$GITHUB_STEP_SUMMARY` and post an issue comment saying no next stage is configured and how to dispatch one manually; otherwise `gh workflow run "$NEXT_WORKFLOW" -f slug="$SLUG"` and log the dispatch to `$GITHUB_STEP_SUMMARY` — mirroring `tasks.yml`'s "Dispatch implement stage (auto)" step and this feature's outbound dispatch contract.
- [ ] T012 [US1] Extend the agent prompt(s) in `.github/workflows/plan.yml` so the lifecycle-issue completion comment is mode-specific: `pr` mode keeps its existing text (plan PR link, "merging advances to task generation"); `auto` mode's text (in the T005 prompt) instead states the plan was committed directly to the spec branch and the tasks stage was dispatched automatically because Gate 3 (plan review) is disabled (FR-005, SC-004; data-model.md Lifecycle issue contract).
- [ ] T013 [US1] Update `.github/workflows/wing-commander-3-plan.yml`: add `plan-review: ${{ vars.WING_COMMANDER_PLAN_REVIEW || 'pr' }}` and `next-workflow: wing-commander-4-tasks.yml` to the `with:` block calling `plan.yml`, and add `actions: write` to the `plan` job's `permissions:` block (needed for the reusable workflow's auto-mode dispatch) — mirroring `wing-commander-4-tasks.yml`'s existing `tasks-review`/`next-workflow` wiring.

**Checkpoint**: Auto-mode Gate 3 bypass works end-to-end (SC-001); default `pr` mode is untouched in behavior (verified in Phase 5).

---

## Phase 4: User Story 2 - Configure each configurable gate independently (Priority: P2)

**Goal**: An invalid `WING_COMMANDER_PLAN_REVIEW` value falls back to `pr` and is surfaced (not silently applied); `plan-review` and `tasks-review` operate independently.

**Independent Test**: `quickstart.md` Scenario 3 — set `WING_COMMANDER_PLAN_REVIEW=maybe`, merge a spec PR, confirm Gate 3 behaves as `pr`, a `::warning::` annotation and step-summary line name the bad value, and the lifecycle issue's "planning started" comment notes the fallback. `quickstart.md` Scenario 5 — set `plan-review=auto` and `tasks-review=pr` together, confirm each gate behaves per its own setting.

### Implementation for User Story 2

- [ ] T014 [US2] Extend the "Resolve review mode" step (T004) in `.github/workflows/plan.yml`: when `inputs.plan-review` is a non-empty value other than `pr`/`auto`, emit `::warning::WING_COMMANDER_PLAN_REVIEW='<value>' is not a recognized value (expected 'pr' or 'auto') — Gate 3 defaulted to enabled ('pr').` and append the same message to `$GITHUB_STEP_SUMMARY` (FR-008).
- [ ] T015 [US2] Extend the "Report run started on lifecycle issue" step in `.github/workflows/plan.yml` (or append a follow-up `gh issue comment` immediately after it) so that when T014's `invalid` output is set, the "planning started" comment additionally names the invalid `WING_COMMANDER_PLAN_REVIEW` value and states Gate 3 defaulted to enabled (FR-008, data-model.md's "Invalid configuration" lifecycle-issue contract).
- [ ] T016 [US2] Desk-check gate independence per `quickstart.md` Scenario 5: confirm no step added in Phase 2/3 reads or is conditioned on `vars.WING_COMMANDER_TASKS_REVIEW` (or vice versa in `tasks.yml`), and that `plan-review`/`tasks-review` are wired by two separate wrapper files into two separate `workflow_call` inputs with no shared state (FR-003, SC-005) — record the confirmation in the PR body.

**Checkpoint**: Invalid configuration is safe and auditable; the two gates are confirmed independent.

---

## Phase 5: User Story 3 - Safe, discoverable defaults (Priority: P3)

**Goal**: Unconfigured repositories see zero behavior change (`pr` mode, identical to pre-feature `plan.yml`), and `WING_COMMANDER_PLAN_REVIEW` is discoverable the same way `WING_COMMANDER_TASKS_REVIEW` already is.

**Independent Test**: `quickstart.md` Scenario 1 — with `WING_COMMANDER_PLAN_REVIEW` unset, confirm the plan PR still opens and nothing auto-dispatches. `quickstart.md` Scenario 6 — a mid-lifecycle configuration change doesn't affect an already-open plan PR.

### Implementation for User Story 3

- [ ] T017 [US3] Desk-check default (`pr`) mode per `quickstart.md` Scenario 1 and Scenario 6 against the finished `.github/workflows/plan.yml`: with `plan-review` unset or `pr`, confirm the step sequence (`agent-pr` → pr-only verify-and-flip) is byte-identical in effect to the pre-feature workflow, and that a plan PR opened before a later `WING_COMMANDER_PLAN_REVIEW=auto` change is unaffected (SC-002) — record the confirmation in the PR body.
- [ ] T018 [P] [US3] Add a `WING_COMMANDER_PLAN_REVIEW` row to `docs/setup.md`'s repository-variables table (default `pr`; `pr` = open a plan PR and wait for a human merge, `auto` = commit the plan directly and dispatch the tasks stage), alongside the existing `WING_COMMANDER_TASKS_REVIEW` row (FR-009, SC-003).
- [ ] T019 [P] [US3] Update `docs/adoption.md`'s "3. `wing-commander-3-plan.yml`" wrapper example (`with:` block) to include `plan-review: ${{ vars.WING_COMMANDER_PLAN_REVIEW || 'pr' }}` and `next-workflow: wing-commander-4-tasks.yml`, and add `actions: write` to that job's `permissions:` block — matching T013 and mirroring the "4. `wing-commander-4-tasks.yml`" example's existing `tasks-review`/`next-workflow` shape.
- [ ] T020 [P] [US3] Update the `reusable-plan.yml` row in `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s Inputs cell to add `plan-review` (string `pr`\|`auto`, default `pr`) and `next-workflow` (string, default `""`) — mirroring the `reusable-tasks.yml` row's phrasing for `tasks-review`/`next-workflow`.
- [ ] T021 [P] [US3] Rewrite the "Stage 2 — Plan" section of `docs/architecture.md` to describe both `pr` and `auto` modes gated on `vars.WING_COMMANDER_PLAN_REVIEW`, mirroring how the existing "Stage 3 — Tasks" section documents `WING_COMMANDER_TASKS_REVIEW`'s `auto`/`pr` split (including the auto-mode dispatch to Stage 3 and the fallback-and-surface behavior for invalid values).

**Checkpoint**: All three stories independently functional; defaults are safe and the feature is fully discoverable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T022 Validate `.github/workflows/plan.yml` end-to-end on paper: YAML parses (e.g. `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` or actionlint if available) and every embedded `run:` script passes `bash -n` (matching `lint-workflows.yml`'s CI checks); confirm every gate/step matches `specs/014-configurable-gates/contracts/plan-workflow.md` (inputs, resolution, verification, dispatch, permissions, lifecycle-record, lifecycle-issue contracts) and that every new `if:` chain correctly honors `steps.dupe.outputs.skip` and `steps.mode.outputs.mode`.
- [ ] T023 Walk `specs/014-configurable-gates/quickstart.md` Scenarios 1-6 against the finished `.github/workflows/plan.yml` and `.github/workflows/wing-commander-3-plan.yml` as a desk-check, and record in the PR body which scenarios were exercised live (via `workflow_dispatch` or a synthetic PR merge against a scratch spec) versus desk-checked only.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on T001. T002 → T003 → T004 (same file, ordered edits; T002/T003 are independent of each other but both precede T004, which reads `inputs.plan-review`).
- **US1 (Phase 3)**: Depends on Phase 2. T005 and T006 both depend on T004 (mode resolution) and can be written in either order but both must land before T007; T007 depends on T005+T006 (both step ids must exist); T008 depends on T005 (auto commit must exist to verify); T009 depends on T004; T010 depends on T008; T011 depends on T010; T012 extends T005's prompt (after T005); T013 (wrapper) depends on T002 (the input must exist to wire) and can be done any time after T002, in parallel with T005-T012.
- **US2 (Phase 4)**: T014 extends T004 (Foundational) — depends on Phase 2 only, can start in parallel with Phase 3. T015 depends on T014 (needs the `invalid` output). T016 is a desk-check, depends on Phase 3 + T014/T015 being present to verify.
- **US3 (Phase 5)**: T017 depends on Phase 3 (needs the finished pr-mode gating to desk-check). T018-T021 are docs-only, independent of the workflow file and each other — can start any time.
- **Polish (Phase 6)**: T022-T023 depend on all prior phases being complete.

### Parallel Opportunities

Minimal within `.github/workflows/plan.yml` (single file, ordered steps — same constraint as `specs/003-tasks-stage/tasks.md`). Across files:

- T013 (wrapper) can proceed in parallel with T005-T012 (different file) once T002 lands.
- T018, T019, T020, T021 (all docs, all different files) can run in parallel with each other and with any workflow-file task, once the corresponding behavior they document is decided (Phase 2/3 complete is sufficient — they describe the finished contract, not intermediate states).

---

## Implementation Strategy

**MVP first (US1)**: Phases 1-3 deliver the requester's concrete need — Gate 3 bypass with automatic tasks-stage hand-off — and are independently testable via `quickstart.md` Scenario 2. US2 (invalid-value safety net) and US3 (default-mode regression proof + discoverability docs) layer on without changing US1 behavior: T004's mode resolution already fails open to `pr` before US2 adds surfacing, and the `pr`-mode path (T006, T009) is structurally unchanged from today, so US3's regression check has nothing to catch by design. Stop and validate at each checkpoint; commit after each task or logical group.
