# Tasks: Converged Means No Task Is Left — The Cycle Signal Reads tasks.md

**Input**: Design documents from `/specs/059-converged-means-tasks-done/`
(plan.md, research.md, data-model.md, quickstart.md,
contracts/convergence-signal.md)

**Tests**: This feature's verification is a deterministic gate script with
checked-in fixtures (Constitution VIII, FR-018–FR-020), not a conventional
test suite — matching this repository's existing `verify-*.py` convention.
Gate/fixture tasks are listed inline with the implementation task they
verify rather than in a separate TDD phase.

**Gate numbering**: the highest gate number wired into
`.github/workflows/lint-workflows.yml` as of this branch is Gate 80
(`grep -n "Gate [0-9]" .github/workflows/lint-workflows.yml`). This
feature's new gate is assigned **Gate 81**. Re-check this at implementation
time in case another in-flight branch has since claimed it (research.md D5)
and renumber every "Gate 81" reference in this file if so.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (a cycle that stops with work left gets another cycle),
  US2 (the signal is read from the tree, never the agent's verdict), US3
  (the issue comment says what is left and why), US4 (a spec whose only
  leftovers are human-only does not grind to the cap)

## Path Conventions

GitHub Actions reusable-workflow pipeline, no `src`/`tests` split. Every
path below is relative to the repository root.

**Shared subject warning**: every user-story phase below edits the SAME two
steps in `.github/workflows/implement.yml` (`Read back cycle outcome`,
`Read back retry outcome`) plus `Consolidate final outcome` and `Dispatch
next step`, because the plan's decision table (data-model.md) is one
coherent unit split across FR groups, not four independent code paths. This
is unlike a typical feature where stories touch disjoint files — expect
each phase's diff to land immediately next to the previous phase's, and do
not skip a phase's checkpoint run before starting the next one.

---

## Phase 1: Setup

- [X] T001 Confirm the gate-number reservation above is still accurate:
  `grep -n "Gate 8[0-9]" .github/workflows/lint-workflows.yml` must show
  nothing above Gate 80. If it does, shift every "Gate 81" reference in
  this file to the next free number before starting Phase 3.

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: FR-007 requires the primary and retry arms to share one
checkbox-counting definition. Both arms, and every story's tasks below,
call this shared read — nothing in Phase 3+ can be wired without it
(research.md D2, D3).

- [X] T002 [P] Create `.github/actions/_shared/count-tasks-checkboxes.sh`
  — the one home of the checkbox read (research.md D2). Invocation shape
  mirrors `read-spec-meta.sh`'s `bash file <args>` convention: takes a git
  ref and a path to `tasks.md` within it. Reads the file with
  `git show "$ref:$path"`; if that fails (unreadable ref or path), the
  script MUST exit non-zero immediately with a message on stderr — unlike
  `read-spec-meta.sh`, it MUST NOT swallow the failure into a `found=false`
  output (FR-006, Principle VIII; research.md D2's explicitly stated
  deviation from the `read-spec-meta.sh` sibling pattern). On success, run
  one `awk` pass (D3) over the content that: toggles an in-fence boolean on
  any line whose text, after stripping leading whitespace, starts with
  ` ``` ` or `~~~`; while not inside a fence, counts lines matching
  `^\s*- \[[xX]\]` as checked and `^\s*- \[ \]` as unchecked (FR-004's
  checkbox forms — the same shape as the existing Arm-A regex at
  `implement.yml:1238-1239`, now fence-aware); collects the literal text of
  every counted unchecked line, in file order. Emit `checked_count=<n>` and
  `unchecked_count=<n>` as `key=value` lines to stdout for the caller to
  `eval` (read-spec-meta.sh's convention), plus the unchecked lines via a
  heredoc-style marker the calling composite step can relay straight into
  `$GITHUB_OUTPUT` (mirroring the existing
  `remaining<<WING_COMMANDER_REMAINING_EOF` convention already used in
  `Read back cycle outcome`, `implement.yml:1295-1301`). Document the exact
  emission format in the script's own header comment — this is the "one
  home" every other reader of this feature will look to.
- [X] T003 [P] Create
  `.github/actions/wing-commander-tasks-checkbox-count/action.yml` — the
  published front-door composite (research.md D2; contracts/
  convergence-signal.md §1). Header comment mirrors
  `wing-commander-spec-meta/action.yml`'s: names
  `count-tasks-checkboxes.sh` as the one home stage workflows must not read
  directly, and carries the Constitution VII minor-version-addition note
  plan.md's Complexity Tracking table already records. Inputs: `ref`
  (required), `path` (required). Outputs: `checked-count`,
  `unchecked-count`, `unchecked-items` (contract's shapes). Its single step
  calls `.github/actions/_shared/count-tasks-checkboxes.sh` (via
  `$GITHUB_ACTION_PATH/../_shared/...`, mirroring
  `wing-commander-spec-meta/action.yml:80`) and appends its output straight
  to `$GITHUB_OUTPUT`; unlike that sibling's step, this one carries no
  `|| true` or other swallowing — a non-zero exit from the shared script
  MUST fail this step and therefore the calling job (FR-006).

**Checkpoint**: the composite is callable in isolation (e.g. against a
scratch ref/path) before any workflow logic depends on it.

---

## Phase 3: User Story 1 - A cycle that stops with work left gets another cycle (Priority: P1) 🎯 MVP

**Goal**: `converged=true` requires zero outstanding unchecked tasks at the
cycle's pushed tip, in addition to the existing `ok`/`truncated` checks —
replacing "no converge: commit landed" as the sole test (FR-001, FR-002's
zero-outstanding clause). Shipping only this story already fixes spec 057's
failure (SC-003).

**Independent Test**: drive the stage's outcome and dispatch logic against
a branch whose `tasks.md` has unchecked tasks and whose range contains no
`converge:` commit; assert `converged=false` and a next-cycle dispatch
(the stage's existing non-converged path already does this once
`converged` is no longer wrongly `true`).

**Depends on**: Phase 2.

- [X] T004 [US1] `.github/workflows/implement.yml`, primary arm: add two
  new steps before `Read back cycle outcome` (id `outcome`, ~line 1180),
  each `uses: ./.wing-commander-pipeline/.github/actions/
  wing-commander-tasks-checkbox-count` (self-checkout resolution, matching
  `meta-cycle`'s `uses:` line at ~1170) — one at
  `ref: ${{ steps.base.outputs.base-sha }}` (contract §1 "Primary arm,
  base"), one at the pushed tip,
  `ref: origin/${{ inputs.spec-prefix }}${{ steps.spec.outputs.slug }}`
  (contract's "post-fetch" call site). `path` for both is
  `${{ steps.spec.outputs.spec-dir }}/tasks.md`. The tip call needs the
  branch fetched first; today's fetch is the first line inside
  `Read back cycle outcome`'s own `run:` block (line 1202) — hoist a
  minimal `git fetch origin "+refs/heads/...:refs/remotes/origin/..."`
  into its own step ahead of the tip composite call (or ahead of both new
  steps), and confirm `Read back cycle outcome`'s own remaining fetch
  logic (the default-branch resolution at 1211-1218, needed for Arm B) is
  left intact and not duplicated pointlessly. Gate both new steps on the
  same `if:` as `Read back cycle outcome`
  (`is-open == 'true' && skip != 'true'`).
- [X] T005 [US1] `.github/workflows/implement.yml`, primary arm,
  `Read back cycle outcome` (~1180-1301): replace the converge-commit-only
  decision (today's 1280-1294:
  `if [ -z "$converge_sha" ]; then converged=true; else converged=false; fi`)
  with FR-001/FR-002's rule, using T004's new steps' `unchecked-count`
  output at the tip: `converged=true` requires `ok=true`, `truncated=false`,
  **and** `unchecked-count(tip) == 0` (data-model.md's decision-table row —
  zero outstanding wins regardless of `converge_sha`, FR-010b). Any of
  `ok=false`, `truncated=true`, or `unchecked-count(tip) > 0` continues to
  leave `converged` false, exactly as today's other branches already
  handle `ok`/`truncated`. `converge_sha` is still computed (existing
  1285-1287 logic, unchanged) — it no longer decides `converged` at all,
  only the non-convergence *reason* (US3, Phase 6). Do not add the
  `progressed`/`handoff` outputs yet (US4, Phase 5) — this task only
  replaces the zero-vs-nonzero-unchecked test.
- [X] T006 [US1] `.github/workflows/implement.yml`, retry arm: mirror T004
  — add the same two composite-call steps before `Read back retry outcome`
  (id `retry-outcome`, ~line 1743), at the retry's own recorded base
  (`ref:` whatever the retry arm resolves as its own base-sha — **not**
  `steps.base.outputs.base-sha`, per FR-007/FR-010a "own base") and at the
  retry's post-agent pushed tip (contract §1 "Retry arm, base"/"Retry arm,
  tip").
- [X] T007 [US1] `.github/workflows/implement.yml`, retry arm: mirror T005
  — replace `Read back retry outcome`'s converge-commit-only decision
  (today's 1840-1853) with the identical zero-unchecked rule, using T006's
  steps' outputs.
- [X] T008 [US1] Audit `.github/scripts/verify-truncated-cycle-carry-forward.py`
  (Gate 30)'s `CYCLE_SCENARIOS` table and any retry/final-outcome fixtures
  for a `tasks.md` fixture whose expected `converged` value depends on the
  OLD converge-commit-only rule while leaving unchecked tasks present — a
  non-truncated scenario asserting `converged=true` from "no converge
  commit" with a fixture `tasks.md` that still has unchecked boxes will now
  correctly flip to `converged=false` under T005/T007's fix. This is a
  stale fixture needing its `tasks.md` content or expectation corrected
  (e.g. to zero unchecked tasks where `converged=true` is asserted), not
  evidence of a regression — Gate 30's own subject is the truncated/failed
  classification, not the convergence rule (research.md D5). Confirm no
  Gate 30 assertion still encodes "no converge commit ⇒ converged=true"
  with outstanding tasks present after this pass.
- [X] T009 [US1] Create `.github/scripts/verify-tasks-checkbox-convergence-signal.py`
  (Gate 81, research.md D5), modeled on
  `verify-truncated-cycle-carry-forward.py`'s structure: import
  `ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout` from
  `wc_shell_harness`; constants naming the exact shipped step names this
  gate drives (`Read back cycle outcome`, `Read back retry outcome`,
  `Consolidate final outcome`, `Dispatch next step`, and the two new
  checkbox-count composite call sites per arm); a `load_steps()` populating
  a module-level `STEPS_CACHE`; a scenario table (e.g.
  `SIGNAL_SCENARIOS`, one dict per fixture with `base_tasks_md`,
  `tip_tasks_md`, `converge_commit`, `verdict`, `cycle_result`, and an
  `expect` dict) and a `main()` that runs every scenario, prints a pass/
  fail summary, and exits non-zero on any failure (FR-018 — drives the
  *shipped* `run:` text, never a copy). This first pass covers only US1's
  FR-019 branches: progress + no converge commit ⇒ `converged=false`; zero
  outstanding ⇒ `converged=true` (SC-004); a `- [ ]` inside a fenced code
  block ⇒ not counted (FR-004); an unreadable `tasks.md` ⇒ the checkbox-
  count composite step fails the job loudly (FR-006); the spec-057 replay
  (11 of 65 tasks ticked, no converge commit, healthy exit) ⇒
  `converged=false` (SC-003). Wire it into `.github/workflows/
  lint-workflows.yml` immediately as "Gate 81 — …" with a bare `run:`
  line naming this script's exact path (Gate 10 requires every check
  script be named by some `run:` line or it is reported orphaned — do not
  leave it unwired even mid-feature).
- [X] T010 [US1] Run `python .github/scripts/run-local-gates.py`; confirm
  Gate 81 and every pre-existing gate (including Gate 30, after T008's
  fixture audit) pass.

**Checkpoint**: A cycle that ends healthy with outstanding tasks and no
converge commit now reports `converged=false` and the existing dispatch
logic sends it to another cycle. User Story 1 is independently shippable
here — this is the MVP fix for spec 057's failure.

---

## Phase 4: User Story 2 - The signal is read from the tree, never from the agent's verdict (Priority: P1)

**Goal**: prove, with checked-in fixtures, that the decision Phase 3
implemented is purely a function of `tasks.md`'s checkbox state and never
of the agent's transcript or closing message (FR-003), and that the
primary and retry arms compute it from one shared definition rather than
two copies that could drift (FR-007).

**Independent Test**: run the shipped outcome logic with a scenario whose
`CYCLE_RESULT`/verdict signals "the agent finished/claims success" while
`tasks.md` is full of unchecked boxes; the signal must come out false, and
the reverse (every box ticked, regardless of what any narrative would say)
must come out true.

**Depends on**: Phase 3 (there is no separate code path to add here — this
story is a set of properties the Phase 3 implementation must already
satisfy by construction, verified by fixtures).

- [X] T011 [US2] Extend Gate 81's scenario table with: (a) a fixture where
  `CYCLE_RESULT=success` and the tip's `tasks.md` still has unchecked
  tasks ⇒ `converged=false` regardless of `CYCLE_RESULT`/verdict wording
  (US2 acceptance scenario 1 — since T005/T007 never read those fields to
  decide `converged`, this fixture should already pass; it exists to
  pin the property against a future regression); (b) a fixture where every
  box is ticked ⇒ `converged=true` (acceptance scenario 2, SC-004); (c) the
  identical fixture shape driven through BOTH the primary and the retry
  arm's shipped step bodies via `run_step`, asserting byte-identical
  `converged` (and, once Phase 5 lands, `progressed`) verdicts on each
  arm's own base (US2 acceptance scenario 3, FR-007) — this fixture also
  becomes the target for Phase 7's "mutation applied to only one arm"
  mutation (SC-008).
- [X] T012 [US2] Add a "single home" structural check to Gate 81
  (research.md D2's closing paragraph, modeled on Gate 61's
  `verify-spec-meta-single-home.py`): fail if the fence-aware
  checkbox-counting `awk` idiom introduced in T002 appears anywhere in
  `implement.yml` outside of the two composite call sites per arm (T004,
  T006) — i.e., no third hand-rolled copy of the counting logic is pasted
  into either read-back step's own `run:` block now that the composite
  exists. This is distinct from Gate 30's own pre-existing Arm-A
  `grep -c '^\s*- \[[xX]\]'` comparison at `implement.yml:1238-1239`, which
  Phase 5 (T014) replaces by reusing this feature's composite outputs
  rather than leaving Arm A's separate grep in place — confirm after
  Phase 5 lands that this structural check has nothing left to flag there.
- [X] T013 [US2] Run `python .github/scripts/run-local-gates.py`; confirm
  Gate 81's new fixtures and structural check pass.

**Checkpoint**: The convergence decision is proven, not merely
implemented, to be tree-derived and shared between both arms.

---

## Phase 5: User Story 4 - A spec whose only leftovers are human-only does not grind to the cap (Priority: P1)

**Goal**: a healthy cycle that checks no new task, leaves outstanding
tasks, and lands no `converge:` commit is treated as the loop's natural
end — `converged=false`, hand off to finalization via the existing
cap-reached dispatch path, no further cycle dispatched (FR-010, FR-010a,
FR-010b).

**Independent Test**: drive the loop against a branch whose `tasks.md` is
byte-identical to its base and still carries unchecked tasks, with no
`converge:` commit in range; assert the stage reports `converged=false`,
dispatches finalize, and does not dispatch another cycle.

**Depends on**: Phase 3 (the `converged`/`unchecked-count` values this
story's hand-off condition consumes) and Phase 2 (the composite's
`checked-count` output at base and tip, reused here).

- [X] T014 [US4] `.github/workflows/implement.yml`, primary arm,
  `Read back cycle outcome`: compute `progressed` from the checkbox-count
  composite's `checked-count` at base (T004's base-ref step) and at tip
  (T004's tip-ref step): `progressed = tip_checked > base_checked` (D1,
  FR-010a), computed unconditionally for every healthy (`ok=true`,
  `truncated=false`) cycle rather than only inside today's
  `VERDICT == "exhausted"` branch. Reuse this same computation to REPLACE
  Arm A's own `before_count`/`after_count` grep at lines 1238-1239 (D1:
  "the identical comparison… just run unconditionally") rather than
  keeping two separate before/after checkbox counts in the same step —
  one calculation, two consumers (the pre-existing truncated-classification
  Arm A, and this new `progressed` output). Emit `progressed=true|false`
  as a new step output; leave it empty when `ok=false` or `truncated=true`
  (data-model.md's "Scope note").
- [X] T015 [US4] `.github/workflows/implement.yml`, retry arm: mirror T014
  in `Read back retry outcome`, against the retry's own base/tip counts
  from T006's steps.
- [X] T016 [US4] `.github/workflows/implement.yml`, both arms: compute
  `handoff` (FR-010, research.md D4) in each read-back step:
  `handoff = (ok == true && truncated == false && converged == false &&
  progressed == false && converge_sha == "")` — outstanding tasks, no
  progress, no converge commit. Emit as a new step output alongside
  `progressed`. Per FR-010b, zero-outstanding already decided
  `converged=true` upstream (T005/T007) before `progressed`/`handoff` are
  even consulted, so `handoff` is never true when `converged=true` — no
  extra ordering logic is needed beyond `handoff`'s own condition already
  requiring `converged == false`.
- [X] T017 [US4] `.github/workflows/implement.yml`, `Consolidate final
  outcome` (~1888-1949): carry `progressed` and `handoff` through the
  existing `RETRY_RAN` selection (same shape as the existing four-output
  selection at 1906-1910) and add them to the output-emission block
  (1940-1949). These remain step-local outputs, never `workflow_call`
  outputs of `implement.yml` (FR-017, contract §3).
- [X] T018 [US4] `.github/workflows/implement.yml`, `Dispatch next step`
  (~2498-2621): add a new `HANDOFF` env var
  (`${{ steps.final.outputs.handoff }}`) to the step's env block
  (~2508-2519), and a new branch, evaluated after the existing
  `TRUNCATED == true` (at-cap) branch and before the existing
  `ITERATION < MAX` branch (contract §4): `elif [ "$HANDOFF" = "true" ]`
  takes the SAME action the final cap-reached `else` branch already takes
  — post `$REMAINING` to the lifecycle issue, dispatch `NEXT_WORKFLOW`
  with `converged=false` — regardless of `$ITERATION` vs `$MAX` (D4: "the
  reused terminal path… taken regardless of ITERATION vs MAX"). No new
  dispatch mechanism or `workflow_dispatch` payload field (FR-010,
  FR-017). Since the `HANDOFF` branch and the cap-reached `else` branch
  (2599-2621) now post the identical shape of comment and dispatch,
  factor the shared body into one place within this step's script (e.g. a
  bash function called from both branches) rather than pasting it twice
  (CLAUDE.md's "one home" applies within a single script too) — the reason
  text is the only thing that must differ (Phase 6, US3).
- [X] T019 [US4] Confirm FR-009 and FR-011 are unaffected: the cap-reached
  terminal behaviour's own shape (`max-iterations` default of 5, the
  existing `else` branch's action) gets no semantic change beyond T018's
  new sibling branch; the cycle/retry agent prompts (`implement.yml:
  896-915`, `1485-1507`) gain no new instruction to keep working while
  turns remain — that correction is FR-015's wording fix only (Phase 7,
  T029), never an added "keep going" instruction.
- [X] T020 [US4] Extend Gate 81 with US4's FR-019 branches: unchecked
  tasks with **zero** progress and no converge commit ⇒
  `converged=false`, `handoff=true`, `Dispatch next step` posts remaining
  work and dispatches finalize with `converged=false`, no next-cycle
  self-dispatch (SC-002, SC-005); unchecked tasks with zero progress
  **and** a converge commit ⇒ `converged=false`, `handoff=false` (a
  converge commit means new work exists — not the FR-010 hand-off), next
  cycle dispatched; a cycle that checked one task and unchecked another ⇒
  `progressed=false` (FR-010a's conservative reading) even though a box
  moved.
- [X] T021 [US4] Run `python .github/scripts/run-local-gates.py`; confirm
  Gate 81's US4 fixtures pass alongside Phases 3-4's.

**Checkpoint**: a spec whose only outstanding tasks are human-only work
costs exactly one more cycle than today (the zero-progress cycle that
discovers it), never the remaining iteration budget (SC-005). All P1
stories are shippable here.

---

## Phase 6: User Story 3 - The issue comment says what is left and why (Priority: P2)

**Goal**: when a cycle does not converge, the lifecycle issue comment
names the reason (converge appended new work / tasks outstanding with
progress / tasks outstanding with no progress / truncated / cap-reached)
and lists the remaining tasks read from `tasks.md`'s tip, never an empty
fenced block (FR-012, FR-013, FR-014).

**Independent Test**: drive the dispatch step with `converged=false` and
no converge commit; assert the posted body lists the unchecked tasks and
names the reason.

**Depends on**: Phase 3 (the `remaining`/`converge_sha` values this story
rewrites the source and narrative of) and Phase 5 (the `handoff`/
`progressed` values this story's reason narrative also names).

- [ ] T022 [US3] `.github/workflows/implement.yml`, both read-back steps:
  change the `remaining` output's source (research.md D6) from
  `git show "$converge_sha" -- "$SPEC_DIR/tasks.md" | grep '^+' | grep -v
  '^+++' | sed 's/^+//'` (today's 1296-1300 / 1855-1860) to the tip's
  `unchecked-items` output from T004/T006's tip-ref composite call — the
  literal unchecked task-list lines at the pushed tip, regardless of
  whether a converge commit landed. This single source change covers both
  non-convergence reasons without double-listing (D6: a converge-appended
  phase is, by construction, additional unchecked lines already present in
  the tip's `tasks.md`).
- [ ] T023 [US3] `.github/workflows/implement.yml`, both read-back steps:
  extend the `reason` output (contract §2: "gains new narrative cases")
  with the non-convergence cases from data-model.md's "Non-convergence
  reason" entity — "converge appended new work" (`converge_sha` non-empty),
  "the cycle ended with tasks outstanding" (`progressed=true`, outstanding
  tasks remain), both concatenated without duplicating the task list
  itself when both fire (FR-013's no-double-report clause; spec's own edge
  case), or the FR-010 hand-off phrasing — "the cycle checked nothing new,
  so the loop is ending here rather than dispatching another cycle" — when
  `handoff=true`. Leave the existing failed/truncated/cap-reached reason
  strings elsewhere in the step untouched; only add these new cases.
- [ ] T024 [US3] `.github/workflows/implement.yml`, `Dispatch next step`:
  update the two existing `$REMAINING`-posting branches (~2582-2598
  standalone next-cycle, ~2599-2621 cap-reached) plus T018's `HANDOFF`
  branch to prefix the posted comment with T023's `reason` narrative, so a
  reader can tell "the spec grew" from "the cycle ran short" from "the
  loop is ending here" without opening the branch (FR-013). Confirm no
  comment ever renders an empty fenced remaining-work block on any path
  that posts `$REMAINING` (FR-012, SC-006) — the truncated/at-cap-while-
  truncated branch (~2560-2576), which posts no `$REMAINING` block at all
  today, is unaffected and keeps its own shape.
- [ ] T025 [US3] `.github/workflows/implement.yml`, both read-back steps:
  add to the step summary (FR-014) the numeric `unchecked-count` (tip)
  the decision used and the `progressed` boolean, written to
  `$GITHUB_STEP_SUMMARY` alongside the existing exhausted/failed summary
  lines (1260, 1264, 1271, 1275) — a run's own log should show why it
  converged, dispatched another cycle, or handed off, without re-deriving
  it from the branch.
- [ ] T026 [US3] Extend Gate 81 with FR-019's remaining-work fixtures: the
  no-converge-commit path (outstanding tasks, no `converge_sha`) produces
  a non-empty `remaining` and a reason naming "tasks outstanding"; the
  converge-commit-appended path's `remaining` lists the appended items
  without duplication; the both-reasons-fire path lists the task set
  exactly once (SC-006).
- [ ] T027 [US3] Run `python .github/scripts/run-local-gates.py`; confirm
  Gate 81's US3 fixtures pass alongside every prior phase's.

**Checkpoint**: every `converged=false` lifecycle comment names its reason
and lists at least one remaining item. All four user stories are shippable
here.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T028 Correct `.github/workflows/implement.yml`'s header comment
  (lines 5-9) and its "Failure detection + convergence signal" comment
  (lines 1151-1164) to describe the shipped rule (FR-015): `converged`
  now requires zero outstanding unchecked tasks at the tip, not merely the
  absence of a `converge:` commit; note the FR-010 zero-progress hand-off
  path explicitly, since it is new terminal behaviour reached before the
  cap.
- [ ] T029 Correct `.github/workflows/implement.yml`'s cycle prompt
  (~896-915) and retry prompt (~1485-1507), and any preceding framing text
  in those prompt blocks that explains the old converge:-commit-only rule
  to the agent, to describe the new signal (FR-015) — without adding any
  instruction to keep working while turns remain (FR-011 remains
  unmodified; this task only corrects what the prompt *describes*).
- [ ] T030 Correct `docs/architecture.md`'s Stage 4 section (lines
  467-500, specifically the commit-range-walk rationale at 486-490) to
  describe the tasks.md-checkbox-driven rule, and retire or restate the
  risk-table row at line 1330 ("Converge 'unchanged tasks.md' is
  syntactic, not semantic | Iteration cap + final converge report always
  posted to the issue") since this feature replaces that mitigation with
  the signal itself (FR-016).
- [ ] T031 Extend Gate 81 with a `MUTATIONS` table (mirroring
  `verify-truncated-cycle-carry-forward.py`'s `_mut_*`/`MUTATIONS`
  pattern, FR-020, SC-008): (a) a mutation reverting the decision to
  consult only `converge_sha` (dropping the unchecked-count check) — must
  flip at least one T009/T020 scenario's expected `converged`; (b) a
  mutation applied to only ONE of the two arms (primary or retry) — must
  flip that arm's scenario (T011c) while leaving the other arm's fixture
  passing, proving the gate attributes a one-arm-only regression; (c) a
  mutation that removes or inverts the FR-010 progress test (T014/T015) —
  must flip the zero-progress-handoff scenario (T020) or the
  tick-one-untick-one scenario. Guard each mutation the way
  `verify-truncated-cycle-carry-forward.py`'s `main()` already does: if the
  mutation's target text no longer exists in the current shipped step, the
  gate must error "mutation inapplicable" rather than silently pass.
- [ ] T032 Add a `check_gate_wired()` self-test to Gate 81 (mirroring
  Gate 30's): confirm the "Gate 81 — …" step exists in
  `.github/workflows/lint-workflows.yml`, is not `if: false`, and its
  `run:` line names `verify-tasks-checkbox-convergence-signal.py`'s exact
  path.
- [ ] T033 `grep -rn` across `.github/workflows/`, `.github/actions/`, and
  `docs/` for any remaining description of "no converge: commit ⇒
  converged" (or equivalent phrasing) after T028-T030; confirm none
  remains anywhere on the branch (SC-009).
- [ ] T034 Run `python .github/scripts/run-local-gates.py` for the full
  suite: confirm Gate 81 (with its complete scenario table and mutation
  battery) and every other gate, including Gate 30 per T008's fixture
  audit, pass together.
- [ ] T035 Replay spec 057's cycle-1 conditions against a real dispatch of
  `implement.yml` (quickstart.md's live-replay section; SC-003 as an
  end-to-end proof, not just Gate 81's synthetic fixture) once this branch
  reaches a PR: dispatch against a spec branch seeded with some tasks
  checked, most unchecked, no `converge:` commit in range, and confirm the
  run posts `converged=false` and dispatches the next cycle rather than
  finalize. NOT DONE at tasks-authoring time — this run's permitted
  command list has no `gh workflow run`/`gh run view`, only `gh issue
  view`/`gh issue comment`/`gh pr view`/`gh pr list`/`gh issue list`. Needs
  a human or a differently-scoped session post-merge, per CLAUDE.md's rule
  that behaviour which only runs in Actions is proven after merge by
  re-driving one run and recording the evidence on the PR or issue.

**Checkpoint**: `python .github/scripts/run-local-gates.py` exits 0; no
document describes the retired rule; the fix is proven against the real
shipped `run:` blocks by Gate 81, pending the post-merge live replay.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup — BLOCKS every user story
  (FR-007's shared composite is what every story's tasks call).
- **User Story 1 (Phase 3)**: depends on Foundational. This is the MVP and
  the base every later phase edits.
- **User Story 2 (Phase 4)**: depends on Phase 3 — it verifies properties
  of Phase 3's implementation; there is no code to write before Phase 3
  exists.
- **User Story 4 (Phase 5)**: depends on Phase 3 (consumes `converged`/
  `unchecked-count`) and Phase 2 (reuses the composite's `checked-count`).
- **User Story 3 (Phase 6)**: depends on Phase 3 (rewrites `remaining`'s
  source) and Phase 5 (reason narrative names `handoff`/`progressed`).
- **Polish (Phase 7)**: depends on all four stories being complete —
  FR-020's mutation battery targets scenarios every prior phase added.

Unlike a typical feature, these stories are **not** independently
parallelizable after Phase 3: Phases 4, 5, and 6 all edit the same two
read-back steps and the same dispatch step Phase 3 first touched. Land and
checkpoint each phase in the order above rather than working them
concurrently.

### Within Each Phase

- The two composite-call-adding tasks per arm (e.g. T004/T006) can run in
  parallel with each other (different arms, same file, non-overlapping
  line ranges) but must land before the corresponding decision-rewrite
  task (T005/T007) that consumes their outputs.
- Gate-extension tasks (T009, T011-T012, T020, T026, T031-T032) touch one
  file (`verify-tasks-checkbox-convergence-signal.py`) sequentially within
  a phase — do not parallelize two gate-extension tasks against the same
  file.

### Parallel Opportunities

- T002 and T003 (Foundational) touch different files and can run in
  parallel.
- T004 and T006 (US1, primary vs. retry arm composite-call additions) can
  run in parallel with each other, though both land in the same
  `implement.yml` file — coordinate to avoid a merge conflict on adjacent
  step insertions.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (the shared composite — blocks
   everything).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run `python .github/scripts/run-local-gates.py`;
   this alone fixes spec 057's failure (SC-003).

### Incremental Delivery

1. Setup + Foundational → the checkbox-count composite exists and is
   callable.
2. Add User Story 1 → the core defect is fixed; a cycle with outstanding
   tasks and no converge commit gets another cycle instead of a premature
   finalize.
3. Add User Story 2 → the fix is proven tree-derived and arm-shared, not
   merely implemented.
4. Add User Story 4 → a spec whose leftovers are human-only stops after
   one extra cycle instead of grinding to the cap — this closes the gap
   that would otherwise make the common case (19 specs on `main`) worse.
5. Add User Story 3 → the lifecycle issue becomes legible about which of
   the above happened, without opening the branch.
6. Polish → documentation, the mutation battery, and the post-merge live
   replay proof.

Every story after US1 narrows or explains behaviour US1 already
implements; none of them is safe to ship ahead of US1, and US4 in
particular should not be deferred past a single PR — shipping US1 alone
would fix spec 057's exact failure but reintroduce a *different* new
failure mode (a spec with only human-only leftovers grinding to the
iteration cap every time) that does not exist on `main` today.
