# Tasks: Tasks Stage — Plan to Task List

**Input**: Design documents from `/specs/003-tasks-stage/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/tasks-workflow.md, quickstart.md

**Tests**: Not requested — the spec defines validation via `quickstart.md` manual scenarios (no automated test suite exists for stages 1–2 either). No test tasks are generated.

**Organization**: Tasks are grouped by user story. Nearly every task edits the same file (`.github/workflows/speckit-4-tasks.yml`), so tasks are ordered sequentially and parallel opportunities are limited by design (see plan.md Structure Decision).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Phase 1: Setup

**Purpose**: Confirm the ground the implementation builds on.

- [X] T001 Verify the stub trigger block in `.github/workflows/speckit-4-tasks.yml` matches the trigger contract in `specs/003-tasks-stage/contracts/tasks-workflow.md` (`pull_request: closed`, `branches: ["spec/**"]`, `paths: ["specs/**"]`) and that `.github/workflows/speckit-3-plan.yml` and `.github/actions/speckit-context` exist as the patterns/composite to reuse; note any drift before editing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared skeleton of the `tasks` job — identity, refusal, and idempotency guards that every review mode and every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Replace the stub body of `.github/workflows/speckit-4-tasks.yml`: header comment (stage purpose, restart procedure, "Implements specs/003-tasks-stage/spec.md"), top-level `permissions: {}`, and a `tasks` job gated on `github.event.pull_request.merged == true && startsWith(github.event.pull_request.head.ref, 'plan/')`, with job-level least-privilege permissions (`contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`) and `concurrency: { group: speckit-tasks-${{ github.event.pull_request.head.ref }}, cancel-in-progress: false }` (research.md idempotency decision).
- [X] T003 Add bootstrap steps to the `tasks` job in `.github/workflows/speckit-4-tasks.yml`: `actions/checkout@v4` with `persist-credentials: false`, then the `./.github/actions/speckit-context` composite (`id: ctx`) with `SPECKIT_APP_ID`/`SPECKIT_APP_PRIVATE_KEY` — mirroring `speckit-3-plan.yml` lines 46–56.
- [X] T004 Add a "Resolve spec identity" step to `.github/workflows/speckit-4-tasks.yml`: strip the `plan/` prefix from `head.ref`, validate against `^[0-9]{3}-[a-z0-9][a-z0-9-]*$`, refuse with `::error::` and exit 1 on mismatch (FR-012); output `slug` and `spec-dir`.
- [X] T005 Add spec-branch checkout + artifact verification to `.github/workflows/speckit-4-tasks.yml`: re-checkout `spec/${{ slug }}` as speckit-bot (`fetch-depth: 0`), then verify `spec.md`, `spec-meta.json`, AND `plan.md` all exist in `$SPEC_DIR` — on failure emit `::error::`, `$GITHUB_STEP_SUMMARY`, and a PR comment when a PR number is available, then exit 1 (FR-012, refusal contract); on success output `issue` from `spec-meta.json`.
- [X] T006 Add the idempotency guard step to `.github/workflows/speckit-4-tasks.yml`: read `.stage` from `$SPEC_DIR/spec-meta.json`; only `"plan"` proceeds — any other value (`"tasks"`, `"stalled"`, later) logs a duplicate/late-notification note to `$GITHUB_STEP_SUMMARY` and exits the job successfully as a no-op, setting a `skip=true` output every later step honors (FR-011, data-model.md state transitions).
- [X] T007 Add the review-mode resolution step to `.github/workflows/speckit-4-tasks.yml`: read `vars.SPECKIT_TASKS_REVIEW`; `pr` → review-required mode, unset/`auto`/anything else → direct-commit mode (fail-open per configuration contract in contracts/tasks-workflow.md); output `mode` (FR-003).

**Checkpoint**: The `tasks` job can resolve a spec, refuse ambiguity, no-op on duplicates, and knows its review mode — user story work can begin.

---

## Phase 3: User Story 1 — Accepted plan becomes a task list and implementation begins (Priority: P1) 🎯 MVP

**Goal**: In default (`auto`) mode, a merged plan PR yields `tasks.md` committed directly to `spec/NNN-slug`, `spec-meta.json` advanced to `"tasks"`, and `speckit-5-implement.yml` dispatched at iteration 1 — zero manual steps.

**Independent Test**: Quickstart Scenario 1 — merge a `plan/NNN-slug → spec/NNN-slug` PR with `SPECKIT_TASKS_REVIEW` unset; verify tasks.md on the spec branch, `stage: "tasks"`, and one implement-stage dispatch.

### Implementation for User Story 1

- [X] T008 [US1] Add the task-generation agent step (auto mode: `if: mode == 'auto' && skip != 'true'`) to `.github/workflows/speckit-4-tasks.yml`: `anthropics/claude-code-action@v1` with `claude_code_oauth_token`, `github_token` from ctx, `SPECIFY_FEATURE_DIRECTORY=$SPEC_DIR` env, prompt (interpolating only the validated slug and integer issue number, spec content framed as data): run the `/speckit-tasks` skill, never wait for user input, update `spec-meta.json` to `"stage": "tasks"`, commit `tasks.md` + `spec-meta.json` together as `tasks: <slug> (#<issue>)` directly on `spec/<slug>` and push (data-model.md: same commit); `claude_args`: `--model claude-sonnet-5`, `--max-turns 60`, least-privilege `--allowedTools` (Skill, Read/Write/Edit/Glob/Grep, `git status/add/commit/push/log/diff`, `.specify/scripts/bash/setup-tasks.sh`, `.specify/scripts/bash/check-prerequisites.sh`, `gh issue view/comment`), `--disallowedTools "WebSearch,WebFetch"` (FR-002, FR-004; constitution II & V).
- [X] T009 [US1] Add a deterministic verification step (auto mode) to `.github/workflows/speckit-4-tasks.yml`: `git fetch` + confirm `specs/<slug>/tasks.md` exists on `origin/spec/<slug>` and `spec-meta.json` there reads `"stage": "tasks"`; `::error::` + exit 1 otherwise (mirrors the plan stage's "verify PR exists" pattern — no agent turns on verification).
- [X] T010 [US1] Add the implementation-stage dispatch step (auto mode, after T009's verify) to `.github/workflows/speckit-4-tasks.yml`: `gh workflow run speckit-5-implement.yml -f spec_dir="specs/$SLUG" -f issue="$ISSUE" -f iteration=1` with the App token, exactly once, then note the dispatch in `$GITHUB_STEP_SUMMARY` (FR-005; outbound dispatch contract).
- [X] T011 [US1] Add the `Upload Claude execution log` step (`if: always()`, `actions/upload-artifact@v4`, path `${{ runner.temp }}/claude-execution-output.json`, `if-no-files-found: ignore`) to the `tasks` job in `.github/workflows/speckit-4-tasks.yml`, mirroring `speckit-3-plan.yml`.

**Checkpoint**: Default-mode pipeline is end-to-end: plan merge → tasks.md → implement dispatch (SC-001).

---

## Phase 4: User Story 2 — Lifecycle issue stays current through task generation (Priority: P2)

**Goal**: The lifecycle issue's stage label flips to `stage:tasks` and a task-summary comment (count, per-story breakdown, MVP scope) is posted, so status is readable without inspecting branches (SC-003).

**Independent Test**: Quickstart Scenario 1 postconditions — after task generation, the issue shows `stage:tasks` and a summary comment.

### Implementation for User Story 2

- [X] T012 [US2] Extend the agent prompt(s) in `.github/workflows/speckit-4-tasks.yml` to post the lifecycle-issue comment as part of the same sonnet step (research.md: no separate haiku step): total task count, per-story breakdown, MVP scope, and — auto mode — confirmation that implementation is being dispatched (FR-009, lifecycle issue contract).
- [X] T013 [US2] Add a deterministic label-flip step to the `tasks` job in `.github/workflows/speckit-4-tasks.yml`: `gh label create "stage:tasks" --force` (color/description consistent with existing `stage:*` labels), `gh issue edit --add-label "stage:tasks"`, `--remove-label "stage:plan"` (`|| true`), run only after the mode-appropriate success verification (FR-009; mirrors `speckit-3-plan.yml`'s flip step).

**Checkpoint**: US1 + US2 — the default path is complete AND visible on the issue.

---

## Phase 5: User Story 3 — Maintainer requires human review of generated tasks (Priority: P3)

**Goal**: With `SPECKIT_TASKS_REVIEW=pr`, tasks arrive as a `tasks/NNN-slug → spec/NNN-slug` PR; implementation dispatch happens only when a human merges it; a PR closed unmerged stalls the spec.

**Independent Test**: Quickstart Scenarios 2 and 3.

### Implementation for User Story 3

- [X] T014 [US3] Add the duplicate-attempt guard for review mode to `.github/workflows/speckit-4-tasks.yml`: if `refs/heads/tasks/$SLUG` already exists on origin, log to `$GITHUB_STEP_SUMMARY` and skip (a prior attempt is in flight, in review, or stalled — restart = delete the branch and re-run), mirroring the plan stage's `plan/$SLUG` check (FR-011, research.md).
- [X] T015 [US3] Add the pr-mode agent step (`if: mode == 'pr' && skip != 'true' && dupe != 'true'`) to `.github/workflows/speckit-4-tasks.yml`: same skill run as T008, but commit `tasks.md` + the `spec-meta.json` `stage: "tasks"` update on a new `tasks/$SLUG` branch, push it, and `gh pr create --base spec/$SLUG --head tasks/$SLUG` with the task-summary body; the agent must NOT commit to `spec/$SLUG`, and never merges or approves (FR-006, FR-010; quickstart Scenario 2). Allowed tools additionally include `gh pr create`/`gh pr list`; verification: a deterministic step confirms the open PR exists (else `::error::` exit 1) before the label flip runs.
- [X] T016 [US3] Make the US2 reporting mode-aware in `.github/workflows/speckit-4-tasks.yml`: in pr mode the issue comment includes the review-PR link and states that implementation starts only after a maintainer merges it; no `speckit-5-implement.yml` dispatch occurs anywhere in the pr-mode path of the `tasks` job (FR-006, lifecycle issue contract).
- [X] T017 [US3] Add a `tasks-approved` job to `.github/workflows/speckit-4-tasks.yml` gated on `github.event.pull_request.merged == true && startsWith(github.event.pull_request.head.ref, 'tasks/')`: resolve+validate the slug from the head ref, checkout `spec/$SLUG`, verify `spec-meta.json` reads `"stage": "tasks"` (the merged PR carried the update — anything else is a duplicate event, no-op per FR-011), then dispatch `gh workflow run speckit-5-implement.yml -f spec_dir="specs/$SLUG" -f issue="$ISSUE" -f iteration=1` and comment on the lifecycle issue that implementation has started (FR-007; concurrency group `speckit-tasks-<head.ref>`).
- [X] T018 [US3] Add a `stalled` job to `.github/workflows/speckit-4-tasks.yml` gated on `github.event.pull_request.merged == false && startsWith(github.event.pull_request.head.ref, 'tasks/')`: mirror `speckit-3-plan.yml`'s stalled job re-keyed to `tasks/` — set `spec-meta.json` `"stage": "stalled"` on `spec/$SLUG` (bot-authored commit), `gh label create "stage:stalled" --force`, add `stage:stalled` / remove `stage:tasks`, and comment that the tasks PR closed unmerged and a maintainer must delete `tasks/$SLUG` and re-run the tasks stage to restart (FR-013; quickstart Scenario 3).

**Checkpoint**: All three stories independently functional; both review modes and the stalled path covered.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T019 [P] Update `docs/architecture.md`: intro sentence ("Stages 1–2 are implemented" → stages 1–3; stub list shrinks), and the Stage 3 section header from "(stub)" to "(implemented)" with a pointer to `specs/003-tasks-stage/` — keeping the section's design text, which the implementation follows.
- [X] T020 Validate `.github/workflows/speckit-4-tasks.yml` end-to-end on paper: YAML parses (e.g. `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` or actionlint if available), every gate/step matches `specs/003-tasks-stage/contracts/tasks-workflow.md` (trigger, refusal, configuration, dispatch, lifecycle record, lifecycle issue contracts), and every `if:` chain honors the `skip`/`dupe` outputs.
- [X] T021 Walk `specs/003-tasks-stage/quickstart.md` Scenarios 1–5 against the finished workflow as a desk-check, and record in the PR body which scenarios can only be exercised live after merge (live runs require the workflow on the default branch).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on T001. T002 → T003 → T004 → T005 → T006 → T007 (each step builds on the previous within the same job; strictly sequential — same file, ordered steps).
- **US1 (Phase 3)**: Depends on Phase 2. T008 → T009 → T010; T011 anytime after T008.
- **US2 (Phase 4)**: T012 depends on T008 (extends its prompt); T013 depends on T009 (runs after verification).
- **US3 (Phase 5)**: T014–T016 depend on Phase 2 and touch the same job as US1/US2 tasks — do after Phase 4. T017 and T018 are separate jobs in the same file; sequential after T016.
- **Polish (Phase 6)**: T019 is independent of the workflow file ([P] with T020); T020–T021 depend on all prior phases.

### Parallel Opportunities

Minimal by design — a single workflow file edited step-by-step. Only T019 (docs/architecture.md) can proceed in parallel with workflow-file tasks.

---

## Implementation Strategy

**MVP first (US1)**: Phases 1–3 deliver the pipeline's core value — plan merge to implement dispatch with zero manual steps — and are independently testable via quickstart Scenario 1. US2 (visibility) and US3 (review mode + stalled path) layer on without changing US1 behavior: mode resolution (T007) already defaults everything to `auto`, so the pr-mode branches are pure additions. Stop and validate at each checkpoint; commit after each task or logical group.
