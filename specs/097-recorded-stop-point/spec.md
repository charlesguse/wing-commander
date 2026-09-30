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

## Clarifications

### Session 2026-09-29 — answered on lifecycle issue #724

- Q: What shape does an honoured stop's record take — reuse the terminal
  `stalled` marker plus the `board:stalled` label, or a distinct
  `stopped` step and/or label with its own release act? → A: **Reuse the
  existing shape.** A terminal `stalled` marker plus `board:stalled`,
  with the reason "stopped by maintainer request", released by a
  maintainer removing the label. No new vocabulary: selection and resume
  already handle it. The recording itself lives in the stop-check
  composite, the single place every job already calls. The kill switch
  keeps writing nothing. (FR-003, FR-018, User Story 1, User Story 3)
- Q: How much in-flight context does the record preserve — enough to
  resume where the item stopped, or may a released item restart? → A:
  **Branch and base commit only**, the fix job's existing stalled shape.
  A released item re-finds its open loop-owned pull request through the
  `board:owned` fallback, and its review round restarts, so state a human
  has touched is reviewed again before anything is reported ready
  (consistent with the owner's answer on #717). (FR-010, User Story 3)
- Q: Is a stop request posted before the loop's first announcement on an
  item ignored entirely, or honoured once? → A: **Honoured once.** With
  an empty baseline the newest authorized stop command stops the item and
  the stop point is recorded, so a human sees an explained stall and the
  board is released rather than wedged. (FR-016, User Story 4)

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
remove `board:stalled` — the same release act every other stalled board
item already uses — and the next scheduled run picks the item back up at
the step spec 100's re-admission rule names (FR-010), without re-reading
the old stop comment as a fresh stop and without opening a second branch
or a second pull request for the issue. If it resumes into review, the
review gets a fresh round budget, so state a human has touched is reviewed
afresh.

**Why this priority**: A stop that cannot be undone is a permanent
exclusion, and a release that immediately re-stops is the original wedge
wearing a hat. The two halves are only useful together, but the stop
(P1/P2) is what unfreezes the board even if release is done by hand.

**Independent Test**: Record a stop, remove `board:stalled`, drive one
run: the item is selected, proceeds past its stop check, and the issue
gains no second stop-point record.

**Acceptance Scenarios**:

1. **Given** an item recorded as stopped, **When** a maintainer removes
   `board:stalled`, **Then** the next run selects the item and its stop
   checks do not stand down on the already-recorded stop command.
2. **Given** a released item that had an open loop-owned pull request
   when it stopped, **When** the loop resumes it, **Then** it re-finds
   that pull request through the `board:owned` fallback, and no second
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
does not get to silently veto the loop forever: it is honoured once — the
item stands down, the stop point is recorded, and the item waits for a
human — so the outcome is visible on the issue rather than an unexplained
repeating stand-down.

**Why this priority**: It is a real freeze (the code review of the #539
fix found it), but it needs an issue whose history predates the loop, so
it bites less often than User Story 1's case — and recording the stop
point already converts it from an endless wedge into a one-time,
explained stall.

**Independent Test**: On an issue with an old authorized stop command and
no loop `**Run:**` announcement at all, drive one run and confirm the item
stood down once, the stop point was recorded, and the board moved on.

**Acceptance Scenarios**:

1. **Given** an issue the loop has never announced a run on, carrying an
   authorized stop command older than the loop's involvement, **When**
   the loop selects it and reaches a stop check, **Then** the newest such
   stop command is honoured, the item stands down, and the stop point is
   recorded on the issue.
2. **Given** that same issue, **When** any later run executes, **Then**
   it is not selected while unreleased, and the issue is not stood down
   on repeatedly with no record.

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
  PR** — both must be recorded, and the second must still find the PR the
  loop already owns when it is released, via the `board:owned` fallback
  rather than a PR number in the record (FR-010, FR-054).
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
- **FR-003**: The record MUST take the existing stalled-and-handed-over
  shape — a terminal `stalled` marker plus the `board:stalled` label,
  carrying the reason "stopped by maintainer request" — the same shape
  triage's handover, route's spec-request and the fix job's post-push
  breach already use. It MUST NOT introduce a distinct `stopped` step, a
  new label, or any other new vocabulary: selection already excludes
  `board:stalled` and already refuses a `stalled` marker as in-flight,
  and a maintainer releases the item by removing that label, exactly as
  for every other stalled board item.
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
- **FR-010**: The stop-point record MUST preserve the item's branch and
  base commit, and only those — the same in-flight context the fix job's
  existing stalled path already keeps. The review round MUST NOT be
  preserved: if a released item resumes into review, that review starts
  again from the first round, so state a human has touched is reviewed
  afresh before anything is reported ready. A released item MUST re-find its open loop-owned pull
  request through the existing `board:owned` fallback rather than through
  a pull request number carried in the record, and FR-054's "no second
  branch or pull request" MUST continue to hold. The step a released item
  resumes at is not set here. A stop is an undisposed stall, so spec 100
  FR-006/FR-006b decide it: `review` when the open `board:owned` PR's head
  moved since its last review or that head cannot be established,
  `readiness` when it provably did not move, and a fresh triage with no
  open PR. Spec 100 FR-009 sets the fresh round budget.
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
  announcement on an item MUST be honoured exactly once. When the
  baseline is empty, the newest authorized stop command in the issue's
  history stands the item down the first time the loop reaches a stop
  check on it, and that stop point MUST be recorded like any other — so
  the maintainer sees an explained stall and the board is released
  instead of wedged. No later run may stand the item down again on that
  same stop command.
- **FR-017**: A failure to complete the recording MUST NOT leave the item
  silently parked. The run MUST end with the item either fully recorded
  as stopped, or plainly eligible for a later retry, and MUST make the
  partial failure loud rather than exiting green.
- **FR-018**: The logic that decides a stop has been honoured and records
  it MUST have exactly one home — the shared stop-check composite every
  job already calls — rather than being repeated per job (CLAUDE.md
  "Shared logic has exactly one home"; spec 057's reuse requirements).
  Whatever item context that home needs in order to write the record is
  passed in by each caller. The label-then-marker write MUST go through
  the existing stall helper, `add_stalled_label()` in
  `board_item_marker.py`, not a new implementation. The composite MUST run
  that helper, and `board_stop_check.py`, from the trusted snapshot rather
  than the workspace (spec 095 FR-011/FR-012).
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
  today, the most recent loop-authored run announcement on the item. When
  an item has none, FR-016 makes the newest authorized stop command count
  once.
- **Stop point record**: the new durable artifact. A `stalled` marker
  with the reason "stopped by maintainer request" and the `board:stalled`
  label, plus the human-legible comment that says the loop honoured a
  stop here, at this step, and what a human must do next (FR-003).
- **Board item marker**: the loop's existing machine-readable item state
  (step, round, PR, branch, base commit) that the next run reads to
  resume. A stop writes a terminal `stalled` step and keeps the branch
  and base commit, dropping the review round (FR-003/FR-010).
- **Stalled/awaiting-a-human state**: the existing "this item needs a
  human before the loop touches it again" condition — the `board:stalled`
  label, which `is_excluded()` already honours — removed by a maintainer
  to release the item.
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
  announcement produces exactly one stand-down, with a record, never an
  unbounded series of silent ones.
- **SC-008**: Every run's durable metrics record distinguishes the three
  stand-down causes; an auditor can count stop-request stand-downs across
  runs from the records alone, without reading any run's logs.
- **SC-009**: The new gate fails when run against the pre-fix behaviour
  and passes against the fixed behaviour.

### Status update 2026-09-30 — reconciled with current `main` and specs 095/100/108 (maintainer spec review)

- **The stop path still records nothing.** `wing-commander-board-stop-check`
  still has a single `paused` output
  (`.github/actions/wing-commander-board-stop-check/action.yml`) and no
  comment, label or marker write. It is called at `board-loop.yml:1333`
  (triage), `1747` (route), `2275` (fix), `3220` (review), `3702`
  (readiness) and `4258` (prove). `find_stop_request()` still starts from
  `baseline = ""` (`board_stop_check.py:199`). FR-014 still stands: to
  record only a stop request, the composite has to expose which cause it
  observed, not just a single boolean.
- **The "Observed facts" on stall ordering are superseded by #782.** Every
  stall site now goes through `add_stalled_label()`
  (`board_item_marker.py:170`), which adds the label first and renders no
  marker when the add fails. There are eight sites, not three
  (`board-loop.yml:1906`, `2263`, `2467`, `3306`, `3311`, `3319`, `3913`,
  plus triage's hand-over). FR-017's retryable-on-failure rule is that
  helper's contract, and FR-018 now requires the stop record to use it.
  Spec 100 FR-004's derived enumeration of stall sites then covers the stop
  record with no list edit. Readiness's stand-down message already names
  both causes (`board-loop.yml:3716`); triage's still names only the kill
  switch (`board-loop.yml:1408`).
- **Spec 100 (merged) governs release.** An honoured stop is an undisposed
  stall. Re-admission after the label is removed follows spec 100
  FR-006/FR-006b, and the fresh budget follows spec 100 FR-009. This spec
  does not restate either rule. US3 and FR-010 previously said a released
  item "picks back up on the branch and base commit" and "its review starts
  again from the first round". That wording is corrected: on an open PR
  whose already-reviewed head has not moved, spec 100 resumes at
  `readiness`. That matches this issue's Q2 rationale, since only state a
  human touched is re-reviewed. The resolution on `main`
  (`board-loop.yml:811-813`, `step = "review"`) is what spec 100 FR-006
  changes.
- **Spec 100 FR-014 and US2 are narrowed for a stop request.** Spec 100
  FR-014 says a readiness stand-down leaves the marker unchanged, and its
  US2 scenario 1 says no `board:stalled` is applied. Both were written
  about readiness's *own* writes. The owner's #724 Q1 answer puts the stop
  record in the composite that every job calls, readiness included. The
  specs reconcile as follows:
  - FR-012/FR-013 of spec 100 still suppress every readiness write.
  - For a kill-switch or closed-issue stand-down, spec 100 FR-014 holds as
    written (FR-011/FR-013 here).
  - For an honoured maintainer stop request, the composite's stop record
    is the one item write (FR-006 here). No readiness step makes it.

  Whichever feature is implemented second updates the other's gate cases
  rather than contradicting them.
- **Spec 108 (merged)** closes a routed original as a duplicate. A closed
  original is never a stop-request source (spec 108 FR-008 and edge
  cases), so FR-013 here writes nothing for it. A disposed issue is
  re-admitted by reopen, not by removing the label.
- **Spec 095 (in review)** puts this composite's `run:` body under its
  provenance rule: `action.yml:113` still runs
  `.github/scripts/board_stop_check.py` from the workspace. The recording
  this spec adds is a new durable write in that same body, so it must
  import from the trusted snapshot (FR-018).
- **Fix's stop check runs before its push** (`board-loop.yml:2275`). A stop
  honoured there records a branch that was never pushed. After release,
  spec 100 FR-006 finds no open PR and triages afresh, so no second
  branch or PR results (FR-054).
- **Owner decisions:** none open. Every item above follows from the #724
  answers or from a merged spec.

## Assumptions

- **The recording lives in the shared stop-check composite** (FR-018),
  the single place every job already calls. The item context that home
  needs in order to write the record is passed in by each caller; exactly
  which inputs those are is a plan-stage detail.
- **The release act is the existing one**: removing `board:stalled` is
  the sole re-eligibility condition on every other stalled board path in
  this repository, and FR-003 keeps stops on that same convention rather
  than giving maintainers a second one to learn.
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
  FR-017 builds on, now implemented once in `add_stalled_label()` (#782).
- Spec 100 (`specs/100-stalled-item-re-admission`): the resume step, the
  fresh budget after release (FR-006/FR-006b/FR-009), and readiness's
  stand-down gating (FR-012-FR-015), narrowed for a stop request as the
  2026-09-30 status update records.
- Spec 108 (`specs/108-routed-original-disposition`): a disposed original
  is not a stop-request source and is re-admitted by reopen.
- Spec 095 (in review): provenance of the stop-check composite's `run:`
  body.
