---

description: "Task list for Bounded, Idempotent spec-request Filing"
---

# Tasks: Bounded, Idempotent spec-request Filing

**Input**: Design documents from `specs/092-bounded-spec-request-filing/`

**Prerequisites**: plan.md, spec.md (required), research.md, data-model.md, contracts/, quickstart.md

**Tests**: research.md D1/D6 and D8, and quickstart.md, call for fixture-driven unit
tests on the new module's pure functions and for Gate 93's new check; they are
included below (not merely optional).

**Organization**: Tasks are grouped by user story (spec.md), in priority order
(US1 P1, US2 P1, US3 P2), inside the repository's existing
`.github/scripts/board_*.py` + `.github/workflows/board-loop.yml` layout
(plan.md "Project Structure"). Line numbers below are anchors into
`.github/workflows/board-loop.yml` and `.github/scripts/*.py` as they read on
`main` at plan time (research.md's "Current-state baseline"); an
implementer should re-locate the named step/function by name if the file has
drifted rather than trust the number blindly.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Phase 1: Setup

- [X] T001 Create `.github/scripts/board_spec_request_filing.py` with its module
  docstring (owning module for research.md D1/D6,
  `contracts/spec-request-existence-check.md`,
  `contracts/spec-request-attempt-bound.md`) and an `argparse`-based `main()`
  exposing two subcommands, `lookup` and `record-attempt` (bodies filled in by
  later tasks), following `board_item_marker.py`'s own `main()`/CLI shape
  (joining `board_item_marker.py`, `board_eligibility.py`,
  `board_spec_request_body.py` as the board loop's family of shared,
  unit-tested modules — FR-018).

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared plumbing both User Story 1 and User Story 2 read or write —
the attempt-budget constant and the marker field it lives in.

**⚠️ CRITICAL**: Both P1 stories touch the marker's new field; extend it once
here rather than duplicating the threading per story.

- [ ] T002 Add `BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET: 3` to
  `.github/workflows/board-loop.yml`'s top-level `env:` block (line 93, beside
  `BOARD_LOOP_ROUND_BUDGET: 5`) — a new, separate `BOARD_LOOP_*` constant,
  never merged with or derived from the round budget (FR-010).
- [ ] T003 Extend `.github/scripts/board_item_marker.py`'s `write_marker()`
  (line 139) to accept a sixth field, `spec_request_attempts` (int, default
  `0`), add it to the JSON payload dict (lines 152-155) alongside `step`/
  `round`/`pr`/`branch`/`base_sha`, and add a `--spec-request-attempts N`
  CLI flag (`type=int, default=0`) to `main()`'s `argparse.ArgumentParser`
  (lines 236-245), passed through to `write_marker()` at line 254 (FR-009,
  data-model.md "Board Item Marker").
- [ ] T004 Thread `spec_request_attempts` through the `select` job's `resume`
  step in `.github/workflows/board-loop.yml` (lines ~589-871) exactly as
  `round` is threaded: read `marker_json | jq -r '.spec_request_attempts //
  0'` alongside `marker_round` (line 606); pass it into the step-resolution
  Python heredoc via env (alongside `MARKER_ROUND` at line 691) and read it
  there (alongside `round_` at line 709); include it unchanged in every
  branch's output dict (lines 830-840) — critically, do **NOT** reset it to
  `0` in any of the "stale marker" branches that reset `round_`/`base_sha`
  (lines 776, 785, 809, 827): it tracks a budget orthogonal to any fix
  attempt's staleness (FR-009; data-model.md; research.md D4). Emit it to
  `$GITHUB_OUTPUT` alongside `round=` (line 869) as
  `spec-request-attempts=`, and add
  `spec-request-attempts: ${{ steps.resume.outputs.spec-request-attempts }}`
  to the `select` job's `outputs:` block (line 145, beside `round:`), so
  route/fix/readiness read it as `needs.select.outputs.spec-request-attempts`
  the same way they already read `needs.select.outputs.round`.
- [ ] T005 [P] Update
  `specs/057-autonomous-board-loop/contracts/board-item-marker.md`'s
  documented payload shape to list the new `spec_request_attempts` field
  (plan.md Project Structure note: this contract is updated in the same PR
  that changes `write_marker()`, not deferred).

**Checkpoint**: The marker can carry and round-trip an attempt count; no
filing site reads or writes it yet.

## Phase 3: User Story 1 - One routing decision never produces two spec-requests (Priority: P1) 🎯 MVP

**Goal**: Before any of the four `spec-request` filing call-site entries
(route's spec verdict, the fix job's post-push breach, readiness's ordinary
backstop-breach entry, and readiness's `step=breach`-retry entry) creates an
issue, it looks for one it (or an earlier, interrupted run) already filed for
the same originating issue, and reuses it instead of creating a second one.

**Independent Test**: Pre-seed an issue with a `spec-request` whose body
carries the `Originating issue: …/issues/N` footer and is authored by the
loop's own bot identity; drive the loop to a spec verdict for issue N;
confirm no new issue is created and the existing one is cross-linked,
commented and labelled instead (quickstart.md Section 2). This story alone
removes duplicate filings even while retries stay unbounded.

### Implementation for User Story 1

- [ ] T006 [US1] Implement `find_existing(issues_json, bot_login, footer)` in
  `.github/scripts/board_spec_request_filing.py`: returns the `html_url` of
  the issue with the earliest `created_at` among `issues_json` entries whose
  `user.type == "Bot"` and `user.login == bot_login`, and whose `body`
  contains `footer` as a whole line (CR-normalized, matching the existing
  `#530` jq predicate's `rtrimstr("\r")` handling), or `None` when none
  match — never a PR reference, never title text (FR-002, FR-003, FR-004;
  contracts/spec-request-existence-check.md; research.md D2).
- [ ] T007 [US1] Implement `reopened_since(events_json, created_at)` in
  `.github/scripts/board_spec_request_filing.py`: returns the `created_at`
  of the last item in `events_json` whose `event == "reopened"`, or
  `created_at` (the issue's own) when no such item exists (FR-003;
  research.md D3).
- [ ] T008 [US1] Implement the `lookup --issue ISSUE_NUMBER --bot-login LOGIN`
  subcommand in `.github/scripts/board_spec_request_filing.py`'s `main()`:
  fetch `repos/OWNER/REPO/issues/ISSUE_NUMBER/events` via `gh api`, compute
  `since` with `reopened_since()`; fetch `repos/OWNER/REPO/issues -f
  state=all -f since=SINCE -f creator=BOT_LOGIN --paginate`, filtered to
  `pull_request == null`; build `footer = "Originating issue:
  {server}/{repo}/issues/{issue}"`; call `find_existing()`; print
  `existing-spec-url=<url-or-empty>` to `$GITHUB_OUTPUT`. Any `gh api`
  failure at either fetch exits 1 with nothing written to
  `existing-spec-url` — never falls back to "no match found"
  (contracts/spec-request-existence-check.md "Behavior"/"Failure"; FR-007).
- [ ] T009 [P] [US1] Fixture tests for `find_existing()` under
  `.github/scripts/tests/board-spec-request-filing/` (following
  `.github/scripts/tests/board-eligibility/`'s checked-in-JSON pattern): an
  open match, a closed match (FR-003), the oldest of two matches wins
  (FR-004), an otherwise-matching body authored by a non-bot account is
  ignored (Edge Case: "a maintainer filed the spec-request by hand"), and a
  body containing the footer text only as a substring (not as a whole line)
  is ignored.
- [ ] T010 [P] [US1] Fixture tests for `reopened_since()` under
  `.github/scripts/tests/board-spec-request-filing/`: never-reopened (falls
  back to the issue's own `created_at`), reopened once, and reopened more
  than once (the *last* reopening's timestamp wins).
- [ ] T011 [US1] Wire route's spec-verdict site in
  `.github/workflows/board-loop.yml`: add a "Look for a spec-request already
  filed for this issue" step calling `board_spec_request_filing.py lookup
  --issue $ISSUE_NUMBER --bot-login ...` immediately before the "Create the
  spec-request artifact on a spec verdict" step (line 1815), as its own step
  (Gate 93 forbids `gh api`/`gh issue view` inside the create step itself —
  `GH_API_RE`/`GH_ISSUE_VIEW_RE`, lines 967-974). Skip the `gh issue create`
  call (line 1890) when the lookup step's `existing-spec-url` output is
  non-empty, and set `steps.spec_request.outputs.spec-url` to that URL in
  its place, so the existing downstream cross-link step (lines 1914-1915,
  gated on `steps.spec_request.outputs.spec-url != ''`) is unaware of which
  path produced it (FR-001, FR-005; research.md D10;
  contracts/spec-request-existence-check.md "Consumers").
- [ ] T012 [US1] Update route's closing comment (line 1908) and its
  `reason`/`$GITHUB_STEP_SUMMARY` record to state explicitly whether the
  artifact was **reused** or **filed**, naming the artifact either way
  (FR-006) — follow readiness's own existing "reusing spec-request
  $spec_url, already filed for PR #$PR_NUMBER" step-summary phrasing (line
  3892) as the model for the wording. Never name a downstream consumer of
  this repository in the new text (FR-022).
- [ ] T013 [US1] Wire the fix job's post-push-breach site the same way as
  T011/T012: add the lookup step before "On a post-push breach, leave the
  branch/PR open and spin off a spec-request" (line 2425), skip `gh issue
  create` (line 2455) on a non-empty `existing-spec-url`, set
  `steps.post-push-breach.outputs.spec-url` to the reused URL, and state
  reused-vs-filed in the closing comment (line 2469).
- [ ] T014 [US1] Wire readiness's *ordinary* backstop-breach entry
  (`report-unmet`, line 3862 — the entry spec 100 FR-016 defers to this
  feature and which has **no** existence check today) the same way: add the
  lookup step before the `gh issue create` inside "Report the unmet
  condition (not ready)" (line 3903), skip the create on a non-empty
  `existing-spec-url`, and state reused-vs-filed in the closing comment
  (lines 3915-3917).
- [ ] T015 [US1] Replace readiness's `step=breach`-retry entry's inline
  lookup ("Look for a spec-request already filed for this breach", `id:
  breach-retry-lookup`, lines 3831-3860, its `BREACH_SPEC_REQUEST_JQ` env
  var at lines 3839-3843) with a call to the same shared
  `board_spec_request_filing.py lookup` step T011 introduced — dropping the
  PR-reference filter and the PR-`createdAt`-scoped `since` in favor of the
  issue-reopen-scoped `since` from T008, per research.md D2/D3 (a **strict
  widening**: every match the old PR-scoped lookup found is still found).
  Keep the step id `breach-retry-lookup` and the output name
  `existing-spec-url` that `report-unmet` (line 3871) already consumes, so
  no downstream step needs to change.
- [ ] T016 [US1] Run Gate 93's existing self-test
  (`python3 .github/scripts/verify-issue-context-single-home.py
  --self-test`) and confirm check 3's create-guard fixtures still pass
  unmodified now that a lookup step precedes each create step — the new
  step must not itself be mistaken for the guarded create step by
  `_is_spec_request_create()`/`_create_guard_problems()` (lines 1017, 1049).

**Checkpoint**: User Story 1 is independently functional — no duplicate
`spec-request` is ever created for one originating issue, even though
retries are still unbounded.

## Phase 4: User Story 2 - A filing that cannot succeed stops consuming the board (Priority: P1)

**Goal**: Each of the four filing-site entries counts its own consecutive
failed attempts (a failed lookup or a failed create both count) in the board
item marker, and on the third such failure stalls the item with an explicit
give-up comment instead of failing loudly forever.

**Independent Test**: Make the create fail deterministically (e.g. remove the
`spec-request` label) against a board holding the target issue and one other
eligible issue; drive three runs; confirm the target is attempted at most
three times, is then stalled with a give-up comment, and the other issue is
worked on the next run (quickstart.md Section 3).

### Implementation for User Story 2

- [ ] T017 [US2] Implement `record_attempt(attempts_before, budget)` in
  `.github/scripts/board_spec_request_filing.py`: returns `{"attempts":
  attempts_before + 1, "stall": attempts_before + 1 >= budget}` — a pure
  function, no I/O (FR-018; research.md D6;
  contracts/spec-request-attempt-bound.md).
- [ ] T018 [US2] Implement the `record-attempt --attempts N --budget B`
  subcommand in `.github/scripts/board_spec_request_filing.py`'s `main()`:
  calls `record_attempt()` and prints the result as one JSON object to
  stdout, for the calling step's shell to branch on with `jq`.
- [ ] T019 [P] [US2] Fixture/unit tests for `record_attempt()` under
  `.github/scripts/tests/board-spec-request-filing/`: below-cap
  (`attempts_before + 1 < budget` → `stall: false`), exactly-at-cap
  (`attempts_before + 1 == budget` → `stall: true`), and past-cap
  (`attempts_before >= budget` → still `stall: true`).
- [ ] T020 [P] [US2] Add `truncate_title(title, limit=256)` to
  `.github/scripts/board_spec_request_body.py` (its existing single home for
  spec-request shaping), deterministically shortening a title longer than
  `limit` before it reaches `gh issue create --title` (FR-016).
- [ ] T021 [P] [US2] Unit tests for `truncate_title()`: a title under the
  limit is returned unchanged, a title exactly at the limit is unchanged,
  and a title over the limit is cut to exactly `limit` characters.
- [ ] T022 [US2] Pipe the drafted/issue title through `truncate_title()` at
  all three `gh issue create ... --title` call sites before T011/T013/T014
  file: route's `$spec_title` (computed line 1839, used at the `--title`
  argument on line 1890), the fix job's post-push-breach `$issue_title`
  (computed line 2448, used at line 2456), and readiness's ordinary entry
  `$issue_title` (computed line 3894, used at line 3903) (FR-016).
- [ ] T023 [US2] Extend route's failed-create branch (the URL guard at line
  1902) in `.github/workflows/board-loop.yml`: on a failed create, **and**
  on a failed T011 lookup, call `board_spec_request_filing.py record-attempt
  --attempts "$SPEC_REQUEST_ATTEMPTS" --budget
  "$BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET"`, where
  `$SPEC_REQUEST_ATTEMPTS` comes from `needs.select.outputs.spec-request-attempts`
  (T004) and the budget from `env.BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET`
  (T002). When `stall` is `false`: persist the new count via a marker-only
  comment (`board_item_marker.py --step route --spec-request-attempts N`,
  with `round`/`pr`/`branch`/`base_sha` at their existing pre-fix defaults)
  carrying only the `**Run:**` line and the marker HTML comment — no
  narrative, no label, no spec-request URL — then still `exit 1` (unchanged
  #514 guard shape). When `stall` is `true`: add `board:stalled` first
  (`add_stalled_label()`, unchanged #782/#604 ordering), post the FR-012
  give-up comment (states explicitly that no `spec-request` was filed, the
  last observed failure, the number of attempts spent, and that removing
  `board:stalled` re-admits the item — never naming a downstream consumer,
  FR-022), write a `stalled`-step marker with `spec_request_attempts` reset
  to `0`, and `exit 0` (research.md D7;
  contracts/spec-request-attempt-bound.md "Branch behavior at each site").
- [ ] T024 [US2] Apply the identical failed-lookup/failed-create branch logic
  from T023 to the fix job's post-push-breach site (URL guard at line 2460).
- [ ] T025 [US2] Apply the identical failed-lookup/failed-create branch logic
  from T023 to readiness's ordinary backstop-breach entry (URL guard at line
  3907).
- [ ] T026 [US2] On every **successful** filing (fresh create or reuse) at
  all four site entries — including T015's `step=breach`-retry entry, which
  files no create of its own but still resolves a filing outcome — write
  `spec_request_attempts=0` into whatever marker/comment that site already
  posts (the T011-T015 stalled/cross-link marker calls), rather than a
  separate write (FR-015; research.md D5).
- [ ] T027 [US2] Extend
  `.github/scripts/verify-issue-context-single-home.py`'s
  `_create_guard_problems()` (line 1049) to recognize the T023-T025 give-up
  shape — a failed-create branch that calls `record-attempt`, and only on
  `stall: true` labels, comments and exits `0` — as sanctioned, while
  continuing to flag a failed create that labels/comments/publishes *below*
  the cap, or with no `record-attempt` call at all, as the original #514
  defect (FR-020; research.md D7, the paragraph following D7's decision).
- [ ] T028 [US2] Run `python3 .github/scripts/verify-issue-context-single-home.py
  --self-test` and update any of check 3's existing fixtures (`_site_fixture`,
  `_GOOD_SITE_RUN`, `_create_guard_cases`, lines ~1360-1492) that no longer
  match the new give-up shape after T027, without weakening what they catch
  below the cap.

**Checkpoint**: User Stories 1 AND 2 both work independently — filings are
deduplicated and retries are capped at three per item, at every site.

## Phase 5: User Story 3 - A maintainer can see, from the issue alone, what happened (Priority: P2)

**Goal**: The give-up comment (T023-T025) and the reused-artifact comment
(T012-T014) already carry everything a maintainer needs; this story verifies
that legibility end to end and confirms re-admission starts the budget fresh.

**Independent Test**: Drive an item to its cap; read only its comments and
labels and confirm the attempt count, the last failure and the recovery step
are all present; remove `board:stalled`; confirm the item is selected again
with a fresh count (quickstart.md Section 4).

### Implementation for User Story 3

- [ ] T029 [P] [US3] Add an assertion (a unit test, or a Gate 93 self-test
  fixture following `_self_test_spec_request_sites`'s pattern) that the
  give-up comment text built in T023-T025 contains all four FR-012
  elements: an explicit "no spec-request was filed" statement, the last
  observed failure text, the attempts-spent count, and the "remove
  board:stalled to re-admit" instruction.
- [ ] T030 [US3] Drive quickstart.md Section 4 ("Recoverability") end to end
  against a disposable test issue: restore the failure's cause, remove
  `board:stalled`, confirm the next run selects the item,
  `spec_request_attempts` starts at `0` (a subsequent failure reads
  "attempt 1", not "attempt 4"), and a subsequent successful filing produces
  exactly one `spec-request` (SC-006).
- [ ] T031 [US3] Drive quickstart.md Section 2's reused-artifact scenario
  once more, reading only the issue's comments (no Actions log), and confirm
  the comment names the reused `spec-request`'s URL and states it was reused
  rather than filed (Acceptance Scenario 3, SC-004).

**Checkpoint**: All three user stories are independently functional and
legible from the issue alone.

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: The single-home gate (FR-019) needs both P1 stories' wiring to
exist before it can check them; cross-site parity and the full local gate
suite close out the feature.

- [ ] T032 Add `check_spec_request_filing_bound()` as Gate 93 check 6 in
  `.github/scripts/verify-issue-context-single-home.py`, called from
  `check_repo()` (line ~1324) alongside `check_spec_request_bodies()`. For
  each of the four call-site entries (route, fix post-push-breach, readiness
  ordinary, readiness `step=breach` retry) it verifies: (a) a
  `board_spec_request_filing.py lookup` step precedes the create step in the
  same job, gating the create on an empty `existing-spec-url`; (b) the
  failed-attempt branch calls `board_spec_request_filing.py
  record-attempt`, never a hand-rolled `$((N+1))` or literal `+ 1` on an
  attempts-shaped variable; (c) `.github/workflows/board-loop.yml`'s `env:`
  block defines exactly one `BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET`, read
  via `env.BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET` at every site, never a
  literal or a second `BOARD_LOOP_*` name; and (d) it enumerates
  spec-request-create sites the same way check 3 already does, so a fourth
  site added later that skips (a) or (b) fails this check without needing
  its own update (contracts/gate-spec-request-single-home.md; FR-019).
- [ ] T033 Add check 6's own regression fixtures as embedded
  `_self_test_*`/`_mutation_check_*` functions in
  `.github/scripts/verify-issue-context-single-home.py`, run from
  `run_self_test()` (line ~2719) — following check 3's own established
  in-file fixture pattern (`_site_fixture()`, `_self_test_spec_request_sites()`,
  lines ~1360-1611), **not** a separate checked-in-JSON directory (see the
  `wing-commander-findings` note on this file's own fixture convention).
  Cover: a compliant site, a site with no lookup step, a site with a
  hand-rolled increment, and a site reading a second `BOARD_LOOP_*` budget
  name — each failing for the stated reason (Constitution VIII).
- [ ] T034 Drive quickstart.md Section 5 ("Cross-site consistency"): repeat
  the User Story 1 and User Story 2 independent tests with the
  failure/duplicate condition triggered at the fix job's post-push breach
  and at readiness's ordinary backstop breach, confirming identical
  behavior at all four site entries (FR-017, SC-005).
- [ ] T035 Run `python .github/scripts/run-local-gates.py` (the full PR-time
  gate suite, CLAUDE.md "Before pushing") and confirm it passes, including
  the new/extended fixtures from T009, T010, T019, T021, T029 and T033.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; BLOCKS both User Story 1 and
  User Story 2 (both read/write the marker's new field, even though US1's
  own independent test does not require it to be populated correctly yet).
- **User Story 1 (Phase 3)**: depends on Foundational. Independently
  testable and shippable on its own (spec.md: "Shipping only this story
  removes duplicate filings even while retries remain unbounded").
- **User Story 2 (Phase 4)**: depends on Foundational; its failed-lookup
  counting (T023-T025) depends on User Story 1's lookup steps existing
  (T011, T013-T015) at each site, so in practice Phase 4 follows Phase 3.
- **User Story 3 (Phase 5)**: depends on both User Story 1 and User Story 2 —
  it verifies content and behavior neither story's own checkpoint asserts
  end-to-end.
- **Polish (Phase 6)**: depends on all three user stories.

### Within Each Phase

- All of `.github/scripts/board_spec_request_filing.py`'s own tasks (T001,
  T006-T008, T017-T018) touch the same new file and are sequential.
- All of `.github/workflows/board-loop.yml`'s per-site tasks (T011,
  T013-T015, T022-T025) touch the same file and are sequential; different
  sites can be split across two agents/reviewers but not run as literal
  parallel edits to one file.
- Fixture/test tasks (T009, T010, T019, T021, T029, T033) touch their own
  new files and can run in parallel with each other and with the
  workflow-editing tasks once the functions/wiring they exercise exist.

## Parallel Example: Foundational + User Story 1 test fixtures

```bash
# Once T006-T008 (find_existing/reopened_since/lookup) land:
Task: "Fixture tests for find_existing() under .github/scripts/tests/board-spec-request-filing/"
Task: "Fixture tests for reopened_since() under .github/scripts/tests/board-spec-request-filing/"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1) — this alone removes duplicate
   `spec-request` filings, spec.md's most damaging gap, even with retries
   still unbounded.
3. **STOP and VALIDATE**: run quickstart.md Section 2 against a disposable
   test issue.

### Incremental Delivery

1. Setup + Foundational → marker ready.
2. User Story 1 → validate → duplicate filings are gone.
3. User Story 2 → validate → board starvation from unbounded retries is
   gone.
4. User Story 3 → validate → the outcome is legible and recoverable from
   the issue alone.
5. Polish → the single-home gate holds the rule for every future filing
   site.
