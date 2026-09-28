---

description: "Task list for The Cost Line Names Its Own Run — Run-Stamped Cost Attribution"
---

# Tasks: The Cost Line Names Its Own Run — Run-Stamped Cost Attribution

**Input**: Design documents from `/specs/064-run-stamped-cost-attribution/`
(spec.md, plan.md, research.md, data-model.md, contracts/run-stamp.md,
contracts/cost-attribution.md, quickstart.md)

**Tests**: This repository's tests ARE its gates (`verify-*.{py,sh}`,
CLAUDE.md's gate-registry convention) — every task below either widens
production code or widens the gate that pins it, and several tasks are
themselves the "write the test" step (T017, T026-T029). There is no
separate unit-test framework to opt into or out of.

**Organization**: Tasks are grouped by user story, in the order a
maintainer would actually land them: Foundational (the widened record
key every later story rests on) → User Story 2 (the stamp — a
prerequisite producer) → User Story 1 (the attribution rule that
consumes the stamp — the reported defect's fix) → User Story 3 (the
gate coverage that proves User Story 1 can't regress silently).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact; line numbers cite this branch's current state and
  may drift by the time a task executes — treat them as a locator, not a
  guarantee.

## Path Conventions

This repository has no `src`/`tests` split — it is a GitHub Actions
pipeline. Paths below are relative to the repository root:
`.github/actions/`, `.github/workflows/`, `.github/scripts/`.

---

## Phase 1: Setup

**Purpose**: Establish the baseline this feature's edits are measured
against.

- [X] T001 Run `python3 .github/scripts/run-local-gates.py` from the
      repository root and confirm it is green before making any edits —
      this is the same command `lint-workflows.yml` derives its PR-time
      gate invocations from (CLAUDE.md), and the baseline every later
      phase's gate run is diffed against.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Widen the metrics record key to
`workflow_run_id:run_attempt:job_key:step_index` (research.md R1,
FR-014) everywhere it is composed, consumed, or pinned by a gate. Both
User Story 1 (the collector matches on `run_id:attempt`) and User Story
2 (the stamp carries this same key verbatim) depend on this key already
being widened — neither story can be implemented, let alone tested,
against the narrow 3-field key.

**⚠️ CRITICAL**: No user story work can begin until this phase is
complete.

- [X] T002 In `.github/actions/wing-commander-metrics-summary/action.yml`'s
      "Render agent run metrics summary" step (`id: render`), add
      `RUN_ATTEMPT: ${{ github.run_attempt }}` to the step's `env:`
      block (action.yml:215, alongside the existing `RUN_ID: ${{
      github.run_id }}`), and read it into `RUN_ATTEMPT="${RUN_ATTEMPT:-}"`
      next to `RUN_ID="${RUN_ID:-}"` (action.yml:243).

- [X] T003 In the same file, widen
      `RECORD_KEY="${RUN_ID}:${JOB_KEY}:${STEP_INDEX}"` (action.yml:245)
      to `RECORD_KEY="${RUN_ID}:${RUN_ATTEMPT}:${JOB_KEY}:${STEP_INDEX}"`,
      inserting the attempt as the **second** segment (research.md R1) so
      `run_id:run_attempt` is a clean two-field prefix a collector can
      split off without knowing anything about `job_key`'s own content.

- [X] T004 In the same file's `emit_record()` jq invocation
      (action.yml:276-373), add `--arg run_attempt "$RUN_ATTEMPT"` to the
      `jq -n` argument list and a new sibling field `run_attempt:
      $run_attempt` inside the emitted `run: {...}` object (next to
      `workflow_run_id`), matching data-model.md's widened record `run`
      shape.

- [X] T005 In
      `.github/actions/wing-commander-metrics-persist/action.yml`'s
      job-id resolution step (the `.run.job_id = $jid | .run.record_key
      = ...` rewrite, action.yml:342-343), change
      `.run.record_key = "\(.run.workflow_run_id):\($jid):\(.run.step_index)"`
      to
      `.run.record_key = "\(.run.workflow_run_id):\(.run.run_attempt):\($jid):\(.run.step_index)"`.
      This rewrite must carry `run_attempt` through unchanged — it only
      ever substitutes `job_key` → `job_id` and must not recompute or
      touch the attempt segment (research.md R1).

- [X] T006 [P] In `.github/scripts/wc_metrics_harness.py`, add an
      `attempt="1"` parameter (default matching `github.run_attempt`'s
      first-attempt default) to `metrics_record()` (line 59), threading
      it into its `record_key` literal (line 68, currently
      `f"{run_id}:{job_key}:{step_index}"`) and into a new
      `run.run_attempt` field; add the same parameter to `resolved_key()`
      (line 110) and `persisted_record()` (line 114), threading it into
      their `record_key` literals the same way.

- [X] T007 [P] In
      `.github/scripts/verify-metrics-summary-record-emission.py`,
      update `mutate()` (line 691) so it targets the new literal
      `RECORD_KEY="${RUN_ID}:${RUN_ATTEMPT}:${JOB_KEY}:${STEP_INDEX}"`
      (not the pre-widen 3-field form) for its existing
      `MUTATION_LABEL` ("record_key drops step_index..."), and add a
      second mutation, `MUTATION_LABEL_ATTEMPT = "record_key drops the
      attempt number (re-run attempts of one workflow run collide)"`,
      that strips the `:${RUN_ATTEMPT}` segment instead — `main()` must
      assert both mutations are independently caught (research.md R1,
      FR-014).

- [X] T008 [P] In `.github/scripts/verify-metrics-persist-retry.py`,
      widen the literal `want_key = f"{run_id}:{diagnose_job_id}:0"`
      (line 607) to `f"{run_id}:1:{diagnose_job_id}:0"` and the
      ambiguous-job-key literal `f"{run_id}:collect:0"` (line 612 area)
      to `f"{run_id}:1:collect:0"` (both using the harness's new default
      attempt from T006), updating every assertion and failure-message
      text that repeats these literals (lines 608-617, 634-643).

- [X] T009 [P] In `.github/scripts/verify-metrics-record-schema.py`
      (Gate 39): add `"run_attempt": str` to `REQUIRED_RUN` (lines
      89-95); add a new positive shape assertion applying the regex
      `^[0-9]+:[0-9]+:[^:]+:[0-9]+$` to every ingested record's
      `run.record_key`, failing any record whose key does not match
      (research.md R9 — this is the check that catches ANY future
      composition site left emitting an un-widened key, not only the
      ones this feature remembers to mutate-test by name); update
      `specs/043-durable-metrics-record/contracts/metrics-record-schema.md`'s
      "## Shape" JSON block to add `run_attempt` to the documented `run`
      object, so `check_fields_match_contract()`'s key-set cross-check
      against `REQUIRED_RUN` continues to pass.

- [X] T010 [P] In
      `.github/scripts/verify-metrics-schema-version-tolerance.py`, add
      `"run_attempt": "1"` and widen `record_key` to `"1:1:cycle:0"` in
      `V1_RECORD` (lines 70-73), and add `"run_attempt": "1"` / widen
      `record_key` to `"2:1:cycle:0"` in `V2_UNKNOWN_RECORD` (lines
      88-91).

- [X] T011 [P] In `.github/scripts/verify-turn-budget-collector.sh`,
      widen the two inline JSON record fixtures' `record_key` literals
      (lines 252-253, 260-261) from `"999000222:cycle:1"` /
      `"999000222:cycle:3"` to `"999000222:1:cycle:1"` /
      `"999000222:1:cycle:3"`, adding `"run_attempt":"1"` alongside each.

- [X] T012 [P] In
      `.github/scripts/verify-watchdog-no-record-on-clean-path.py`
      (Gate 74), widen `ABSENT_KEY = "9001:diagnose:0"` (line 60) to
      `"9001:1:diagnose:0"` and `PRESENT_KEYS = ("1000:implement:0",
      "1001:clarify:0")` (line 61) to `("1000:1:implement:0",
      "1001:1:clarify:0")`.

- [X] T013 [P] Widen every `record_key` literal (and add a sibling
      `run_attempt` field to each `run` object that carries one) across
      the fixture files under
      `.github/scripts/fixtures/metrics-record-schema/*.json` that
      contain `record_key` — every file in that directory except
      `invalid-renamed-field.json`, whose deliberate `record_key` →
      `recordKey` rename must be preserved unchanged for that negative
      test, though its other `run` fields (`workflow_run_id`, `job_key`,
      `job_id`, `step_index`) still gain `run_attempt` so it keeps
      matching T009's widened schema shape everywhere else.

**Checkpoint**: The metrics record key, every place it is composed, its
test-harness builders, and every gate that pins its shape agree on
`workflow_run_id:run_attempt:job_key:step_index`. User Story 2 and User
Story 1 can now both proceed.

---

## Phase 3: User Story 2 - Every cost-bearing comment names its run, from one place (Priority: P1)

**Goal**: Every comment the pipeline posts carrying a cost line — the
normal case and the degraded "metrics unavailable" fallback alike —
carries a machine-readable, human-invisible stamp naming the run that
posted it, computed at the single place the cost line is formatted.

**Independent Test**: Render the cost line for a known run and confirm
the stamp names that run; then confirm that a workflow posting a cost
line without going through the formatter fails a gate.

- [ ] T014 [US2] Add a new, unconditional **first** step to
      `.github/actions/wing-commander-metrics-summary/action.yml`'s
      `runs.steps` list (before the existing `id: render` step): `id:
      run-stamp`, no `continue-on-error` (nothing in it can fail), with
      its own `env:` block (`RUN_ID: ${{ github.run_id }}`,
      `RUN_ATTEMPT: ${{ github.run_attempt }}`, `JOB_KEY: ${{
      github.job }}`, `STEP_INDEX: ${{ inputs.step-index }}`) and a
      `run:` body computing
      `STAMP="<!-- wing-commander-cost-stamp:${RUN_ID}:${RUN_ATTEMPT}:${JOB_KEY}:${STEP_INDEX} -->"`
      then `echo "value=$STAMP" >> "$GITHUB_OUTPUT"` (research.md R2,
      contracts/run-stamp.md). Place a `(canonical copy, do not
      condense)`-marked comment next to this step documenting the
      stamp's shape and its single-home rule (FR-013) — this is the one
      place that text is written; every other reference must point at
      it rather than restate it.

- [ ] T015 [US2] Add a new `stamp` output to the composite's `outputs:`
      block in the same file, `value: ${{ steps.run-stamp.outputs.value
      }}`, documented analogously to the existing `cost-line` output
      immediately above it.

- [ ] T016 [US2] Add `STAMP: ${{ steps.run-stamp.outputs.value }}` to
      the existing `render` step's `env:` block (action.yml:201-223)
      and pass it into the cost-line jq pipeline via `--arg stamp
      "$STAMP"`; change the pipeline's final concatenation line
      (action.yml:390, `"**Cost**: " + costpart + " · " + turnspart +
      " · " + modelpart`) to append `+ " " + $stamp`, so the `cost-line`
      output's own text always carries the stamp in both the normal and
      internally-degraded paths, with zero call-site changes needed for
      those paths (research.md R2).

- [ ] T017 [US2] In
      `.github/scripts/verify-metrics-summary-record-emission.py`, add
      `case_run_stamp_has_exactly_one_home()`, a sibling to the existing
      `case_cost_line_formatter_has_exactly_one_home()` (line 558),
      scanning the same two sources that function already scans
      (`_workflow_texts()` over `.github/workflows/*.yml`, and an
      `os.walk(".github/actions")` over `action.yml`/`action.yaml`/
      `*.sh`/`*.py` excluding the canonical action path) for a
      **construction** of the `wing-commander-cost-stamp:` marker prefix
      — a occurrence of that text not immediately adjacent to
      `outputs.stamp` or `$RUN_STAMP` on the same or an adjacent line
      (research.md R9, contracts/run-stamp.md's Enforcement section).
      Add it to `CASES` (line 663) with two fixtures: one proving a
      literal reconstruction of the marker outside the canonical action
      fails the case, one proving the real call-sites' `$RUN_STAMP`
      consumption (T018-T020) passes it.

- [ ] T018 [P] [US2] For each of these 7 stage workflows' single
      "Compute cost line" step — `.github/workflows/clarify.yml` (`id:
      cost-line`, reads `steps.metrics-summary.outputs.stamp`),
      `.github/workflows/intake.yml` (same), `.github/workflows/plan.yml`
      (same), `.github/workflows/tasks.yml` (same),
      `.github/workflows/rebase.yml` (same), `.github/workflows/cleanup.yml`
      (same), `.github/workflows/finalize.yml` (same) — add `RUN_STAMP:
      ${{ steps.metrics-summary.outputs.stamp }}` to the step's `env:`
      block and change `[ -n "$line" ] || line="**Cost**: metrics
      unavailable"` to `[ -n "$line" ] || line="**Cost**: metrics
      unavailable $RUN_STAMP"` (research.md R3) — one added `env:` line
      and one changed fallback line per file, reusing the composite's
      already-computed `stamp` output rather than reconstructing the
      marker.

- [ ] T019 [US2] In `.github/workflows/implement.yml`, apply the same
      env-line-plus-fallback-line edit from T018 to all three of its
      "Compute cost line" steps: `cost-line-cycle` (line 1123, `steps.
      metrics-summary-cycle.outputs.stamp`), `cost-line-retry` (line
      1698, `steps.metrics-summary-retry.outputs.stamp`), and
      `cost-line-progress` (line 2289,
      `steps.metrics-summary-progress.outputs.stamp`).

- [ ] T020 [US2] In `.github/workflows/pr-conversation.yml`, apply the
      same edit to both of its "Compute cost line" steps:
      `cost-line-classify` (line 1068, `steps.metrics-summary-classify.
      outputs.stamp`) and `cost-line-act` (line 2245, `steps.
      metrics-summary-act.outputs.stamp`).

**Checkpoint**: Every cost-bearing comment the pipeline can post — 12
call sites across 9 stage workflows, normal and degraded paths alike —
carries a stamp naming its run, and a second formatter anywhere else
fails T017's gate.

---

## Phase 4: User Story 1 - A run that posted no cost line is reported, even with a neighbour on the same issue (Priority: P1)

**Goal**: The watchdog's cost-report collector attributes a lifecycle
issue's comments to the inspected run by stamp, in preference to the
time window, closing the reported defect (two overlapping runs
crediting each other's line) while keeping the window as a fallback for
pre-stamp comments.

**Independent Test**: Replay the #369/#370 shape — two cost-bearing runs
on one lifecycle issue whose windows overlap, one of which posted a cost
line — and confirm each run's collection produces the correct verdict
for that run alone.

**Depends on**: Phase 2 (widened record key) and Phase 3 (the stamp
that carries it) — the collector has nothing to match against until
both exist.

- [ ] T021 [US1] In `.github/workflows/watchdog.yml`'s "Fetch inspected
      run metadata" step (`id: run-meta`, line 447), add `attempt` to
      the `gh run view --json` field list and add `echo
      "attempt-number=$(printf '%s' "$json" | jq -r '.attempt //
      empty')" >> "$GITHUB_OUTPUT"` alongside the existing `created-at`/
      `updated-at` output lines (research.md R6) — one field added to an
      already-invoked command, no new network call.

- [ ] T022 [US1] In `collect-cost-report`'s `env:` block
      (watchdog.yml:1442-1450), add `ATTEMPT: ${{
      steps.run-meta.outputs.attempt-number }}`.

- [ ] T023 [US1] In `collect-cost-report`'s body
      (watchdog.yml:1549-1581), relax the `comments_checked` gate: the
      `elif [ -z "$CREATED_AT" ] || [ -z "$UPDATED_AT" ] || [ -z
      "$BOT_SLUG" ]` branch changes so `comments_checked` requires only
      `$ISSUE` and `$BOT_SLUG`; thread `$CREATED_AT`/`$UPDATED_AT` into
      the attribution jq call as optional bounds (empty string when
      unresolved), exactly as the filter already treats an open-ended
      `since`/`until` (research.md R5, contracts/cost-attribution.md's
      Gating section). When neither a stamp match nor a window is
      available, the collector must still report nothing (FR-009,
      unchanged).

- [ ] T024 [US1] Rewrite `COST_ATTRIBUTION_FILTER`
      (watchdog.yml:1495-1507) into the three-way partition from
      contracts/cost-attribution.md: `authored` (unchanged login
      filter, FR-007) → parse each comment's stamp with
      `<!-- wing-commander-cost-stamp:([^:]+):([^:]+):([^:]+):([^:]+) -->`
      (a non-match yields `stamp: null`, never an error — research.md
      R7) → `stamped_own` (stamp's `run_id:attempt` equals
      `$RUN_ID:$ATTEMPT`, **except** when `$ATTEMPT` is empty, in which
      case a same-`RUN_ID` stamp is NOT trusted into this set —
      research.md R6, FR-002a) → `stamped_foreign` (stamp present,
      run-identity portion does not match — excluded unconditionally,
      never window-bounded, FR-006) → `unstamped` (no stamp, an
      unparseable stamp, or R6's attempt-unresolvable demotion —
      eligible only when `createdAt` falls inside `[since, until]`,
      treating an empty bound as open, FR-008) → `own = stamped_own ∪
      (unstamped ∩ window)`. Keep the existing "first cost line wins,
      sorted by `createdAt`" extraction applied to `own` unchanged.

- [ ] T025 [US1] Pass `$ATTEMPT` into the jq attribution call alongside
      the existing `--arg since`/`--arg until`/`--arg app`
      (watchdog.yml:1572); add one new fact to `COST_REPORT_FILTER`'s
      emitted signal facts (watchdog.yml:1462-1477): `attribution:
      "stamp"` when the verdict rests on `stamped_own` membership
      (including "no `stamped_own` comment existed" driving a
      `cost-line-missing`), `"window"` when it rests on the `unstamped ∩
      window` fallback (FR-010, research.md R8) — thread it through
      `filter_input` (watchdog.yml:1583-1584) as an added key. No
      `normalizedFacts` schema change is needed: `diagnose`'s existing
      generic fixed-vocabulary prompt already reads every signal fact
      and may fold `attribution` into `actual`'s free text on its own
      (constitution IX's "descriptive fact, not a new judgment"
      carve-out).

**Checkpoint**: Two overlapping runs on one lifecycle issue each get
their own verdict; two attempts of one workflow run are told apart. The
reported defect (#369/#370) is fixed.

---

## Phase 5: User Story 3 - The attribution rule has a gate that can fail it (Priority: P2)

**Goal**: The overlapping-runs case becomes a checked-in scenario of the
gates that already exercise the cost-report collector, so a future
regression to the attribution rule fails a gate instead of masking a
supervision signal for weeks.

**Independent Test**: Run the PR-time gate suite against a collector
with the stamp preference removed, and confirm a gate fails.

**Depends on**: Phase 4 (the attribution rule these fixtures exercise
must exist first).

- [ ] T026 [US3] In `.github/scripts/verify-gate-19.py`, add a
      `stamped_comment(created_at, login, body, run_id, attempt,
      job_key="cycle", step_index=0)` fixture helper (sibling to the
      existing `api_comment()`, line 1579) that embeds a
      `<!-- wing-commander-cost-stamp:... -->` marker in the comment
      body; thread a new `attempt` field through `COST_SCENARIOS` dicts
      and `run_cost_one()` (line 1693) so each scenario can set
      `run_env["ATTEMPT"]`.

- [ ] T027 [US3] Add fixtures to `COST_SCENARIOS` (line 1598) for every
      branch data-model.md's "Gate fixtures" table names, each asserting
      the verdict independently per FR-012: (a) two overlapping runs,
      only run A posts a stamped line → run A no signal, run B
      `cost-line-missing` with `attribution: window`; (b) two
      overlapping runs, both post stamped lines → neither signals, each
      reads its own amount; (c) a window containing one foreign-stamped
      comment plus one unstamped well-formed comment → the foreign one
      is excluded, the unstamped one is still accepted, no signal
      (FR-008); (d) several stamps from one run (differing job/step,
      same run-identity) inside one window → all treated as this run's
      own, first-by-creation-time rule unaffected; (e) two attempts of
      one workflow run, only the second posts → first attempt
      `cost-line-missing`, second attempt no signal, verdicts
      independent (SC-008); (f) the inspected run's attempt number is
      unresolvable, a window is also present → same-run-id stamped
      comments demote to unstamped, `attribution: window` (research.md
      R6); (g) a malformed/truncated stamp → degrades to unstamped, no
      collector error (research.md R7); (h) a stamp inside a comment
      from a non-pipeline author → ignored, author filter unchanged
      (FR-007); (i) a replay of #369/#370 (two clarify runs, windows
      overlapping, 8 seconds apart) → the correct, independent verdict
      for each (SC-002).

- [ ] T028 [US3] Add three entries to `COST_MUTATIONS` (line 1760):
      dropping the stamp preference entirely (falls back to window-only,
      reproducing #369/#370); inverting it to prefer `stamped_foreign`;
      and dropping the attempt number from the matched run-identity
      portion (collapses to run-id-only matching, reproducing the re-run
      defect). Each must make `main()`'s mutation loop (line 2288)
      report the suite as failing (SC-005, FR-012).

- [ ] T029 [US3] In `.github/scripts/verify-cost-report-collector.sh`,
      add inline JSON fixtures, in the same style as its existing
      `run_filter`/`run_attribution` calls, pinning the three-way
      partition's new branches in `COST_ATTRIBUTION_FILTER` directly
      (`stamped_own`/`stamped_foreign`/`unstamped`, the
      attempt-unresolvable demotion) and the new `attribution` key in
      `COST_REPORT_FILTER`'s output — the script already extracts both
      programs live from `watchdog.yml` via
      `wc_shell_harness.extract_quoted_var()`, so no hand-copied jq text
      is added (research.md R9's own reason this script exists: a
      hand-copied filter here previously stayed green through a real
      shipped break).

**Checkpoint**: The overlapping-runs case and its adversarial mutations
are checked-in; `run-local-gates.py` fails if the stamp preference is
removed, inverted, or if the attempt number is dropped from the matched
key.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T030 [P] Update
      `specs/046-watchdog-supervision-collectors/data-model.md`'s
      `cost-report` collector description to mention the new
      `attribution` fact and the stamp-based partition this feature
      adds, so that document — which predates this feature and defines
      the collector's boundary — does not describe a claim shape this
      feature has since widened (plan.md's Project Structure section
      flags this explicitly as a candidate follow-up for the tasks
      stage to decide).

- [ ] T031 Run `python3 .github/scripts/run-local-gates.py` from the
      repository root and confirm the full suite passes, including
      every gate touched by T002-T029 (CLAUDE.md's PR-time gate suite;
      quickstart.md's own closing step).

- [ ] T032 [P] Grep-audit
      `.github/actions/wing-commander-metrics-summary/action.yml` and
      `.github/actions/wing-commander-metrics-persist/action.yml` for
      every `record_key`-composing line and confirm each includes
      `run_attempt` (quickstart.md's informal cross-cutting check,
      backed by T009's shape-regex gate as the actual enforcement).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — run first.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS User Story 2 and
  User Story 1 — neither has a widened key to consume otherwise.
- **User Story 2 (Phase 3)**: Depends on Foundational. Produces the
  stamp User Story 1 consumes — build this before, not in parallel
  with, User Story 1, even though both are Priority P1 (spec.md: "The
  attribution rule in User Story 1 cannot exist without the stamp").
- **User Story 1 (Phase 4)**: Depends on Foundational and User Story 2.
- **User Story 3 (Phase 5)**: Depends on User Story 1 — its fixtures and
  mutations exercise the attribution rule Phase 4 implements.
- **Polish (Phase 6)**: Depends on every phase above.

### Within Each Phase

- Foundational: T002→T005 are sequential (same two files, each step
  building on the last); T006-T013 are independent fixture/gate files
  and may run in parallel with each other once T002-T005 land (they
  reference the new literal shape T003 introduces).
- User Story 2: T014→T016 are sequential (same file, same composite);
  T017 depends on T014-T016 existing to fixture against; T018-T020 are
  independent per-file edits that may run in parallel once T014-T016
  land.
- User Story 1: T021→T025 are sequential (each builds on the prior
  step's output within the same two watchdog.yml steps).
- User Story 3: T026 first (the fixture helper), then T027-T029 may
  proceed in parallel once it exists.

### Parallel Opportunities

- All of T006-T013 (Foundational's gate/fixture widenings) once T002-T005
  land.
- T018 (7 single-call-site workflow files) in parallel with each other,
  and with T019/T020 once T014-T016 land.
- T027-T029 (User Story 3's fixture/mutation additions) once T026 lands.
- T030 and T032 (Polish) in parallel with each other; T031 last.

---

## Parallel Example: Foundational Gate Widenings

```bash
# Once T002-T005 land, launch the independent gate/fixture widenings together:
Task: "Add attempt parameter to wc_metrics_harness.py's record builders (T006)"
Task: "Widen verify-metrics-summary-record-emission.py's mutation literal, add attempt mutation (T007)"
Task: "Widen verify-metrics-persist-retry.py's want_key literals (T008)"
Task: "Add run_attempt + shape regex to verify-metrics-record-schema.py, update the spec-043 contract doc (T009)"
Task: "Widen verify-metrics-schema-version-tolerance.py fixtures (T010)"
Task: "Widen verify-turn-budget-collector.sh fixtures (T011)"
Task: "Widen verify-watchdog-no-record-on-clean-path.py literals (T012)"
Task: "Widen fixtures/metrics-record-schema/*.json literals (T013)"
```

## Parallel Example: User Story 2 Call Sites

```bash
# Once T014-T016 land, launch the 7 single-call-site workflows together:
Task: "Add RUN_STAMP env + fallback edit to clarify.yml (T018)"
Task: "Add RUN_STAMP env + fallback edit to intake.yml (T018)"
Task: "Add RUN_STAMP env + fallback edit to plan.yml (T018)"
Task: "Add RUN_STAMP env + fallback edit to tasks.yml (T018)"
Task: "Add RUN_STAMP env + fallback edit to rebase.yml (T018)"
Task: "Add RUN_STAMP env + fallback edit to cleanup.yml (T018)"
Task: "Add RUN_STAMP env + fallback edit to finalize.yml (T018)"
# implement.yml (T019) and pr-conversation.yml (T020) run alongside these too.
```

---

## Implementation Strategy

### MVP Scope

Foundational + User Story 2 + User Story 1 together are the MVP: this
is the smallest slice that actually fixes lifecycle issue #491's
reported defect (#369/#370). User Story 2 alone stamps every comment but
changes no observable behavior; User Story 1 alone has nothing to match
against without User Story 2's stamp. Both are Priority P1 for exactly
this reason — ship them together.

1. Complete Phase 1 (Setup) and Phase 2 (Foundational — CRITICAL, blocks
   everything).
2. Complete Phase 3 (User Story 2 — the stamp).
3. Complete Phase 4 (User Story 1 — the attribution rule). **STOP and
   VALIDATE**: replay the #369/#370 shape per quickstart.md Story 1 and
   confirm each run gets its own verdict.
4. Deploy/demo — the reported defect is fixed.

### Incremental Delivery

5. Add Phase 5 (User Story 3 — gate coverage) so the fix this MVP
   shipped can't silently regress.
6. Complete Phase 6 (Polish).

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps a task to its user story for traceability; Setup,
  Foundational, and Polish tasks carry no story label by convention.
- Commit after each phase's checkpoint, not after every individual task
  — several tasks in Phase 2 and Phase 3 touch the same file across
  adjacent lines and are easiest to review as one coherent diff per
  file.
- Re-run `python3 .github/scripts/run-local-gates.py` at every
  checkpoint, not only at T031 — a gate touched by an earlier phase
  (e.g. Gate 39 in Foundational) can be broken by a later phase's edit
  (e.g. a fixture T013 missed) and is cheaper to catch immediately.
- A change that touches any `if:`, `continue-on-error:`, or failing step
  in `watchdog.yml` (T021-T025 touch `collect-cost-report`, which
  carries `continue-on-error: true`) should get a pass from the
  `review-step-gating` skill before merge, per CLAUDE.md.
