---

description: "Task list for Surface Per-Run Agent Metrics for Pipeline Tuning (Tier 1)"
---

# Tasks: Surface Per-Run Agent Metrics for Pipeline Tuning (Tier 1)

**Input**: Design documents from `/specs/009-agent-metrics/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/speckit-metrics-summary-action.md, contracts/step-summary-format.md

**Tests**: No automated test suite exists for any pipeline stage
(research.md D9); validation is `quickstart.md`'s 9 scenarios run by hand —
some by invoking the new composite action directly against hand-crafted
fixture transcripts, some by dispatching a real workflow. No test tasks are
generated; quickstart validation is folded into User Story 1's own tasks
(this feature's committed scope is a single user story, FR-012) plus a
final full-suite pass in Polish.

**Organization**: `spec.md` defines three user stories, but FR-012 commits
this feature to **tier 1 / User Story 1 only** — User Story 2 (per-feature
lifecycle-issue rollup) and User Story 3 (durable trend record) are
explicitly deferred to later features and get **no tasks here**. Every
task below either builds the one new file
(`.github/actions/speckit-metrics-summary/action.yml`) or wires a call to
it into one of the eight existing workflow files, per plan.md's Project
Structure.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (independent edits or reads)
- **[Story]**: Which user story this task belongs to (only `US1` appears —
  US2/US3 are deferred, no tasks)
- Every task names the exact file (and, where useful, line/step anchor) it
  edits or reads

## Path Conventions

Single project, CI/CD-only feature (plan.md's Project Structure):

- **New**: `.github/actions/speckit-metrics-summary/action.yml`
- **Edited** (one new step per existing agent invocation): `speckit-1-intake.yml`,
  `speckit-2-clarify.yml`, `speckit-3-plan.yml`, `speckit-4-tasks.yml`,
  `speckit-5-implement.yml`, `speckit-6-finalize.yml`, `speckit-7-cleanup.yml`,
  `speckit-rebase.yml` (all under `.github/workflows/`)
- Reused, unchanged: `.github/actions/speckit-context` (not touched by this
  feature — the new action takes no App token, no secrets, FR-011/Constitution V)

---

## Phase 1: Setup

**Purpose**: Create the new composite action's skeleton — metadata and
input contract only, no extraction/rendering logic yet.

- [ ] T001 Create `.github/actions/speckit-metrics-summary/action.yml` with
      `name`, `description`, the five inputs from
      `contracts/speckit-metrics-summary-action.md` (`transcript-path`
      defaulting to `${{ runner.temp }}/claude-execution-output.json`,
      `model` required, `max-turns` optional/no default, `warn-fraction`
      defaulting to `0.8`, `run-label` optional/empty default), no outputs,
      and `runs: using: composite` with a single placeholder `shell: bash`
      step — mirroring `.github/actions/speckit-context/action.yml`'s shape
      (research.md D2).

**Checkpoint**: The action can be referenced via
`uses: ./.github/actions/speckit-metrics-summary` with valid inputs; it
does nothing yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The extraction/rendering core inside `action.yml`'s single
composite step — every wiring task in User Story 1 depends on this logic
existing and being correct, since it is the entire behavioral contract
(FR-001–FR-005) this feature commits to.

**⚠️ CRITICAL**: No User Story 1 wiring task should be considered done
until this phase's logic is in place and passes the fixture scenarios in
T018 (order note: T018 is listed under US1 below since it's part of the
Independent Test, but nothing stops running it against the bare action
immediately after this phase, before any workflow is touched).

- [ ] T002 In `action.yml`'s composite step, resolve `transcript-path`
      (default already set by T001) and determine `availability`: read the
      file; if it does not exist, is empty, fails to parse as JSON via
      `jq`, or parses but contains no entry with `.type == "result"`, set
      `availability=unavailable` and skip all further extraction; otherwise
      set `availability=ok` and capture the **last** matching entry as the
      result record (data-model.md's Execution transcript table; FR-009).
- [ ] T003 [P] When `availability=ok`, defensively extract each field from
      the result record independently via a `jq '... // empty'`-style
      pattern so one missing/misnamed field never blocks another:
      `turns_used` from `.num_turns`, `duration_ms` from `.duration_ms`,
      `cost_usd` from `.total_cost_usd`, a best-effort `tokens` read of the
      transcript's token-usage object, and a best-effort `per_model_breakdown`
      read (research.md D6 — field names are the documented assumption from
      spec.md's worked example; each falls back to "unavailable"
      independently rather than failing the step).
- [ ] T004 [US1-independent, feeds US1] Compute the turn-budget fields:
      when the `max-turns` input is provided and `turns_used` was
      successfully extracted, compute `turns_ratio = turns_used / max-turns`
      and `turn_warning = (turns_ratio >= warn-fraction)`; when `max-turns`
      is omitted, leave `turns_ratio` and `turn_warning` entirely unset —
      never fabricate a budget or a ratio (FR-003, FR-004, FR-005,
      contracts/speckit-metrics-summary-action.md points 4–5; the `>=`
      boundary against `warn-fraction`, default `0.8`, must be exact).
- [ ] T005 Format the extracted/computed values for display: `duration_ms`
      into a human-readable duration, `cost_usd` into a `$`-prefixed
      amount, `tokens`/`per_model_breakdown` into their rendered forms —
      each independently falling back to the literal string `unavailable`
      when its source value was absent (data-model.md's Run metrics
      "Renders as" column).
- [ ] T006 Render the **normal-case** Markdown block per
      `contracts/step-summary-format.md` ("Normal case"): heading
      `### 🤖 Agent run metrics` with `— <run-label>` appended only when
      `run-label` is non-empty; a table row whose Turns cell is exactly
      `<turns_used> / <max-turns>` when a budget was supplied or exactly
      `<turns_used>` alone when it wasn't (never a `/ —` placeholder); the
      ⚠️ turn-budget-warning line present if and only if `turn_warning` is
      true (silence otherwise — no "all clear" line, Acceptance Scenario
      3); the per-model-breakdown line present only when that data was
      extracted. Append this block to `$GITHUB_STEP_SUMMARY`.
- [ ] T007 Render the **unavailable-case** Markdown block per
      `contracts/step-summary-format.md` ("Unavailable case") when
      `availability=unavailable`: the same heading rule, followed only by
      the italic `_Metrics unavailable for this run (execution transcript
      missing or unparseable)._` line — no table, no partial fields.
      Append this block to `$GITHUB_STEP_SUMMARY` and exit the step `0` in
      every case (T002–T007 combined must never produce a non-zero exit,
      contracts/speckit-metrics-summary-action.md point 1).

**Checkpoint**: `.github/actions/speckit-metrics-summary` is a complete,
self-contained composite action satisfying FR-001–FR-005 and FR-009 on its
own — invokable and verifiable with hand-crafted fixtures with no workflow
wiring yet.

---

## Phase 3: User Story 1 - Each agent run reports its own metrics where the run is watched (Priority: P1) 🎯 MVP

**Goal**: Every existing agent invocation across the pipeline gets its own
metrics summary, appended immediately to that step's run, with turn-budget
warnings surfaced and missing/broken transcripts degrading gracefully —
without altering any stage's own behavior or outcome (FR-011).

**Independent Test**: Run any agent-invoking stage to completion and
confirm its run summary shows model, turns used against the budget,
duration, tokens, and cost derived from that run's execution transcript —
and that a run which used a high fraction of its turn budget is visibly
flagged — all without opening the uploaded artifact.

### Wiring: one metrics step per existing agent invocation

- [ ] T008 [P] [US1] In `.github/workflows/speckit-1-intake.yml`, add a
      `uses: ./.github/actions/speckit-metrics-summary` step immediately
      after the existing "Upload Claude execution log" step (currently
      lines 176-182), `if: always()`, with `model: claude-opus-4-8` and
      `max-turns: 50` — the same literals already hardcoded in that job's
      `claude_args` (line 146-147, research.md D5).
- [ ] T009 [P] [US1] In `.github/workflows/speckit-2-clarify.yml`, add the
      same kind of step immediately after its "Upload Claude execution log"
      step (around lines 138-141), `if: always()`, with
      `model: claude-opus-4-8` and `max-turns: 40` (matching lines
      127-128).
- [ ] T010 [P] [US1] In `.github/workflows/speckit-3-plan.yml`, add the
      same kind of step immediately after its "Upload Claude execution log"
      step (around lines 271-274), `if: always()`, with
      `model: claude-sonnet-5` and `max-turns: 80` (matching lines
      234-235).
- [ ] T011 [P] [US1] In `.github/workflows/speckit-4-tasks.yml`, add **one**
      metrics step, `if: always()`, positioned after both mutually-exclusive
      agent steps ("Generate task list (direct commit)" at lines 171-219
      and "Generate task list (review PR)" at lines 224-278) and before the
      "Verify tasks committed" steps that follow — since exactly one of the
      two agent steps runs per invocation and both configure
      `model: claude-sonnet-5` / `max-turns: 60` identically, this single
      unconditional step correctly reads whichever transcript the branch
      that actually ran produced (plan.md Project Structure: "shared across
      the two mutually-exclusive agent steps").
- [ ] T012 [US1] In `.github/workflows/speckit-5-implement.yml`, add a
      metrics step immediately after the primary "cycle" agent step's
      "Upload Claude execution log (cycle)" step (lines 280-283), `if:
      always()`, with `model: ${{ steps.tier.outputs.tier }}` and
      `max-turns: 100` (matching lines 270-272), and `run-label: cycle`
      (research.md D3, FR-008).
- [ ] T013 [US1] In the same file, add a second metrics step immediately
      after the conditional opus "retry" agent step's "Upload Claude
      execution log (retry)" step (lines 407-410), `if: always()`, with
      `model: claude-opus-4-8` and `max-turns: 100` (matching lines
      399-401), and `run-label: retry`. Must run before the haiku
      progress-comment step (T014) so the shared transcript file isn't
      overwritten out of order (research.md D3).
- [ ] T014 [US1] In the same file, add a third (new) metrics step
      immediately after the "Post progress comment (haiku)" agent step
      (around line 522-555) — this invocation currently has no
      `claude-execution-output` artifact upload to anchor near, so the step
      goes directly after the agent step itself — `if: always()`, with
      `model: claude-haiku-4-5` and `max-turns: 15` (matching lines
      554-555), and `run-label: progress comment` (research.md D4 — every
      invocation gets a summary, not just the ones with a pre-existing
      upload).
- [ ] T015 [P] [US1] In `.github/workflows/speckit-6-finalize.yml`, add the
      same kind of step immediately after its "Upload Claude execution log"
      step (around lines 226-229), `if: always()`, with
      `model: claude-haiku-4-5` and `max-turns: 20` (matching lines
      219-220).
- [ ] T016 [P] [US1] In `.github/workflows/speckit-7-cleanup.yml`, add the
      same kind of step immediately after its "Upload Claude execution log"
      step (around lines 178-181), `if: always()`, with
      `model: claude-haiku-4-5` and `max-turns: 20` (matching lines
      171-172).
- [ ] T017 [P] [US1] In `.github/workflows/speckit-rebase.yml`, add the same
      kind of step immediately after its per-matrix-entry "Upload Claude
      execution log" step (around lines 293-296), `if: always()`, with
      `model: claude-sonnet-5` and `max-turns: 30` (matching lines
      286-287).

### Validation for User Story 1

- [ ] T018 [P] [US1] Validate `quickstart.md` Scenarios 2, 3, 5, and 6
      directly against the composite action (no workflow dispatch needed):
      turn-budget warning fires at/above 80% (Scenario 2: 65/80), no
      warning below it (Scenario 3: 40/80), a partial result record renders
      real values for the fields present and `unavailable` only for the
      missing ones rather than the whole block (Scenario 5), and an
      invocation with no `max-turns` input renders turns-used alone with no
      ratio or warning regardless of the count (Scenario 6).
- [ ] T019 [P] [US1] Validate `quickstart.md` Scenario 4 directly against
      the composite action: a nonexistent transcript path, an empty file,
      and a file containing `not valid json`, each invoked separately —
      confirm all three render the "Unavailable case" block, the step
      exits `0`, and no other step in a hypothetical job would be affected.
- [ ] T020 [P] [US1] Validate `quickstart.md` Scenario 1 (dispatch
      `speckit-3-plan.yml` — or another single-invocation stage — for a
      scratch spec past intake, open the run's own summary with no
      artifact download, confirm the full normal-case block) and Scenario
      9 (compare that run's actual outcome — PR opened, label flipped —
      against a pre-feature run of the same stage; confirm identical
      behavior and artifacts besides the new step-summary block, FR-011).
- [ ] T021 [P] [US1] Validate `quickstart.md` Scenario 7 (dispatch
      `speckit-5-implement.yml` on an iteration that exercises cycle +
      retry, or simulate all three invocations locally with distinct
      `run-label`s; confirm three distinct, correctly-ordered blocks appear
      in one job's step summary — not one block reflecting only the last
      invocation, FR-008) and Scenario 8 (inspect a deterministic-only job,
      e.g. `speckit-7-cleanup.yml`'s `teardown-rejected` job, and confirm no
      metrics block appears anywhere in its summary).

**Checkpoint**: User Story 1 is fully functional and independently
testable/deployable as the MVP — every existing agent invocation across
all eight workflow files now reports its own metrics, with turn-budget
warnings and graceful degradation, and nothing else about any stage's
behavior has changed.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency checks spanning the whole feature. (User
Stories 2 and 3 are deferred per FR-012 — no tasks for them here.)

- [ ] T022 [P] Run `lint-workflows.yml`'s own checks locally against
      `.github/actions/speckit-metrics-summary/action.yml` and all eight
      edited workflow files (YAML parses via `yaml.safe_load` and every
      `run:`/composite `shell: bash` block passes `bash -n` after
      neutralizing `${{ ... }}` expressions) before opening the eventual
      review PR, since that workflow gates every PR touching
      `.github/workflows/**` and (per its own scope) likely
      `.github/actions/**`.
- [ ] T023 [P] Cross-check `docs/architecture.md`'s per-stage sections
      (Stage 2 Plan, Stage 3 Tasks, Stage 4 Implement, Stage 5 Finalize,
      Stage 6 Cleanup, Auto-rebase) against the finished implementation;
      update only if a section should note that stage's steps now emit a
      metrics summary — no changes are expected beyond a brief mention,
      since this feature adds no new stage behavior (plan.md's Structure
      Decision: purely additive).
- [ ] T024 Run the full `quickstart.md` scenario suite (all 9 scenarios,
      T018-T021 plus a final end-to-end pass) in one sitting against the
      finished set of eight workflow files, to confirm no later wiring
      task regressed an earlier one (e.g. that `speckit-5-implement.yml`'s
      three-step ordering from T012-T014 still produces three
      correctly-ordered, non-clobbered blocks after all other files were
      also touched).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001) completion — BLOCKS
  User Story 1 (the extraction/rendering logic every wiring task relies on
  producing correct output).
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the
  MVP and the feature's entire committed scope (FR-012).
- **Polish (Phase 4)**: Depends on User Story 1 being complete.

### Within This Feature

- T002 → T003 → T004 → T005 → T006/T007 are sequential (each depends on the
  prior step's extracted/computed values) within the same file
  (`action.yml`'s single composite step) — not parallelizable against each
  other.
- T008, T009, T010, T011, T015, T016, T017 each edit a different workflow
  file and have no dependency on one another — fully parallelizable `[P]`.
- T012 → T013 → T014 edit the same file (`speckit-5-implement.yml`) at
  three different, ordered locations (research.md D3's ordering
  constraint: cycle's metrics step must exist before retry's step could
  ever overwrite the shared transcript, and retry's before the
  progress-comment step) — sequential, not `[P]`.
- T018, T019, T020, T021 are independent validation runs against the
  finished artifacts of Phase 2/3 — parallelizable `[P]` once T002-T017 are
  done (T020/T021 specifically need the relevant wiring tasks — T010/T017
  for T020's stage choice, T012-T014/T016 for T021 — complete first).
- T022, T023 are independent of each other — parallelizable `[P]`. T024
  depends on every prior task.

### Parallel Opportunities

- T008, T009, T010, T011, T015, T016, T017 (seven of the eight wiring
  tasks, every file except `speckit-5-implement.yml`) can all run in
  parallel — each is an independent edit to its own workflow file.
- T018 and T019 (fixture-driven validation) can run in parallel with each
  other, and with the wiring tasks above, since they only need Phase 2
  (the composite action itself) complete, not any workflow wiring.
- T022 and T023 (Polish) can run in parallel.

---

## Parallel Example: User Story 1 wiring

```bash
# Once Phase 2 (T002-T007) is complete, these seven wiring tasks are independent:
Task: "Wire speckit-1-intake.yml's metrics step (T008)"
Task: "Wire speckit-2-clarify.yml's metrics step (T009)"
Task: "Wire speckit-3-plan.yml's metrics step (T010)"
Task: "Wire speckit-4-tasks.yml's shared metrics step (T011)"
Task: "Wire speckit-6-finalize.yml's metrics step (T015)"
Task: "Wire speckit-7-cleanup.yml's metrics step (T016)"
Task: "Wire speckit-rebase.yml's metrics step (T017)"

# speckit-5-implement.yml's three steps (T012-T014) must stay sequential —
# same file, ordering-dependent on the shared transcript path (research.md D3).
```

---

## Implementation Strategy

### MVP First (and only) — User Story 1

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002-T007) — CRITICAL, blocks the
   wiring tasks; verifiable standalone against fixtures before touching any
   workflow.
3. Complete Phase 3: User Story 1 (T008-T021) — wire all eight files, then
   validate all 9 quickstart scenarios.
4. **STOP and VALIDATE**: T018-T021 already cover every acceptance
   scenario and edge case in spec.md's User Story 1. Since User Story 1 is
   this feature's entire committed scope (FR-012), completing it *is*
   completing the feature.
5. Polish (T022-T024): lint, docs cross-check, full-suite regression pass.

### Suggested MVP Scope

**User Story 1 in full** (T001-T021): there is no smaller shippable slice
— FR-012 already commits this feature to tier 1 only, so User Story 1 is
simultaneously the MVP and the complete deliverable. User Stories 2
(lifecycle-issue rollup) and 3 (durable trend record) are deferred to
later features and are out of scope for this tasks list entirely.

### Incremental Delivery

1. Setup + Foundational → the composite action exists and is independently
   correct against fixtures (T018/T019 can already pass).
2. Add the seven parallelizable wiring tasks (T008-T011, T015-T017) →
   most of the pipeline now reports metrics.
3. Add the three sequential `speckit-5-implement.yml` tasks (T012-T014) →
   every agent invocation across the whole pipeline now reports metrics.
4. Validate (T020-T021) → live-dispatch and multi-invocation scenarios
   confirmed.
5. Polish (T022-T024) → lint, docs cross-check, full-suite regression pass.

---

## Notes

- [P] tasks marked above are independent file edits or independent
  validation runs; T012-T014 share one file and are ordering-dependent, so
  they are not marked [P] against each other.
- Every wiring task (T008-T017) names the exact existing step it anchors
  after and the exact `model`/`max-turns` literals to pass through
  unchanged — no task requires re-deriving those values from anywhere else
  (research.md D5).
- Every task in Phase 2/3 traces to a specific FR (FR-001–FR-005, FR-008,
  FR-009, FR-011) or contract point
  (`contracts/speckit-metrics-summary-action.md`,
  `contracts/step-summary-format.md`) so no task needs additional context
  beyond this file, plan.md, and the design docs.
- Commit after each phase (or logical group within a phase); each
  checkpoint above is a safe point to stop and validate independently
  before continuing.
- Field names extracted in T003 (token usage, per-model breakdown) are a
  documented assumption, not a confirmed schema (research.md D6) — if a
  live `claude-execution-output.json` artifact is available to inspect
  while implementing T003, verify the real field names against it and
  adjust the `jq` paths; because extraction is defensive, a wrong name
  degrades to "unavailable" rather than breaking anything.
