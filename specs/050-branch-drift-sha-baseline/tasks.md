---

description: "Task list template for feature implementation"
---

# Tasks: Exact-SHA Branch-Drift Baseline for Dispatched Implement Runs

**Input**: Design documents from `/specs/050-branch-drift-sha-baseline/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md (all present)

**Tests**: Not explicitly requested as TDD; this feature's own contract
(`contracts/gate-coverage-050.md`) requires fixture-backed gate coverage as
part of the implementation itself, so gate/fixture tasks are interleaved
with the code they cover rather than split into a separate up-front phase.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task names exact file paths

---

## Phase 1: Setup

**Purpose**: Confirm the plan's line-number/step-name assumptions and
provisional gate number still hold before editing anything (research.md
flags both as "confirmed at implementation time").

- [X] T001 Re-grep the current state of `.github/workflows/implement.yml`
  (`Record base SHA` ~647, `Agent run metrics summary (cycle)` ~894,
  `Read back cycle outcome` ~966, `Consolidate final outcome` ~1532,
  `Record truncated-cycle count` ~1900-1958, `Flip stage label (first
  cycle)` ~1962) and `.github/workflows/watchdog.yml` (`"Collect: branch
  drift"` / `collect-branch-drift` ~628-805, the two-miss-cases comment
  ~704-716), and confirm `52` is still the highest `Gate [0-9]+` number in
  `.github/workflows/lint-workflows.yml` (so the new gate below is Gate
  53). Record any drift from plan.md's line numbers before starting T009+.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `branch_advance` exists as a validated, additive record group
before any call site populates it or any watchdog logic reads it.

**⚠️ CRITICAL**: No user story task may start until this phase is complete.

- [X] T002 [P] In `specs/043-durable-metrics-record/contracts/metrics-record-schema.md`,
  add the `branch_advance` clause per `contracts/metrics-record-schema-delta.md`:
  insert the 8-field `branch_advance` object (`available`, `branch`,
  `before_sha`, `before_available`, `after_sha`, `after_available`,
  `commits`, `commits_available`) into the `## Shape` JSON block, add the
  same group at `available: false` to the "Degraded record" example, and
  add a short paragraph stating the group is stage-neutral (FR-020) and
  that its absence on a pre-feature record must be treated identically to
  `available: false` (never a validation failure).

- [X] T003 In `.github/actions/wing-commander-metrics-summary/action.yml`,
  add seven optional inputs to the `inputs:` block — `branch` (default
  `''`), `before-sha` (default `''`), `before-sha-available` (default
  `'false'`), `after-sha` (default `''`), `after-sha-available` (default
  `'false'`), `commits` (default `''`), `commits-available` (default
  `'false'`) — and thread them through `emit_record()`'s `env:`/jq
  invocation so the written record gains a `branch_advance` object:
  `available` computed as `true` only when `branch` is non-empty AND
  (`before-sha-available == 'true'` OR `after-sha-available == 'true'`);
  `branch`/`before_sha`/`after_sha`/`commits` null when their own
  `*_available` flag (or, for `branch`, the group's own `available`) is
  false. Every existing call site (`implement.yml:894`, `:1330`, `:1835`)
  must require zero line changes, since all seven inputs default to the
  degraded state (data-model.md's "New composite inputs" table;
  research.md R3).

- [X] T004 In `.github/scripts/verify-metrics-record-schema.py`, add a
  `REQUIRED_BRANCH_ADVANCE` field-type map (`available: bool`, `branch:
  (str, type(None))`, `before_sha: (str, type(None))`, `before_available:
  bool`, `after_sha: (str, type(None))`, `after_available: bool`,
  `commits: (int, type(None))`, `commits_available: bool`) and, in
  `validate_record()`, validate `record["branch_advance"]` against it
  **only when the key is present** — unlike every other entry in
  `REQUIRED_TOP`, `branch_advance`'s own absence from a record is not a
  failure (a pre-feature record has no such key at all; data-model.md's
  Compatibility note).

- [X] T005 In the same file, extend `check_fields_match_contract()`'s
  `levels` list with a `("record.branch_advance", REQUIRED_BRANCH_ADVANCE,
  shape.get("branch_advance", {}))` entry, and adjust the existing
  `("record", REQUIRED_TOP, shape)` comparison so `branch_advance` being
  present in the doc's `## Shape` block but absent from `REQUIRED_TOP` is
  not itself reported as drift (it is the one field this gate treats as
  optional-at-top; contracts/gate-coverage-050.md).

- [X] T006 [P] Add 7 new fixture files under
  `.github/scripts/fixtures/metrics-record-schema/` (data-model.md's Gate
  fixtures table / FR-008): `branch_advance` with both points
  present+different+`commits>0`; both present+equal+`commits:0`;
  `before_available:false`; `after_available:false`; `commits:0` with
  differing `before_sha`/`after_sha` (backwards-reset case); both points
  present with `commits_available:false`; one wrong-typed `branch_advance`
  field (negative — e.g. `commits` as a string). Update
  `verify-metrics-record-schema.py`'s `_fixture_files()` pinned count from
  `8` to `15` to match.

- [X] T007 Confirm an existing fixture with no `branch_advance` key at all
  (e.g. `.github/scripts/fixtures/metrics-record-schema/valid-single-model.json`)
  still validates under T004/T005's special-casing — this is the
  "record predating this feature" positive fixture data-model.md requires
  (FR-008, SC-005); no new file needed for it.

- [X] T008 [P] In `.github/scripts/verify-metrics-persist-retry.py`, add a
  `branch_advance`-populated record (a literal alongside `batch`/
  `_reusable_workflow_record()`-style fixtures already in the file) to one
  existing case function's fixture batch — e.g.
  `case_idempotent_repeat_persistence_is_byte_for_byte_unchanged()` — and
  confirm append, dedup (by `record_key`, unaffected by any other field),
  and the concurrent-writer retry path all behave identically whether or
  not the new fields are present (FR-009, research.md R9).

**Checkpoint**: `branch_advance` is a validated, additive, optional group.
No call site populates it yet; no watchdog logic reads it yet.

---

## Phase 3: User Story 1 - A dispatched implement run that pushed nothing is caught even after a rebase (Priority: P1) 🎯 MVP

**Goal**: `implement.yml` records the exact before/after/commits triple for
a cycle; the watchdog compares those two recorded SHAs directly instead of
counting commits in an open-ended time window, closing the rebase-miss
case.

**Independent Test**: Drive a dispatched implement run that completes
without pushing to the spec branch, force-push a rebase of that branch
before the watchdog inspects it, and confirm the watchdog still reports
lost-progress for that cycle — naming the branch and the two SHAs it
compared — where the timestamp baseline reports nothing. (Proven here by
Gate 53's fixture harness, not a live rebase — quickstart.md Scenario 1.)

### Implementation for User Story 1

- [X] T009 [US1] In `.github/workflows/implement.yml`'s `cycle` job, add a
  new step named `Record branch advance (cycle)` between `Record
  truncated-cycle count` (~1900-1958) and `Flip stage label (first cycle)`
  (~1962), guarded by the same `if: steps.lifecycle-gate.outputs.is-open
  == 'true' && steps.guard.outputs.skip != 'true'` condition as its
  neighbors. It computes: `branch = ${{ inputs.spec-prefix }}${{
  steps.spec.outputs.slug }}`; `before-sha` = `steps.base.outputs.base-sha`
  reused verbatim, `before-sha-available` = `'true'` unless empty
  (research.md R1 — no new capture point); `after-sha` = the result of
  `git fetch origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"`
  then `git rev-parse refs/remotes/origin/$BRANCH` (mirroring `Read back
  cycle outcome`'s fetch at ~966), `after-sha-available` = `'true'` unless
  the fetch/rev-parse itself fails (research.md R4); `commits` = `git
  rev-list --count "$BEFORE..$AFTER"` computed once while both refs are
  locally held, `commits-available` = `'false'` only when either SHA is
  itself unavailable (research.md R5). Each of the three degrades
  independently to `*-available: 'false'` on failure rather than failing
  the cycle (spec.md Assumption).

- [X] T010 [US1] Immediately after T009's step, add a step that invokes
  `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-metrics-summary`
  with: `transcript-path: ${{ runner.temp }}/wing-commander-no-transcript.json`
  (a path that does not exist — deliberately drives the existing
  degraded-record path, research.md R2); `model: ${{
  steps.effective-model.outputs.model }}`; `stage: implement`; `spec-dir:
  ${{ inputs.spec-dir }}`; `spec-issue: ${{ inputs.issue-number }}`;
  `run-label: branch advance`; `step-index: '3'`; `record-path: ${{
  runner.temp }}/wing-commander-metrics-record-branch-advance.json`; and
  the seven `branch`/`before-sha`/`before-sha-available`/`after-sha`/
  `after-sha-available`/`commits`/`commits-available` inputs from T009's
  outputs (data-model.md's "fourth implement.yml call site" table).

- [X] T011 [US1] Immediately after T010, add a step `Upload metrics record
  (branch advance)` mirroring the three existing `Upload metrics record
  (...)` steps (e.g. `.github/workflows/implement.yml` ~914): `uses:
  actions/upload-artifact@v6`, `with: { name:
  metrics-record-branch-advance, path: ${{ runner.temp
  }}/wing-commander-metrics-record-branch-advance.json, if-no-files-found:
  ignore, retention-days: 90 }`.

- [X] T012 [US1] In `.github/scripts/verify-metrics-summary-record-emission.py`,
  add a fourth-invocation case (extending
  `case_repeated_invocation_in_one_job_gets_distinct_record_keys()`'s
  three-invocation harness to four, and adding a dedicated assertion
  alongside it) that invokes the real composite with T009/T010's own
  inputs (populated `branch`/`before-sha`/`after-sha`/`commits`, an
  absent transcript) and asserts the emitted record has
  `record_available: false` AND `branch_advance.available: true` with the
  exact values passed in (contracts/gate-coverage-050.md).

- [X] T013 [US1] In `.github/workflows/watchdog.yml`'s
  `collect-branch-drift` step, before the existing `baseline` selection
  falls through to `"since-created"` (~717-732), add: download the
  inspected run's `metrics-record*` artifact via `gh run download "$RUN_ID"
  --repo "$GITHUB_REPOSITORY" -p 'metrics-record*' -D <dir>` (the same
  pattern `wing-commander-inspected-run-identity`'s `record_fallback`
  already uses, `.github/actions/wing-commander-inspected-run-identity/action.yml:191`),
  then scan the downloaded `*.json` files, sorted, for the first whose
  `.branch_advance.available == true`. When found, set `baseline =
  "exact-sha"` and read `before_sha`/`after_sha` directly from that
  record's `branch_advance.before_sha`/`.after_sha` (research.md R7).

- [X] T014 [US1] In the same step, when `baseline = "exact-sha"`: skip the
  existing `git fetch`/`rev-parse`/`rev-list` block (~734-789) entirely —
  the verdict is `before_sha == after_sha` (lost-progress when equal), and
  `commits` for the signal is `branch_advance.commits` read verbatim,
  never recomputed (FR-019, research.md R5). When the two SHAs differ,
  exit 0 with no signal (mirroring the existing `[ "$commits" != "0" ]`
  early exit at ~787, adapted to compare SHAs).

- [X] T015 [US1] Update the signal-emission jq blocks (~791-805) so the
  `exact-sha` arm emits `facts: {branch, "before-sha": <before_sha>,
  since: null, "after-sha": <after_sha>, commits: <recorded commits>}`
  (data-model.md's "Branch-drift signal" table), while the
  `since-created` arm's shape stays byte-for-byte unchanged. The
  already-handled/stalled short-circuit (`META_STAGE == "stalled" ||
  STALLED_LABEL == "true"` → `alreadyHandledBy`) applies identically to
  both arms, unchanged (FR-014).

- [X] T016 [US1] Replace the comment block at
  `.github/workflows/watchdog.yml` ~704-716 (the "Both err toward a
  missed detection, never a false one, but they are baked in" comment
  quoted in spec.md's Input) with a comment stating: (a) why
  `HEAD_SHA..spec/<slug>` still cannot be used directly for a dispatched
  run (the unchanged part of the reasoning); (b) that a dispatched
  implement run's own metrics record now carries the exact before/after
  pair the stage observed, closing both previously-permanent misses; (c)
  that the `--since=<createdAt>` arm survives only as the fallback for a
  record that predates this feature or never reached the recording point
  (FR-015, research.md R8).

- [X] T017 [US1] Create `.github/scripts/verify-branch-drift-sha-baseline.py`
  (new, provisional Gate 53): a `wc_shell_harness.py`-style harness
  following `verify-finalize-refresh.py`'s pattern (`extract_between()` to
  pull `collect-branch-drift`'s real shipped bash out of
  `watchdog.yml`, `sh()` to run it via `subprocess` against a local bare
  git repository and synthetic run-metadata/metrics-record JSON). Cover:
  scenario 1 — `branch_advance.available: true`, `before_sha ==
  after_sha` → a `lost-progress` signal naming the branch, both SHAs, and
  the recorded `commits` (US1 AS1); scenario 2 — same but `before_sha !=
  after_sha` → no signal (US1 AS3). Run scenario 1 twice, the second time
  with the fixture's *current* branch tip mutated (simulating an
  intervening rebase and an intervening later-cycle push) and assert the
  verdict is byte-for-byte unchanged (US1 AS2, SC-001, SC-003).

- [X] T018 [US1] Extend `verify-branch-drift-sha-baseline.py` with
  scenario 3: identical inputs to T017's scenario 1, but the inspected
  spec's lifecycle already reads `stalled` (`META_STAGE=stalled` or
  `STALLED_LABEL=true`) → assert the `alreadyHandledBy` shape fires
  instead of a bare `lost-progress` class-hint (US1 AS4, FR-014).

- [X] T019 [US1] Extend `verify-branch-drift-sha-baseline.py` with a
  negative mutation fixture (mirroring `verify-finalize-refresh.py`'s
  `_mut_*` functions): mutate the extracted collector text so it
  re-derives `commits` via `git rev-list` instead of reading
  `branch_advance.commits`, run it against a local git state deliberately
  set up so a live walk would disagree with the recorded value, and
  assert the mutation makes scenario 1's exact-`commits` assertion fail —
  proving the "never re-walk the recorded range" invariant (FR-019) is
  load-bearing, not just documentation.

- [X] T020 [US1] Wire the new script into `.github/workflows/lint-workflows.yml`
  as `Gate 53 — <short description of the exact-SHA branch-drift
  baseline>` (confirm the number against T001's re-check), placed after
  Gate 52's step (~3179) and before Gate 10 (~3197), `if: "!cancelled()"`,
  not conditional on any other gate's outcome (matching this
  repository's step-gating convention). `verify-gate-wiring.py` (Gate 10)
  then picks it up automatically by filename convention — no separate
  registration.

**Checkpoint**: User Story 1 is fully functional and independently
testable — a pushed-nothing cycle is caught even after a rebase.

---

## Phase 4: User Story 2 - A second run on the same branch does not mask the first run's lost cycle (Priority: P1)

**Goal**: Prove, structurally, that the exact-sha arm's verdict cannot be
affected by a second run having already pushed to the same branch by
inspection time — the same mechanism User Story 1 built, made explicit.

**Independent Test**: Drive two consecutive implement cycles on one spec
branch where the first pushes nothing and the second pushes commits,
delay the watchdog's inspection of the first until after the second has
pushed, and confirm the first run is still reported as lost-progress and
the second is not. (Proven structurally via Gate 53, per research.md R9 —
no live two-run drive required for this to hold.)

### Implementation for User Story 2

- [X] T021 [US2] Extend `.github/scripts/verify-branch-drift-sha-baseline.py`
  with a scenario asserting that when `baseline = "exact-sha"` fires (T013),
  the collector issues no `git fetch`/`rev-parse`/`rev-list` against the
  measured branch's *current* state at all — only the `since-created`
  fallback arm performs those reads. Assert this by pointing the fixture
  repo's remote branch tip at a commit that would change the verdict if
  it were read, and confirming the reported verdict/commit count still
  match only the record's own `before_sha`/`after_sha`/`commits` (US2
  AS1-AS2, spec.md: "the collector never reads the branch's current state
  for this arm at all").

- [X] T022 [US2] Re-read `specs/024-watchdog-precision-hardening/data-model.md`'s
  fingerprint definition (`sha256(class + "|signals:" +
  sorted-joined(signal ids))`) and confirm no code change is needed: the
  fingerprint projects only `branch` and signal identity, never `facts`
  contents, so both the old (`since`-based) and new (`before-sha`-based)
  fact shapes dedup identically (US2 AS3, research.md R11, Out of Scope).
  Note this confirmation explicitly in the implementation PR description.

**Checkpoint**: User Stories 1 AND 2 both hold — back-to-back runs on one
branch are measured independently of inspection timing.

---

## Phase 5: User Story 3 - A run whose recorded SHAs are absent degrades visibly, never silently (Priority: P2)

**Goal**: A run whose record lacks `branch_advance` evidence falls back to
today's timestamp baseline exactly as before, but the step summary states
which baseline was used — and every case outside the dispatched-implement
arm stays provably untouched.

**Independent Test**: Inspect a run whose metrics record carries no branch
SHAs and confirm the watchdog's step summary names the since-created
timestamp baseline it fell back to for that run, and that the collector
still reports a successful outcome rather than an untrusted read.

### Implementation for User Story 3

- [X] T023 [US3] In `.github/workflows/watchdog.yml`'s
  `collect-branch-drift` step, when no downloaded record carries
  `branch_advance.available: true`, keep the existing `baseline =
  "since-created"` computation exactly as-is (FR-018) and append a
  `$GITHUB_STEP_SUMMARY` line naming the baseline used for this run: the
  exact-sha wording ("measuring `<branch>` via the implement run's own
  recorded before/after SHAs") from T013-T015 when that arm fired, vs.
  "...via commits since the run was created at `<timestamp>` (no recorded
  branch-advance evidence on this run)" otherwise (FR-013; data-model.md's
  "Step summary addition").

- [X] T024 [US3] Extend `.github/scripts/verify-branch-drift-sha-baseline.py`
  with a scenario: a downloaded `metrics-record*` artifact set containing
  no record with `branch_advance.available: true` → the since-created
  fallback fires unchanged and the step summary names it as the fallback
  (US3, FR-013, FR-017, FR-018).

- [X] T025 [US3] Extend `verify-branch-drift-sha-baseline.py` with a
  regression scenario: a spec-branch-head run (`plan`/`tasks`,
  `baseline = "head-sha"`), a non-push-expected stage (a `RUN_NAME` not
  in the push-expected list ~656), and a skipped/cancelled run
  (`RUN_CONCLUSION` in `skipped|cancelled`) are all unaffected by
  T013-T015's new arm (FR-012).

- [X] T026 [US3] Extend `verify-branch-drift-sha-baseline.py` with a
  regression scenario: a run whose `RUN_CREATED_AT`/slug cannot be
  resolved still exits quietly, unchanged from today's behavior
  (contracts/gate-coverage-050.md assertion 6).

**Checkpoint**: All three user stories are independently functional. The
detection gap named in issue #331 is closed for any run whose record
carries the new evidence, and every other case is provably unaffected.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Close the deferred follow-up this feature's own scope
excludes, and confirm the success criteria that span every story.

- [ ] T027 File the FR-020 follow-up issue (research.md R10 — not filed by
  the tasks/plan stage, which has no `gh issue create` in its tool
  surface): title it around "plan/tasks stages populate branch_advance",
  reference `specs/050-branch-drift-sha-baseline` and FR-020, and state
  that until it lands, `plan`/`tasks` records carry `branch_advance` as
  `available: false` and the watchdog's behavior for those stages is
  unchanged (FR-012, Out of Scope).
  **BLOCKED this cycle**: this implement run's own tool surface also has
  no `gh issue create` (only `gh issue view`/`gh issue comment`) — noted
  on issue #331 (comment) with the exact title/body a maintainer or a
  future run with issue-creation tooling should use. Left unchecked
  deliberately rather than silently skipped.

- [X] T028 [P] Run `python .github/scripts/run-local-gates.py` (the full
  PR-time gate suite, CLAUDE.md's "Before pushing" rule) and confirm
  Gates 39, 41, 43, and 53 all pass.

- [X] T029 [P] Confirm SC-006/FR-016 (no new agent invocation anywhere in
  this feature): `grep -c "uses: anthropics/claude-code-action"
  .github/workflows/implement.yml` reports the same count (three) before
  and after this feature's diff, and
  `python3 .github/scripts/verify-actions-layer-invariants.py` still
  passes against the edited
  `.github/actions/wing-commander-metrics-summary/action.yml`
  (quickstart.md Scenario 7).

- [X] T030 Run the `review-step-gating` skill against the full diff
  (CLAUDE.md: any change touching an `if:`, `continue-on-error:`, or a
  failing step in a workflow gets a pass from this skill) — T009 and
  T013-T015/T023 all touch `if:`/step-ordering in
  `.github/workflows/implement.yml` and `.github/workflows/watchdog.yml`.
  Gate 24 (`verify-gate-24.py`) passes. The skill's own enumeration
  script (`stranded-steps.py`) is outside this run's permitted tool
  surface; manual review against its criteria found no stranded
  teardown/degradation/report step: the new implement.yml steps
  (`Record branch advance (cycle)`, its metrics-summary call, its
  upload) are each `continue-on-error: true` (or gate identically to
  their neighbors) with nothing downstream depending on their success;
  the new watchdog.yml logic is added entirely INSIDE the pre-existing
  `continue-on-error: true` collect-branch-drift step via internal
  `if`/`exit 0` branches, matching that step's own established pattern,
  with no new step boundary and no new hard exit.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — run first.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS every user story —
  `branch_advance` must exist, validate, and be persist-safe before any
  call site populates it or any watchdog logic reads it.
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on
  US2/US3.
- **User Story 2 (Phase 4)**: Depends on Foundational AND on US1's T013
  (the `exact-sha` arm T021 asserts a property of) — sequential after
  Phase 3 in practice, even though its own independent test is separate.
- **User Story 3 (Phase 5)**: Depends on Foundational AND on US1's
  T013-T015 (the fallback/regression scenarios in T023-T026 assert
  properties of the same step). Sequential after Phase 3.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Phase 2 (Foundational)

T002 and T003 can proceed in parallel (different files). T004 depends on
T002 existing (its cross-check reads the doc). T005 depends on T004. T006
can be written in parallel with T004/T005 but its self-test only passes
once T004/T005 land. T007 depends on T004/T005. T008 is independent of
T002-T007 (different file).

### Within Phase 3 (User Story 1)

T009 → T010 → T011 (each step reads the previous step's outputs) → T012
(exercises the shipped result of T009-T011). T013 → T014 → T015 → T016
(same step, sequential edits) — independent of T009-T012 until both sides
exist. T017 → T018 → T019 → T020 depend on T013-T015's shipped text
existing to extract.

### Parallel Opportunities

- Foundational: T002 with T003; T006 and T008 with the T004/T005 pair.
- User Story 1: the `implement.yml` side (T009-T012) and the
  `watchdog.yml` side (T013-T016) can be developed in parallel by
  different people — Gate 53 (T017-T020) needs both sides done.
- Polish: T028 and T029 in parallel once all stories are complete.

---

## Parallel Example: Foundational Phase

```bash
Task: "Add branch_advance to specs/043-durable-metrics-record/contracts/metrics-record-schema.md"
Task: "Add 7 optional inputs + branch_advance emission to .github/actions/wing-commander-metrics-summary/action.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1) — this alone closes the rebase-miss
   case (SC-001, SC-003) named in issue #331 and is independently
   demonstrable via `python3 .github/scripts/verify-branch-drift-sha-baseline.py`.
3. **STOP and VALIDATE**: run `python .github/scripts/run-local-gates.py`.

### Incremental Delivery

1. Foundational → schema/contract/gates ready.
2. User Story 1 → the primary detection gap closes (MVP).
3. User Story 2 → the second-run-masking property is proven explicitly.
4. User Story 3 → fallback visibility and regression scope are proven.
5. Polish → the FR-020 follow-up is filed and the full gate suite is green.

### Suggested MVP Scope

User Story 1 (Phase 3, T009-T020) plus the Foundational phase it depends
on. User Stories 2 and 3 add proof of properties the same mechanism
already has by construction (research.md R7) and reporting polish,
respectively — valuable, but not required to close the detection gap
issue #331 names.

---

## Phase 7: Convergence

- [X] T031 Add a positive Gate 39 fixture under
  `.github/scripts/fixtures/metrics-record-schema/` for `branch_advance`'s
  "both points unavailable" state (`available: false`, `before_available:
  false`, `after_available: false` — the shape
  `contracts/metrics-record-schema.md`'s degraded-record example already
  documents, with the `branch_advance` key present rather than absent)
  and update `verify-metrics-record-schema.py`'s `_fixture_files()` pinned
  count from `15` to `16` to match (8 `branch_advance` fixtures in total:
  the seven from T006 plus this one). SC-004 lists six new-field states
  requiring a checked-in fixture; the seven fixtures added in T006 each
  mark only one of `before_available`/`after_available` false at a time
  (or both true/available), so this state has no fixture of its own yet
  (missing).
