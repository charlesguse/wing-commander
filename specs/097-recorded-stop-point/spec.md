# Feature Specification: An Honoured Stop Records Its Stop Point — One Stop Halts One Item, Not the Board

**Feature Branch**: `spec-draft/097-recorded-stop-point`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #724 — "board-loop: an honoured stop request
records no stop point, so the stopped item is re-selected and stood down
every run" (routed from board-loop.yml, issue #540; originating issue
#540, found while diagnosing the #402 wedge in
[run 36084496038](https://github.com/charlesguse/wing-commander/actions/runs/36084496038)),
plus the maintainer comment of 2026-09-25 folding in the empty-baseline
case surfaced by the code review of the #539 fix.

## Overview

Spec 057 FR-052 says a maintainer comment must be able to stop an
in-flight board item **and that "the stop point MUST be recorded"**. The
first half shipped; the second did not.

Today, when `wing-commander-board-stop-check` returns `paused=true`
because a maintainer posted a stop command (as opposed to the kill switch
being set), the calling job's durable-action step prints a line to
`$GITHUB_STEP_SUMMARY` and exits 0. Nothing durable is written: no board
item marker, no label, no comment on the issue. The item's state on
GitHub is byte-identical to what it was before the run.

That makes the stand-down self-repeating. The item's newest marker still
says `triage`/`route`/`fix`/`review`, so the next scheduled run's
selection pass sees exactly the same board it saw last time, picks the
same item (as the in-flight candidate, or as oldest-first), walks it to
the same job, re-reads the same stop comment, and stands down again — and
because the loop takes one item in flight repository-wide, every other
eligible issue on the board waits behind an item that can never move. One
genuine "stop" on one issue freezes the whole board, and keeps burning a
scheduled run's worth of API reads and agent turns doing it. This is the
shape of the #402 wedge.

The maintainer comment on the lifecycle issue adds the case that makes
this worse rather than merely wasteful. `find_stop_request()` honours a
stop only when it was posted after a baseline: the timestamp of the most
recent comment the loop's own App posted carrying a `**Run:** <url>`
line. When the loop has never touched an issue, there is no such comment
and the baseline is the empty string — so **every** maintainer comment in
the issue's history is "after the baseline", and a `stop.` posted months
before the loop existed halts every run that ever selects that issue,
forever, with no record of why.

This feature closes both by giving an honoured stop a durable
consequence: the loop records where it stopped, marks the item as needing
a human, and so drops out of the candidate set until a maintainer
releases it. The record is what releases the board, and it is also the
only evidence a maintainer has that the loop obeyed them.

The kill switch keeps writing nothing. It is a global pause of the whole
loop, deliberately leaving every item's state untouched so that clearing
the switch resumes the board exactly as it was; recording a per-item stop
point for it would stall every item the loop happened to be holding when
the switch went on.

### Observed facts (verified against main at 6960f4a)

- `.github/actions/wing-commander-board-stop-check/action.yml` ends its
  stop branch with `paused=true` and nothing else — there is no issue
  comment, no `--add-label`, and no marker write anywhere in the
  composite. Its only durable side effect is `gh run cancel` against a
  *different* run.
- Each caller's durable-action step stands down with a summary line only.
  `.github/workflows/board-loop.yml` (triage): `if [ "$PAUSED" = "true" ];
  then echo "board-loop: kill switch set immediately before triage's
  durable action -- standing down without acting." >>
  "$GITHUB_STEP_SUMMARY"; exit 0; fi`. The message names only the kill
  switch, though the same output is what an honoured stop request
  produces.
- `board_eligibility.py` already has everything needed to take a stopped
  item out of the candidate set: `STALLED_LABEL = "board:stalled"` makes
  `is_excluded()` return `(True, STALLED_LABEL)`, and `TERMINAL_STEPS =
  frozenset({"closed", "stalled", "proven"})` keeps a `stalled` marker
  from qualifying the item as in-flight. Nothing on the stop path uses
  either.
- `board_stop_check.find_stop_request()`'s docstring already defines
  `stand_down` as true "iff an authorized, **unactioned** stop request
  exists" — but no code anywhere ever actions a stop request, so the
  qualifier is unreachable as written.
- `find_stop_request()` computes `baseline = ""` and only ever raises it
  from a bot-authored `**Run:**` comment, so an issue with no loop
  announcement admits stop commands of unbounded age.
- Three other board-loop paths already write the exact
  stalled-and-handed-over shape this feature needs — triage's `handover`
  arm, route's spec-request arm, and the fix job's post-push breach arm —
  each posting a comment, adding `board:stalled`, and writing a
  `stalled` marker. #530 fixed the ordering for two of them: the label
  goes on **before** the stalled marker, so a failure between the two
  leaves the item retryable rather than silently parked.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One stop halts one item, and the board keeps moving (Priority: P1)

A maintainer watching the loop work issue #402 decides the approach is
wrong and comments `stop - wrong approach`. The run in flight stands down
at its next durable action, as it does today. On the next scheduled run,
the loop does **not** pick #402 back up: it is marked as stopped and
awaiting a human, so selection passes over it and the loop starts work on
the next eligible issue instead.

**Why this priority**: This is the defect. Without it, one stop costs the
whole board every subsequent run, and the loop never makes progress on
anything again until a human notices and intervenes manually. Everything
else here is legibility or edge-case correctness on top.

**Independent Test**: With a stop command on the in-flight item, drive two
consecutive runs. The first stands down; the second selects a *different*
eligible item (or reports an empty board) and never re-enters a job for
the stopped item.

**Acceptance Scenarios**:

1. **Given** an item in flight and an authorized stop command posted
   after the item's current run announcement, **When** a job reaches its
   stop check before a durable action, **Then** that job takes no other
   durable action and the item is left recorded as stopped and needing a
   human.
2. **Given** an item recorded as stopped by a previous run, **When** the
   next scheduled run runs its selection pass, **Then** that item is not
   selected — neither as the in-flight candidate nor by oldest-first —
   and another eligible item is selected if one exists.
3. **Given** an item recorded as stopped, **When** a later run selects
   nothing else because the board is otherwise empty, **Then** the run
   completes as a no-op with its own cost line and metrics record, with
   no job entered for the stopped item.
4. **Given** the kill switch is set (and no stop command exists),
   **When** a job stands down at its stop check, **Then** nothing durable
   is written for the item: no comment, no label change, no marker — the
   board resumes unchanged when the switch is cleared.
5. **Given** an authorized stop command **and** the kill switch set at
   the same time, **When** a job stands down, **Then** the stop point is
   still recorded (the stop is about this item and outlives the switch).

---

### User Story 2 - The stop point is legible on the issue (Priority: P2)

A maintainer comes back to the issue a day later, or someone else does.
The issue thread says, in plain language, that the loop stopped because
of a maintainer stop request, which comment it read, how far it had got
when it stopped, and what a human has to do to let it continue.

**Why this priority**: FR-052's own words are "the stop point MUST be
recorded", and FR-046's principle is that a stand-down is recorded rather
than silent so a quiet board is distinguishable from a paused one. A stop
whose only trace is a line in a run's step summary — which expires with
the run's retention — is indistinguishable from the loop having silently
lost interest.

**Independent Test**: Post a stop, drive one run, then read the issue with
no access to the run logs. The reason, the stopping point and the release
instruction are all determinable from the issue alone.

**Acceptance Scenarios**:

1. **Given** a stop is honoured, **When** the loop records it, **Then**
   the issue carries a human-legible comment naming the maintainer stop
   request as the cause, identifying the stop comment it acted on, and
   stating the single condition under which the item becomes eligible
   again.
2. **Given** the maintainer's stop command carried a reason (`stop: the
   fix is wrong`), **When** the record is written, **Then** the reason is
   reproduced as inert text — never as instructions, never rendering an
   `@mention`, `#N` cross-reference, link or HTML from it.
3. **Given** two jobs in the same run both reach their stop check with
   the same honoured stop, **When** each stands down, **Then** the issue
   carries exactly one stop-point record for that run, not one per job.
4. **Given** a stop is honoured, **When** the run finishes, **Then** its
   metrics record and cost line distinguish a stop-request stand-down
   from a kill-switch stand-down and from an ordinary quiet run.

---

### User Story 3 - A maintainer releases a stopped item and it continues (Priority: P2)

Having looked, the maintainer decides the loop should carry on. They
perform the release act — the same one every other stalled board item
already uses — and the next scheduled run picks the item back up and
continues from where it stopped, without re-reading the old stop comment
as a fresh stop and without opening a second branch or a second pull
request for the issue.

**Why this priority**: A stop that cannot be undone is a permanent
exclusion, and a release that immediately re-stops is the original wedge
wearing a hat. The two halves are only useful together, but the stop
(P1/P2) is what unfreezes the board even if release is done by hand.

**Independent Test**: Record a stop, release the item, drive one run:
the item is selected, proceeds past its stop check, and the issue gains no
second stop-point record.

**Acceptance Scenarios**:

1. **Given** an item recorded as stopped, **When** a maintainer performs
   the release act, **Then** the next run selects the item and its stop
   checks do not stand down on the already-recorded stop command.
2. **Given** a released item that had an open loop-owned pull request
   when it stopped, **When** the loop resumes it, **Then** no second
   branch and no second pull request are opened for that issue (FR-054).
3. **Given** a released item, **When** the maintainer posts a *new*
   authorized stop command, **Then** that new stop is honoured and
   recorded again.
4. **Given** an item recorded as stopped that a maintainer never
   releases, **When** any number of later runs execute, **Then** the item
   is never selected and no further stop-point record is written for it.

---

### User Story 4 - An ancient stop does not silently own an untouched issue (Priority: P3)

A maintainer replied `stop.` in a thread on an issue long before the board
loop existed, or before the loop ever announced a run on it. That comment
does not get to silently veto the loop forever: the loop's treatment of a
stop request that predates its own first announcement on the item is one
stated rule, and whichever way it falls, the outcome is visible on the
issue rather than an unexplained repeating stand-down.

**Why this priority**: It is a real freeze (the code review of the #539
fix found it), but it needs an issue whose history predates the loop, so
it bites less often than User Story 1's case — and recording the stop
point already converts it from an endless wedge into a one-time,
explained stall.

**Independent Test**: On an issue with an old authorized stop command and
no loop `**Run:**` announcement at all, drive one run and confirm the
stated rule applied and left a legible outcome.

**Acceptance Scenarios**:

1. **Given** an issue the loop has never announced a run on, carrying an
   authorized stop command older than the loop's involvement, **When**
   the loop selects it and reaches a stop check, **Then** the outcome
   follows the stated empty-baseline rule and is recorded on the issue if
   it stops the item.
2. **Given** that same issue, **When** any later run executes, **Then**
   the issue is not stood down on repeatedly with no record.

---

### Edge Cases

- **Kill switch only** — nothing durable is written (User Story 1,
  scenario 4). The global pause must stay non-destructive.
- **Issue already closed** — the `prove` job's stop check also pauses
  when the issue is closed (FR-053). A closed issue is already outside
  the candidate set, so no stop-point record is written for that cause;
  the loop does not comment on an issue a human deliberately closed.
- **Stop honoured, then recording fails** — a failed label application or
  a failed comment must not leave the item silently parked. The item must
  end the run either fully recorded as stopped or plainly retryable, with
  the failure loud in the run, following the #530 ordering rule already
  established for the other stalled paths.
- **Two jobs, one run** — the record is written once (User Story 2,
  scenario 3), and the second job still stands down. Writing the record
  must never itself read back as evidence that the stop has been
  satisfied and the item may proceed.
- **Stop plus cancellable earlier run** — the existing `gh run cancel`
  behaviour for a genuinely-still-running earlier run is unchanged, and
  a failed cancel does not prevent the stop point being recorded.
- **Stop arrives between a job's stop check and its durable action** —
  unchanged: the check is a point-in-time read, and the stop is honoured
  at the next check.
- **Item stopped while it had no branch or PR yet** (during triage or
  route) versus **stopped mid-fix or mid-review with an open loop-owned
  PR** — both must be recorded, and the second must not lose track of
  the PR the loop already owns (FR-054).
- **A non-maintainer posts a stop command** — unchanged: not honoured, so
  nothing is recorded.
- **Prose containing "stop"** — unchanged: `is_stop_command()`'s
  first-line command rule (#539) still decides what a stop is; this
  feature only changes what happens once one is honoured.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the loop honours an authorized maintainer stop request
  against a board item, it MUST record the stop point durably on that
  item's issue, satisfying spec 057 FR-052's "the stop point MUST be
  recorded".
- **FR-002**: The recorded stop point MUST take the item out of the
  loop's candidate set, so that no later run selects it — neither as the
  in-flight candidate nor by oldest-first — until a maintainer releases
  it.
- **FR-003**: The record MUST take the shape of
  [NEEDS CLARIFICATION: does an honoured stop reuse the existing terminal
  `stalled` marker plus the `board:stalled` label — the same shape
  triage's handover, route's spec-request and the fix job's post-push
  breach already use, released by removing that label — or does it
  introduce a distinct `stopped` step and/or label that is never a
  candidate and is released by its own act?].
- **FR-004**: The stop-point record MUST include a human-legible
  statement on the issue that names a maintainer stop request as the
  cause, identifies the stop comment acted on, and states the single
  condition that makes the item eligible again.
- **FR-005**: Any reason text carried by the maintainer's stop command
  MUST be reproduced as inert data, never as instructions and never
  rendering mentions, cross-references, links or HTML (Constitution V;
  the loop's existing fencing rule for quoted content).
- **FR-006**: Recording the stop point MUST be the only durable action
  the stopping job takes. The job MUST NOT perform the durable action it
  was about to perform, and MUST NOT close the issue, close or merge a
  pull request, or push code as part of stopping.
- **FR-007**: At most one stop-point record MUST be written per run, even
  when several jobs in that run each reach their own stop check with the
  same honoured stop.
- **FR-008**: Writing the stop-point record MUST NOT be readable as
  evidence that the stop has been satisfied. Every remaining stop check
  in the same run, and every check on any later run before the item is
  released, MUST continue to stand down.
- **FR-009**: After a maintainer releases a stopped item, the stop
  request that was already recorded MUST NOT stand the item down again; a
  *new* authorized stop command posted after the release MUST be honoured
  and recorded afresh.
- **FR-010**: The stop-point record MUST preserve
  [NEEDS CLARIFICATION: how much of the item's in-flight context — step,
  review round, pull request, branch, base commit — so that a released
  item resumes where it stopped? Or is a released item allowed to restart
  from triage, provided FR-054's "no second branch or PR" still holds?].
- **FR-011**: A stand-down caused by the kill switch alone MUST write
  nothing for the item: no comment, no label change, no marker. Clearing
  the switch MUST leave the board exactly as it was.
- **FR-012**: When the kill switch and an authorized stop request are
  both present, the stop point MUST still be recorded.
- **FR-013**: A stand-down caused solely by the issue being closed
  (FR-053, the `prove` job's extra pre-check) MUST write nothing for the
  item.
- **FR-014**: The stand-down messages the loop emits MUST name the cause
  they actually observed — a stop request, the kill switch, or a closed
  issue — rather than naming the kill switch for all of them.
- **FR-015**: Each run's own outcome record and cost line MUST let a
  stop-request stand-down be distinguished from a kill-switch stand-down
  and from a quiet run, from the durable record alone (FR-046/FR-047).
- **FR-016**: A stop request posted before the loop's first run
  announcement on an item MUST be handled by one stated rule:
  [NEEDS CLARIFICATION: is such a pre-loop stop ignored entirely (only a
  stop posted after the item's first loop announcement counts), or
  honoured once — recorded, stalling the item for a human — the first
  time the loop selects the item?].
- **FR-017**: A failure to complete the recording MUST NOT leave the item
  silently parked. The run MUST end with the item either fully recorded
  as stopped, or plainly eligible for a later retry, and MUST make the
  partial failure loud rather than exiting green.
- **FR-018**: The logic that decides a stop has been honoured and records
  it MUST have exactly one home, reused by every job that re-checks
  before a durable action, rather than being repeated per job (CLAUDE.md
  "Shared logic has exactly one home"; spec 057's reuse requirements).
- **FR-019**: A PR-time gate MUST fail on a change that removes the
  recording from the honoured-stop path, that makes the kill-switch-only
  path write to the item, or that lets a recorded stop be re-selected;
  the gate MUST be able to fail its subject (i.e. it must be shown to
  fail on the pre-fix behaviour).
- **FR-020**: Nothing above may change what counts as a stop command
  (`is_stop_command()`'s first-line rule, #539), who may issue one (the
  maintainer association check), or the existing cancel-an-earlier-run
  behaviour.

### Key Entities

- **Stop request**: an authorized maintainer comment whose first
  non-skipped line is a stop command, posted after the applicable
  baseline. Unchanged by this feature except for FR-016's treatment of
  the empty-baseline case.
- **Stop baseline**: the timestamp after which a stop command counts —
  today, the most recent loop-authored run announcement on the item. The
  fact that an item may have none is what FR-016 resolves.
- **Stop point record**: the new durable artifact. The item state, plus
  the human-legible statement, that says the loop honoured a stop here,
  at this step, and what a human must do next.
- **Board item marker**: the loop's existing machine-readable item state
  (step, round, PR, branch, base commit) that the next run reads to
  resume. What a stop writes into it is FR-003/FR-010.
- **Stalled/awaiting-a-human state**: the existing "this item needs a
  human before the loop touches it again" condition that removes an item
  from selection, and the act that releases it.
- **Kill switch**: the repository-wide pause. Deliberately leaves no
  per-item trace (FR-011).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After one honoured stop on an item, that item is selected
  by zero of the next ten runs, until a maintainer releases it.
- **SC-002**: An honoured stop produces exactly one stand-down per item
  and exactly one stop-point record, no matter how many jobs or runs
  follow it — zero repeat stand-downs on an unreleased item.
- **SC-003**: With one item stopped and at least one other eligible item
  on the board, the very next scheduled run starts work on that other
  item — the board's throughput is unchanged by the stop.
- **SC-004**: A maintainer reading only the issue (no run logs) can state
  why the loop stopped, how far it had got, and what to do to resume it,
  in under one minute.
- **SC-005**: A kill-switch-only stand-down produces zero comments, zero
  label changes and zero markers on every item, and clearing the switch
  resumes the same item at the same step.
- **SC-006**: Releasing a stopped item results in the loop resuming it
  within one scheduled run, with zero additional branches and zero
  additional pull requests opened for that issue.
- **SC-007**: An issue with a pre-loop stop command and no loop
  announcement produces at most one stand-down with a record, never an
  unbounded series of silent ones.
- **SC-008**: Every run's durable metrics record distinguishes the three
  stand-down causes; an auditor can count stop-request stand-downs across
  runs from the records alone, without reading any run's logs.
- **SC-009**: The new gate fails when run against the pre-fix behaviour
  and passes against the fixed behaviour.

## Assumptions

- **Where the recording lives is a plan-stage decision, constrained by
  FR-018**: CLAUDE.md's "shared logic has exactly one home" points at the
  shared stop-check composite rather than six copies in the workflow's
  jobs, and the issue names this as an owner trade-off only because the
  composite would then need each caller's item context (step, round, PR,
  branch, base commit) passed in as inputs. This spec requires one home
  and leaves the placement to planning rather than spending a
  clarification on it.
- **The release act is the existing one** unless FR-003 is answered with
  a distinct stopped state: every other stalled board path in this
  repository states that removing `board:stalled` is the sole
  re-eligibility condition, and a second release convention for stops
  would be a new thing for maintainers to learn.
- **A stop is per-item, not board-wide.** The issue states the
  kill-switch case must keep writing nothing "since that is a global
  pause, not an item stop"; the converse is assumed to hold — an
  honoured stop excludes only its own item, and the loop is expected to
  continue on other eligible items in the same or the next run.
- **Only the loop's own App-authored `**Run:**` announcements** continue
  to establish the baseline (#547), and only the last such line in a
  comment (#580). This feature does not widen what may move a baseline.
- **The stop-point record is a comment plus item state on the issue**,
  posted by the loop's own App, matching FR-044 (every step posts what it
  did on the originating issue) and the existing handover/spec-request/
  breach paths — not a new artifact type, a new label namespace, or a
  notification outside the issue.
- **Round budgets and turn ceilings are unaffected**: a run that stands
  down and records a stop spends no agent turns beyond those already
  spent before the stop check.
- **The item's pull request is left alone.** An honoured stop records
  where the loop stopped; whether the open loop-owned PR should be
  closed, converted to draft or commented on is a maintainer's call, not
  the loop's (FR-006).
- **Actions-only behaviour**: this path runs only inside GitHub Actions,
  so the merged change is proven after merge by re-driving one run and
  recording the evidence, per CLAUDE.md's board rules, in addition to the
  PR-time gate FR-019 requires.

## Dependencies

- Spec 057 (`specs/057-autonomous-board-loop`) — FR-046, FR-051, FR-052,
  FR-053, FR-054 and its `board-loop-workflow.md` /
  `board-item-marker.md` / `eligibility-and-selection.md` contracts,
  which remain live and which this feature's behaviour must stay
  consistent with.
- The existing stop-decision contract (specs 085, 087, 088) — the
  two-fact `stand_down`/`cancel_run_id` answer, its error classification,
  and the closed-check read policy. This feature adds a consequence to
  `stand_down`; it must not alter the decision itself or the cancel path.
- The existing selection and marker rules in `board_eligibility.py` and
  `board_item_marker.py`, including the `board:stalled` exclusion and the
  terminal-step set, which are what make FR-002 achievable without a new
  selection mechanism.
- The `#530` ordering rule for stalled paths (label before marker) that
  FR-017 builds on.
