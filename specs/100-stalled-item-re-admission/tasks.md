---

description: "Task list template for feature implementation"
---

# Tasks: A Stall Holds Until a Maintainer Re-Admits It — and a Stop Halts Readiness's Filing

**Input**: Design documents from `specs/100-stalled-item-re-admission/`
(spec.md, plan.md, research.md, data-model.md, quickstart.md, contracts/)

**Prerequisites**: plan.md (required), spec.md (required for user stories),
research.md, data-model.md, contracts/

**Tests**: No test-first (TDD) tasks were requested. Every gate-script and
fixture task below is itself the feature's verification mechanism
(Constitution VIII); there is no separate "write a failing test, then
implement" split, matching this repository's existing `verify-*.py`
convention where the check and its fixtures are the deliverable.

**Organization**: Tasks are grouped by user story (US1/US2/US3), matching
spec.md's priorities. Per research.md D1, US1 and US2 describe behavior
`#782` already built; their phases below are re-verification of those
already-built invariants, not new code. US3 is the one live requirement
(FR-006 through FR-011) and carries all the new code.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact; line numbers cite this session's read of `main`
  and may have drifted by a line or two by implementation time — re-derive
  live, don't trust the number blindly (the same caveat spec 062's
  tasks.md and this feature's own research.md apply to gate numbers below).

## Path Conventions

Single project, automation-only (plan.md "Structure Decision"): this
feature's files live under `.github/workflows/board-loop.yml`,
`.github/scripts/`, `.github/scripts/tests/`, and two live contracts under
other features' `specs/*/contracts/` directories (FR-019 — contracts are
fixed like code, unlike those features' own frozen `spec.md`/`plan.md`/
`tasks.md`).

---

## Phase 1: Setup

**Purpose**: Reserve the one shared resource (a gate number) every later
gate-registration task in Phase 5 needs.

- [X] T001 (confirmed **126** against `main`'s tip at implementation time —
  grep still finds 125 as the highest registered gate) Confirm the highest `Gate N —` currently registered in
  `.github/workflows/lint-workflows.yml` (this session's read of `main`
  finds **125** as the highest, via `grep -on "Gate [0-9]\+"
  .github/workflows/lint-workflows.yml`) and provisionally reserve **Gate
  126** for this feature's new gate script (research.md D8). Record the
  provisional number in this file's checkbox text when checked off,
  re-derived against `main`'s actual tip at implementation time — the same
  renumbering caveat `specs/062-lifecycle-review-gate/tasks.md` documents
  for its own Gate reservations applies here (main moves between this
  tasks-generation session and implementation).

---

## Phase 2: Foundational (Blocking Prerequisites)

**No blocking prerequisites.** Every line of new code this feature adds
lives inside User Story 3's phase below (the shared reviewed-head
determination and the resume clause-2 split); User Stories 1 and 2 require
no code changes at all — only re-confirming, via the gate `#782` already
built (Gate 97, `verify-board-loop-resume-gating.py`), that the invariants
research.md D1 describes still hold unmodified. Proceed directly to Phase 3.

---

## Phase 3: User Story 1 - A failed label add never turns a stall into a review round (Priority: P1)

**Goal**: Confirm `#782`'s existing `stall_label_findings()` coverage in
Gate 97 still enforces FR-001–FR-005 at all eight current stall sites, so
this feature's own Phase 5 changes cannot regress it.

**Independent Test** (spec.md): Drive each stall site with a stubbed label
call that fails, assert no `stalled` marker and a failed run; then with the
label call succeeding, assert the label precedes the marker comment. This
is exactly what Gate 97's existing self-test mutations already exercise
(commit `aaaa140`, PR #782).

- [X] T002 [US1] Run `python3 .github/scripts/verify-board-loop-resume-gating.py`
  and confirm `stall_label_findings()` reports zero findings for all eight
  current stall sites — triage's hand-over (`board-loop.yml:1427`), route's
  spec verdict (`:1906`), fix's gate-suite-red stall and post-push breach
  (`:2263`/`:2467`), review's three stall arms (`:3306`/`:3311`/`:3319`),
  and readiness's backstop breach (`:3913`) — satisfying FR-001/FR-004 and
  SC-001/SC-003.
- [X] T003 [US1] Run `python3 .github/scripts/verify-board-loop-resume-gating.py --self-test`
  and confirm the stall-label self-test mutations (reverting any one site
  to marker-before-label, or continuing past a failed `add_stalled_label()`
  call) still fail and name the site, satisfying FR-002/FR-003/FR-005 and
  SC-002.

**Checkpoint**: US1's invariant is confirmed intact before Phase 5 touches
any code in the same file.

---

## Phase 4: User Story 2 - A maintainer's stop halts readiness before it files anything (Priority: P2)

**Goal**: Confirm `#782`'s existing `readiness_stop_gate_findings()`
coverage in Gate 97 still enforces FR-012–FR-015 on every readiness durable
step.

**Independent Test** (spec.md): Run readiness against a stub where the
stop check answers "stand down", once with the backstop holding and once
breaching, and assert zero durable calls in both — exactly what Gate 97's
`readiness_stop_gate_findings()` and its self-test already exercise.

- [X] T004 [US2] Run `python3 .github/scripts/verify-board-loop-resume-gating.py`
  and confirm `readiness_stop_gate_findings()` reports zero findings across
  every readiness durable step gated on
  `steps.killswitch-recheck.outputs.paused` (`board-loop.yml:3696-3934`:
  the ready report and its marker, the not-ready comment, the breach-retry
  lookup, the `spec-request` create, the `board:stalled` label, and the
  cross-link), satisfying FR-012/FR-014 and SC-007.
- [X] T005 [US2] Run `python3 .github/scripts/verify-board-loop-resume-gating.py --self-test`
  and confirm removing the stand-down gate from any one of those readiness
  durable steps still fails and names that step, satisfying FR-013/FR-015
  and SC-008.

**Checkpoint**: US2's invariant is confirmed intact before Phase 5 touches
any code in the same file.

---

## Phase 5: User Story 3 - A maintainer's label removal does what they meant (Priority: P3) 🎯 owner-requested behavior change

**Goal**: State and gate the re-admission rule FR-006 asks for — the resume
fallback's `board:owned` clause resolves to `review` when the open PR's
head has moved since the last review, `readiness` when it has not (spec
093's refinement), and a fresh `triage` when no such PR exists — with a
fresh review-round budget (FR-009), no additional agent spend on a retry
(FR-010), and a run-summary record of what fired and why (FR-011).

**Independent Test** (spec.md): Drive resume against a stalled marker plus
an open loop-owned PR whose head moved since its last review and assert
`review`; with an unmoved head, assert `readiness`; against a stalled
marker with no open PR, assert a fresh `triage`. In every case, assert no
second branch/PR and a run-summary line naming the clause that fired.

### Implementation for User Story 3

- [X] T006 [US3] Implement the shared reviewed-head determination in
  `.github/scripts/board_item_marker.py` (contracts/reviewed-head-determination.md,
  FR-006b): a function `head_moved_since_last_review(pr_number, comments,
  bot_login, run=None)` — signature matching this module's own `read_marker(comments,
  bot_login)` and `add_stalled_label(..., run=None)` (the resume step's `comments`
  variable is the flat per-issue array at `board-loop.yml:582`'s
  `$RUNNER_TEMP/board-issue-comments.json`, already fetched before the step-resolution
  heredoc runs — not the `comments_by_issue` map the earlier `select` step builds, which
  is a different step's own file; the contract's "illustrative" signature names
  is deliberately not binding per its own header). Algorithm: (1) call `run(["gh", "pr",
  "view", str(pr_number), "--json", "headRefOid,commits", ...])` (default
  `subprocess.run`, matching `add_stalled_label()`'s own injectable-`run`
  testability pattern) and take the `committedDate` of the commit matching
  `headRefOid`; (2) scan `comments` for the loop's own bot-authored (`user.login
  == bot_login`) comment whose body matches review's **converged** wording
  (`"Review round {N} converged --"`, `board-loop.yml:3300`) or its
  **budget-spent** wording (`"Review round budget ({N}) spent on PR #{P}"`,
  `:3321`) for this `pr_number`, and take the most recent by `created_at` —
  this MUST NOT also match the parse-failed (`"Review round {N} on PR #{P}
  could not be read"`, `:3308`) or malformed-findings (`"Review round {N} on
  PR #{P} returned no valid in-scope finding"`, `:3313`) wording, both of
  which share the generic "Review round N on PR #P" prefix but are
  inconclusive by FR-006b's own rule; a naive prefix match on that generic
  form would wrongly treat an inconclusive round as a resolved review. (3)
  Return `True` (moved) when no such comment is found or the `gh pr view`
  call fails (`run`'s returncode != 0); return `True` when the head
  commit's `committedDate` is strictly after the matched comment's
  `created_at`; return `False` only when a matching comment's `created_at`
  is at or after the head commit's `committedDate`.
- [X] T007 [US3] (comments threaded via a new `COMMENTS_JSON` env var, cat'd
  from the already-fetched `$RUNNER_TEMP/board-issue-comments.json`, rather
  than re-reading the file inside the heredoc -- keeps Gate 97's own
  `RESUME_CASES` heredoc-execution harness working with no stub needed) In
  `.github/workflows/board-loop.yml`'s `select` job resume
  step's step-resolution heredoc, change clause 2 (currently at
  `:811-813`: `elif pr_from_fallback: step = BREACH_STEP if marker_step ==
  BREACH_STEP else "review"`) to the three-way split
  `contracts/resume-recovery-readmission.md`'s "Amended clause 2" states:
  when `marker_step == BREACH_STEP`, `step = BREACH_STEP` (unconditional,
  unchanged, `#530`'s carve-out); otherwise call `head_moved_since_last_review()`
  (T006) with `pr_number`, the resume step's already-loaded `comments` list, and
  `BOT_LOGIN` (both already in scope in this heredoc's environment — `BOT_LOGIN` is
  set at the step's `env:`, line `578`); `step = "review"` when it returns `True`,
  `step = "readiness"` when `False`. Do not touch clauses 0, 1, 3, or 4.
- [X] T008 [US3] (satisfied by reusing the step's existing generic `note`
  field/echo rather than adding a new one: clause 2b sets `note` to name the
  resolved step and, per the contract's own wording, "the head moved ... or
  no reviewed head was resolvable" vs "the head had not moved since the
  last review" -- the already-existing `if [ -n "$resume_note" ]; then
  echo ...` at the bottom of the step prints it unconditionally) Extend the
  resume step's existing `$GITHUB_STEP_SUMMARY`
  echo lines (`board-loop.yml:855-861`) so that, whenever T007's clause-2b
  split fires, the line also names which of `review`/`readiness` was
  resolved and why (head moved / head unmoved / no reviewed head
  resolvable), reusing the same `echo ... >> "$GITHUB_STEP_SUMMARY"` idiom
  already used at that site and at readiness's stand-down record (FR-011,
  research.md D6).
- [X] T009 [US3] Add one `$GITHUB_STEP_SUMMARY` line at each of the eight
  stall sites (the same lines T002 lists), immediately after a successful
  `add_stalled_label()` + marker render, naming the issue, the step it
  stalled from, and that a `stalled` marker was recorded — reusing the
  existing summary-echo idiom (FR-011, research.md D6, data-model.md "Run
  Summary Record"). This line fires on every successful pass through a
  stall site, which is what makes it also cover the "FR-002 retry"
  case FR-011 names: the loop has no separate signal for "this attempt is a
  retry of a previously failed label-add" (a failed attempt posts no marker
  and leaves no state to distinguish it), so recording every successful
  stall satisfies FR-011 for both a first attempt and a retry.
- [X] T010 [US3] Update `add_stalled_label()`'s docstring in
  `.github/scripts/board_item_marker.py` (currently lines `183-186`: "...
  Re-admission keeps the resume step's ordinary re-derivation from live
  state: review when an open board:owned PR cites the issue, otherwise a
  fresh triage.") to state the combined rule FR-006/FR-006a now require:
  review when an open `board:owned` PR cites the issue **and its head has
  moved since the last review**, readiness when it has not, otherwise a
  fresh triage — cross-referencing `head_moved_since_last_review()` (T006)
  as the shared determination, per FR-006's requirement that the rule live
  "in one canonical place."
- [X] T011 [P] [US3] (both source contracts left in place as this feature's
  own review record, per the task's own "either is acceptable" clause) Fold `specs/100-stalled-item-re-admission/contracts/resume-recovery-readmission.md`'s
  "Amended clause 2" text directly into
  `specs/061-marker-owned-in-flight/contracts/resume-recovery.md`'s own
  "Step resolution" clause 2 and its "Acceptance mapping" table (FR-019),
  per that delta document's own instruction ("applied to
  resume-recovery.md itself in the same change that implements this
  feature... the merged tasks stage folds its text into resume-recovery.md
  clause 2 directly"). Delete `resume-recovery-readmission.md` and
  `reviewed-head-determination.md` from this feature's own `contracts/`
  once folded in, or leave them as this feature's own review record if the
  implement stage prefers — either is acceptable since the live contract is
  what gates now read.
- [X] T012 [P] [US3] Amend
  `specs/057-autonomous-board-loop/contracts/labels-and-cross-links.md`'s
  `board:stalled` row's "Cleared by" cell (currently: "a human removing the
  label — the sole condition FR-010 [of spec 057] reads for
  re-eligibility") to add one sentence cross-referencing
  `resume-recovery.md`'s amended clause 2 for what happens *after* the
  label is cleared (FR-019/FR-020). No new row, column, or label.
- [X] T013 [US3] Create `.github/scripts/verify-board-loop-readmission.py`
  (Gate 126 per T001), fixture-driven in the style of
  `verify-board-eligibility.py` (file-based fixtures under
  `.github/scripts/tests/`) for the reviewed-head determination, and in the
  style of `verify-board-loop-resume-gating.py` (Gate 97: parses the real
  `board-loop.yml` step text) for the clause-2 structural check: (a) import
  and call `head_moved_since_last_review()` (T006) directly against each
  fixture case under `.github/scripts/tests/board-loop-readmission/<case>/`
  (T014-T019, T020); (b) statically read the resume step's heredoc text out
  of `board-loop.yml` and confirm clause 2 branches on a call to
  `head_moved_since_last_review` rather than resolving unconditionally to
  `"review"` — reverting clause 2 to today's unconditional form MUST fail
  this check and name the clause (FR-006's failure mode, research.md D8,
  Constitution VIII); (c) include a `--self-test` mode mirroring
  `verify-board-loop-resume-gating.py --self-test`'s own convention,
  exercising that reversion. Fails loudly (not vacuously) when any fixture
  file under (a) is missing, matching `verify-board-eligibility.py`'s own
  rule.
- [X] T014 [P] [US3] Fixture case `head-moved-resolves-review/` under
  `.github/scripts/tests/board-loop-readmission/`: a round-outcome comment
  with `created_at` before the PR's `gh pr view` head-commit
  `committedDate` → `head_moved_since_last_review()` returns `True`, and
  the clause-2 simulation resolves `step == "review"`.
- [X] T015 [P] [US3] Fixture case `head-unmoved-resolves-readiness/`: a
  round-outcome comment with `created_at` at or after the head commit's
  `committedDate` → returns `False`, clause-2 simulation resolves `step ==
  "readiness"`.
- [X] T016 [P] [US3] Fixture case `no-reviewed-head-defaults-review/`: no
  round-outcome comment matches this `pr_number` (or only a
  parse-failed/malformed-findings comment does) → returns `True` (FR-006b's
  safe default), `step == "review"`.
- [X] T017 [P] [US3] Fixture case `pr-lookup-fails-defaults-review/`: the
  stubbed `run` for `gh pr view` returns a non-zero returncode → returns
  `True`, `step == "review"`.
- [X] T018 [P] [US3] Fixture case `breach-marker-ignores-head-movement/`: a
  `breach`-step marker whose PR was recovered only via the fallback, with
  both a head-moved and a head-unmoved sub-case → clause-2 simulation
  resolves `step == "breach"` regardless (`#530`'s carve-out, unaffected by
  T007).
- [X] T019 [P] [US3] Fixture case `no-open-pr-falls-to-triage/`: no
  `board:owned` PR citing the issue resolves via either the marker or the
  fallback → clause-2 is never reached, resolution falls to clause 4 →
  `step == "triage"`.
- [X] T020 [US3] (the round-0 half is gated directly via the heredoc; the
  "spends a fresh budget and stalls again" half is the review job's own
  pre-existing, unmodified round-count/budget logic -- not re-simulated
  here, since clause 2b never touches `round_` and so cannot regress it)
  Fixture case `fresh-budget-after-readmission/` (FR-009,
  SC-006, research.md D4): a `stalled` marker (`round: 0`, per every stall
  site's marker call omitting `--round`) recovered via the fallback with a
  moved head → resolved `step == "review"` with `round == "0"` — the same
  starting value a freshly selected item gets — and, spending a fresh
  `BOARD_LOOP_ROUND_BUDGET` (5) rounds with findings still open, stalling
  again on the same terms.
- [X] T021 [US3] Implement FR-010's no-extra-agent-invocation check inside
  `verify-board-loop-readmission.py` (contracts/stall-and-readmission-invariants.md
  "Added: FR-010's no-extra-invocation property"): confirm, for each of the
  eight stall sites, that the label-add call (`add_stalled_label()`) is
  reached and its failure fails the step *before* that job's step graph
  would invoke its agent step a second time within the same run — i.e., no
  loop or retry construct inside a single job execution re-invokes the
  agent after a label-add failure; a retry is simply the next scheduled
  workflow run re-entering the job exactly once, at the cost of one
  ordinary round, never an extra one.
- [X] T022 [US3] Register `verify-board-loop-readmission.py` (T013) in
  `.github/workflows/lint-workflows.yml` as a `"Gate 126 — ..."` /
  `"Gate 126 self-test — ..."` step pair, following the existing two-step
  convention immediately visible at Gate 97's own registration
  (`lint-workflows.yml:4193-4212`) — using whichever number T001's
  re-derivation against `main`'s tip at implementation time actually
  yields, renumbering every other `Gate 126` reference in this tasks.md
  together if it differs.

**Checkpoint**: All user stories are independently functional; the
combined rule is stated once (`add_stalled_label()`'s docstring, T010),
gated once (`verify-board-loop-readmission.py`, T013/T022), and recorded on
the run summary (T008/T009).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Whole-suite and whole-diff checks that span every story.

- [X] T023 [P] (197/197 gates passed, including Gate 126 and its self-test,
  with none skipped or waived) Run `python .github/scripts/run-local-gates.py` end-to-end
  and confirm every existing gate stays green alongside Gate 126, with none
  skipped, waived, or weakened to accommodate this change (SC-010).
- [X] T024 (confirmed: every file this feature touches is `board-loop.yml`,
  `.github/scripts/*.py`, `.github/scripts/tests/**`,
  `.github/workflows/lint-workflows.yml` (not itself a `workflow_call`
  reusable workflow -- it triggers on `workflow_dispatch`/push/pull_request,
  so its own internal step list is not a published interface), or a
  `specs/*/contracts/*.md`) Confirm FR-021/SC-011: diff every changed file against
  published-surface boundaries — no `workflow_call` stage workflow's
  `inputs`/`outputs`/`secrets`, and no published composite action's
  `action.yml` `inputs`/`outputs`, changed by this feature (every changed
  file is `board-loop.yml`, `.github/scripts/*.py`, `.github/scripts/tests/**`,
  or a `specs/*/contracts/*.md`, none of which are the published surface
  per Constitution VII).
- [X] T025 (recorded as a comment on lifecycle issue #752, since this
  implement-stage agent opens no PRs itself:
  https://github.com/charlesguse/wing-commander/issues/752#issuecomment-5922077122)
  Per CLAUDE.md "A fix to behaviour that only runs in Actions is
  proven after merge" and quickstart.md's "Post-merge Actions proof": note
  in this feature's implementation PR description that, after merge, one
  `board-loop.yml` run must be re-driven via its dispatchable wrapper
  against a real stalled item (or a directed single-issue run), with the
  run URL, resolved step, and summary line recorded on the PR or lifecycle
  issue #752.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. T001 has no code dependency but its
  reserved number is consumed by T013/T022.
- **Foundational (Phase 2)**: None — skipped.
- **User Story 1 (Phase 3)**, **User Story 2 (Phase 4)**: No dependency on
  Phase 1 or on each other. Both can start immediately and can run in
  parallel with each other and with Phase 5's early tasks, since neither
  touches a file Phase 5 changes until Phase 5's tasks land — but because
  Phase 5 edits the same `board-loop.yml` regions Gate 97 reads, re-run
  T002-T005 once more after Phase 5 completes as a final regression check
  (folded into T023).
- **User Story 3 (Phase 5)**: T006 before T007 (T007 calls T006's
  function) before T008 (extends the summary line T007's split needs).
  T010 after T006 (same file, describes what T006/T007 build). T013 after
  T006 and T007 (imports/inspects both). T014-T020 after T013 (need the
  gate's fixture-loading shape defined). T022 after T013 and T001.
  T009, T011, T012, T021 have no dependency beyond T006/T007 conceptually
  but touch disjoint files/regions from each other.
- **Polish (Phase 6)**: After every phase above.

### Parallel Opportunities

- T002-T003 (US1) and T004-T005 (US2) can run in parallel with each other
  and with all of Phase 5 except the final regression fold-in (T023).
- Within Phase 5: T011 and T012 (different contract files) can run in
  parallel with T006-T010 (code files) and with each other.
- T014-T019 (six fixture cases, six different directories) can run in
  parallel once T013 exists.
- T023 and T025 can run in parallel with each other; T024 is a quick diff
  check independent of both.

---

## Parallel Example: Phase 5 fixture cases

```bash
# Once T013 (verify-board-loop-readmission.py) exists, launch all six
# clause-2 fixture cases together:
Task: "Fixture case head-moved-resolves-review/ (T014)"
Task: "Fixture case head-unmoved-resolves-readiness/ (T015)"
Task: "Fixture case no-reviewed-head-defaults-review/ (T016)"
Task: "Fixture case pr-lookup-fails-defaults-review/ (T017)"
Task: "Fixture case breach-marker-ignores-head-movement/ (T018)"
Task: "Fixture case no-open-pr-falls-to-triage/ (T019)"
```

---

## Implementation Strategy

### MVP First

User Stories 1 and 2 (Phases 3-4) require zero new code — they are
confirmation that `#782`'s existing behavior and Gate 97 coverage still
hold. Running T001-T005 alone closes out US1/US2 with no risk of
regressing anything, and can be done first, fast, and independently of the
rest.

### Incremental Delivery

1. T001 (reserve the gate number) — no-op, unblocks Phase 5's registration
   task later.
2. T002-T005 (US1 + US2 regression confirmation) — ships first, zero new
   code, confirms the invariants this feature must not disturb.
3. T006-T022 (US3 — the owner-requested rule) — the one live requirement;
   ships last per spec.md's own framing ("US1 and US2 are correct without
   it, so it ships last").
4. T023-T025 (Polish) — whole-suite gate run, published-surface check,
   post-merge Actions proof reminder.

### Sequencing Note

Because Phase 5 edits the exact `board-loop.yml` regions Gate 97
(Phase 3/4) reads, run T002-T005 a second time after T007-T009 land, before
T023's full suite run — this is the same regression concern noted under
"Phase Dependencies" above, not a new task.

## Maintainer Feedback (review of 7b4b0825, PR #885)

- [ ] T026 [US3] BLOCKING: Fix clause 2b (board-loop.yml:822-827) so only the review job's converged-verdict wording resolves `step == "readiness"`; a budget-spent verdict (board_item_marker.py:170's `_REVIEW_BUDGET_SPENT_RE`) must instead resolve to `review` with a fresh round budget (FR-009). Update contracts/resume-recovery.md's "spent budget → readiness" row to match and add a checked-in fixture covering a re-admitted budget-spent stall with an unmoved head.

## Maintainer Feedback (review of 7b4b0825, PR #885)

- [ ] T027 [US3] Fix: board-loop.yml:689 passes `COMMENTS_JSON` via an environment variable, which can exceed the OS's ~128 KiB single-argument/env limit (reproduced with a 142 KB comments array: `python3: Argument list too long`, rc=126) and silently wedges resume under `set -uo pipefail`. Pass `COMMENTS_PATH` instead and `json.load()` the file in the heredoc, matching the marker read at board-loop.yml:589.

## Maintainer Feedback (review of 7b4b0825, PR #885)

- [ ] T028 [US3] Fix board_item_marker.py:221-238's `head_moved_since_last_review()`: comparing `committedDate` (client-set) to the matched comment's `created_at` lets a commit authored before the verdict but pushed after it, or a push landing mid-run, resolve to `moved=False` and send readiness an unreviewed head (FR-006b). Compare the head SHA against the reviewed SHA instead — recorded in the verdict comment text (FR-019 freezes only the marker schema, not comment text) or read from the review's `commit_id`. Also fix the `headRefOid` lookup at :235 to return `True` when not found in `commits`, rather than falling back to `commits[-1]`.
