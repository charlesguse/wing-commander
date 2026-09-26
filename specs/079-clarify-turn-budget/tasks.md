# Tasks: Clarify's Turn Budget Reflects the Work Clarify Actually Does

**Input**: Design documents from `/specs/079-clarify-turn-budget/`
(plan.md, research.md, data-model.md, quickstart.md,
contracts/clarify-turn-budget-delta.md, contracts/gate-coverage-079.md)

**Tests**: This feature's verification is a deterministic gate script with
checked-in fixtures (constitution VIII/FR-018, contracts/gate-coverage-079.md),
not a conventional test suite. The gate task is listed with the
implementation task it verifies, matching this repository's existing
`verify-*.py` convention rather than a separate TDD phase.

**Gate numbering**: the highest gate number wired into
`.github/workflows/lint-workflows.yml` as of this branch is Gate 98
(`grep -n "Gate 9[0-9]" .github/workflows/lint-workflows.yml`). This
feature's one new gate is assigned **Gate 99**. Re-check this at
implementation time in case another in-flight branch has since claimed it
(research.md's own numbering caveat) and renumber this file and
contracts/gate-coverage-079.md by the same offset if so.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on an
  incomplete task)
- **[Story]**: US1 (declared budget describes real work), US2 (ceiling
  side effect is stated, not silent), US3 (scope stays clarify-only, no
  new knob), US4 (the next trend has a written procedure)

## Path Conventions

GitHub Actions reusable-workflow pipeline, no `src`/`tests` split. Every
path below is relative to the repository root.

---

## Phase 1: Setup

- [X] T001 Confirm the gate-number reservation above is still accurate:
  `grep -n "Gate 9[0-9]" .github/workflows/lint-workflows.yml` must show
  nothing above Gate 98. If it does, shift every "Gate 99" reference in
  this file and in contracts/gate-coverage-079.md to the next free number
  before starting Phase 5. Also confirm the current values this plan
  assumes: `.github/workflows/clarify.yml`'s `max-turns` default is `40`
  (lines 25-29) and `docs/adoption.md`'s `### clarify` Inputs row states
  `` `max-turns` (number, `40`) `` (line 1161) — if either has already
  moved on this branch, treat this file's `40`/`65`/`100`/`163` literals
  as stale and re-derive per research.md R1 before proceeding.

---

## Phase 2: Foundational

None. This feature has no shared infrastructure that blocks every story —
each user story edits its own non-overlapping file(s) (the workflow
default, the docs row, the new gate script, the new docs subsection).
The only real ordering constraint is that **User Story 3's live gate run
(T012) and User Story 4's worked example (T016) both read the values
User Story 1 (Phase 3) lands** — land Phase 3 before running either.

---

## Phase 3: User Story 1 - A stage's declared turn budget describes the work that stage really does (Priority: P1) 🎯 MVP

**Goal**: `clarify.yml`'s `max-turns` default moves from `40` to `65`,
with an inline comment recording the accepted range (`39-61`), the source
(issue #587's recorded history), and the resulting ceiling (`163`), so a
maintainer reading the input alone finds the reasoning (FR-001).

**Independent Test**: Replay the recorded clarify history (39, 45, 61
counted turns) against the new budget of `65` and confirm none are
reported over budget and no `elevated` trend band results (quickstart.md
step 2, SC-001/SC-002).

- [X] T002 [US1] `.github/workflows/clarify.yml`: change the `max-turns`
  input's `default:` from `40` to `65` (lines 25-29), and add an inline
  comment immediately above the `default:` line recording, verbatim: the
  accepted range `39-61` counted turns, the source (issue #587's recorded
  history), and the resulting ceiling `ceil(65 * 2.5) = 163`
  (contracts/clarify-turn-budget-delta.md's "Where the reasoning is
  recorded", research.md R1). Do not touch the input's `description`,
  `type`, or `required` fields — only the literal default and the new
  comment (FR-008/SC-004).
- [X] T003 [US1] Verify by replay (quickstart.md step 2): using the
  recorded history `{39, 45, 61}` and the new budget `65`, confirm
  `counted >= intended` is `false` for all three (no run over budget,
  SC-002) and that the window's `max-consumed-ceiling-fraction`
  (`61 / 163 = 0.374`) falls under the `0.6` climb threshold
  (`WING_COMMANDER_TURN_BUDGET_CLIMB_FRACTION`, docs/setup.md), so no
  trend band results (SC-001). Depends on T002.

**Checkpoint**: Clarify's declared budget now describes its real observed
range, with the reasoning recorded beside it. Independently shippable
here — Acceptance Scenarios 1, 2 and 4 of User Story 1 hold.

---

## Phase 4: User Story 2 - Re-basing a budget does not quietly re-base what a runaway agent may spend (Priority: P1)

**Goal**: The same edit (T002) states the resulting ceiling explicitly
rather than leaving it an unremarked side effect (FR-003), and every
clarify agent invocation still declares an explicit model and a bounded,
finite ceiling — nothing here is left to change silently (FR-004).

**Independent Test**: Compare the worst-case turn count before (`100`)
and after (`163`) the change, and confirm `163` is the value stated in
T002's comment rather than a number noticed only later (quickstart.md
step 1).

**Depends on**: Phase 3 (T002 is the edit this story's tasks verify).

- [X] T004 [US2] Confirm T002's inline comment states the resulting
  ceiling `163` explicitly, not just the accepted range — `grep -n "163"
  .github/workflows/clarify.yml` must find it beside the `max-turns`
  default (FR-003, SC-003, Acceptance Scenario 1 of User Story 2). Also
  run the independent arithmetic check from quickstart.md step 1
  (`awk`'s `ceil(65 * 2.5)`) and confirm it matches `163`.
- [X] T005 [US2] Verify only — no code change expected (research.md R3):
  every clarify agent invocation still declares an explicit `--model` and
  a bounded ceiling fed from `wing-commander-turn-ceiling`. Confirm
  `.github/workflows/clarify.yml` lines ~558-561 (`intended-turns:
  ${{ inputs.max-turns }}` into the ceiling action), ~673-678 (`--model
  ${{ inputs.model }}` / `--max-turns ${{ steps.agent-ceiling.outputs.ceiling
  }}`), ~715-718 (agent-verdict's `intended-turns`), and ~743-747
  (metrics-summary's `max-turns`/`ceiling`) are unchanged by T002 — only
  the value flowing through them is larger. Then run Gates 22
  (`verify-agent-verdict.py`) and 23 (`verify-gate-23.py`) and confirm
  both pass with no fixture change, since neither gate's fixtures encode
  clarify's specific literal (Acceptance Scenario 3 of User Story 2,
  FR-004/FR-011).

**Checkpoint**: The ceiling's new worst-case value (`163`) is stated,
not silent, and no invocation anywhere was left unbounded. User Stories 1
and 2 are both independently shippable here.

---

## Phase 5: User Story 3 - Re-basing one stage changes one stage, and widens nothing (Priority: P2)

**Goal**: `docs/adoption.md`'s clarify row is updated to match; a new
gate (`verify-stage-turn-budget-docs.py`, Gate 99) fails loudly if any
published stage's declared `max-turns` default and its docs row ever
disagree again; and every other stage, plus the pipeline's contract
surface, is confirmed untouched.

**Independent Test**: Diff the change and confirm exactly one stage's
declared budget value moved, and that the set of inputs, repository
variables and other knobs the pipeline exposes is identical before and
after (quickstart.md step 3).

**Depends on**: Phase 3 (T002 supplies the `65`/`163` values T006 and the
live gate run in T012 must agree with).

- [ ] T006 [P] [US3] `docs/adoption.md`: update the `### clarify` section's
  Inputs row (line 1161) from `` `max-turns` (number, `40`) `` to
  `` `max-turns` (number, `65`) `` — no other cell in that row changes
  (data-model.md's doc table).
- [ ] T007 [P] [US3] Create `.github/scripts/fixtures/stage-turn-budget-docs/`
  with five fixtures per contracts/gate-coverage-079.md, each a minimal
  scratch pair of workflow-YAML-snippet + docs/adoption.md-snippet
  sufficient for the gate's `--self-test` to exercise one branch:
  `all-agree/` (all nine stages' workflow default and docs default match,
  clarify already at `65`/`65`), `workflow-drifted/` (clarify workflow
  says `70`, docs still say `65`), `docs-drifted/` (docs say `70`,
  workflow still `65`), `docs-missing-cell/` (a stage's docs section has
  no `max-turns` cell while its workflow declares one), `no-subjects/`
  (an empty scratch directory — zero stage files discoverable).
- [ ] T008 [US3] Write `.github/scripts/verify-stage-turn-budget-docs.py`
  (Gate 99), modeled on `verify-versioning-refs.py`'s
  WHY-IT-EXISTS/WHAT-IT-CHECKS/WHAT-IT-DOES-NOT-CHECK/`--self-test`
  docstring shape (research.md R5). For each of the nine published stage
  workflows that declare a `workflow_call.inputs.max-turns.default`
  (`intake.yml` 50, `clarify.yml` 40→65, `plan.yml` 110, `tasks.yml` 60,
  `implement.yml` 180, `finalize.yml` 20, `cleanup.yml` 20, `rebase.yml`
  50, `pr-conversation.yml` 40 — data-model.md's published-stage table),
  parse that literal and the matching `docs/adoption.md` `### <stage>`
  section's Inputs-row `` `max-turns` (number, `NNN`) `` cell, and fail
  (exit 1) naming every `{stage, workflow-default, docs-default}` triple
  that disagrees. Zero stage files discovered is a failure, not a
  vacuous pass; a stage whose docs section omits its `max-turns` cell
  while the workflow declares one fails naming the stage, never silently
  skipped (constitution VIII, contracts/gate-coverage-079.md). Ship
  `--self-test` running all five of T007's fixtures and reporting each by
  name. Depends on T007.
- [ ] T009 [US3] Register Gate 99 in `.github/workflows/lint-workflows.yml`'s
  gate registry, following Gate 98's shape: a preceding comment naming
  this issue (#587) and describing the check, a `run:` step invoking
  `python .github/scripts/verify-stage-turn-budget-docs.py` gated
  `if: "!cancelled()"`, and a paired self-test step invoking the same
  script with `--self-test`. No edit to `run-local-gates.py` is needed —
  it derives its invocation set from `lint-workflows.yml` (CLAUDE.md).
  Depends on T008.
- [ ] T010 [US3] Run `python .github/scripts/verify-stage-turn-budget-docs.py
  --self-test` and confirm all five of T007's fixtures pass/fail exactly
  as contracts/gate-coverage-079.md specifies; then run the script live
  against the working tree (after T002 and T006 have both landed) and
  confirm exit 0 for all nine stages (quickstart.md step 4). Depends on
  T002, T006, T009.
- [ ] T011 [US3] Confirm no repository variable, workflow input, or other
  knob was added anywhere: `git diff main -- .github/workflows/
  .github/actions/` shows only `clarify.yml`'s literal default and inline
  comment plus `lint-workflows.yml`'s new gate registration — no new
  `inputs:`, `vars.`, or `secrets.` entry anywhere (FR-008, SC-004,
  quickstart.md step 3, Acceptance Scenario 1 of User Story 3).
- [ ] T012 [P] [US3] Confirm every stage other than clarify is
  byte-identical: `git diff main -- .github/workflows/intake.yml
  .github/workflows/plan.yml .github/workflows/tasks.yml
  .github/workflows/implement.yml .github/workflows/finalize.yml
  .github/workflows/cleanup.yml .github/workflows/rebase.yml
  .github/workflows/pr-conversation.yml` is empty (FR-002/FR-009/SC-005,
  Acceptance Scenario 2 of User Story 3). Depends on T002 having landed
  (so the diff base is meaningful).
- [ ] T013 [P] [US3] Confirm the invalid-budget guard (empty, zero,
  negative, non-numeric `max-turns` → loud failure naming the value)
  inside `wing-commander-turn-ceiling` still fires unchanged: per
  research.md R3 this guard is a function of whatever `intended-turns`
  value arrives, not of clarify's specific literal, and the composite
  action itself is untouched by this feature — confirm via its existing
  fixture set / Gates 22/23 passing with no fixture edits (FR-011,
  SC-008, Acceptance Scenario 3 of User Story 3).

**Checkpoint**: Exactly one stage's declared budget moved; the pipeline's
contract surface is unchanged; a gate now stands behind the "docs agree
with the workflow default" rule so it cannot drift back silently. User
Stories 1, 2 and 3 are all independently shippable here.

---

## Phase 6: User Story 4 - The next budget trend has a stated response, not a re-derivation (Priority: P3)

**Goal**: A new `docs/architecture.md` subsection gives the next
`turn-budget-trend` on any stage a written, evidence-based procedure
(FR-013), demonstrated against clarify's own numbers so it is shown
working rather than merely asserted (FR-014).

**Independent Test**: Hand the recorded clarify history and the written
procedure to someone who did not work this issue, and confirm they
arrive at the same declared budget (`65`) and ceiling (`163`) this
feature lands (quickstart.md's intent; data-model.md's "Written
procedure" table).

**Depends on**: Phase 3 (the worked example restates the `65`/`163`
values T002 lands — write this after, so the two cannot disagree).

- [ ] T014 [US4] Add a new subsection to `docs/architecture.md`
  immediately after the existing "What a 'turn' is here" / ceiling
  explanation (after the Gate 22/51 paragraph, ~lines 244-294, research.md
  R4 — the only place in the repository that already explains the
  budget/ceiling/verdict mechanism end-to-end). State, in order: (a) the
  evidence to read — a `turn-budget-trend` signal's `facts.history`, the
  window's `{run, counted-turns, intended-budget}` triples the watchdog
  collector already emits; (b) the arithmetic — new budget = the smallest
  multiple of 5 strictly greater than the window's maximum counted-turns,
  stated beside the accepted range (the window's min-max) it is derived
  to cover; (c) the cost consequence to check — the resulting ceiling,
  `ceil(new_budget * 2.5)`, computed and stated in the same change, never
  left implicit; (d) when to accept the trend instead of moving the
  number — the window's maximum is a single diagnosed-contaminated run
  (turns inflated by a cause unrelated to real work, e.g. spec 037's
  denied-tool-call inflation), or the band is `critical` with a rising
  `consecutive-at-or-over-budget` count that a bigger budget would only
  relabel — both cases close the `pipeline-defect` as accepted rather
  than move the number (data-model.md's "Written procedure" table).
- [ ] T015 [US4] In the same subsection, add the worked example: applying
  the stated arithmetic to clarify's cited history (`{39, 45, 61}`)
  yields budget `65` (smallest multiple of 5 strictly greater than `61`)
  and ceiling `163` (`ceil(65 * 2.5)`) — the same values T002 lands,
  demonstrating FR-014 by construction rather than a separate
  demonstration harness. Depends on T002 and T014.

**Checkpoint**: A future `turn-budget-trend` on any stage now has a
written procedure a maintainer can follow without re-arguing the three
options from scratch. All four user stories are independently shippable
here.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T016 Confirm no stale clarify-attributed `40` remains anywhere else
  (FR-017's "no stale number left behind"): `grep -rn "40" docs/
  README.md .github/scripts/` and check every hit that could plausibly
  refer to clarify's turn budget. Research.md R6 found only
  `docs/adoption.md` line 1161 (fixed by T006) and confirmed
  `docs/architecture.md` line 240's "specify / clarify" reference is
  about model tier, not turn count — re-confirm that finding still holds
  on this branch.
- [ ] T017 Run `python .github/scripts/run-local-gates.py` (CLAUDE.md:
  before pushing) and confirm the full suite passes, including new Gate
  99 and unmodified Gates 22/23.
- [ ] T018 Follow quickstart.md steps 1-6 end to end as a final
  acceptance pass: the declared budget and ceiling moved together (step
  1), the cited history replays with no trend band and no over-budget
  note (step 2), every other stage is untouched (step 3), Gate 99 passes
  both self-test and live (step 4), the full gate suite is green (step
  5), and the invalid-budget guard still fires (step 6) — confirming
  SC-001 through SC-009 all hold on the real tree.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: None (see above) — does not block anything.
- **User Story 1 (Phase 3)**: Can start immediately after Setup. Blocks
  the live (non-self-test) parts of User Story 3 (T010, T012) and User
  Story 4 (T015), since those read the values T002 lands.
- **User Story 2 (Phase 4)**: Depends on Phase 3 (T002) — it verifies the
  same edit rather than making a new one.
- **User Story 3 (Phase 5)**: T006/T007/T008/T009 have no dependency on
  Phase 3 and can be built in parallel with it (the gate's self-test
  fixtures are synthetic); T010/T011/T012/T013 need Phase 3's edit landed
  first.
- **User Story 4 (Phase 6)**: T014 (the procedure's general shape) has no
  dependency on Phase 3; T015 (the worked example) does.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Within Each User Story

- User Story 1: T002 before T003 (verification reads the edit).
- User Story 2: T004/T005 both read T002's edit; independent of each
  other.
- User Story 3: T007 before T008 (the gate's self-test needs fixtures to
  run against); T008 before T009 (nothing to register yet); T009 before
  T010 (self-test needs the registered script, though it can also be run
  standalone); T002 and T006 before T010's live run; T012/T013 can run
  any time after T002.
- User Story 4: T014 before T015 (the worked example extends the
  subsection T014 creates); T002 before T015.

### Parallel Opportunities

- T006 (docs edit) and T007 (fixtures) can run in parallel with each
  other and with Phase 3's T002/T003 — different files, and T006/T007's
  content is fixed by research.md's already-decided values, not computed
  from T002 at runtime.
- T012 and T013 (both read-only verification, different subjects) can
  run in parallel once T002 has landed.
- T014 (the procedure's general prose) can be drafted in parallel with
  Phase 3-5, since its shape does not depend on any of this feature's own
  edits — only its worked example (T015) does.

---

## Parallel Example: User Story 3

```bash
# Once Phase 3 (T002) is underway, these can start immediately:
Task: "Update docs/adoption.md's ### clarify Inputs row to max-turns 65"
Task: "Create the five stage-turn-budget-docs fixtures"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

Both are Priority P1 and land as one coherent edit: T002 (the value move)
plus T003-T005 (the replay proof and the ceiling/wiring verification).
This alone resolves the immediate request — the declared budget describes
clarify's real work, and the ceiling's new worst case is stated, not
silent (constitution II). Stop and validate here before continuing:
confirm SC-001, SC-002 and SC-003 hold.

### Incremental Delivery

1. Setup (T001) → confirm the gate number and current values are still
   as this plan assumes.
2. User Stories 1 + 2 (T002-T005) → the re-based budget lands, with its
   ceiling consequence stated and its wiring proven unchanged. **MVP.**
3. User Story 3 (T006-T013) → the docs row, the new drift-proof gate, and
   confirmation that nothing else moved and no knob was added.
4. User Story 4 (T014-T015) → the written procedure, demonstrated against
   this feature's own numbers, so the next trend has a recorded answer.
5. Polish (T016-T018) → stale-number sweep, full gate suite, final
   acceptance pass against quickstart.md.

Each step adds value without breaking the previous one; User Story 3's
gate (T008/T009) can be built in parallel with User Story 1 landing,
since its self-test needs only synthetic fixtures.
