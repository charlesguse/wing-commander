---

description: "Task list for 065-intake-silent-path-cost"
---

# Tasks: A Run That Spent Money Says So — Intake's Silent Outcome Paths Report Their Cost

**Input**: Design documents from `/specs/065-intake-silent-path-cost/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cost-report-action.md, contracts/gate-extensions.md, quickstart.md

**Tests**: Not applicable as a separate phase — this feature's "tests" ARE the
PR-time gate scripts it extends (`verify-clarification-gating.py`,
`verify-metrics-summary-record-emission.py`, `verify-plan-tasks-cost-line.py`).
Each user story's tasks include updating the relevant gate script/scenario
table in the same phase as the workflow change it verifies, per Constitution
VIII ("a gate that cannot fail proves nothing").

**Chosen step name**: every call site of the new composite is named
`Report run cost` in all four stage workflows (intake.yml, clarify.yml,
plan.yml, tasks.yml) — one consistent name, so a future reader searching for
it finds all four sites the same way. This name is this document's own
choice (the contract leaves the summary text and step name as an
implementation detail); keep it identical across all four files.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3/US4)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Infrastructure-only feature: no `src/`/`tests/` split. All paths are under
`.github/actions/`, `.github/workflows/`, and `.github/scripts/` at the
repository root.

---

## Phase 1: Setup

**Purpose**: Re-confirm the current shape of the four workflows before
editing, since research.md's Decision 3 explicitly left one item
unconfirmed and exact line numbers shift between planning and
implementation.

- [X] T001 Re-read `.github/workflows/intake.yml`, `.github/workflows/clarify.yml`,
      `.github/workflows/plan.yml`, and `.github/workflows/tasks.yml` fresh and
      confirm by name (not by line number, which will have shifted) that:
      (a) intake.yml still has "Compute cost line", "Append cost line to
      clarification questionnaire", "Announce clarification needed", and
      "Announce spec PR ready for review"; (b) clarify.yml still has the same
      four plus "Report cost of a reply that answered nothing"; (c) plan.yml
      and tasks.yml still have "Dispatch tasks/implement stage (auto)" (id
      `dispatch-auto`) and "Report cost of an auto-mode hand-off"; and (d)
      confirm the open item from research.md's Decision 3: plan.yml's and
      tasks.yml's `mode == 'pr'` (human-reviewed PR) success paths post **no**
      cost statement anywhere today — there is no second, non-hand-off
      callout embedding the cost line to strip, only the auto-mode hand-off
      and the standalone (`NEXT_WORKFLOW` empty) comment inside
      "Dispatch ... stage (auto)" (which builds its body with
      `printf '%s\n\n%s' <message> "$COST_LINE"`) carry it today. Record any
      drift found before continuing — do not silently work around a renamed
      step.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one new composite action every stage will call, and the one
harness fix every gate-script change in this feature depends on. No user
story's workflow or gate-script edits are meaningful until both exist.

**⚠️ CRITICAL**: Complete both tasks before starting any user story phase.

- [X] T002 [P] Create `.github/actions/wing-commander-cost-report/action.yml`
      per `contracts/cost-report-action.md`: a composite action with required
      inputs `token`, `issue-number`, `cost-line`, `stage-label`; no outputs
      required; it composes a fixed-shape summary from `stage-label` that
      names only "a cost is being reported," never a stage's outcome (FR-008),
      and calls `./.wing-commander-pipeline/.github/actions/wing-commander-callout`
      (the same relative self-checkout path every existing composite call
      uses — see any existing `uses:` line in the four stage workflows) with
      `kind: info` and `body: ${{ inputs.cost-line }}` verbatim — no
      reformatting, rounding, or recomputation of the value (FR-004). Do not
      gate internally on outcome, agent status, or cancellation; that
      judgment belongs entirely to each call site's own `if:` (Constitution
      IX).

- [X] T003 [P] In `.github/scripts/verify-clarification-gating.py`, extend
      `evaluate_if()` (around line 209) to treat a bare `!cancelled()` term as
      always-true, the same way the function already special-cases a bare
      `always()` term (see the `if term == "always()": continue` branch).
      Without this, the function's blanket guard
      (`if "||" in expr or "${{" in expr or "!" in expr.replace("!=", ""):
      sys.exit(...)`) hard-errors on any step whose `if:` contains
      `!cancelled()` — which every new `Report run cost` call site's `if:`
      will, per research.md Decision 2
      (`always() && !cancelled() && steps.agent.outcome != 'skipped'`). None
      of `INTAKE_SCENARIOS`/`CLARIFY_SCENARIOS` model a cancelled run, so
      treating the term as a no-op (like `always()`) is correct for every
      existing scenario; it is not a general `!`-support relaxation — keep
      the hard-error for every other use of `!`.

---

## Phase 3: User Story 1 - A run that found no feature request still reports what it spent (Priority: P1) 🎯 MVP

**Goal**: Intake's four deliberately-silent outcome paths gain a cost
statement on the lifecycle issue, without changing that they announce no
outcome.

**Independent Test**: Walk `INTAKE_SCENARIOS`' four silent-path entries
("no discernible feature request, empty clarifications"; "no discernible
feature request WITH questions"; "spec authored, no questions, no
discoverable branch"; "specified=false but a spec branch resolved") and
confirm each now shows a fired cost report alongside its existing
`expect_silent_green=True`.

- [X] T004 [US1] In `.github/workflows/intake.yml`, add a new step named
      `Report run cost` calling
      `./.wing-commander-pipeline/.github/actions/wing-commander-cost-report`,
      placed after "Compute cost line" (so `steps.cost-line` has already run)
      and not nested inside any outcome-branch's own `if:`. Its `if:` is
      `steps.lifecycle-gate.outputs.is-open == 'true' && always() &&
      !cancelled() && steps.agent.outcome != 'skipped'` — the same
      `is-open`/`agent ran` gate "Compute cost line" already uses
      (research.md Decision 2), plus the added `!cancelled()`. Inputs:
      `token: ${{ env.WC_BOT_TOKEN }}`, `issue-number: ${{ inputs.issue-number }}`,
      `cost-line: ${{ steps.cost-line.outputs.line }}`, `stage-label: Intake`.

- [X] T005 [US1] In `.github/scripts/verify-clarification-gating.py`:
      1. Set `report_cost="Report run cost"` on `INTAKE_STAGE`'s `Stage(...)`
         construction (it currently passes no `report_cost`, unlike
         `CLARIFY_STAGE`).
      2. Split the "which callouts fire" tracking (around lines 784–813) into
         two independent checks instead of one, because the new report is no
         longer mutually exclusive with the outcome callouts the way
         clarify's old bespoke `report_cost` was (it now fires *alongside*
         `render`/`announce_q`/`resolve_pr`/`announce_pr` on every non-silent
         path too):
         - Keep `by_key`/`fired`/`expect_fires` scoped to the four outcome
           callouts only (`render`, `announce_q`, `resolve_pr`, `announce_pr`)
           — remove `report_cost` from `by_key` and from `stage.posting_steps`
           (the `posting_steps` property at line ~142 should return
           `{announce_q, announce_pr}` only, not union in `report_cost`),
           so the existing "more than one posting callout fired" mutual-
           exclusion check keeps meaning what it always meant (an outcome
           callout and its sibling can never both fire) and is not tripped by
           the report firing alongside a real outcome callout.
         - Add a new, separate per-scenario field `expect_cost_report` (bool)
           and a new check: `evaluate_if(steps[stage.report_cost].get("if"),
           ctx, stage.report_cost, stage.path)` must equal
           `sc["expect_cost_report"]` whenever `stage.report_cost` is set.
      3. Update `carries_cost_line()`'s call sites (around line 807): today it
         asserts every step in `stage.posting_steps` embeds the cost line —
         invert this now that FR-002a moves the cost line off outcome
         callouts entirely. Assert instead that `announce_q` and
         `announce_pr` (and clarify's ready callout, in US3) do **not**
         reference `steps.cost-line.outputs.line` in body/body-file, and that
         `stage.report_cost`'s `with.cost-line` input does.

- [X] T006 [US1] In `.github/scripts/verify-clarification-gating.py`, add
      `expect_cost_report=True` to the four silent-path entries in
      `INTAKE_SCENARIOS` (the "no discernible feature request, empty
      clarifications", "no discernible feature request WITH questions",
      "spec authored, no questions, no discoverable branch", and
      "specified=false but a spec branch resolved" entries — see
      `data-model.md`'s restated Silent Outcome Path table for the exact
      four). Leave each entry's existing `expect_silent_green=True` and
      `expect_fires` untouched (outcome behavior is unchanged, FR-008) —
      this task only adds the new, independent cost-report expectation
      alongside it.

**Checkpoint**: Intake's four silent paths now provably report their cost
while still announcing nothing.

---

## Phase 4: User Story 2 - Every intake outcome reports its cost exactly once (Priority: P1)

**Goal**: Extend the same guarantee to every remaining intake path (the two
happy paths, the two veto paths, the malformed-result paths), and make sure
none of them now reports twice.

**Independent Test**: Walk every remaining `INTAKE_SCENARIOS` entry and
confirm exactly one cost statement per scenario — the report on paths that
used to embed the line in a callout, unchanged elsewhere.

- [X] T007 [US2] In `.github/scripts/verify-clarification-gating.py`, add
      `expect_cost_report=True` to every remaining `INTAKE_SCENARIOS` entry
      whose synthetic transcript represents an agent that actually ran —
      that is, every entry except none, since no entry sets
      `steps.agent.outcome` to `skipped` (confirm this per-entry rather than
      assuming it; the malformed-result and `is_error=True` entries near the
      end of the list still provide a transcript, so the agent step itself
      still ran and still cost money even though its structured result
      failed validation or the run goes red — FR-012's "conclusion-blind"
      rule applies to these too, not only the two named vetoes).

- [X] T008 [US2] In `.github/workflows/intake.yml`, delete the
      "Append cost line to clarification questionnaire" step entirely (the
      one whose `run:` is `printf '\n%s\n' "$COST_LINE" >>
      ".../intake-clarification.md"`) so "Announce clarification needed" no
      longer carries a cost line in its rendered questionnaire body (FR-002a).
      Leave "Render clarification questionnaire" and "Announce clarification
      needed" themselves untouched — only the line-appending step goes.

- [X] T009 [US2] In `.github/workflows/intake.yml`, remove
      `body: ${{ steps.cost-line.outputs.line }}` from "Announce spec PR
      ready for review"'s `with:` block. That callout's other inputs
      (`pr-url`, `pr-label`, `summary`, `kind: action`) are unaffected —
      confirm `wing-commander-callout` does not require `body` when
      `pr-url`/`pr-label` are set (its own contract already supports a
      PR-pointer callout with no free-text body; if it does not, this task
      also updates `wing-commander-callout`'s inputs to make `body` fully
      optional rather than working around the gap in intake.yml).

- [X] T010 [US2] Re-run `verify-clarification-gating.py`'s scenario suite
      mentally against T008/T009's edits: confirm the inverted
      `carries_cost_line()` assertions from T005 now pass for intake (the
      two outcome callouts no longer carry the line, `Report run cost` does),
      and that the mutual-exclusion check from T005 still passes (removing
      the cost line changes callout bodies, not their firing conditions, so
      `fired` is unchanged by this task).

- [X] T011 [US2] In `.github/scripts/verify-clarification-gating.py`, retire
      or repurpose `mut_cost_report_on_every_path` (around line 1125): today
      it encodes "the cost-only callout firing beside a callout that already
      carries the cost line" as a *bug* to catch (#366's original, narrower
      fix). After this feature ships, `Report run cost` firing alongside an
      outcome callout on every non-silent path is the *intended* behavior,
      so this mutation's premise is now false and it must not survive as a
      self-test case that would fail against the shipped tree. Remove it from
      the mutation list (do not leave a mutation whose "broken" state is
      actually correct post-ship), and confirm no other mutation in the file
      shares this same now-inverted assumption before moving on.

**Checkpoint**: Every intake outcome path — silent, happy, and vetoed —
reports its cost exactly once.

---

## Phase 5: User Story 3 - One cost report, not a fourth copy of one (Priority: P1)

**Goal**: Apply the same uniform report to clarify, plan, and tasks, retiring
the three existing bespoke copies (#366 in clarify, #377 twice in plan and
tasks) and stripping the cost line from every other stage's outcome
callouts too.

**Independent Test**: Search the repository for cost-report definitions —
find exactly one (`wing-commander-cost-report`), consumed by all four stage
workflows; confirm the two retired bespoke step names are gone.

- [X] T012 [US3] In `.github/workflows/clarify.yml`, replace "Report cost of a
      reply that answered nothing" with a `Report run cost` step calling
      `wing-commander-cost-report`, gated
      `if: steps.lifecycle-gate.outputs.is-open == 'true' && always() &&
      !cancelled() && steps.agent.outcome != 'skipped'` (no longer
      conditioned on `steps.clarification.outputs.outcome == 'none'` — the
      old bespoke step's whole reason for existing was that no other callout
      covered that one outcome; the new step covers every outcome instead).
      Inputs mirror T004's, with `stage-label: Clarify`. Update or remove the
      adjacent `# #366:` explanatory comment block, since it describes the
      retired bespoke step, not the shared composite.

- [X] T013 [US3] In `.github/workflows/clarify.yml`: delete the "Append cost
      line to clarification questionnaire" step (same shape as intake's,
      feeding "Announce remaining clarification questions"), and remove
      `body: ${{ steps.cost-line.outputs.line }}` from "Announce spec PR
      ready for review"'s `with:` block — the same two edits T008/T009 made
      in intake.yml, applied to clarify's equivalent steps.

- [X] T014 [US3] In `.github/scripts/verify-clarification-gating.py`:
      1. Point `CLARIFY_STAGE`'s `report_cost=` at the renamed
         `"Report run cost"` step (it already carries the old name today;
         only the string changes).
      2. Add `expect_cost_report=True` to every `CLARIFY_SCENARIOS` entry
         whose agent ran (apply the same per-entry confirmation T007 used for
         intake — check the malformed/terminal-result entries individually).
      3. Update `mut_drop_cost_report` (around line 1115): it currently
         breaks the report by rewriting its `if:`'s
         `outputs.outcome == 'none'` term to `'never'` — that term no longer
         exists on the new unconditioned `if:`, so rewrite the mutation to
         instead drop the `!cancelled()` or `steps.agent.outcome != 'skipped'`
         conjunct (mirroring the new mutations T019 adds for intake), and
         confirm `mut_cost_report_without_cost` (blanking `with.body`) is
         updated to blank `with.cost-line` instead, since the new composite's
         input is named `cost-line`, not `body`.
      4. Apply the same `carries_cost_line()` inversion T005/T010 made for
         intake to clarify's "Announce remaining clarification questions" and
         "Announce spec PR ready for review".

- [X] T015 [US3] [P] In `.github/workflows/plan.yml`:
      1. Delete "Report cost of an auto-mode hand-off".
      2. In "Dispatch tasks stage (auto)", remove `"$COST_LINE"` from the
         standalone-mode `printf` call (the `NEXT_WORKFLOW`-empty branch) so
         that comment no longer embeds the cost line either (FR-002a applies
         to this inline comment exactly as it does to a `wing-commander-
         callout` body) — leave the rest of that message and the `dispatched`
         output logic untouched.
      3. Add a new `Report run cost` step calling `wing-commander-cost-report`
         with `stage-label: Plan`, gated
         `if: steps.dupe.outputs.skip != 'true' && always() && !cancelled() &&
         (steps.agent-auto.outcome != 'skipped' ||
         steps.agent-pr.outcome != 'skipped')` — unlike intake/clarify,
         plan.yml is dual-mode (`agent-auto` vs `agent-pr`, mutually
         exclusive per run), so this is the first call site that needs the
         "either mode's agent step ran" form already used elsewhere in this
         file (see "File findings from this run"'s
         `steps.verify-pr.outcome != 'skipped' ||
         steps.verify-auto.outcome != 'skipped'` for precedent). This closes
         a gap wider than #377's original scope: today `mode == 'pr'` runs
         (the ones that open a PR for a human to review) post **no** cost
         statement at all, not even a bespoke one — confirmed in T001.
      4. Update or remove the adjacent `# #377:` comment block describing the
         retired step.

- [X] T016 [US3] [P] In `.github/workflows/tasks.yml`: apply the same four
      edits T015 made in plan.yml, to tasks.yml's "Report cost of an
      auto-mode hand-off", its "Dispatch implement stage (auto)" standalone
      branch, and its `agent-auto`/`agent-pr` pair, with `stage-label: Tasks`.

- [X] T017 [US3] In `.github/scripts/verify-plan-tasks-cost-line.py` (Gate
      63): re-point `FILES`, `check_structure`, and `check_behavior` from the
      retired "Report cost of an auto-mode hand-off" step to the new
      `Report run cost` step calling `wing-commander-cost-report`:
      - `check_structure`'s `uses:`/body checks now look for
        `wing-commander-cost-report` and `with.cost-line` (not
        `wing-commander-callout` and `with.body`); its `DISPATCHED_COND`/
        `mode == 'auto'` checks against the OLD step no longer apply, since
        the new step deliberately is **not** gated on `dispatched` or on
        `mode == 'auto'` — it must fire on the PR-mode path too. Add new
        structural coverage for the PR-mode case: the new step's `if:` must
        include an "agent-pr ran" disjunct so a `mode == 'pr'` run gets a
        report (T015/T016's point 3 gap).
      - `check_behavior`'s two existing scenarios (standalone vs dispatched)
        stay, since the standalone comment's `$COST_LINE` stripping and the
        dispatch step's `dispatched=true` gating are unchanged by this
        feature; add a third executed scenario for `mode == 'pr'` confirming
        the new step's `if:` evaluates true there too (Gate 63 does its own
        raw-string/executed checking, not `evaluate_if()`'s restricted
        grammar, so the `||` and dual-mode condition are not a parsing
        problem here the way T003 was for `verify-clarification-gating.py`).
      - Keep every one of the 8 existing self-test mutations meaningful
        against the new call sites (report step dropped, `id: dispatch-auto`
        dropped, either `if:` conjunct stripped, cost line dropped from
        `with.cost-line`, `uses:` swapped, `dispatched=true` hoisted, the
        standalone `$COST_LINE` blanked) — none may be silently dropped in
        the re-point (Constitution VIII).

- [X] T018 [US3] Confirm the single-home properties by hand (quickstart.md
      step 4): `grep -rn "Report cost of a reply that answered nothing"
      .github/` and `grep -rn "Report cost of an auto-mode hand-off"
      .github/` return nothing, and `grep -rln "wing-commander-cost-report"
      .github/workflows/` returns exactly `intake.yml`, `clarify.yml`,
      `plan.yml`, `tasks.yml`.

**Checkpoint**: All four cost-bearing stages share one report; the three
bespoke copies are gone.

---

## Phase 6: User Story 4 - The cost report cannot quietly disappear again (Priority: P2)

**Goal**: A gate fails, naming the path, whenever the report is removed,
mis-gated, emptied, or pasted as a private duplicate.

**Independent Test**: Run each gate script's `--self-test` mode and confirm
every mutated (broken) variant is rejected.

- [ ] T019 [US4] In `.github/scripts/verify-clarification-gating.py`, add
      self-test mutations for the new `Report run cost` step (both
      `INTAKE_STAGE` and `CLARIFY_STAGE`), mirroring Gate 63's mutation
      style: (1) the step removed entirely; (2) its `if:` loses `always()`;
      (3) its `if:` loses `!cancelled()`; (4) its `if:` loses the
      `steps.agent.outcome != 'skipped'` conjunct; (5) its `cost-line` input
      blanked; (6) its `uses:` swapped away from `wing-commander-cost-report`.
      Each must make `expect_cost_report=True` scenarios fail. Confirm the
      clean (unmutated) tree still passes first, per every other gate's
      self-test convention in this file.

- [ ] T020 [US4] In `.github/scripts/verify-metrics-summary-record-emission.py`,
      add a sibling check next to `case_cost_line_formatter_has_exactly_one_home`
      that scans every workflow file and every `.github/actions/**` file
      (excluding `wing-commander-cost-report/action.yml` itself) for: (a) the
      retired step names — `"Report cost of a reply that answered nothing"`
      and `"Report cost of an auto-mode hand-off"`; (b) any `gh issue
      comment` call or `wing-commander-callout` invocation whose body
      references `steps.cost-line.outputs.line` (or a local `cost-line` step
      output) from outside `wing-commander-cost-report/action.yml`. Either
      hit fails with a message naming the one home, matching
      `case_cost_line_formatter_has_exactly_one_home`'s existing failure
      message shape. Add a self-test fixture: a synthetic workflow snippet
      containing a pasted copy of the retired report shape, and confirm the
      new check rejects it.

**Checkpoint**: Deleting, ungating, blanking, or duplicating the report now
fails the PR-time gate suite by name.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and the process steps CLAUDE.md and plan.md
call for around this specific change.

- [ ] T021 Run `python .github/scripts/run-local-gates.py` (the full PR-time
      gate suite) and each touched script's own `--self-test` mode
      (`verify-clarification-gating.py --self-test`,
      `verify-metrics-summary-record-emission.py --self-test`,
      `verify-plan-tasks-cost-line.py --self-test`) per quickstart.md steps 1
      and 2; all must pass clean and reject every mutation.
- [ ] T022 Before merge, run the `review-step-gating` skill over the diff
      (CLAUDE.md requires this for any change touching an `if:` or a failing
      step — every task in Phases 3–6 touches one), specifically checking
      FR-012a: the new report step must not be strandable by the readiness
      veto or the contradiction veto's failing step above it.
- [ ] T023 In the implementation PR description, record Constitution VII's
      note explicitly per plan.md: adding `wing-commander-cost-report` is a
      deliberate, additive widening of the composite-action surface (a new
      composite alongside `wing-commander-callout`), not a breaking change —
      no existing input, secret, or output is removed or renamed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS every user story
  (the composite action and the harness's `!cancelled()` support are both
  load-bearing for every later phase).
- **User Story 1 (Phase 3)**: Depends on Foundational. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on User Story 1's harness rework
  (T005) landing first — it edits the same `run_scenario()` machinery and
  the same intake.yml callouts.
- **User Story 3 (Phase 5)**: Depends on Foundational only for plan.yml/
  tasks.yml/Gate 63 work (T015–T017); its clarify.yml work (T012–T014)
  additionally reuses the `by_key`/`posting_steps`/`carries_cost_line` split
  T005 already made, so do Phase 3 first even though clarify is a different
  stage.
- **User Story 4 (Phase 6)**: Depends on Phases 3–5 (there is nothing to
  regression-test until the report exists everywhere).
- **Polish (Phase 7)**: Depends on all of the above.

### Within-Phase Notes

- T002 and T003 are independent files — parallel.
- T015 and T016 are independent files (plan.yml vs tasks.yml) — parallel;
  both depend on T002.
- T019 and T020 are independent files — parallel; both depend on Phase 5
  being complete.
- Every other task within a phase touches a file (or a harness section) a
  prior task in the same phase already changed — sequential.

---

## Parallel Example: Foundational

```bash
Task: "Create .github/actions/wing-commander-cost-report/action.yml"
Task: "Extend evaluate_if() in verify-clarification-gating.py for !cancelled()"
```

## Parallel Example: User Story 3 (plan/tasks half)

```bash
Task: "Retire plan.yml's bespoke hand-off report; add Report run cost (dual-mode agent gate)"
Task: "Retire tasks.yml's bespoke hand-off report; add Report run cost (dual-mode agent gate)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (composite action + harness fix).
3. Complete Phase 3: User Story 1 — intake's four silent paths report cost.
4. **STOP and VALIDATE**: run `verify-clarification-gating.py` directly and
   confirm the four silent-path scenarios now show a fired cost report.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. User Story 1 → intake's reported defect is fixed (MVP).
3. User Story 2 → the rest of intake stops being at risk of double-posting
   and the veto/malformed paths are covered too.
4. User Story 3 → clarify/plan/tasks join the same mechanism; three bespoke
   copies retire.
5. User Story 4 → the regression gate locks all of the above in.
6. Polish → full suite, review-step-gating pass, PR description note.

Because US1/US2/US3 are all Priority P1 and share files (intake.yml and
verify-clarification-gating.py in particular), treat Phases 3–5 as one
release unit in practice — shipping US1 alone without US2's cost-line
stripping (T008–T010) would leave intake's happy paths double-reporting,
which is itself a new defect (FR-003). The phase split exists so each
story's acceptance scenarios can be checked off independently, not so that
US1 ships to production alone.
