---

description: "Task list template for feature implementation"
---

# Tasks: The Plan and Tasks Stages Record Their Own Branch Advance

**Input**: Design documents from `/specs/068-plan-tasks-branch-advance/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md (all present)

**Tests**: Not explicitly requested as TDD; this feature's own contract
(`contracts/gate-coverage-068.md`) requires fixture-backed gate coverage as
part of the implementation itself (following `specs/050-branch-drift-sha-
baseline`'s own precedent), so gate/fixture tasks are interleaved with the
code they cover rather than split into a separate up-front phase.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Every task names exact file paths

---

## Phase 1: Setup

**Purpose**: Confirm the plan's line-number and gate-number assumptions
still hold before editing anything — plan.md/research.md were written
against a snapshot of the tree, and this repository's own convention
(`specs/050-branch-drift-sha-baseline/tasks.md` T001) is to re-verify
before relying on them.

- [ ] T001 Re-grep the current state of the four files this feature edits
  and confirm/correct the following against plan.md's and research.md's
  assumptions, recording any drift before starting T002+:
  - `.github/workflows/implement.yml`'s `Record branch advance (cycle)`
    step is at ~2396-2432, feeding `Agent run metrics summary (branch
    advance)` at ~2441-2461 and `Upload metrics record (branch advance)`
    at ~2473-2481.
  - `.github/workflows/plan.yml`: `Resolve review mode` (~634) runs
    *before* `Checkout spec branch as wing-commander-bot` (~666); the
    existing `Agent run metrics summary` step is at ~1071-1088 with `if:
    always() && (steps.agent-pr.outcome != 'skipped' ||
    steps.agent-auto.outcome != 'skipped')` — **not** `!cancelled()`, which
    is what research.md R3 mis-cites as "the same condition" — and
    `Fail loud on non-healthy agent verdict (pr)` (~1123) runs *after* it.
  - `.github/workflows/tasks.yml`: unlike plan.yml, `Checkout spec branch
    as wing-commander-bot` (~587, no `if:` guard at all) runs *before*
    `Resolve review mode` (~648, `if: steps.guard.outputs.skip !=
    'true'`) — the reverse order from plan.yml, so research.md R2's claim
    that "Resolve review mode runs before the checkout in both files" is
    wrong for this file; the new "before" capture step below must be
    placed after `Resolve review mode`, not immediately after the
    checkout. The existing `Agent run metrics summary` step is at
    ~1052-1069 (same `always() && (...)` shape as plan.yml), and here
    `Fail loud on non-healthy agent verdict (pr)` (~1038) already runs
    *before* it, not after — confirm the new capture step still only
    needs to land immediately before the existing metrics-summary step in
    both files, regardless of this reordering.
  - `.github/workflows/watchdog.yml`'s `collect-branch-drift` step: the
    outer push-expected-stage gate at ~684-690, the two stale comment
    blocks at ~696-731, the implement-only guard at ~772 (`if [ "$RUN_NAME"
    != "Wing Commander · 5 implement" ] || [ -z "$RUN_CREATED_AT" ]`), the
    record-download-and-scan block at ~779-827, the exact-sha verdict at
    ~830-857, the since-created verdict at ~858-915, and the signal
    emission at ~917-938.
  - The gate that will be extended for branch-drift is **not** "Gate 53"
    as plan.md, research.md, data-model.md and
    `contracts/gate-coverage-068.md` all say (11 references) — Gate 53 in
    the current `.github/workflows/lint-workflows.yml` is a different
    script (the turn-budget collector). `verify-branch-drift-sha-
    baseline.py` is currently wired as **Gate 65** (`lint-workflows.yml`
    ~3619-3635, renumbered from a provisional 53 by
    `specs/050-branch-drift-sha-baseline` itself once it collided with
    Gates 63/64). Use Gate 65 in every task below and in the PR/issue
    comment language; treat every "Gate 53" in this feature's own planning
    docs as the stale name for Gate 65.
  - Confirm Gates 39, 43, and 60 are still correctly numbered (they are,
    as of this run: `lint-workflows.yml` ~3302, ~3343, ~3551
    respectively).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The single home for the "after"/"commits" git plumbing exists
and implement.yml's own recorded values are proven unchanged by moving to
it, before either new stage call site is added.

**⚠️ CRITICAL**: No user story task may start until this phase is complete.

- [ ] T002 Create `.github/actions/wing-commander-branch-advance/action.yml`
  (research.md R1; `contracts/branch-advance-capture-contract.md`): a
  composite action with inputs `branch` (required), `before-sha` (optional,
  default `''`), `before-sha-available` (optional, default `'false'`), and
  outputs `after-sha`, `after-sha-available`, `commits`,
  `commits-available`. Its single `run:` step (`shell: bash`) is the
  byte-identical git plumbing extracted from `implement.yml`'s current
  "Record branch advance (cycle)" step (T001's confirmed ~2396-2432):
  `git fetch origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"` →
  `git rev-parse "refs/remotes/origin/$BRANCH"` for `after-sha` (empty/
  `'false'`-available on failure) → `git rev-list --count
  "$BEFORE_SHA..$AFTER_SHA"` for `commits`, computed only when both SHAs
  are available. Never fails its own step (every failure degrades an
  output; belt-and-braces `continue-on-error: true` stays the caller's
  concern, matching `wing-commander-refresh-remote/action.yml`'s shape as
  the nearest structural template).

- [ ] T003 In `.github/workflows/implement.yml`, replace the inline bash in
  "Record branch advance (cycle)" (T001's confirmed ~2396-2432) with a
  single `uses:
  ./.wing-commander-pipeline/.github/actions/wing-commander-branch-advance`
  call, keeping the step's `id: branch-advance`, its unchanged `if:`
  condition, and computing `branch`/`before-sha`/`before-sha-available`
  exactly as today from `${{ inputs.spec-prefix }}${{
  steps.spec.outputs.slug }}` / `steps.base.outputs.base-sha` in a small
  preceding `run:` step (or as inline `with:` expressions, whichever needs
  fewer lines) — the composite's own `after-sha`/`after-sha-available`/
  `commits`/`commits-available` outputs feed the existing "Agent run
  metrics summary (branch advance)" step unchanged. No value implement.yml
  records may change (FR-011).

- [ ] T004 [P] In `.github/scripts/verify-metrics-summary-record-emission.py`,
  add a case (alongside `case_repeated_invocation_in_one_job_gets_distinct_record_keys`)
  that runs the real `wing-commander-branch-advance` composite (T002)
  standalone against a local git fixture with a known before-SHA/branch,
  and against implement.yml's pre-refactor inline-bash behavior (captured
  as a literal shell snippet or via a saved fixture repo state), asserting
  both produce byte-identical `after-sha`/`commits` outputs for the same
  inputs — the regression proof FR-011 requires
  (`contracts/gate-coverage-068.md` assertion 1).

**Checkpoint**: The single home for "after"/"commits" exists.
implement.yml's own recorded values are unchanged. No plan/tasks call site
exists yet.

---

## Phase 3: User Story 1 - A plan or tasks run that pushed nothing is caught (Priority: P1) 🎯 MVP

**Goal**: A plan run and a tasks run each record the branch they advanced
plus a before/after tip in their own metrics record, and the watchdog's
branch-drift collector reads that evidence for all three push-expected
stages instead of only implement.

**Independent Test**: Drive a plan run and a tasks run that each complete
without pushing to their target branch, and confirm each is reported as
lost-progress, naming the stage, the branch, and the two identical commits
it compared — where today both are silently skipped (spec.md US1).

### Implementation for User Story 1

- [ ] T005 [P] [US1] In `.github/workflows/plan.yml`, add a new step named
  "Record branch tip before agent" immediately after "Checkout spec branch
  as wing-commander-bot" (T001's confirmed ~666-673) and before "Compute
  agent turn ceiling (auto)" (~689), guarded by `if: steps.dupe.outputs.skip
  != 'true'` (mirroring the checkout step's own condition). It computes,
  as step outputs: `branch` = `${{ steps.mode.outputs.mode }} == 'auto'`
  → `${{ inputs.spec-prefix }}${{ needs.resolve-spec.outputs.slug }}`,
  else → `${{ inputs.plan-prefix }}${{ needs.resolve-spec.outputs.slug }}`
  (confirm the exact input name for the pr-mode branch prefix by grepping
  `plan.yml` for how the `plan/<slug>` branch name is built elsewhere, e.g.
  around the `git checkout -b` in the pr-mode agent prompt); `before-sha`
  = `git rev-parse HEAD` (the tip of the just-checked-out spec branch);
  `before-sha-available` = `'true'` unless the rev-parse fails
  (research.md R2).

- [ ] T006 [US1] In `.github/workflows/tasks.yml`, add the same kind of
  step, "Record branch tip before agent", but placed after "Resolve review
  mode" (T001's confirmed ~648-650) rather than immediately after the
  checkout (T001: tasks.yml checks out before resolving mode, the reverse
  of plan.yml) and before the first mode-specific step that follows it.
  Guard it with `if: steps.guard.outputs.skip != 'true'` (mirroring
  "Resolve review mode"'s own condition). Same two outputs as T005, using
  `${{ inputs.tasks-prefix }}` (confirm the exact input name) for the
  pr-mode branch.

- [ ] T007 [P] [US1] In `.github/workflows/plan.yml`, add a new step named
  "Record branch advance (after agent)" immediately before the existing
  "Agent run metrics summary" step (T001's confirmed ~1071), using the
  **same** `if:` shape as that existing step (`if: always() &&
  (steps.agent-pr.outcome != 'skipped' || steps.agent-auto.outcome !=
  'skipped')` — not the `!cancelled()` form research.md R3 mis-describes;
  run the `review-step-gating` skill against this choice per T028) and
  `continue-on-error: true`. It calls `uses:
  ./.wing-commander-pipeline/.github/actions/wing-commander-branch-advance`
  with T005's `branch`/`before-sha`/`before-sha-available` outputs, then a
  second call to `wing-commander-metrics-summary` (transcript-path pointed
  at a nonexistent file, mirroring implement.yml's fourth call site) with
  `stage: plan`, a `step-index` distinct from the existing call's (check
  `wing-commander-metrics-summary/action.yml`'s default/derivation before
  choosing one), `record-path: ${{ runner.temp
  }}/wing-commander-metrics-record-branch-advance.json`, and the six
  branch-advance inputs/outputs threaded through. Follow with an "Upload
  metrics record (branch advance)" step (`actions/upload-artifact@v6`,
  `name: metrics-record-branch-advance`, `if-no-files-found: ignore`,
  `retention-days: 90`, `continue-on-error: true`), mirroring
  implement.yml's own three-step shape (T003).

- [ ] T008 [US1] In `.github/workflows/tasks.yml`, add the same three steps
  as T007 (branch-advance capture, transcript-less metrics-summary call
  with `stage: tasks`, upload), placed immediately before the existing
  "Agent run metrics summary" step (T001's confirmed ~1052), using that
  step's exact `if:` shape.

- [ ] T009 [P] [US1] In `.github/scripts/verify-metrics-summary-record-emission.py`,
  add a case exercising an "auto"-mode and a "pr"-mode invocation shaped
  like T007/T008's new call site (populated `branch`/`before-sha`/
  `after-sha`/`commits` inputs, an absent transcript path, `stage: plan`
  and `stage: tasks`) and assert each produces `record_available: false`
  with `branch_advance.available: true` matching the inputs verbatim
  (`contracts/gate-coverage-068.md` assertions 2-3).

- [ ] T010 [P] [US1] Add three new fixtures under
  `.github/scripts/fixtures/metrics-record-schema/` (research.md R8;
  `contracts/gate-coverage-068.md`):
  `valid-branch-advance-branch-created-from-this-commit.json` (schema-
  identical to `valid-branch-advance-both-present-different.json`, its own
  file so FR-020's "branch the run created" case is traceable by name),
  `valid-branch-advance-persistent-branch.json` (`branch:
  "spec/068-plan-tasks-branch-advance"`), and
  `valid-branch-advance-review-branch.json` (`branch:
  "plan/068-plan-tasks-branch-advance"`). Update
  `verify-metrics-record-schema.py`'s `_fixture_files()` pinned count to
  match the new total (confirm the current pinned count first — do not
  assume the number in any planning doc).

- [ ] T011 [US1] In `.github/workflows/watchdog.yml`'s `collect-branch-drift`
  step, move the metrics-record download-and-scan block (T001's confirmed
  ~779-827) out from inside the `if [ "$RUN_NAME" != "Wing Commander · 5
  implement" ] || [ -z "$RUN_CREATED_AT" ]` guard (~772) so it runs for
  all three push-expected stages — the outer `case "$RUN_NAME"` gate at
  ~684-690 already restricts the whole step to plan/tasks/implement, so no
  new stage becomes reachable. Keep the existing rule that
  `measure_branch` is set from the found record's own `branch_advance
  .branch` when present (today's ~820-823 logic), now applied
  unconditionally rather than only inside the implement-only arm
  (research.md R5; FR-004).

- [ ] T012 [US1] Replace the two comment blocks at `.github/workflows/watchdog.yml`
  ~696-699 and inside ~719-731 (both quoted verbatim in spec.md's Overview
  — "plan and tasks push to the persistent spec branch, but... the
  collector skips it" / "...so with a non-spec head they still skip") with
  a comment stating: (a) why a plan/tasks run's head branch still cannot
  be used directly (a draft or default-branch head names nothing about
  what the run pushed — unchanged reasoning), and (b) that a plan/tasks
  run's own metrics record now carries the exact branch/before/after/
  commits quadruple it observed (T005-T008), read the same way
  implement's already is (T011), closing the gap the replaced comments
  described as total (FR-023, research.md R7). Treat this as a behavior-
  describing edit under CLAUDE.md's load-bearing-comments rule, not a
  cosmetic one.

- [ ] T013 [US1] Extend `.github/scripts/verify-branch-drift-sha-baseline.py`
  (Gate 65 — see T001; **not** "Gate 53") with two new scenarios (research.md
  R9 cases 1-2): a plan run (`RUN_NAME = "Wing Commander · 3 plan"`) with a
  downloaded record carrying `branch_advance.available: true`, `branch:
  "plan/068-..."`, `before_sha == after_sha` → asserts a `lost-progress`
  signal naming the `plan/` branch, both SHAs, and the recorded `commits`;
  a tasks run, same shape, `before_sha != after_sha` → asserts no signal.
  Follow the existing harness's synthetic run-metadata/record JSON style
  (no new fixture files needed).

**Checkpoint**: A plan run and a tasks run that push nothing are each
reported as lost-progress by Gate 65's fixture harness — the primary
detection gap issue #511 names is closed.

---

## Phase 4: User Story 2 - The verdict does not change with when the watchdog looks (Priority: P1)

**Goal**: Prove, structurally, that the exact-sha arm's verdict for a plan
or tasks run cannot be affected by an intervening force-push or a later
stage's push — the same mechanism User Story 1 built, made explicit for
the two new stages.

**Independent Test**: Inspect the same completed plan run twice — once
before and once after an intervening force-push of its branch and an
intervening later push by the next stage — and confirm both inspections
produce the same verdict (spec.md US2).

### Implementation for User Story 2

- [ ] T014 [US2] Extend `.github/scripts/verify-branch-drift-sha-baseline.py`
  with a scenario for a plan (or tasks) run: when T011's widened exact-sha
  arm fires, assert no `git fetch`/`rev-parse`/`rev-list` runs against the
  measured branch's *current* state — mirroring the existing
  `scenario_exact_sha_ignores_live_branch_state` implement-only case, but
  for a `plan/<slug>`-branch record — by pointing the fixture repo's
  remote branch tip at a commit that would change the verdict if it were
  read, and confirming the reported verdict/commit count still match only
  the record's own `before_sha`/`after_sha`/`commits` (spec.md US2 AS1-2).

- [ ] T015 [US2] Confirm (no code change expected) that the fingerprint/
  dedup mechanism downstream of the collector (`specs/024-watchdog-
  precision-hardening`'s definition: `sha256(class + "|signals:" +
  sorted-joined(signal ids))`) projects only `branch` and signal identity,
  never `facts` contents — so a plan/tasks finding groups with existing
  findings for the same branch exactly as one does today (FR-019; spec.md
  Out of Scope). Note this confirmation explicitly in the implementation
  PR description.

**Checkpoint**: Both P1 stories hold — plan and tasks runs are measured
independently of inspection timing, the same way implement already is.

---

## Phase 5: User Story 3 - The capture has exactly one home (Priority: P2)

**Goal**: A structural gate, not just Phase 2's extraction, guarantees the
branch-advance capture cannot silently regain a second or third copy.

**Independent Test**: Search the repository for the capture logic and
confirm it appears exactly once; add a second copy to a workflow and
confirm the gate suite fails on it (spec.md US3).

### Implementation for User Story 3

- [ ] T016 [US3] In `.github/scripts/verify-single-home-idioms.py` (Gate
  60), add a `branch-advance-capture` entry to `DECLARED_HOMES` pointing at
  `.github/actions/wing-commander-branch-advance/action.yml` (T002), keyed
  on the co-occurrence, in one file, of the refspec-form fetch fragment
  (`git fetch origin "+refs/heads/$`) and the `..`-range commit-count
  fragment (`git rev-list --count "$` immediately followed by a `..`
  range) — verify by grepping the pre-T003 tree that this pair appears
  together only in implement.yml's old inline step, so the check has no
  false-positive risk from either fragment appearing alone elsewhere
  (research.md R10). Add the new key to `CHECK_NAMES`'s implicit
  `DECLARED_HOMES` iteration and to `ALL_CHECKS` following the existing
  pattern of every other entry (do not assume a specific ordinal count of
  existing entries — confirm the current count first).

- [ ] T017 [US3] In the same file, add the new home's shipped shell to
  `selftest_clean_tree_passes()`'s clean-tree fixture (mirroring every
  other `DECLARED_HOMES` entry) and add a
  `selftest_third_paste_fails("branch-advance-capture", ...)` call proving
  a synthetic third paste of the two fragments into an unrelated workflow
  fails, naming the declared home.

**Checkpoint**: A re-paste of the branch-advance capture into any workflow
or composite other than its declared home now fails Gate 60 structurally.

---

## Phase 6: User Story 4 - A run that cannot be measured degrades visibly (Priority: P2)

**Goal**: A plan or tasks run whose record carries no usable branch-advance
pair keeps exactly today's outcome (no signal), is never reported as
failed, and the step summary says so in words distinct from implement's
own no-evidence message.

**Independent Test**: Inspect a plan run whose record carries no usable
branch evidence and confirm the step summary names what it did instead,
that no lost-progress signal is emitted, and that the collector's outcome
is still recorded as trustworthy (spec.md US4).

### Implementation for User Story 4

- [ ] T018 [US4] In `.github/workflows/watchdog.yml`'s `collect-branch-drift`
  step, after T011's widened download-and-scan finds no usable record:
  make the `baseline="since-created"` fallback (T001's confirmed ~776-777,
  826) fire **only when `RUN_NAME` is `"Wing Commander · 5 implement"`**
  (research.md R5; `contracts/branch-drift-collector-delta.md`). For a
  plan or tasks run reaching this point, append a `$GITHUB_STEP_SUMMARY`
  line reading "no recorded branch-advance evidence on this
  `<plan|tasks>` run — skipping" (textually distinct from implement's own
  "...measuring `<branch>` for commits since the run was created at
  `<timestamp>`" message), `exit 0` with no signal, and record the
  collector's own outcome as `"ok"` — never `"failed"` — since an absent
  optional field is data, not a failed read (FR-016).

- [ ] T019 [US4] Extend `.github/scripts/verify-branch-drift-sha-baseline.py`
  (Gate 65) with two scenarios (research.md R9 cases 3-4): a plan run and
  a tasks run whose downloaded artifact set carries no record with
  `branch_advance.available: true` → assert no signal is emitted, the
  since-created fallback's `git rev-list --since=...` is **not** invoked
  (distinguishing this from implement's own no-record case, which does
  fall back), the step summary names T018's exact skip wording, and the
  collector's own outcome is `"ok"`.

- [ ] T020 [US4] Extend `verify-branch-drift-sha-baseline.py` with a
  regression scenario confirming a spec-branch-head run (`baseline =
  "head-sha"`) and a non-push-expected stage remain unaffected by T011/
  T018's changes (mirrors `specs/050-branch-drift-sha-baseline`'s own case
  5; research.md R9 item 5).

- [ ] T021 [US4] Confirm (no code change expected) that a record predating
  this feature — one with no `branch_advance` key at all, e.g. an existing
  fixture like `valid-single-model.json` — still validates under Gate 39
  unchanged, and that a plan/tasks run whose record lacks the group (an
  adopting repository on an older pipeline version) still resolves to
  today's unconditional skip via T018's implement-only fallback guard,
  producing no false detection (FR-017; spec.md US4 AS2).

**Checkpoint**: All four user stories hold. A measurable plan/tasks run is
caught; an unmeasurable one degrades visibly and never falsely.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Update the published contract to describe what shipped, and
confirm the properties that span every story.

- [ ] T022 In `specs/043-durable-metrics-record/contracts/metrics-record-
  schema.md`, amend the `branch_advance` clause per
  `contracts/metrics-record-schema-delta.md`: state that implement, plan,
  and tasks all populate the group now (not implement alone); restate
  "before" stage-neutrally as "the point the run advanced the branch
  from" (existing tip for a branch that already existed, the creation
  commit for a branch the run created) as a widening, not a behavior
  change, of every already-persisted value (FR-005/FR-009/FR-010).

- [ ] T023 [P] Run `python .github/scripts/run-local-gates.py` (CLAUDE.md
  "Before pushing") and confirm Gates 39, 43, 60, and 65 (T001 — not "53")
  all pass, alongside the full suite.

- [ ] T024 [P] Confirm SC-007/FR-007 (no new agent invocation anywhere):
  `grep -c "uses: anthropics/claude-code-action" .github/workflows/plan.yml`
  and the same for `tasks.yml` and `implement.yml` each report the same
  count before and after this feature's diff, and
  `verify-actions-layer-invariants.py` still passes against the new
  `wing-commander-branch-advance/action.yml` (quickstart.md Scenario 7).

- [ ] T025 Run the `review-step-gating` skill against the full diff
  (CLAUDE.md: any change touching an `if:`, `continue-on-error:`, or a
  failing step in a workflow gets a pass from this skill) — T003, T005-T008,
  T011, and T018 all touch `if:`/step-ordering in
  `.github/workflows/implement.yml`, `plan.yml`, `tasks.yml`, and
  `watchdog.yml`. Pay particular attention to T007/T008's choice of
  `always()` over `!cancelled()` (T001's correction of research.md R3) —
  confirm that choice is actually correct for the new steps, not merely
  consistent with the sibling it copies, before treating it as settled.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — run first; corrects drift every
  later phase's task text relies on.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS every user story —
  the composite must exist and implement.yml's refactor must be proven
  unchanged before either new stage call site is added.
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on
  US2/US3/US4.
- **User Story 2 (Phase 4)**: Depends on US1's T011 (the widened exact-sha
  arm T014 asserts a property of).
- **User Story 3 (Phase 5)**: Depends on Foundational's T002 (the
  composite Gate 60's new check declares as the home) — independent of
  US1/US2/US4, may proceed in parallel with Phase 3 once Phase 2 is done.
- **User Story 4 (Phase 6)**: Depends on US1's T011 (the same
  download-and-scan block T018 adds the fallback-restriction to).
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Within Phase 3 (User Story 1)

T005 and T006 are independent (different files). T007 depends on T005
(consumes its outputs); T008 depends on T006. T009 depends on T007/T008's
shipped shape existing to test against. T010 is independent of T005-T009
(fixture files only). T011 → T012 (same step/file, sequential). T013
depends on T011 (extracts the widened text).

### Within Phase 6 (User Story 4)

T018 depends on US1's T011 (same block). T019 → T020 → T021 build on
T018's shipped text.

### Parallel Opportunities

- Foundational: T004 can be written once T002/T003 land; T002 and T003
  are themselves sequential (T003 consumes T002).
- User Story 1: T005/T006 (the two workflow files) in parallel; T010
  (fixtures) in parallel with the workflow-file tasks.
- User Story 3 can be worked in parallel with User Story 1/2/4 once
  Phase 2 is done — it only depends on T002.
- Polish: T023 and T024 in parallel once all stories are complete.

---

## Parallel Example: User Story 1

```bash
Task: "Add 'Record branch tip before agent' to plan.yml"
Task: "Add three new fixtures under fixtures/metrics-record-schema/"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1) — this alone closes the total detection
   gap issue #511 names for both plan and tasks runs, and is independently
   demonstrable via
   `python3 .github/scripts/verify-branch-drift-sha-baseline.py -v`.
3. **STOP and VALIDATE**: run `python .github/scripts/run-local-gates.py`.

### Incremental Delivery

1. Foundational → the single home exists, implement unaffected.
2. User Story 1 → the primary detection gap closes for plan and tasks
   (MVP).
3. User Story 2 → the timing-invariance property is proven explicitly for
   the two new stages.
4. User Story 3 → the one-home guarantee becomes structural, not just
   true-by-construction.
5. User Story 4 → the no-evidence case degrades visibly and never falsely.
6. Polish → the published contract is updated and the full gate suite is
   green.

### Suggested MVP Scope

Phase 2 (Foundational) plus Phase 3 (User Story 1, T005-T013). User
Stories 2, 3, and 4 add proof of properties the same mechanism already has
by construction, a structural guarantee against regression, and reporting
polish, respectively — valuable, but not required to close the detection
gap issue #511 names.
