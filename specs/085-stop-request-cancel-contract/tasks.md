# Tasks: The Stop Decision Answers Both Questions — One Home for "Stand Down" and "Cancel What"

**Input**: Design documents from `/specs/085-stop-request-cancel-contract/`
(plan.md, research.md, data-model.md, quickstart.md,
contracts/decision-function.md, contracts/composite-invocation.md,
contracts/gate-60-structural-check.md, contracts/gate-87-coverage.md)

**Tests**: This feature's verification is two existing deterministic gate
scripts with checked-in fixtures (Gate 87 — `verify-board-stop-check.py`;
Gate 60 — `verify-single-home-idioms.py`), not a conventional test suite
(constitution VIII, FR-011, FR-010). No new gate is added (Out of Scope) —
every gate/fixture task below amends one of these two scripts and is listed
inline with the implementation task it verifies, matching this repository's
existing `verify-*.py` convention rather than a separate TDD phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on an
  incomplete task)
- **[Story]**: US1 (the decision function's two-fact contract), US2 (the
  composite's CLI invocation and Gate 87's shell-layer proof), US3 (Gate 60's
  structural rework)

## Path Conventions

GitHub Actions/CI-tooling repository, no `src`/`tests` application layout.
Every path below is relative to the repository root and already exists —
this feature edits four files in place
(`.github/scripts/board_stop_check.py`,
`.github/actions/wing-commander-board-stop-check/action.yml`,
`.github/scripts/verify-board-stop-check.py`,
`.github/scripts/verify-single-home-idioms.py`) plus the fifteen fixture
files under `.github/scripts/tests/board-stop-check/`. No file is created or
deleted.

---

## Phase 1: Setup

- [X] T001 Run `python .github/scripts/run-local-gates.py` and record that it
  passes on the unmodified tree — the pre-change baseline every later
  gate-suite run in this file is compared against (SC-006).

---

## Phase 2: Foundational

None. The only cross-story ordering constraint is that **Phase 4 (User
Story 2) depends on Phase 3 (User Story 1)**: the composite's new invocation
(T010-T012) pipes into `board_stop_check.py`'s CLI, so `main()`'s changed
JSON stdout contract (T004) must exist first, and Gate 87's shell-layer
mutation (T016) is combined with the decision-function mutation T007 adds.
**User Story 3 (Phase 5, Gate 60)** has no code dependency on either — its
structural rework and self-test fixtures are synthetic and independent of
the real composite/module content — and may be done in any order relative
to Phases 3-4, per spec.md's own dependency note ("It depends on User Story
1 only in that the guard-free form is the safe form").

---

## Phase 3: User Story 1 - A maintainer's stop halts the loop and never costs it its own run (Priority: P1) 🎯 MVP

**Goal**: `find_stop_request()` returns a `StopDecision(stand_down,
cancel_run_id)` two-fact tuple, `cancel_run_id` is never the current run's
own id, and `main()`'s stdout states the same contract as one JSON line.

**Independent Test**: Drive the decision function over the existing
first-pass fixture and confirm it reports "stand down, nothing to cancel";
drive it over the earlier-run fixture and confirm it reports "stand down,
cancel run N". Delete the no-self-cancel rule and confirm at least one
checked-in case fails. All of this runs at the Python-function layer only —
no shell, no composite (spec.md's Independent Test for this story).

- [X] T002 [US1] In `.github/scripts/board_stop_check.py`, add
  `StopDecision = collections.namedtuple("StopDecision", ["stand_down",
  "cancel_run_id"])` and change `find_stop_request()` to return
  `StopDecision(stand_down, cancel_run_id)` in place of the current bare
  `str | None`. `stand_down` is `True` iff an authorized, unactioned stop
  request exists at or after the baseline (FR-002 — exactly today's
  `stop_seen` condition). `cancel_run_id` is `last_other_run_id` when one
  exists, and `None` in every other case — **the fallback
  `last_other_run_id if last_other_run_id is not None else current_run_id`
  (today's line 218) is replaced by a fallback to `None`**; per FR-003 and
  data-model.md's invariant, "the function MUST NOT return the current
  run's own id as `cancel_run_id` under any input." Returns `StopDecision(False,
  None)` immediately when `stop_seen` is `False` (today returns `None`
  early at line 216).
- [X] T003 [US1] In `.github/scripts/board_stop_check.py`, rewrite
  `find_stop_request()`'s docstring (currently: "Returns the run_id (str)
  to `gh run cancel` when an authorized, unactioned stop request exists,
  else None") to state the two-fact `StopDecision` contract in its own
  terms, and state plainly that the current run is never a valid
  `cancel_run_id` (FR-005, contracts/decision-function.md). No sentence in
  this module may describe the return value as "the run_id (str) to `gh run
  cancel`" after this task.
- [X] T004 [US1] In `.github/scripts/board_stop_check.py`, change `main()`
  so that on success it prints exactly one line — `json.dumps({"stand_down":
  ..., "cancel_run_id": ...})` (or `decision._asdict()`) — always, including
  the `stand_down: False` case (today's `main()` prints the bare run id and
  prints nothing when there is no stop request). Update `main()`'s own
  docstring to match (FR-005). Failure behaviour is unchanged: a malformed
  payload already raises inside `json.load`/dict access, writing a
  traceback to stderr and exiting non-zero with nothing on stdout — no new
  error-handling code is needed (contracts/decision-function.md, research.md
  D3).
- [X] T005 [P] [US1] Migrate every fixture under
  `.github/scripts/tests/board-stop-check/*.json` (all fifteen files in
  `EXPECTED_FILES`) from `"expected_run_id": <string or null>` to
  `"expected": {"stand_down": <bool>, "cancel_run_id": <string or null>}`,
  computed from the *same outcome* each fixture already encodes (all fifteen
  fixtures share `"current_run_id": "999"`): `expected_run_id: null` →
  `{"stand_down": false, "cancel_run_id": null}`; `expected_run_id: "999"`
  (the current run's own id — `first-pass-own-run-only.json`,
  `evidence-link-not-a-marker.json`, `run-line-in-prose-ignored.json`, and
  the four `forged-marker-*` cases whose value is `"999"`) →
  `{"stand_down": true, "cancel_run_id": null}` per FR-003; every other
  value (`maintainer-stop.json`: `"111"`, `skips-own-run.json`: `"222"`,
  `bot-marker-honoured.json` and `forged-run-line-in-own-comment.json`:
  `"333"`) → `{"stand_down": true, "cancel_run_id": "<that value>"}`. No
  fixture is deleted and no fixture's real-world scenario changes — a shape
  migration only (FR-012, SC-003, contracts/gate-87-coverage.md).
- [X] T006 [US1] In `.github/scripts/verify-board-stop-check.py`, update
  `run_fixtures()` to compare `board_stop_check.find_stop_request(...)`
  against each fixture's new `expected` dict/`StopDecision` (in place of the
  old `spec["expected_run_id"]` bare-string comparison), and update
  `run_command_cases()`'s `want_run = "111" if want else None` computation
  to the equivalent `StopDecision(want, "111" if want else None)` comparison
  (the `MARKER_BODY` fixture there announces run `"111"`, a genuinely
  earlier run relative to `current_run_id="999"`). Depends on T005.
- [X] T007 [US1] In `.github/scripts/verify-board-stop-check.py`, add a
  fifth entry to `MUTATIONS`: `("self-run returned as cancel target,
  pre-085", "find_stop_request", ...)`, a replacement `find_stop_request`
  that reintroduces the pre-fix fallback (`StopDecision(stand_down,
  last_other_run_id if last_other_run_id is not None else current_run_id)`
  instead of `StopDecision(stand_down, last_other_run_id)`). No new
  plumbing needed — `mutation_check()` already runs every `MUTATIONS` entry
  through `run_fixtures()`/`run_command_cases()`. `first-pass-own-run-only.json`
  (from T005, now declaring `cancel_run_id: null`) is the fixture this
  mutation must fail, since under the mutation it reports `cancel_run_id:
  "999"` (FR-011's decision-function-layer proof, contracts/gate-87-
  coverage.md). Depends on T002, T006.
- [X] T008 [US1] Run `python3 .github/scripts/verify-board-stop-check.py`
  and confirm `run_fixtures()`, `run_command_cases()`, and all five
  `MUTATIONS` entries (including T007's new one) report `[ok]`/"mutation
  caught" with `0 failure(s)` — the composite-shell portion of this gate is
  still on the pre-change composite and is expected to still pass unchanged
  at this point (its own update is Phase 4). Depends on T002-T007.
- [X] T009 [US1] Follow quickstart.md steps 1 and 2: run the `python3 -c`
  snippet against the in-tree module and confirm it prints
  `StopDecision(stand_down=True, cancel_run_id=None)`; pipe the two
  `echo '{"comments": ...}' | python3 .github/scripts/board_stop_check.py`
  payloads and confirm the first prints `{"stand_down": true,
  "cancel_run_id": "222"}` and `echo 'not json' | python3
  .github/scripts/board_stop_check.py; echo "exit: $?"` prints no stdout, a
  traceback on stderr, and a non-zero exit (FR-007's module-level half).
  Depends on T002, T004.

**Checkpoint**: `find_stop_request()` and `main()` carry the two-fact
contract, mutation-proven independent of any shell or composite. User
Story 1 is independently shippable here.

---

## Phase 4: User Story 2 - The composite calls the module's documented interface (Priority: P2)

**Goal**: The composite's `check` step obtains its decision by piping a
payload into `board_stop_check.py`'s CLI — no `sys.path` insert, no module
import — fails loudly on an unreadable answer, and keeps exactly one
redundant "not this run" comparison as documented defence in depth.

**Independent Test**: Extract the composite's `check` step and run it
against the existing stub `gh`; every shell case produces the same `paused`
output and the same `gh run cancel` calls as before the change (spec.md's
Independent Test for this story).

**Depends on**: Phase 3 (T004's `main()` JSON contract must exist before the
composite can pipe into it; T007 supplies the decision-function mutation
T016 combines with).

- [X] T010 [US2] In
  `.github/actions/wing-commander-board-stop-check/action.yml`'s `check`
  step, remove the inline `python3 -c` block (lines 110-117 today) that
  inserts `.github/scripts` onto `sys.path` and imports `find_stop_request`.
  In its place, assemble the same stdin payload `main()` documents with
  `jq` from the comments file already on disk plus `$GITHUB_RUN_ID` and
  `$BOT_LOGIN`, and pipe it into `python3 .github/scripts/board_stop_check.py`
  — e.g. `stop_decision_json="$(jq -n --slurpfile comments
  "$RUNNER_TEMP/board-stop-check-comments.json" --arg run_id "$GITHUB_RUN_ID"
  --arg bot_login "$BOT_LOGIN" '{comments: $comments[0], current_run_id:
  $run_id, bot_login: $bot_login}' | python3 .github/scripts/board_stop_check.py)"`.
  No `sys.path` manipulation and no `from board_stop_check import` line may
  remain anywhere in this step (FR-006, User Story 2 Acceptance Scenario 1,
  SC-002, contracts/composite-invocation.md, research.md D4). The unchanged
  paginated comment read (lines 107-109) stays exactly as today.
- [X] T011 [US2] In the same `check` step, immediately after capturing
  `stop_decision_json`, validate it before reading either field — e.g. `jq
  -e '.stand_down | type=="boolean"' >/dev/null <<<"$stop_decision_json" ||
  { echo "::error::..." ; exit 1; }` — so a malformed payload, a crash, or a
  non-zero `python3` exit (already caught by the step's existing `set -uo
  pipefail`, line 102) all fail the step loudly rather than resolving to "no
  stop request" (FR-007, User Story 2 Acceptance Scenario 2, research.md
  D5). Depends on T010.
- [X] T012 [US2] In the same `check` step, read `stand_down` and
  `cancel_run_id` from the validated JSON (`jq -r '.stand_down'`, `jq -r
  '.cancel_run_id // empty'`), and keep exactly one shell comparison of
  `cancel_run_id` against `$GITHUB_RUN_ID` in the same position the old
  `stop_run_id != "$GITHUB_RUN_ID"` check occupied, renaming the variable
  throughout. Rewrite its guarding comment (today: lines 118-125) to state:
  this check is deliberately redundant with `find_stop_request()`'s own
  contract; that contract, mutation-proven under FR-011, is the primary
  guard; the check is kept anyway because `gh run cancel` is not recoverable
  by retry — the same belt-and-braces framing the workflow-path and
  repository-target guards already carry in this step (FR-004, User Story 1
  Acceptance Scenario 4, contracts/composite-invocation.md, research.md D6).
  `paused` computation is unchanged. Depends on T010, T011.
- [X] T013 [P] [US2] Diff
  `.github/actions/wing-commander-board-stop-check/action.yml`'s `inputs:`,
  `outputs:`, the `closed-check` step, and every guard below the self-cancel
  comparison (unreadable-run, workflow-path, repository, completed-status)
  against `main` — confirm none of it changed (FR-008). Verify only; no
  edit expected.
- [X] T014 [US2] In `.github/scripts/verify-board-stop-check.py`, add
  `"999": {"status": "in_progress", "path": OWN_PATH, "repository":
  {"full_name": REPO}}` to `RUNS` — closing the gate gap spec.md's own
  section names: `GITHUB_RUN_ID` is hard-coded `"999"` in
  `_run_shell_case`'s environment, and `999` was deliberately absent from
  `RUNS`, which is why the existing forged-marker shell case is saved by the
  unreadable-run guard regardless of the self-cancel comparison (FR-011,
  contracts/gate-87-coverage.md, research.md D9(2)).
- [X] T015 [US2] In the same file, add a `SHELL_CASES` entry: `("a first
  pass through this run cancels nothing even though that run is otherwise a
  readable, same-workflow, non-completed run", [_marker(999), STOP],
  "true", None)` — proving the self-cancel invariant holds end-to-end
  through the real composite shell now that `999` is readable (T014). This
  is the exact scenario the "gate gap" section traces as previously
  unprovable. Depends on T014.
- [X] T016 [US2] In `composite_shell_check()`, extend the existing
  `GUARD_LINE_RE`-based mutation with a second mutation that also disables
  the redundant `cancel_run_id != $GITHUB_RUN_ID`-shaped comparison
  (T012's line), run in combination with a temporary on-disk copy of
  `board_stop_check.py` carrying T007's self-cancel mutation, against the
  new `999`-only `SHELL_CASES` entry (T015): with the shipped function
  alone, disabling the redundant shell comparison must change nothing (the
  function never hands back `999`); with *both* the function bug and the
  guard removed, the case must fail (`want_cancel` becomes `"999"` where the
  fixture expects `None`) — proving the shell comparison is independently
  load-bearing as a backstop (FR-004, FR-011's shell-layer proof,
  contracts/gate-87-coverage.md's "Extending the composite-shell mutation"
  section). The existing workflow-path guard mutation is unchanged and
  continues to run on its own. Depends on T007, T010-T012, T014, T015.
- [X] T017 [US2] Run `python3 .github/scripts/verify-board-stop-check.py`
  and confirm `0 failure(s)` end to end: every fixture, command case, all
  five `MUTATIONS` entries, every `SHELL_CASES` case (including T015's new
  one), and both composite-shell mutations (the pre-existing workflow-path
  one and T016's new combined one) report caught/`[ok]` (quickstart.md step
  4, in full). Depends on T008, T010-T016.
- [X] T018 [P] [US2] Follow quickstart.md step 3: `grep -n "sys.path"` and
  `grep -n "from board_stop_check import"` against
  `.github/actions/wing-commander-board-stop-check/action.yml` and confirm
  both find nothing (User Story 2 Acceptance Scenario 1, SC-002). Depends
  on T010.
- [X] T019 [P] [US2] Follow quickstart.md step 7: `git diff main --
  .github/workflows/board-loop.yml` and confirm no output — this file
  consumes the composite's `paused` output across six jobs and is not part
  of this feature's diff (FR-008).

**Checkpoint**: The composite has no inline reimplementation, fails loudly
on an unreadable decision, and Gate 87 proves the self-cancel invariant at
both the function and shell layers. User Stories 1 and 2 are both
independently shippable here.

---

## Phase 5: User Story 3 - Gate 60 still catches a second copy, in any style (Priority: P3)

**Goal**: `verify-single-home-idioms.py`'s `check_board_stop_check()`
reasons structurally about each job's/composite's resolved step list
(following `check_token_mint()`) instead of three file-wide literal
fragments, one of which this feature's own fix deletes.

**Independent Test**: Plant a copy of the idiom, written in the post-change
style, in a throwaway workflow inside the gate's own self-test tree and
confirm the gate reports a finding naming the declared home; plant a
module-referencing file that orchestrates no cancel and confirm no finding;
run the gate's clean-tree self-test and confirm no finding (spec.md's
Independent Test for this story). No dependency on Phases 3-4's real code.

- [ ] T020 [US3] In `.github/scripts/verify-single-home-idioms.py`, rewrite
  `check_board_stop_check()` to follow `check_token_mint()`'s pattern: for
  each `(path, doc)` via `load_yaml` (never grep raw text), resolve every
  step list via the existing `_step_lists(doc)` helper, excluding the
  declared home's own directory
  (`.github/actions/wing-commander-board-stop-check/`, the same exclusion
  `check_dispatch_and_wait` applies), and test the concatenated `run:` text
  of each step list for co-occurrence of two facts: (1) obtains a stop
  decision — a regex matching `board_stop_check\.py` (the post-change CLI
  invocation) OR `from board_stop_check import find_stop_request` (the
  pre-change import style, kept so a paste of the *old* idiom is still
  caught per FR-009's "regardless of the style it is written in"); (2)
  performs a cancellation — the unchanged literal `gh run cancel`. A step
  list is a finding only when both facts are present in that same list, not
  merely somewhere in the file (FR-009, User Story 3 Acceptance Scenario 3,
  research.md D7). Drop `BOARD_STOP_CHECK_FRAGMENTS`'s third element
  (`"board-stop-check-comments.json"`) entirely — it named an
  implementation-detail filename that is no longer needed once facts 1 and 2
  require co-occurrence within one orchestration. Update the finding
  message's `<detail>` text to name which of the two facts matched and
  where.
- [ ] T021 [US3] In the same file, rewrite `DECLARED_HOMES["board-stop-check"]`'s
  comment (currently describing the `find_stop_request` import as the
  idiom) to describe the post-change idiom: obtain a decision from
  `board_stop_check.py`'s documented CLI, then `gh run cancel` whatever
  earlier run it names. Keep the comment's issue-#462 provenance note
  (FR-010, research.md D8).
- [ ] T022 [US3] In `_clean_tree()`, rewrite the synthetic fixture planted
  at `DECLARED_HOMES["board-stop-check"]` (currently a shell containing the
  three literal fragments, with the import only as a never-executed `#
  from board_stop_check import find_stop_request` comment) to a shell that
  actually pipes a payload to `.github/scripts/board_stop_check.py` and
  calls `gh run cancel` on the result — so `selftest_clean_tree_passes()`
  exercises the real post-change shape Gate 60 must stay silent on (FR-010,
  research.md D8). Depends on T020 (the new check must stay silent on this
  rewritten fixture).
- [ ] T023 [US3] Rewrite the existing `selftest_third_paste_fails(
  "board-stop-check", ".github/workflows/third-board-stop-check.yml", ...)`
  call in `run_selftest()` to plant the *post-change* style (piping a
  payload to `.github/scripts/board_stop_check.py`, then `gh run cancel`)
  and assert a `board-stop-check` finding at that path (FR-010's "a finding
  on a planted paste written in the post-change style," User Story 3
  Acceptance Scenario 1). Depends on T020, T022.
- [ ] T024 [US3] In `run_selftest()`, add a new self-test case that plants a
  file whose steps reference `.github/scripts/board_stop_check.py` (fact 1)
  but perform no `gh run cancel` (no fact 2) — e.g. a hypothetical dry-run
  reporter — and assert **no** `board-stop-check` finding for it (FR-010's
  third named self-test direction, User Story 3 Acceptance Scenario 3).
  Depends on T020, T022.

**Checkpoint**: Gate 60's `board-stop-check` check catches a second site
regardless of style, and stays silent on a legitimate non-loop consumer.
User Story 3 is independently shippable here (and does not require Phases 3
or 4 to have landed).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T025 [US3] Run `python3 .github/scripts/verify-single-home-idioms.py`
  (against the real tree — expect `0 failure(s)`, no second site of the
  idiom exists) and `python3 .github/scripts/verify-single-home-idioms.py
  --self-test` (expect `0 failure(s)` across every synthetic case,
  including T023's post-change-style third paste and T024's new
  no-cancellation case) — quickstart.md step 5, User Story 3's all four
  Acceptance Scenarios. Depends on T020-T024.
- [ ] T026 Run `python .github/scripts/run-local-gates.py` and confirm every
  gate passes, including the amended Gate 87 (T017) and Gate 60 (T025), with
  none skipped or waived to reach green (SC-006, quickstart.md step 6).
  Depends on T017, T025.
- [ ] T027 Final cross-check of SC-002: confirm the shipped composite
  contains zero lines that import or path-bootstrap the stop-check module,
  and at most one comparison of a stop-check result against the current run
  id (the FR-004 redundant guard, carrying the comment T012 wrote stating
  so). Depends on T010-T012.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: None — see the Phase 2 note above for the one
  real cross-story constraint (Phase 4 depends on Phase 3).
- **User Story 1 (Phase 3)**: Depends on Setup only.
- **User Story 2 (Phase 4)**: Depends on Phase 3 (T004, T007).
- **User Story 3 (Phase 5)**: Depends on Setup only — independent of
  Phases 3-4.
- **Polish (Phase 6)**: Depends on Phases 3, 4, and 5 all being complete
  (T026 runs the full suite; T027 checks Phase 4's composite).

### Within Each User Story

- US1: T002 (StopDecision/contract) → T003 (docstrings) → T004 (`main()`
  JSON) are sequential (same file). T005 (fixture shape) can run in
  parallel with T002-T004 (different files). T006 depends on T002 and T005.
  T007 depends on T002 and T006. T008 depends on all of T002-T007. T009
  depends on T002 and T004.
- US2: T010 → T011 → T012 are sequential (same file,
  `action.yml`). T013 is independent verification. T014 → T015 → T016 are
  sequential (same file, `verify-board-stop-check.py`) and T016 also
  depends on T007 and T012. T017 depends on everything before it in this
  phase. T018 depends on T010; T019 has no code dependency in this phase.
- US3: T020 → T021 → T022 → T023 → T024 are sequential (same file,
  `verify-single-home-idioms.py`). T025 depends on all of them.

### Parallel Opportunities

- T005 (fixture-shape migration) can run in parallel with T002-T004
  (`board_stop_check.py` itself) — different files, and the fixture shape is
  fixed by data-model.md independent of the code that will satisfy it.
- T013, T018, T019 are read-only verification tasks with no file-edit
  conflicts and can run in parallel with each other once their named
  dependency (if any) is met.
- Phase 5 (User Story 3) can be executed in parallel with Phases 3-4
  entirely, by a different contributor, since it touches only
  `verify-single-home-idioms.py` and has no code dependency on either.

---

## Parallel Example: Phase 3 (User Story 1) + Phase 5 (User Story 3)

```bash
# One contributor works Phase 3 sequentially (same-file edits):
# T002 -> T003 -> T004 -> T006 -> T007 -> T008 -> T009
# while T005 (a different file set) runs alongside T002-T004.

# A second contributor works Phase 5 independently, in full, at the same time:
# T020 -> T021 -> T022 -> T023 -> T024 -> T025
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 3: User Story 1 — the decision function's two-fact
   contract, mutation-proven in isolation from any shell or composite.
3. **STOP and VALIDATE**: T008/T009 confirm Gate 87's Python-level checks
   and the CLI contract independently.
4. This alone closes the spec's correctness core (defect 1) even before the
   composite or Gate 60 are touched — though FR-013 requires all three
   defects to ship together in the final PR, since Gate 60's fragment set
   and the composite's invocation cannot both stay correct across two
   separate commits.

### Incremental Delivery

1. Setup → User Story 1 (decision function) → validate independently.
2. Add User Story 2 (composite CLI reuse + Gate 87 shell-layer proof) →
   validate independently.
3. Add User Story 3 (Gate 60 structural rework) → validate independently —
   can be developed in parallel with 1-2 since it has no code dependency on
   either.
4. Polish: full local gate suite, final SC-002 cross-check.
5. Ship as one PR per FR-013 — no part of this spec is deferred to a
   follow-up.
