---

description: "Task list for An Honoured Stop Records Its Stop Point — One Stop Halts One Item, Not the Board"
---

# Tasks: An Honoured Stop Records Its Stop Point — One Stop Halts One Item, Not the Board

**Input**: Design documents from `/specs/097-recorded-stop-point/`
(plan.md, research.md D1–D12, data-model.md, contracts/, quickstart.md)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md — all present and read.

**Tests**: Not explicitly requested as TDD. This feature's "tests" are the
new Gate 128 (`verify-stop-point-recording.py`) and its fixture corpus,
whose own contract (`contracts/gate-128-stop-point-recording.md`) requires
it to be shown failing on the pre-fix shape and passing on the fixed one
(SC-009) — so gate-check tasks are interleaved with the implementation
they check, not written strictly before it.

**Organization**: Tasks are grouped by user story. The recording mechanism
itself (stop-cause, the record write) is one shared composite every story
depends on, so it lives in Phase 2 (Foundational) rather than being split
four ways; each user story phase then adds the gate coverage, wiring, or
fixtures that specifically prove that story's acceptance scenarios.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1/US2/US3/US4, per spec.md's priorities (P1, P2, P2, P3)
- File paths are exact; line numbers are "as of this checkout" anchors, not
  guarantees — re-locate by content if a prior task has shifted them.

## Path Conventions

This is a GitHub Actions pipeline change, not an application — see plan.md
"Project Structure." All paths are repository-root-relative:
`.github/actions/wing-commander-board-stop-check/action.yml`,
`.github/scripts/board_stop_check.py`, `.github/scripts/board_item_marker.py`
(unchanged, reused), `.github/workflows/board-loop.yml`,
`.github/workflows/lint-workflows.yml`, `.github/scripts/
verify-stop-point-recording.py` (new), `.github/scripts/tests/
board-stop-check/` (new fixtures).

---

## Phase 1: Setup

**Purpose**: Documentation housekeeping that has no code dependency and can
proceed before any implementation.

- [X] T001 [P] Extend `specs/085-stop-request-cancel-contract/contracts/
  composite-invocation.md` with an additive note describing the widened
  `wing-commander-board-stop-check` surface this feature adds — the two new
  optional inputs `marker-branch` (default `""`) and `marker-base-sha`
  (default `""`), and the new `stop-cause` output (`""` |
  `"closed-issue"` | `"kill-switch"` | `"stop-request"`) — per research.md
  D3's Principle VII note ("a follow-up during implementation should extend
  that contract doc ... or record a superseding note in this feature's own
  contracts"). Make clear the existing "Unchanged surface (FR-008)" clause
  still holds letter-for-letter: no existing input/output's name, default,
  or meaning changes.
- [X] T002 [P] Create `.github/scripts/verify-stop-point-recording.py` with
  only its module header: a docstring naming Gate 128, FR-019, and
  `specs/097-recorded-stop-point/contracts/gate-128-stop-point-recording.md`,
  matching the header style of `.github/scripts/
  verify-board-loop-resume-gating.py` (Gate 97), plus an empty `main()` and
  `if __name__ == "__main__":` dispatch with a `--self-test` flag stub (no
  checks yet — those are added in T012–T013, T016–T017, T020, T026, T029).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one recording mechanism every user story depends on —
`stop-cause`, the two new pure functions, and the actual label+marker+
comment write. No user story's acceptance scenarios are reachable before
this phase completes (every one of them needs an honoured stop to produce
a durable, legible record in the first place).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add `find_stop_command_comment(comments, bot_login)` to
  `.github/scripts/board_stop_check.py`, next to `find_stop_request()`
  (research.md D2). It recomputes the same baseline `find_stop_request()`
  computes — the newest `is_loop_marker_author()` comment's
  `last_run_match()`, same predicate and ordering as
  `find_stop_request()`'s existing loop at `board_stop_check.py:201-210` —
  and returns the **last** comment at or after that baseline where
  `author_association in MAINTAINER_ASSOCIATIONS and
  is_stop_command(comment.get("body"))`, or `None` when none exists. Do not
  modify `find_stop_request()` itself, its `StopDecision` return shape, or
  `main()`'s existing stdin/stdout contract (D1 — Gate 87 mutation-proves
  `find_stop_request()` today and must keep doing so unchanged).
- [X] T004 Add `stop_command_reason(body)` to `.github/scripts/
  board_stop_check.py`, reusing the existing private `_command_line()` and
  the module-level `STOP_COMMAND_RE` (research.md D2). Returns the text on
  the matched line after `STOP_COMMAND_RE`'s match end, stripped; returns
  `""` when the stop command carried no reason (e.g. a bare `stop.`).
- [X] T005 [P] Add `html_url` to the composite's existing `gh api
  repos/.../issues/.../comments` `--jq` projection in `.github/actions/
  wing-commander-board-stop-check/action.yml`'s `check` step (currently
  `--jq '.[] | {body, author_association, created_at, user: {login:
  .user.login, type: .user.type}}'` at `action.yml:108`) — purely additive,
  one more object field (research.md D9). `specs/085-.../contracts/
  composite-invocation.md`'s "Unchanged" description of this JSON shape
  stays accurate since nothing downstream reads the object positionally.
- [X] T006 Add a `--stop-comment` CLI mode to `.github/scripts/
  board_stop_check.py`'s `main()`: reads `{"comments": [...], "bot_login":
  "..."}` JSON from stdin (the same comments-array shape `main()` already
  reads, now including `html_url` per T005), calls
  `find_stop_command_comment()` (T003) and, when it returns a comment,
  `stop_command_reason()` (T004) on its body; prints exactly one line of
  JSON — `{"html_url": ..., "login": ..., "created_at": ..., "reason":
  ...}` when a comment won, or `{}` when `find_stop_command_comment()`
  returned `None`. This is the one home `board_stop_check.py` provides so
  the composite's `run:` shell never re-derives the match/authorization
  rule itself (FR-018; contracts/stop-check-composite.md step 2's `--jq
  ... | python3 -I ".../board_stop_check.py" --stop-comment` usage, exact
  flag shape confirmed here).
- [X] T007 Fix provenance of the **existing** `board_stop_check.py`
  invocation in `.github/actions/wing-commander-board-stop-check/
  action.yml`'s `check` step (currently `python3 .github/scripts/
  board_stop_check.py` at `action.yml:113`) to `python3 -I
  "$RUNNER_TEMP/wc-pristine/scripts/board_stop_check.py"` (FR-018 last
  sentence; research.md D8; spec 095 FR-011/FR-012). Every **new**
  invocation this feature adds (T006's `--stop-comment` call, and the
  `board_item_marker.py` call in T010) is written with the pristine path
  from the start — this task only fixes the one pre-existing bare-path
  call.
- [X] T008 Add two new optional inputs to `.github/actions/
  wing-commander-board-stop-check/action.yml`: `marker-branch` (required:
  false, default `""`) and `marker-base-sha` (required: false, default
  `""`) — "The item's currently-known branch name / base commit... passed
  through to the stop-point record's marker when a stop is honoured... no
  effect on a kill-switch-only or closed-issue stand-down" (contracts/
  stop-check-composite.md).
- [X] T009 Add the new `stop-cause` output to `.github/actions/
  wing-commander-board-stop-check/action.yml`, computed once inside the
  existing `check` step via this exact decision order (contracts/
  stop-check-composite.md):
  ```text
  1. if check-issue-closed == "true" and the issue reads closed:
       stop-cause = "closed-issue"
  2. elif find_stop_request(comments, run_id, bot_login).stand_down:
       stop-cause = "stop-request"
  3. elif initial-paused == "true":
       stop-cause = "kill-switch"
  4. else:
       stop-cause = ""
  ```
  `paused` keeps its exact existing computation and meaning — `true` iff
  `stop-cause != ""` — so every one of the ~30 existing
  `steps.killswitch-recheck.outputs.paused` reads across `board-loop.yml`
  keeps working unchanged (FR-008's frozen clause, D3).
- [X] T010 Implement the record-write block inside `.github/actions/
  wing-commander-board-stop-check/action.yml`'s `check` step, gated on
  `stop-cause == "stop-request"` (research.md D5, D6, D8; contracts/
  stop-check-composite.md "Recording"):
  1. Fresh-read `gh issue view "$ISSUE_NUMBER" -R "$GITHUB_REPOSITORY"
     --json labels`. If `board:stalled` is already present, skip to step 4
     (idempotency, satisfies FR-007 "at most one stop-point record per
     run" — D6). This read is **not** given `continue-on-error: true`: an
     unreadable label state must not be guessed, unlike the existing
     closed-check step's documented exception.
  2. Run T006's `--stop-comment` CLI mode (from the pristine snapshot) to
     get the winning comment's `html_url`/`login`/`created_at`/`reason`.
  3. Write the label+marker via `python3 -I "$RUNNER_TEMP/wc-pristine/
     scripts/board_item_marker.py" --step stalled --issue "$ISSUE_NUMBER"
     --add-label "board:stalled" ${MARKER_BRANCH:+--branch
     "$MARKER_BRANCH"} ${MARKER_BASE_SHA:+--base-sha "$MARKER_BASE_SHA"}`
     — the exact CLI every other stall site uses (FR-018: "MUST go through
     the existing stall helper... not a new implementation"). On non-zero
     exit, `echo "::error::...no stop-point record is posted, so a later
     run retries the check (FR-017)."` and fail the step — nothing further
     in this branch runs.
  4. Post the comment with `gh issue comment`, using the exact template
     from `contracts/stop-point-record.md` (T010 depends on this
     template's content — see that contract for the literal text): names
     the cause ("a maintainer stop request"), `Stop comment: <html_url>
     (from <login>, <created_at>)` with **no leading `@`** on the login,
     the reason — when `stop_command_reason(body) != ""` — rendered via
     `fenced_section("Reason given:", reason, 2000)` from `.github/scripts/
     board_spec_request_body.py` (imported from the pristine snapshot, the
     same way `board-loop.yml`'s fix job already does at its gate-failure
     rendering site), omitted entirely when the reason is empty, the
     literal sentence "To resume this item, remove the `board:stalled`
     label.", then the marker text step 3 produced. Check this call's own
     exit code explicitly and fail loudly on error (FR-017) — stricter
     than several existing stall sites' bare `gh issue comment` calls,
     since this is new code with no legacy call site to match.
  5. `paused`/`stop-cause` outputs (T009) are unaffected by whether step 1
     short-circuited (FR-008: writing the record must never read back as
     "the stop is satisfied").
- [X] T011 Wire the six call sites in `.github/workflows/board-loop.yml` —
  triage (`id: killswitch-recheck` at `board-loop.yml:1336`), route
  (`:1750`), fix (`:2277`), review (`:3223`), readiness (`:3705`), prove
  (`:4261`) — to pass `marker-branch: ${{ needs.select.outputs.branch }}`
  and `marker-base-sha: ${{ needs.select.outputs.base-sha }}` to the
  `wing-commander-board-stop-check` composite invocation (research.md D4;
  the exact pair the fix job's own `EXISTING_BRANCH`/`EXISTING_BASE_SHA`
  already reuses verbatim at `board-loop.yml:2060-2061`). Triage and route
  naturally pass through empty strings today (no branch exists pre-fix) —
  no special-casing needed.
- [X] T012 Add Gate 128 structural check 1 to `.github/scripts/
  verify-stop-point-recording.py`: parses `.github/actions/
  wing-commander-board-stop-check/action.yml` as text/YAML (no execution)
  and fails when there is no step, gated on `stop-cause == "stop-request"`,
  that invokes `board_item_marker.py --step stalled ... --add-label
  "board:stalled"` (contracts/gate-128-stop-point-recording.md check 1).
- [X] T013 [P] Add Gate 128 structural check 2 to `.github/scripts/
  verify-stop-point-recording.py`: fails when the `board_stop_check.py`
  invocation or the new `board_item_marker.py` invocation in `action.yml`
  references a bare `.github/scripts/...` path instead of
  `$RUNNER_TEMP/wc-pristine/scripts/...` (contracts/gate-128... check 2;
  spec 095 FR-011/FR-012, research.md D8).
- [X] T014 Add `--self-test` coverage for checks 1 and 2 to `.github/
  scripts/verify-stop-point-recording.py`: mutation 1 deletes the
  record-write step's `if:` condition or its body and asserts check 1 then
  fails; mutation 2 rewrites the invocation to a bare `.github/scripts/...`
  path and asserts check 2 then fails (contracts/gate-128... Self-test
  items 1–2; Principle VIII/SC-009 — the gate must be shown to fail its own
  subject).
- [X] T015 Register Gate 128 in `.github/workflows/lint-workflows.yml`,
  immediately after the existing Gate 127 block (ends at
  `lint-workflows.yml:4653`), following the exact two-step pattern every
  other gate uses:
  ```yaml
  - name: "Gate 128 — an honoured stop records its stop point, and the kill switch keeps writing nothing"
    if: "!cancelled()"
    run: python3 .github/scripts/verify-stop-point-recording.py
  - name: "Gate 128 self-test — ..."
    if: "!cancelled()"
    run: python3 .github/scripts/verify-stop-point-recording.py --self-test
  ```

**Checkpoint**: The composite now computes `stop-cause`, writes the label+
marker+comment record exactly once per honoured stop, leaves kill-switch-
only and closed-issue stand-downs untouched, and Gate 128 proves the write
itself exists and runs from the trusted snapshot. User story work can now
begin.

---

## Phase 3: User Story 1 - One stop halts one item, and the board keeps moving (Priority: P1) 🎯 MVP

**Goal**: An honoured stop takes the item out of the candidate set so the
board's throughput is unaffected, while a kill-switch-only stand-down
writes nothing.

**Independent Test**: With a stop command on the in-flight item, drive two
consecutive runs. The first stands down and records; the second selects a
*different* eligible item (or reports an empty board) and never re-enters a
job for the stopped item.

- [X] T016 [P] [US1] Add Gate 128 eligibility-level check 5 to `.github/
  scripts/verify-stop-point-recording.py`: constructs the data-model.md
  fixture — an issue with `"labels": [{"name": "board:stalled"}]` plus a
  companion bot comment carrying the marker
  `{"step": "stalled", "round": 0, "pr": null, "branch": null, "base_sha":
  null}` — and imports `board_eligibility` directly (no Actions runtime) to
  assert `is_excluded()` returns `(True, "board:stalled")` and neither
  `in_flight_candidate()` nor `select()` ever returns that issue, across
  ten simulated successive selection passes (contracts/gate-128... check 5;
  SC-001: "selected by zero of the next ten runs").
- [X] T017 [P] [US1] Add Gate 128 check 6 to `.github/scripts/
  verify-stop-point-recording.py`: fails when a fixture composite
  invocation with `stop-cause` resolving to `"kill-switch"` or
  `"closed-issue"` still reaches the record-write block added in T010
  (contracts/gate-128... check 6; FR-011/FR-013).
- [X] T018 [US1] Add `--self-test` coverage for checks 5 and 6 to `.github/
  scripts/verify-stop-point-recording.py`: mutation 5 feeds a marker
  fixture with the `board:stalled` label omitted and asserts check 5's
  exclusion assertion no longer holds (proving the check actually reads the
  label, not vacuously passing); mutation 6 forces `stop-cause` to
  `"kill-switch"` in a fixture that also satisfies the record-write
  block's own gating condition (a deliberately broken `if:` that ignores
  `stop-cause`) and asserts check 6 then fails (contracts/gate-128...
  Self-test items 5–6).
- [X] T019 [US1] Run `quickstart.md` Scenario A (one stop halts one item,
  board keeps moving) and Scenario E (kill-switch-only writes nothing)
  structurally against the fixtures added in T016/T017 — confirm SC-001,
  SC-003 and SC-005 hold without requiring a live Actions run.

**Checkpoint**: At this point, User Story 1 is independently verified: one
honoured stop excludes exactly one item, the board's other eligible items
are unaffected, and a kill-switch-only stand-down writes nothing durable.

---

## Phase 4: User Story 2 - The stop point is legible on the issue (Priority: P2)

**Goal**: A maintainer reading only the issue — no run logs — can state why
the loop stopped, which comment it acted on, and how to resume it, and an
auditor can distinguish stop-request stand-downs from kill-switch
stand-downs from the metrics records alone.

**Independent Test**: Post a stop, drive one run, then read the issue with
no access to the run logs. The reason, the stopping point and the release
instruction are all determinable from the issue alone.

- [X] T020 [P] [US2] Add Gate 128 cause-aware-messaging check 3 to
  `.github/scripts/verify-stop-point-recording.py`: fails when any of the
  six stand-down message strings in `.github/workflows/board-loop.yml`
  hardcodes "kill switch" prose unconditionally — the pre-fix shape at,
  e.g., `board-loop.yml:1412` (contracts/gate-128... check 3; FR-014).
- [X] T021 [US2] Reword the six stand-down messages in `.github/workflows/
  board-loop.yml` to read `steps.killswitch-recheck.outputs.stop-cause`
  and name the actual observed cause — "a maintainer stop request" / "the
  kill switch" / "the issue being closed" — rather than hardcoding "kill
  switch" for all of them (research.md D12): triage (`:1412`, currently
  "kill switch set immediately before triage's durable action -- standing
  down without acting."), route's spec-request stand-down path, fix,
  review, readiness (`:3716`/`:3720`, currently "kill switch or stop
  request found immediately before readiness's durable actions... (#604)"
  — generalize to name the specific cause rather than "kill switch or stop
  request"), and prove (`:4523-4524`, currently `label="stood down"` with
  no cause named).
- [X] T022 [US2] Add `--self-test` coverage for check 3 to `.github/
  scripts/verify-stop-point-recording.py`: restores one hardcoded "kill
  switch" string and asserts check 3 then fails (contracts/gate-128...
  Self-test item 3).
- [X] T023 [US2] Add one additional step, `if: always()`, named `Record run
  outcome (<job>)`, to the end of each of the six resume-stage jobs in
  `.github/workflows/board-loop.yml` (triage, route, fix, review,
  readiness, prove), modeled on the `select` job's existing accounting-only
  invocation (`board-loop.yml:901-911`):
  ```yaml
  - name: Record run outcome (<job>)
    if: always()
    continue-on-error: true
    uses: ./.wc-pristine-repo/.github/actions/wing-commander-metrics-summary
    with:
      transcript-path: ${{ runner.temp }}/wing-commander-no-transcript.json
      model: ''
      stage: board-loop
      run-label: <computed per priority order below>
      record-path: ${{ runner.temp }}/wing-commander-metrics-record-<job>-outcome.json
  ```
  `run-label` priority order (contracts/metrics-classification.md):
  `stop-cause == "stop-request"` → `"<job>: stopped (stop-request)"`;
  `stop-cause == "kill-switch"` → `"<job>: stood down (kill-switch)"`;
  `stop-cause == "closed-issue"` → `"<job>: stood down (issue closed)"`
  (prove only); otherwise `"<job>: " + ` the job's own existing outcome
  label (e.g. triage's `$outcome`, readiness's ready/not-ready, route's
  route verdict). Use the `run_label` field precisely — never the
  `outcome` enum (`healthy|exhausted|rate-limited|failed|unclassifiable|
  unavailable`), which is left exactly as each job's own earlier per-agent
  metrics call already sets it.
- [X] T024 [P] [US2] Upload each new "Record run outcome" record via
  `actions/upload-artifact` with `retention-days: 90`, for all six jobs,
  following the `select` job's existing artifact-upload precedent exactly
  (contracts/metrics-classification.md "Mechanism").
- [X] T025 [US2] Verify, against the template implemented in T010, that
  `contracts/stop-point-record.md`'s inert-reason guarantee holds for a
  reason containing `` `@everyone` fixes #1 <script>alert(1)</script> ``:
  confirm it renders inside the fence as inert text — no mention fires, no
  `#1` cross-reference resolves, no `<script>` executes — matching
  `quickstart.md` Scenario B's verification step, and that SC-004 ("under
  one minute") is satisfiable from the rendered template alone.

**Checkpoint**: At this point, User Stories 1 AND 2 both work
independently: the board keeps moving past a stopped item, and every stop
is legible on the issue and countable from the metrics records alone.

---

## Phase 5: User Story 3 - A maintainer releases a stopped item and it continues (Priority: P2)

**Goal**: Removing `board:stalled` lets the item resume without the old
stop command re-triggering and without opening a second branch or PR.

**Independent Test**: Record a stop, remove `board:stalled`, drive one run:
the item is selected, proceeds past its stop check, and the issue gains no
second stop-point record.

- [X] T026 [P] [US3] Add an FR-009 fixture to `.github/scripts/tests/
  board-stop-check/` and to Gate 128's decision-function-agreement check
  (research.md D2's invariant: `find_stop_command_comment(...) is not None
  == find_stop_request(...).stand_down`, checked over Gate 87's existing
  corpus plus new fixtures) — a comments list where the recorded
  stop-point comment's own `**Run:**` line is now the newest bot-authored
  run announcement, placed strictly after the original stop comment;
  assert both functions agree that the original stop comment no longer
  stands the item down (FR-009: "the stop request that was already
  recorded MUST NOT stand the item down again"), per research.md D10's
  observation that this falls out of the unmodified baseline computation
  with no new logic.
- [X] T027 [US3] Add `--self-test` coverage for Gate 128 check 4's FR-009
  fixture to `.github/scripts/verify-stop-point-recording.py`: a
  hand-crafted fixture where a comment matches `is_stop_command()` but
  predates a synthetic baseline in one function's copy of the logic and
  not the other, asserting check 4 then fails (contracts/gate-128...
  Self-test item 4 — "the mutation Gate 87 cannot catch, since Gate 87
  only proves `find_stop_request()` alone").
- [X] T028 [US3] Run `quickstart.md` Scenario C (release and resume)
  structurally against the fixtures in T026: confirm no second
  stop-point record is produced from the original stop comment (FR-009)
  and that spec 100's `board:owned` fallback (unchanged by this feature)
  remains the only mechanism re-finding an open loop-owned PR, so no
  second branch or PR results (FR-054).

**Checkpoint**: Releasing a stopped item is confirmed safe: the old stop
comment cannot re-trigger, and no duplicate branch or PR is created.

---

## Phase 6: User Story 4 - An ancient stop does not silently own an untouched issue (Priority: P3)

**Goal**: A stop command posted before the loop ever announced a run on an
issue is honoured exactly once, not as an unbounded, unexplained series of
stand-downs.

**Independent Test**: On an issue with an old authorized stop command and
no loop `**Run:**` announcement at all, drive one run and confirm the item
stood down once, the stop point was recorded, and the board moved on.

- [X] T029 [P] [US4] Add an FR-016 fixture to `.github/scripts/tests/
  board-stop-check/` and to Gate 128's decision-function-agreement check —
  a comments list with **no** bot-authored `**Run:**` comment at all (empty
  baseline, `baseline = ""`) and one old, authorized, stop-command comment
  — asserting both `find_stop_request()` and `find_stop_command_comment()`
  agree the item stands down on the very first stop check that reaches it
  (FR-016: "honoured exactly once"), and that a second fixture representing
  the *next* run — where the stop-point record's own `**Run:**` comment is
  now the newest baseline — asserts neither function stands the item down
  again from that same old comment.
- [X] T030 [US4] Run `quickstart.md` Scenario D (ancient stop, empty
  baseline) structurally against the fixture in T029: confirm SC-007 ("an
  issue with a pre-loop stop command and no loop announcement produces
  exactly one stand-down, with a record, never an unbounded series of
  silent ones").

**Checkpoint**: All four user stories are independently functional: the
board survives one stop, the stop is legible and auditable, release works
cleanly, and a pre-loop stop command cannot wedge an issue forever.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Whole-suite verification and the post-merge proof CLAUDE.md's
board rules require for Actions-only behaviour.

- [X] T031 [P] Run `python .github/scripts/run-local-gates.py` locally
  (CLAUDE.md "Before pushing"). Confirm Gate 128 and its `--self-test` both
  pass, and that Gate 87 still passes completely unchanged (`research.md`
  D1 — `find_stop_request()` was never modified).
- [X] T032 [P] Run `quickstart.md` Scenario F (kill switch and stop request
  together) structurally: confirm the stop point IS still recorded
  (FR-012) and the item's only release mechanism afterward is removing
  `board:stalled`, independent of the kill switch's own state.
- [ ] T033 After this feature's PR merges, re-drive one
  `board-loop.yml` run (`gh workflow run board-loop.yml` or the appropriate
  directed-dispatch input) reproducing `quickstart.md` Scenario A
  end-to-end, and record that evidence on the PR or on lifecycle issue
  #724 — the minimum post-merge proof CLAUDE.md's board rules and this
  feature's own Assumptions section ("Actions-only behaviour") require for
  a fix to behaviour that only runs in Actions.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001/T002 can start immediately
  and run in parallel with each other and with Phase 2.
- **Foundational (Phase 2)**: No dependency on Setup's content, but
  T003→T004→T006→T007 are a strict same-file sequence in
  `board_stop_check.py`/`action.yml`; T008→T009→T010→T011 likewise in
  `action.yml`/`board-loop.yml`; T012→T013→T014→T015 add and wire the gate
  around the now-complete mechanism. **BLOCKS all user stories.**
- **User Stories (Phase 3–6)**: All depend on Foundational completion
  (T003–T015). They may then proceed in parallel by story, though T016/
  T017/T020/T026/T029 all edit the same `verify-stop-point-recording.py`
  file and so cannot literally run concurrently against that one file
  despite being logically independent per story.
- **Polish (Phase 7)**: Depends on every user story phase whose scenario it
  re-runs (T031 depends on all gate tasks; T032 depends on T010; T033
  depends on the PR having merged).

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Foundational. No dependency on
  US2/US3/US4.
- **User Story 2 (P2)**: Depends only on Foundational (reuses T010's
  comment template and T009's `stop-cause` output; does not depend on
  US1's gate checks).
- **User Story 3 (P2)**: Depends only on Foundational (reuses T003/T006's
  pure functions and fixture corpus; does not depend on US1/US2).
- **User Story 4 (P3)**: Depends only on Foundational, and shares its
  fixture file/gate check with US3 (both extend Gate 128 check 4) —
  sequence T026 before T029 if both are assigned to the same session, to
  avoid two uncoordinated edits to the same check.

### Within Each User Story

- Gate-check tasks before their own `--self-test` coverage task.
- Message/metrics wiring (US2's T021/T023) is independent of the gate-check
  tasks in the same phase (T020/T022) — different files.

---

## Parallel Example: Foundational Phase

```bash
# T001 and T002 (Setup) can run together — different files, no dependencies:
Task: "Extend specs/085-.../contracts/composite-invocation.md with the widened-surface note"
Task: "Scaffold .github/scripts/verify-stop-point-recording.py's module header"

# T005 can run alongside T003/T004 — action.yml vs board_stop_check.py:
Task: "Add html_url to the composite's comments --jq projection in action.yml"
```

## Parallel Example: User Story 1

```bash
# T016 and T017 both edit verify-stop-point-recording.py but check
# logically independent properties (selection exclusion vs no-write-on-
# kill-switch) -- sequence them if working solo, or split by check number
# if two sessions coordinate on non-overlapping line ranges.
Task: "Gate 128 check 5 -- fixture excluded by is_excluded()/in_flight_candidate()/select() across ten passes"
Task: "Gate 128 check 6 -- kill-switch/closed-issue fixture never reaches the record-write block"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002).
2. Complete Phase 2: Foundational (T003–T015) — **this is the actual fix**:
   without it, nothing records anything and the #402 wedge persists.
3. Complete Phase 3: User Story 1 (T016–T019) — proves the wedge is closed
   and the board keeps moving.
4. **STOP and VALIDATE**: run `python .github/scripts/run-local-gates.py`;
   confirm Gate 128 passes and Gate 87 is unaffected. This alone already
   satisfies spec.md's own stated priority ("This is the defect... Without
   it, one stop costs the whole board every subsequent run").

### Incremental Delivery

1. Setup + Foundational → the recording mechanism exists and is gate-proven
   at the structural level (record exists, runs from the trusted snapshot).
2. Add User Story 1 → SC-001/SC-003/SC-005 proven from the real selection
   code → this is the MVP that closes the #402 wedge.
3. Add User Story 2 → the record becomes legible and auditable (SC-004,
   SC-008) — a maintainer can read the issue alone and trust the metrics.
4. Add User Story 3 → release-and-resume is proven safe (no re-trigger, no
   duplicate branch/PR).
5. Add User Story 4 → the pre-loop/empty-baseline edge case is closed
   (SC-007) — the lowest-incidence but real freeze the #539 fix's review
   found.
6. Polish → full local gate suite, the kill-switch-plus-stop-request
   combination (FR-012), and the mandatory post-merge Actions proof.

### Parallel Team Strategy

With two sessions available (CLAUDE.md's board rules cap concurrent local
agents at two): one completes Setup + Foundational alone (it is one
tightly-sequenced file chain); once that lands, a second session can start
User Story 2's message/metrics wiring (T021/T023/T024 — `board-loop.yml`,
independent of the gate script) while the first continues the Gate 128
checks for US1/US3/US4 (all in `verify-stop-point-recording.py`, so best
kept to one session to avoid edit collisions).

---

## Phase 8: Convergence

- [X] T034 Add a "Snapshot helper scripts (before any agent runs)" step
  (identical to the one `.github/workflows/board-loop.yml`'s fix/review/
  readiness jobs already carry — the same `git archive … | tar -x` of
  `.github/scripts`/`.github/schemas` from `$GITHUB_SHA` into
  `$RUNNER_TEMP/wc-pristine`, write-protected afterward) to the triage,
  route, and prove jobs, placed after each job's own `Checkout` step and
  before its `wing-commander-board-stop-check` call site. T007/research.md
  D8 made the composite's `board_stop_check.py` invocation run
  unconditionally from `$RUNNER_TEMP/wc-pristine/scripts/…` for every
  caller (confirmed present and required by Gate 128 check 2), but only
  fix, review, and readiness populate that directory — triage, route, and
  prove do not (verified: `grep -n "Snapshot helper scripts"
  .github/workflows/board-loop.yml` finds exactly three occurrences). Every
  run of those three jobs will fail at the composite's `check` step with
  "No such file or directory" once this lands, regardless of whether a
  stop is pending, since that invocation runs on every call. All 201 local
  gates pass without catching this because none of them execute
  board-loop.yml itself — Gate 128 checks the composite's own text
  structurally, and Gate 87's harness synthesizes the pristine directory
  itself rather than reading it from a real job. (missing; research.md D8,
  FR-018)

## Maintainer Feedback

- [ ] Have `wing-commander-board-stop-check`'s composite resolve `board_stop_check.py`, `board_item_marker.py` and the `board_spec_request_body` import relative to itself (e.g. `$GITHUB_ACTION_PATH/../../scripts/...`) instead of depending on a caller-populated `./.wc-pristine-repo` — every caller already checks that out per spec 086 FR-003, so this adds no trust surface.
- [ ] Drop the three T034 "Snapshot helper scripts" steps added to the triage, route and prove jobs, now unneeded.
- [ ] Extend `board_prove.py`'s `SCRIPT_PATH_RE` and Gate 128 check 2 to accept the `$GITHUB_ACTION_PATH`-relative resolution form.
- [ ] Add a Gate 128 check asserting the composite never depends on a caller-populated `wc-pristine` directory (today, deleting the three T034 steps keeps the gate at 0 failures).

## Maintainer Feedback

- [ ] **Blocking (FR-008/FR-006):** In `board_stop_check.py`, treat a stop-point record comment posted by `current_run_id` as still standing the item down, so the record's own `**Run:**` line does not move `find_stop_request()`'s baseline past the honoured stop within the same run. Keep FR-009/FR-016 intact (a later run's different run id is unaffected).
- [ ] Add a fixture: a stop followed by this run's own stop-point record comment, same run id, asserting `stand_down=true`; add the corresponding Gate 128 check.
- [ ] (Nice-to-have per reviewer) Gate triage's and review's continuation outputs on the stand-down too; leave route's to #901.
