# Tasks: The Per-Job Minute Floor — No-Op and Healthy Paths Cost What They Run

**Input**: Design documents from `/specs/058-per-job-minute-floor/`
(plan.md, research.md, data-model.md, quickstart.md,
contracts/image-check-shape-delta.md, contracts/watchdog-clean-path-delta.md,
contracts/metrics-persist-sweep-delta.md, contracts/gate-coverage-058.md)

**Tests**: This feature's verification is deterministic gate scripts with
checked-in fixtures (constitution VIII/FR-006/FR-008/FR-032/SC-012), not a
conventional test suite. Gate/fixture tasks are listed inline with the
implementation task they verify, matching this repository's existing
`verify-*.py`/`.sh` convention rather than a separate TDD phase.

**Gate numbering**: the highest gate number wired into
`.github/workflows/lint-workflows.yml` as of this branch is Gate 72
(`grep -n "Gate " .github/workflows/lint-workflows.yml`). This feature's new
gates are assigned sequentially from **Gate 73**. Re-check this at
implementation time in case another in-flight branch has since claimed one
of these numbers (research.md's own numbering caveat) and renumber if so.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (sub-problem A, image check), US2 (sub-problem B,
  watchdog clean path), US3 (sub-problem C, metrics persistence sweep)

## Path Conventions

GitHub Actions reusable-workflow pipeline, no `src`/`tests` split. Every
path below is relative to the repository root.

---

## Phase 1: Setup

- [X] T001 Confirm the gate-number reservation above is still accurate:
  `grep -n "Gate 7[0-9]" .github/workflows/lint-workflows.yml` must show
  nothing above Gate 72. If it does, shift every "Gate 7x" reference in
  this file and in contracts/gate-coverage-058.md by the same offset before
  starting Phase 3.

---

## Phase 2: Foundational

None. Unlike most features, this one has no shared infrastructure that
blocks all three stories — instead, spec.md's own ordering constraint
*is* the dependency: **User Story 1 (Phase 3) must complete before Phases
4 and 5**, because sub-problem A rewrites every job-graph condition in
`watchdog.yml` and `metrics-persist.yml` that sub-problems B and C then
build on (plan.md's Structure Decision). Do not start Phase 4 or Phase 5
until Phase 3's checkpoint passes.

---

## Phase 3: User Story 1 - A stage with no container image pays nothing for the image check (Priority: P1) 🎯 MVP

**Goal**: `verify-image-prerequisites` gains a job-level `if:` so it
reports `skipped` (zero billed minutes) when no image is configured, in
all 13 published stages, while every dependent job's run/skip behavior is
otherwise unchanged.

**Independent Test**: dispatch any stage twice (no image, then a bad
image) and read the jobs API of each run — see quickstart.md Story 1.

### Per-stage job-graph rewrite (data-model.md's dependent-job condition table, research.md R-A1/R-A2)

Each task below: (1) adds `if: inputs.container-image != ''` to the
`verify-image-prerequisites` job itself; (2) rewrites the `if:` of every
job in the same file whose `needs:` names `verify-image-prerequisites`
directly, per data-model.md's three shapes — entry job (bare `needs:`) →
`if: !cancelled() && needs.verify-image-prerequisites.result != 'failure'`
(plus `&& needs.<X>.result == 'success'` for each other named dependency);
survivor job (already has a status-function `if:`) → narrow its existing
`needs.verify-image-prerequisites.result == 'success'` clause to
`!= 'failure'`, leaving every other clause in that `if:` byte-for-byte
unchanged. A job that reaches the check only transitively (through
another job already carrying this condition) is left untouched
(research.md R-A2) — do not add a redundant clause to it. Job names/line
numbers below are current as of this branch; re-grep
(`needs:.*verify-image-prerequisites`) before editing since they will have
shifted.

- [X] T002 [P] [US1] `.github/workflows/intake.yml`: job-level `if:` on
  `verify-image-prerequisites` (~line 244); entry job `intake` (~line 347,
  bare `needs: verify-image-prerequisites`, carries the `#224` comment —
  update or remove that comment since the job-level skip is now
  intentional); survivor job `stalled` (~line 1402-1409, narrow the
  `needs.verify-image-prerequisites.result == 'success'` clause at line
  1404 only — the second reference at line 1406,
  `needs.verify-image-prerequisites.result == 'failure'`, is a distinct
  clause identifying *why* `stalled` fired and must stay `== 'failure'`
  unchanged).
- [X] T003 [P] [US1] `.github/workflows/clarify.yml`: job-level `if:` on
  `verify-image-prerequisites` (~line 204); entry job `clarify` (~line
  306, bare `needs:`); survivor job `stalled` (~line 1157-1162, one other
  dependency `clarify`).
- [X] T004 [P] [US1] `.github/workflows/plan.yml`: job-level `if:` on
  `verify-image-prerequisites` (~line 271); entry job `resolve-spec`
  (~line 371, bare `needs:`). The `plan` job (~line 395) depends only on
  `resolve-spec`, not on the check directly — no rewrite (R-A2).
- [X] T005 [P] [US1] `.github/workflows/tasks.yml`: job-level `if:` on
  `verify-image-prerequisites` (~line 276); entry job `resolve-spec`
  (~line 378, bare `needs:`); survivor jobs `stalled` (~line 1524-1530,
  other deps `resolve-spec`, `tasks`) and `stalled-approved` (~line
  1662-1668, other deps `resolve-spec`, `tasks-approved`).
- [X] T006 [P] [US1] `.github/workflows/implement.yml`: job-level `if:`
  on `verify-image-prerequisites` (~line 260); entry job `implement`
  (~line 363, bare `needs:`); survivor job `stalled` (~line 2662-2667,
  other dep `implement`).
- [X] T007 [P] [US1] `.github/workflows/finalize.yml`: job-level `if:`
  on `verify-image-prerequisites` (~line 210); entry job `finalize`
  (~line 310, bare `needs:`); survivor job `stalled` (~line 1402-1407,
  other dep `finalize`).
- [X] T008 [P] [US1] `.github/workflows/cleanup.yml`: job-level `if:` on
  `verify-image-prerequisites` (~line 238); entry job `select` (~line
  337, bare `needs:`). `teardown-done`, `teardown-rejected`,
  `mark-stalled` depend only on `select` — no rewrite (R-A2).
- [X] T009 [P] [US1] `.github/workflows/rebase.yml`: job-level `if:` on
  `verify-image-prerequisites` (~line 186); entry job `discover` (~line
  284, bare `needs:`). `rebase` depends only on `discover` — no rewrite
  (R-A2).
- [X] T010 [P] [US1] `.github/workflows/watchdog.yml`: job-level `if:`
  on `verify-image-prerequisites` (~line 238); entry job `collect`
  (~line 321, bare `needs:`); survivor jobs `act` (~line 3080-3118,
  other deps `collect`, `diagnose`, `triage`), `findings-dropped` (~line
  3564-3568, other deps `collect`, `diagnose`), `report-unhandled-failure`
  (~line 3627-3636, other deps `collect`, `diagnose`, `triage`, `act`,
  `findings-dropped`). This file is also rewritten by User Story 2
  (Phase 4) — land this task's changes first so Phase 4 rewrites
  `collect`/`diagnose` against the already-amended job-graph, not the old
  one.
- [X] T011 [P] [US1] `.github/workflows/pr-conversation.yml`: job-level
  `if:` on `verify-image-prerequisites` (~line 245); entry job
  `classify-and-announce` (~line 330, bare `needs:` at ~346); survivor
  jobs `dispatch-once` (~line 2559-2563, other deps
  `classify-and-announce`, `act`), `report-fold-outcomes` (~line
  2742-2746, same other deps), `legs-dropped` (~line 2957-2961, other dep
  `classify-and-announce`), `stalled` (~line 3018-3023, same other dep,
  plus an `image-result` output reference at ~line 3136 that stays
  unchanged).
- [X] T012 [P] [US1] `.github/workflows/metrics-persist.yml`: job-level
  `if:` on `verify-image-prerequisites` (~line 111); entry job `persist`
  (~line 165, bare `needs:` at ~166). This file is also rewritten by User
  Story 3 (Phase 5) for the `since` input — land this task first.
- [X] T013 [P] [US1] `.github/workflows/auto-update-spec-kit.yml`:
  job-level `if:` on `verify-image-prerequisites` (~line 213); entry jobs
  `health-check` (~line 298, bare `needs:` at ~307), `pr-merged` (~line
  2979, bare `needs:` at ~2981), `comment-reply` (~line 3123, bare
  `needs:` at ~3125); survivor jobs `evaluate-path` (~line 822-826, other
  deps `settle`, `comment-reply`), `prepare` (~line 1417-1430, other dep
  `evaluate-path`), `e2e-stage` (~line 1645-1655, other dep `prepare`),
  `verify` (~line 2218-2224, other deps `prepare`, `e2e-stage`), `act`
  (~line 2555-2568, other deps `health-check`, `evaluate-path`,
  `prepare`, `verify`). Largest single-file rewrite in this story — eight
  dependent jobs.
- [X] T014 [P] [US1] `.github/workflows/private-image-dogfood.yml`:
  job-level `if:` on `verify-image-prerequisites` (~line 76); entry job
  `dogfood` (~line 130, bare `needs:` at ~131).

### Gates (FR-006, FR-007, FR-008, contracts/gate-coverage-058.md)

- [X] T015 [US1] Amend Gate 23's real check in
  `.github/workflows/lint-workflows.yml` (the inline Python block at the
  "Gate 23 — every published stage checks adopter-chosen image
  prerequisites before any real job starts" step, ~lines 2314-3030):
  (a) invert the `#224` job-level-`if:` rejection at ~lines 2434-2441 —
  today it errors on *any* job-level `if:` on `verify-image-prerequisites`;
  after this feature the job MUST carry job-level
  `if: inputs.container-image != ''` exactly, so the check must instead
  error when that line is *absent* or differs; (b) change
  `has_result_guard` (~line 2378-2395) from matching
  `needs.verify-image-prerequisites.result == 'success'` to matching
  `!= 'failure'` (data-model.md's survivor shape); (c) extend the
  entry-job branch (~lines 2483-2504, currently only checks that
  `verify-image-prerequisites` is named in `needs:`) to also require the
  entry job's own `if:` contain the literal
  `needs.verify-image-prerequisites.result != 'failure'` and
  `!cancelled()` — this is FR-007's reversion check (Acceptance Scenario
  5): a job with `needs:` naming the check but no `if:` at all, or an
  `if:` that omits this comparison (including one narrowed back to
  `== 'success'`), must fail by name (stage + job).
- [X] T016 [US1] Amend Gate 22 in `.github/workflows/lint-workflows.yml`
  (the inline Python block at "Gate 22 — every job of every published
  stage carries the runner/container-image passthrough", ~line
  2041-2300) to add a fourth byte-for-byte comparison, alongside
  `EXPECTED_RUNS_ON`/`EXPECTED_IMAGE`/`EXPECTED_CREDENTIALS`: an
  `EXPECTED_VIP_IF` constant for
  `if: inputs.container-image != ''` on the `verify-image-prerequisites`
  job itself, asserted identical across all 13 stages.
- [X] T017 [US1] Update `.github/scripts/verify-gate-23.py`'s
  `--selftest` fixtures (the extracted-source self-test for 038's image-
  prerequisites gate) to match T015's amended detector: a fixture proving
  a bare-`needs:` reversion (no `if:` at all) still fails, and a new
  fixture proving an `if:` narrowed back to
  `needs.verify-image-prerequisites.result == 'success'` (instead of
  `!= 'failure'`) also fails, naming the stage and job (data-model.md's
  "Gate fixtures" table).
- [X] T018 [US1] Update `.github/scripts/verify-gate-22.py`'s self-test
  fixtures to cover T016's new `EXPECTED_VIP_IF` comparison: one fixture
  with the line present and correct, one fixture missing it — the second
  must fail, naming the stage (contracts/gate-coverage-058.md).
- [X] T019 [US1] Extend Gate 15's self-test `CASES` list in
  `.github/scripts/verify-gate-15.py` (~line 73) with one new case: a
  rewritten entry job (T002-T014's shape — `if: !cancelled() &&
  needs.verify-image-prerequisites.result != 'failure'`, no second real
  dependency) that Gate 15's existing status-function walk must still
  flag correctly if it omits the ancestor check, proving the newly
  broadened ~30-job population is actually exercised (research.md R-A3).
  No production-code change to Gate 15 itself is needed — the walk
  already covers the new shape once it exists.

### Validation (SC-001–SC-004, quickstart.md Story 1)

- [X] T020 [US1] Run `python .github/scripts/run-local-gates.py` and
  confirm all gates pass on the real tree, including the amended Gate 22
  and Gate 23 and their self-tests (T015-T019).
- [ ] T021 [US1] Follow quickstart.md's Story 1 steps 1-4 and 7 against a
  representative sample of the 13 rewritten stages (at minimum `intake`,
  `watchdog`, and `auto-update-spec-kit` — the largest rewrite): confirm
  the no-image run shows `verify-image-prerequisites` skipped with every
  other job's conclusion matching current `main`, the bad-image run shows
  it failed with every dependent skipped, and a forced-failure of a
  second dependency still skips a two-dependency dependent job
  (Acceptance Scenarios 1, 2, 4). NOT DONE this session: this requires
  dispatching real workflow runs and reading their jobs API
  (`gh workflow run`/`gh run view`), neither of which this run's permitted
  command list includes (only `gh issue view`/`gh issue comment` are
  granted). Needs a human or a differently-scoped run to dispatch the
  sample runs and confirm the job graph live, once this branch reaches
  main or a PR.
- [X] T022 [US1] Follow quickstart.md's Story 1 step 6: on a scratch
  branch, revert one dependent job's `if:` to bare `needs:` and confirm
  Gate 23 (T015) fails, naming that stage and job (Acceptance Scenario 5,
  FR-007); revert the scratch change afterward. Done in-place (this
  session has no scratch-branch tooling): `intake.yml`'s `intake` job's
  `if:`/comment lines were removed, Gate 23 was confirmed to fail by name
  (`.github/workflows/intake.yml`, job `'intake'`), and the change was
  reverted via a matching Edit (confirmed byte-identical to HEAD via
  `git diff`) since `git checkout`/`git restore` are outside this run's
  permitted command list.

**Checkpoint**: All 13 stages bill zero jobs for the image check on the
no-image path, every gate passes, and FR-007's reversion check is proven
live. User Story 1 is independently shippable here.

---

## Phase 4: User Story 2 - A clean watchdog inspection is decided by code, not by an agent (Priority: P2)

**Goal**: an empty aggregate signal set alone (not "zero signals AND zero
failed collectors") skips `diagnose` and posts a deterministic
passed-inspection record from `collect`, billing at most two jobs and
invoking no agent.

**Independent Test**: drive one healthy inspection and one signal-bearing
inspection; read both jobs APIs — see quickstart.md Story 2.

**Depends on**: Phase 3 (T010 rewrites `watchdog.yml`'s image-check
shape first).

### `watchdog.yml` changes (research.md R-B1/R-B2/R-B4/R-B5, contracts/watchdog-clean-path-delta.md)

- [X] T023 [US2] `.github/workflows/watchdog.yml`: widen `diagnose`'s
  `if:` (~line 1946, currently
  `needs.collect.outputs.evidence-available != 'false'`) to additionally
  require a non-empty signal set:
  `needs.collect.outputs.evidence-available != 'false' &&
  needs.collect.outputs.signals != '' && needs.collect.outputs.signals != '[]'`
  (research.md R-B1). The existing all-failed branch
  (`evidence-available == 'false'`, ~line 1927's "could not inspect"
  step) is untouched — FR-013.
- [X] T024 [US2] `.github/workflows/watchdog.yml`: add a new
  deterministic step to the `collect` job, immediately after the
  `aggregate` step (~line 1880-1925), gated:
  `steps.aggregate.outcome == 'success' &&
  steps.aggregate.outputs.evidence-available != 'false' &&
  (steps.aggregate.outputs.signals == '' || steps.aggregate.outputs.signals == '[]')`.
  It posts the passed-inspection comment to the lifecycle issue, choosing
  full wording (`steps.aggregate.outputs.collectors-failed == 0`) or
  partial wording (`> 0`, naming both counts) by relocating — not
  rewording — the two existing strings from `diagnose`'s "Report 'passed
  inspection'" step (~lines 2616 and 2618). Gating on
  `steps.aggregate.outcome == 'success'` (not just reading its outputs)
  is required so a failed `aggregate` step never yields a false "passed"
  (spec.md's edge case). No issue is filed or updated (FR-009). This adds
  zero jobs — FR-018's "collection job plus at most one guaranteed-report
  job" comes from placement inside `collect`, not a new job (research.md
  R-B2's rejected alternative).
- [X] T025 [US2] `.github/workflows/watchdog.yml`: confirm (no code
  change expected, verify only) that the existing "Report 'passed
  inspection'" step inside `diagnose` (~line 2599-2618) and its
  downstream `stalled`/`report-unhandled-failure` conditions referencing
  `needs.diagnose.outputs.outcome != 'passed-inspection'` (~lines 2662,
  3114) are unaffected by T023/T024 — this is a different event (the
  agent ran and found nothing actionable after weighing real signals),
  reached only when `diagnose` actually ran (FR-012).
- [X] T026 [US2] `.github/workflows/watchdog.yml`: make `run-name`
  optional (default `''`) on the published `workflow_call` input block;
  when empty, resolve it inside `collect`'s existing inspected-run lookup
  via the same `gh run view --repo ... --json workflowName --jq
  .workflowName` call `wing-commander-8-watchdog.yml`'s `resolve` job
  makes today (research.md R-B4, data-model.md). A caller that still
  supplies `run-name` explicitly must see no behavior change.

### Wrapper and self-verifier (FR-020, FR-032)

- [X] T027 [US2] `.github/workflows/wing-commander-8-watchdog.yml`:
  remove the `resolve` job entirely. The remaining `watchdog` job becomes
  a bare `uses: ./.github/workflows/watchdog.yml` with
  `run-id: ${{ format('{0}', inputs.run-id || github.event.workflow_run.id) }}`
  and no `run-name:` input supplied (letting T026's stage-side default/
  resolution apply) — same shape as
  `wing-commander-metrics-persist.yml`'s own prior `resolve`-removal
  (spec 043), reused per research.md R-B4. Keep the pause kill-switch
  (`vars.WING_COMMANDER_WATCHDOG_PAUSED`) and the skipped-source guard on
  the remaining job exactly as they are today (FR-015 — unexempted).
- [X] T028 [US2] `.github/scripts/verify-watchdog-run.sh`: lower the
  hardcoded absolute floor constant (currently `40` at ~line 113) to a
  value measured against this feature's own post-merge component
  durations (`collect` ~25s + `report-unhandled-failure` ~8s,
  sequential, on the no-finding path) with headroom — the exact number is
  an implementation-time measurement (research.md R-B5), not fixed by
  this plan. Do not remove the absolute floor (it protects the
  fewer-than-3-prior-runs bootstrap window the median term cannot cover);
  the median-based term itself needs no code change. Add a passing branch
  to the diagnose-duration ceiling check: `diagnose` being `skipped` (not
  just "ran under its ceiling") is a valid healthy shape.

### Gates (contracts/gate-coverage-058.md)

- [X] T029 [US2] New Gate 73 — `verify-watchdog-clean-path`
  (`.github/scripts/verify-watchdog-clean-path.py` or `.sh`, matching
  whichever existing watchdog-gate convention it most resembles), wired
  into `.github/workflows/lint-workflows.yml`. Asserts against fixtures
  of `collect`'s job graph: (a) every collector reports + empty signal
  set → `diagnose` skipped, no agent step, full-pass wording posted; (b)
  one failed collector + one reporting collector + empty signal set →
  `diagnose` skipped, partial-pass wording naming both counts (FR-019,
  FR-011 — spec.md's explicit edge case); (c) all collectors fail →
  unchanged "could not inspect" path, no passed-inspection record
  (FR-013 — proves the new step does not fire here); (d) `aggregate`
  step itself fails → no passed-inspection record regardless of its
  (stale) outputs; (e) at least one signal → `diagnose` runs, matching
  today's filing/triage/action behavior byte-for-byte (FR-012, a
  regression guard). Ship with checked-in fixtures for each branch
  (data-model.md's "Gate fixtures" table, constitution VIII).
- [X] T030 [US2] New Gate 74 — `verify-watchdog-no-record-on-clean-path`
  (`.github/scripts/verify-watchdog-no-record-on-clean-path.py` or
  `.sh`), wired into `lint-workflows.yml`. On T029's full-pass and
  partial-pass fixtures, asserts no `metrics-record*` artifact is
  produced and the lifecycle rollup's "every agent run appears exactly
  once" computation (spec 043,
  `.github/scripts/verify-metrics-rollup-idempotent.py`'s subject) does
  not list the run at all — never as a record that existed and could not
  be retrieved (FR-031, spec.md's edge case).
- [X] T031 [US2] New Gate 75 — `verify-watchdog-wrapper-resolve-fold`
  (`.github/scripts/verify-watchdog-wrapper-resolve-fold.py` or `.sh`),
  wired into `lint-workflows.yml`. Asserts
  `wing-commander-8-watchdog.yml` has exactly one job (`watchdog`), it is
  a bare `uses:` call, and `run-name` is not among the inputs it passes;
  and, on the stage side, that `watchdog.yml`'s `collect` job resolves
  `run-name` internally when the input is empty (FR-020). Fixture: a
  `run-name`-omitted invocation, asserting the stage's own resolution
  step ran and produced a non-empty value used in the posted comments.
- [X] T032 [US2] Amend `.github/scripts/verify-watchdog-run.sh` (Gate 71
  in `lint-workflows.yml` per its existing "the watchdog verifier"
  wiring — confirm exact gate number by grep, do not assume) and its
  companion fixture harness `.github/scripts/verify-watchdog-run-
  failure-paths.sh` (Gate 36): add the new healthy shape (`diagnose`
  skipped, passed-inspection comment present, no execution-output
  artifact, no metrics record, whole-run duration under T028's new
  absolute floor) as a **passing** case. Every existing failure branch
  (crashed/stalled agent, could-not-inspect degradation, fired safety
  net, fabricated verdict) must still fail on its own fixture — do not
  weaken any existing assertion (FR-032, SC-014). Two corrections, both
  from doing what this task asked rather than assuming. Gate number:
  `verify-watchdog-run.sh` is not wired as a gate in `lint-workflows.yml`
  at all (it runs inside stage 8b); only its fixture harness is wired,
  and as **Gate 36** — 71 is the stage-findings pair. Duration: a run
  genuinely *under* the new absolute floor must still FAIL, so the
  passing shape is one under the OLD 40s floor and above the new 20s one
  (~33s). New scenarios: s11 (the clean path verifies healthy and files
  nothing), s12 (a 15s clean-path run still fails the re-scaled floor),
  s13 (diagnose skipped with neither of collect's reporters run fails).
  New mutations m3/m4 cover s12/s13; `run_mutation`'s scenario-id regex
  widened from `s[0-9]` to `s[0-9]+` so two-digit scenarios are
  attributed correctly. `verify-watchdog-run.sh` also gained the
  neither-reporter-ran check the healthy shape's "passed-inspection
  comment present" clause implies.

### Validation (SC-005–SC-008, SC-013, SC-014, quickstart.md Story 2)

- [X] T033 [US2] Run `python .github/scripts/run-local-gates.py` and
  confirm the new Gates 73-75 and amended Gate 71/36 pass on the real
  tree, alongside every gate from Phase 3. Run: 118/118 passed
  (115 before this phase; the three new gates are the difference),
  including `verify-watchdog-clean-path.py`,
  `verify-watchdog-no-record-on-clean-path.py`,
  `verify-watchdog-wrapper-resolve-fold.py`,
  `verify-watchdog-run-failure-paths.sh` (Gate 36, see T032's gate-number
  correction) and `verify-watchdog-self-skip-guard.py` (Gate 70, which
  T027 retargeted).
- [ ] T034 [US2] Follow quickstart.md's Story 2 steps 1-11: a healthy
  inspection bills at most two jobs and posts exactly one full-pass
  comment with no agent step anywhere in the run (grep the run's job logs
  for `anthropics/claude-code-action` as a second check); a
  one-failed/one-reporting-collector inspection posts the partial-pass
  wording; a signal-bearing inspection still runs `diagnose` with
  unchanged filing/triage/action outcomes; the all-failed case still
  reaches "could not inspect"; the aggregate-failure case posts nothing;
  the watchdog's own runs stay unexempted; `report-unhandled-failure`
  still executes when every other job dies; the wrapper's job list is
  exactly one job with a correctly resolved run name; the self-verifier
  accepts the new healthy shape and still fails every pre-existing
  failure shape. NOT DONE this session, for the same reason T021 is not:
  every step needs `gh workflow run`/`gh run view` against live runs, and
  this run's permitted command list grants only `gh issue view`/`gh issue
  comment`. Needs a human or a differently-scoped run once this branch
  reaches main or a PR. The deterministic half of each claim is covered
  by Gates 73-75 and Gate 36's s11-s13 against checked-in fixtures.
- [X] T035 [US2] `grep -rn "anthropics/claude-code-action"
  .github/workflows .github/actions` and diff the match set against
  current `main` — confirm no new agent invocation was added anywhere
  (SC-013). Done as a per-file match count on both trees
  (`git grep -c ... origin/main` vs `... HEAD`): identical, 13 files,
  22 references, including `watchdog.yml`'s single one. Zero new agent
  invocations.

**Checkpoint**: A clean watchdog inspection bills at most two jobs and
invokes no agent; a signal-bearing one is byte-for-byte unchanged. User
Stories 1 and 2 are both independently shippable here.

---

## Phase 5: User Story 3 - Metrics persistence pays only for completions that emitted a record (Priority: P3)

**Goal**: the nine stage workflows whose records are read back promptly
keep their per-completion persistence run; the watchdog leaves the
completion trigger (a healthy inspection now emits nothing, per Phase 4);
a daily scheduled sweep, resuming from a durable high-water mark, picks
up signal-bearing watchdog inspections and any missed completion.

**Independent Test**: drive a burst of completions plus a healthy
watchdog inspection, then list persistence runs and read the records file
— see quickstart.md Story 3.

**Depends on**: Phase 3 (T012 rewrites `metrics-persist.yml`'s image-check
shape first) and Phase 4 (FR-030(b) states the wrapper trigger removal in
terms of "after FR-031").

### `metrics-persist.yml` stage — `since` input and sweep mode (research.md R-C1, contracts/metrics-persist-sweep-delta.md)

- [ ] T036 [US3] `.github/workflows/metrics-persist.yml`: add optional
  input `since` (string, ISO-8601 timestamp, default `''`) to the
  `workflow_call` inputs block (~line 13-76, alongside `run-id`). Update
  the input's own description and `run-id`'s description to note it is
  ignored when `since` is set.
- [ ] T037 [US3] `.github/workflows/metrics-persist.yml`: in the
  `persist` job (~line 158 onward), branch on whether `inputs.since` is
  empty. Empty (today's only value): unchanged single-`run-id` behavior.
  Non-empty: list every workflow run in the repository concluded at or
  after `since` minus a one-hour overlap (paginated `gh api
  .../actions/runs`, filtered client-side per the existing Gate 18
  per-page-not-whole-result caution — research.md R-C3), then invoke the
  existing discover→retrieve→validate→append-with-retry pipeline
  (`.github/actions/wing-commander-metrics-persist/action.yml`) once per
  discovered run-id, batching every run's records into one
  append-with-retry commit rather than one push per run (research.md
  R-C1).
- [ ] T038 [US3] `.github/actions/wing-commander-metrics-persist/
  action.yml`: extend the "Append records with retry" step (~line 265
  onward) so a sweep-mode invocation (batched multi-run input) also
  writes, in the **same** commit as any `records.jsonl` append:
  `sweep-state.json` (`{"high_water_mark": "<ISO-8601>"}`, the maximum
  `concluded_at` among runs just processed — research.md R-C2) and
  `unpersisted.jsonl` (one line per discovered run whose artifact had
  already expired before the sweep reached it:
  `{"run_id", "workflow", "reason": "artifact_expired", "discovered_at"}`
  — FR-028, research.md R-C4). A completion-triggered (non-sweep) run
  writes neither file — only `records.jsonl`, unchanged. The high-water
  mark still advances past an expired-artifact run so it is not
  rediscovered on every subsequent sweep.
- [ ] T039 [US3] Confirm (verify only, no code change expected per
  research.md R-B3) that `.github/actions/wing-commander-metrics-persist/
  action.yml`'s existing "no `metrics-record*` artifact found" tolerance
  (`persisted-count: 0`, not an error) already covers T024's no-record
  healthy-inspection case with zero changes needed.

### Wrapper — sweep trigger, dropped watchdog trigger (research.md R-C5/R-C6/R-C7)

- [ ] T040 [US3] `.github/workflows/wing-commander-metrics-persist.yml`:
  remove `"Wing Commander · 8 watchdog"` from the `workflow_run.workflows`
  list (~line 28, FR-030(b)). Add
  `schedule: - cron: "37 6 * * *"` alongside the existing
  `workflow_run`/`workflow_dispatch` triggers (FR-030(c), research.md
  R-C6 — chosen to avoid colliding with `lint-workflows.yml` (`43 5`),
  `wing-commander-rebase.yml` (`17 4`),
  `wing-commander-7-cleanup.yml` (`53 6`), and
  `wing-commander-auto-update-spec-kit.yml` (`13 7`)). Add a `since`
  input to the existing `workflow_dispatch.inputs` block
  (`required: false`) rather than a second `workflow_dispatch:` block.
- [ ] T041 [US3] `.github/workflows/wing-commander-metrics-persist.yml`:
  add a new `sweep` job, gated
  `if: github.event_name == 'schedule' || (github.event_name ==
  'workflow_dispatch' && inputs.since != '')`, calling the same
  `metrics-persist.yml` with
  `since: ${{ inputs.since || <computed high-water-mark minus one-hour
  overlap> }}` — read `sweep-state.json` from the destination branch
  directly (a plain `git show`/`gh api` read of that one file, no full
  pipeline-repo checkout needed) to compute the default when `schedule:`
  fired with no explicit `since`. No `concurrency:` group gates `sweep`
  against the existing `persist` job or against itself (FR-030(d),
  research.md R-C7, explicit non-decision — do not add one).

### Gates (contracts/gate-coverage-058.md)

- [ ] T042 [US3] New Gate 76 — `verify-metrics-sweep-idempotence`
  (`.github/scripts/verify-metrics-sweep-idempotence.sh`), wired into
  `lint-workflows.yml`. Fixture: one run already persisted via the
  completion trigger, one run reachable only by the sweep — after a
  sweep pass, each appears in `records.jsonl` exactly once, and
  re-running the sweep a second time over the same window adds nothing
  new (FR-022, FR-027).
- [ ] T043 [US3] New Gate 77 — `verify-metrics-sweep-high-water-mark`
  (`.github/scripts/verify-metrics-sweep-high-water-mark.sh`), wired into
  `lint-workflows.yml`. Asserts the mark advances to the latest
  concluded-run timestamp processed, in the same commit as any records
  append (a fixture forcing a push rejection proves both files retry
  together — research.md R-C2); a second sweep from the advanced mark
  does not re-list runs the first already accounted for except within
  the fixed one-hour overlap (research.md R-C3).
- [ ] T044 [US3] New Gate 78 — `verify-metrics-expired-artifact-outcome`
  (`.github/scripts/verify-metrics-expired-artifact-outcome.sh`), wired
  into `lint-workflows.yml`. Fixture: a discovered run whose artifact
  fixture returns expired/404 produces exactly one `unpersisted.jsonl`
  line naming it, the high-water mark advances past it, and a subsequent
  sweep does not re-list or re-log it (FR-028).
- [ ] T045 [US3] New Gate 79 — `verify-metrics-wrapper-trigger-drops-
  watchdog` (`.github/scripts/verify-metrics-wrapper-trigger-drops-
  watchdog.py`), wired into `lint-workflows.yml`. Asserts
  `"Wing Commander · 8 watchdog"` is absent from
  `wing-commander-metrics-persist.yml`'s `workflow_run.workflows` list,
  and `schedule:` is present with exactly one cron entry that does not
  collide (same minute+hour) with any other scheduled workflow in the
  repository (FR-030(b), FR-030(c)).
- [ ] T046 [US3] Add each of T042-T045's `run:` lines to
  `.github/workflows/lint-workflows.yml`'s PR-triggered gate job, with
  `!cancelled()` (not bare `always()`) and a `paths:` filter covering the
  files each gate actually reads — including this feature's contract
  documents and data-model.md, so a documented shape that drifts from
  the code it describes is caught (contracts/gate-coverage-058.md's
  "Wiring assertions" section). Confirm `verify-gate-wiring.py` picks up
  all four automatically.

### Validation (SC-009–SC-012, quickstart.md Story 3)

- [ ] T047 [US3] Run `python .github/scripts/run-local-gates.py` and
  confirm Gates 76-79 pass alongside every gate from Phases 3 and 4.
- [ ] T048 [US3] Follow quickstart.md's Story 3 steps 1-9: a burst of
  completions produces at most one persistence run per completion and
  zero for the watchdog completion; every record-bearing run in the
  burst lands within minutes; a manually triggered sweep with `since`
  before a signal-bearing watchdog inspection picks up its record exactly
  once; re-running the same sweep is a no-op and the high-water mark does
  not regress; the hand-driven single-run re-drive is safe to use while a
  sweep is in flight; a persistence failure never touches the origin run;
  an expired-artifact fixture produces exactly one `unpersisted.jsonl`
  line and the mark still advances; two overlapping sweep dispatches
  neither lose a record nor strand the mark.

**Checkpoint**: All three sub-problems land. Every no-op and healthy path
now bills only the jobs it actually runs.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T049 Update `docs/architecture.md` (or wherever this repository's
  published-stage/watchdog/metrics-persist diagrams and job counts live —
  grep for "verify-image-prerequisites", "5 job" watchdog references, and
  the metrics-persist job count) so any prose or diagram citing the old
  per-stage/per-watchdog/per-persistence job counts reflects this
  feature's new counts.
- [ ] T050 Record the three delta contracts' versioning as a minor
  release per `specs/010-reusable-pipeline/contracts/versioning.md` and
  `specs/043-durable-metrics-record`'s own precedent — confirm no output,
  secret, or required-input name changed anywhere (image-check-shape-
  delta.md, watchdog-clean-path-delta.md, metrics-persist-sweep-delta.md
  each already state this; this task is the final cross-check before the
  implementation PR, not new prose).
- [ ] T051 Run the full quickstart.md gate-regression pass: all gates on
  the real tree (SC-012), each new/amended gate's own negative fixture in
  turn, and confirm `verify-gate-wiring.py` catches a `run:` line removed
  from `lint-workflows.yml`.
- [ ] T052 Final `grep -rn "anthropics/claude-code-action" .github/
  workflows .github/actions` diff against pre-feature `main`, confirming
  zero new agent invocations across the whole feature (SC-013,
  constitution IX) — the single cross-cutting check that spans all three
  stories.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: none — see Phase 2's note. Phase 3 itself is
  the blocking prerequisite for Phases 4 and 5.
- **User Story 1 (Phase 3)**: depends on Phase 1. Must complete (through
  its checkpoint) before Phase 4 or Phase 5 starts — both touch files
  Phase 3 also rewrites (`watchdog.yml`, `metrics-persist.yml`).
- **User Story 2 (Phase 4)**: depends on Phase 3's T010
  (`watchdog.yml`'s image-check rewrite).
- **User Story 3 (Phase 5)**: depends on Phase 3's T012
  (`metrics-persist.yml`'s image-check rewrite) and Phase 4 in full
  (FR-030(b) is stated "after FR-031").
- **Polish (Phase 6)**: depends on Phases 3-5 all being complete.

### Within Each User Story

- T002-T014 (US1's 13 per-file rewrites) are mutually independent — [P].
- T015-T016 (Gate 23/22 amendments) depend on T002-T014 existing so the
  gates have the new shape to check against; T017-T018 (self-test
  fixtures) depend on T015-T016; T019 (Gate 15) can run any time after
  T002-T014.
- T023-T026 (watchdog.yml code changes) are sequential within the same
  file; T027 (wrapper) depends on T026 (the stage must resolve `run-name`
  before the wrapper stops supplying it); T028 (self-verifier floor)
  is independent of T023-T027 but its fixture (T032) depends on them.
- T029-T032 (US2 gates) depend on T023-T028.
- T036-T039 (metrics-persist.yml/action.yml sweep mode) are sequential
  within their files; T040-T041 (wrapper) depend on T036 existing (the
  `since` input the wrapper's `sweep` job passes).
- T042-T046 (US3 gates) depend on T036-T041.

### Parallel Opportunities

- All of T002-T014 (13 files, no shared file) in one batch.
- T017 and T018 (different self-test scripts) in parallel once T015/T016
  land.
- T029-T031 (three independent new gate scripts) in parallel once
  T023-T027 land; T042-T045 (four independent new gate scripts) in
  parallel once T036-T041 land.

---

## Parallel Example: User Story 1's per-file rewrite

```bash
# Launch all 13 stage-file rewrites together — independent files:
Task: "T002 .github/workflows/intake.yml image-check shape"
Task: "T003 .github/workflows/clarify.yml image-check shape"
Task: "T004 .github/workflows/plan.yml image-check shape"
Task: "T005 .github/workflows/tasks.yml image-check shape"
Task: "T006 .github/workflows/implement.yml image-check shape"
Task: "T007 .github/workflows/finalize.yml image-check shape"
Task: "T008 .github/workflows/cleanup.yml image-check shape"
Task: "T009 .github/workflows/rebase.yml image-check shape"
Task: "T010 .github/workflows/watchdog.yml image-check shape"
Task: "T011 .github/workflows/pr-conversation.yml image-check shape"
Task: "T012 .github/workflows/metrics-persist.yml image-check shape"
Task: "T013 .github/workflows/auto-update-spec-kit.yml image-check shape"
Task: "T014 .github/workflows/private-image-dogfood.yml image-check shape"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 3: User Story 1 (T002-T022).
3. **STOP and VALIDATE**: run the gate suite and quickstart Story 1 steps.
4. This alone removes ~5,100 minutes/month (24% of usage per spec.md's
   own evidence table) and is independently mergeable per spec.md's
   Assumptions ("whether the three ship as one PR or three is a planning
   decision").

### Incremental Delivery

1. Setup → User Story 1 → validate → ship (largest, cheapest, highest-
   regression-risk win first, per spec.md's own priority ordering).
2. Add User Story 2 → validate → ship (removes the agent call from the
   common watchdog path — the real budget win).
3. Add User Story 3 → validate → ship (stops billing persistence runs for
   the healthy inspections Story 2 just emptied).
4. Polish (Phase 6) after all three, or folded into whichever PR ships
   last — it is cross-cutting documentation/verification, not new
   behavior.

### Sequencing constraint (not a team-parallelism opportunity)

Unlike the template's usual "stories can be staffed in parallel once
Foundational is done," this feature's own file-overlap argument (plan.md's
Structure Decision) means Phases 3→4→5 must land **in that order**, even
across separate PRs — B and C both edit files A rewrites, and C's wrapper
change is stated in terms of "after" B's record-emission change.
