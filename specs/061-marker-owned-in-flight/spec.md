# Feature Specification: The Loop Recognizes Its Own Work — In-Flight Detection Reads the Board Item Marker

**Feature Branch**: `spec-draft/061-marker-owned-in-flight`

**Created**: 2026-09-23

**Status**: Draft

**Input**: Lifecycle issue #473 — "board-loop.yml's in-flight/resume PR
detection can't tell its own PR from an unrelated open fix PR"

## Overview

The board loop is meant to finish the board item it already started before
reaching for a fresher one (spec 057, User Story 7 / FR-048 / FR-054). To
decide "am I already mid-flight on something?", the `select` job currently
takes the **first open pull request in the whole repository** whose body
matches `Fixes #N` and treats issue `N` as its in-flight item. The `resume`
job does the same kind of repository-wide body search to recover the item's
pull request number.

Neither search asks the question that actually matters: *is this pull
request mine?* This repository's ordinary, non-loop workflow is exactly
"file an issue, open a fix pull request that says `Fixes #N`", so any
ordinary fix pull request that happens to be open when the schedule fires
is indistinguishable, to the loop, from its own in-progress work.

The loop already records the answer. When it opens a fix pull request it
writes a **board item marker** onto the issue — an HTML comment carrying
`step`, `round`, `pr`, `branch`, and `base_sha` — and that marker is the
loop's own, unforgeable-by-accident record of what it is working on. This
feature makes in-flight detection and resume read that record instead of
pattern-matching pull request bodies belonging to anyone.

### Observed failure (confirmed live)

Run 35839986595:

- `gh pr list --state open` returned pull request #469 (`Fixes #396, item 3.`)
  first, ahead of #467 (`Fixes #391, item 4.`). Both were ordinary
  session-filed fix pull requests, unrelated to the loop; neither issue
  carried a board item marker.
- The exclusion check the shortcut applies only inspects labels and state.
  Issue #396 carried none, so the shortcut fired and pinned the run to
  issue #396. The real oldest-first eligibility scan never ran.
- In `resume`, the same repository-wide search found #469 again. No marker
  existed, so `branch` resolved empty — but `pr` did not, and the
  "fall back to triage" path requires *both* to be empty. The step name was
  left empty, so every downstream job's step check matched nothing and
  triage, route, fix, review, readiness and prove all reported `skipped`.

Merging the two unrelated pull requests clears this instance. The failure
mode returns with the next unrelated open fix pull request, and while it is
active the loop is stalled on one issue no matter how many others are
eligible.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An unrelated open fix PR no longer hijacks the loop (Priority: P1)

A maintainer has an ordinary fix pull request open that says `Fixes #396`.
The board loop's schedule fires. The loop looks for work it started itself,
finds none, and proceeds to its normal oldest-first eligibility scan —
picking the genuinely oldest eligible issue, which may or may not be #396,
and picking it on eligibility grounds rather than on a stranger's pull
request body.

**Why this priority**: This is the reported defect. Until it is fixed, one
unrelated pull request can stall the entire autonomous board loop
indefinitely, and the stall is silent — every downstream job reports
`skipped`, which reads like "nothing to do".

**Independent Test**: With an open pull request whose body cites an eligible
issue, and no board item marker anywhere on the board, run the loop and
confirm the selected issue is the one the oldest-first eligibility scan
returns, not the one the pull request cites.

**Acceptance Scenarios**:

1. **Given** an open pull request citing eligible issue A, and no issue
   carries a board item marker, **When** the loop selects, **Then** it
   selects by the oldest-first eligibility scan and reports which issue it
   selected and why.
2. **Given** an open pull request citing issue A, and issue B carries a
   board item marker recording a non-terminal step, **When** the loop
   selects, **Then** it selects issue B.
3. **Given** an open pull request citing issue A, and issue A also carries
   a board item marker recording a non-terminal step, **When** the loop
   selects, **Then** it selects issue A — the right answer for the right
   reason, and the run's record says the marker is why.

---

### User Story 2 - Resume recovers the loop's own item, or declares it fresh (Priority: P1)

The loop resumes an item it started on a previous run. It reads the item's
own marker for the branch and pull request it opened, re-derives both
against live GitHub state, and continues from the recorded step. When it
cannot establish that any prior work of its own exists, it starts the item
from triage — it never leaves the step unresolved, because an unresolved
step silently skips every downstream job.

**Why this priority**: The empty-step outcome is the half of the live
failure that turns a mis-selection into a no-op run. Even with User Story 1
fixed, any future state that leaves the step unresolved reproduces the same
silent stall, so the "never unresolved" guarantee is worth having on its
own.

**Independent Test**: Run the loop against an issue with no marker and a
repository containing an unrelated open pull request that cites it; confirm
the run proceeds through triage rather than reporting every job `skipped`.

**Acceptance Scenarios**:

1. **Given** a selected issue with a marker naming a branch that still
   exists and a pull request that still exists, **When** resume runs,
   **Then** it continues from the marker's recorded step with the
   re-derived branch and pull request.
2. **Given** a selected issue with no marker, **When** resume runs, **Then**
   the step resolves to triage and no pull request from an unrelated issue
   is adopted as this item's pull request.
3. **Given** a selected issue with a marker whose branch no longer exists
   and whose recorded pull request no longer exists, **When** resume runs,
   **Then** the step resolves to triage.
4. **Given** any selected issue in any state, **When** resume finishes,
   **Then** the resolved step is one of the loop's named steps — never
   empty — so no run can skip every downstream job without saying so.

---

### User Story 3 - The rule has a home and a gate that can fail it (Priority: P2)

The decision "is this issue an in-flight board item of mine?" is one rule
with one home and checked-in fixtures covering each of its branches, so the
next change to it fails a gate rather than a scheduled run three weeks
later.

**Why this priority**: The defect survived because the rule lived as an
inline shell pipeline no fixture could exercise; the existing eligibility
gate could not fail on it because the rule was not part of the subject the
gate scans. Constitution VIII ("a green check means what it says") and this
repository's "shared logic has exactly one home" rule both apply.

**Independent Test**: Run the repository's PR-time gate suite against a
deliberately broken in-flight rule and confirm a gate fails.

**Acceptance Scenarios**:

1. **Given** the in-flight decision and its fixtures, **When** the PR-time
   gate suite runs, **Then** each fixture asserts the decision's exact
   result and the gate fails loudly if a fixture file is missing.
2. **Given** a change that makes the in-flight decision admit an issue with
   no marker, **When** the gate suite runs, **Then** a gate fails.

---

### Edge Cases

- **Marker records a terminal step** (the item is finished). The item is not
  in flight; selection falls through to the oldest-first scan.
- **Marker records a non-terminal step but the issue is now excluded**
  (closed, `disposition:*`, `board:stalled`, `stage:*`/`spec:*`). Exclusion
  wins, exactly as it does today; the loop moves to the next eligible item.
- **Several issues carry non-terminal markers.** Only one item is in flight
  repository-wide (FR-048), so this is a state the loop should not create;
  it must nevertheless pick deterministically and record that it found more
  than one.
- **Marker is unparsable or missing fields.** It degrades to "no marker" and
  the loop reads live GitHub state, per spec 057 FR-054 — never raises,
  never guesses.
- **Marker's recorded pull request was closed without merging, or merged,
  while its step is still non-terminal.** Covered by the clarification in
  FR-002.
- **Marker exists on an issue that is not in the run's fetched open-issues
  set** (e.g. closed between fetch and check). Treated as not in flight.
- **An ordinary fix pull request cites the very issue the loop is working.**
  The marker still decides; the coincidence changes nothing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: In-flight detection MUST identify a candidate item only from
  a board item marker the loop itself wrote onto an issue. It MUST NOT
  derive a candidate from pull request bodies, pull request titles, or any
  other repository-wide search that cannot distinguish the loop's own work
  from a third party's.

- **FR-002**: An issue qualifies as in flight when it carries a board item
  marker whose recorded step is not terminal, and
  [NEEDS CLARIFICATION: is a non-terminal step sufficient on its own, or
  must the marker's recorded pull request also still resolve to an open
  pull request? Requiring an open pull request stops a closed-without-merge
  item from being re-selected forever; not requiring one keeps pre-PR steps
  (triage, route) in flight, since no pull request exists yet].

- **FR-003**: An issue that qualifies under FR-002 MUST still be subject to
  the existing exclusion rule (closed, `disposition:*`, `board:stalled`,
  `stage:*`, `spec:*`), evaluated by the same single decision the
  oldest-first scan uses — never a second, parallel exclusion rule.

- **FR-004**: When no issue qualifies as in flight, selection MUST fall
  through to the existing oldest-first eligibility scan unchanged.

- **FR-005**: When more than one issue qualifies as in flight, the loop MUST
  choose deterministically (the most recently written marker) and MUST
  record in the run's summary that it found more than one, so the
  FR-048 violation is visible rather than silently resolved.

- **FR-006**: Resume MUST recover the item's branch and pull request from
  that item's own marker, re-derived against live GitHub state before any
  durable action, per spec 057 FR-054.

- **FR-007**: Resume MUST NOT adopt a pull request as this item's pull
  request on the strength of a repository-wide body or text search.
  [NEEDS CLARIFICATION: should resume retain any pull-request search as a
  fallback for the case where the marker is missing but a prior run did
  open a pull request — and if so, narrowed by what (head branch matching
  the loop's own branch convention, pull request author, a loop-applied
  label)? Or should "no marker" mean "no prior pull request", full stop?]

- **FR-008**: Resume MUST resolve the item's step to one of the loop's named
  steps in every case. A state in which no step can be established MUST
  resolve to the first step (triage), never to an empty value.

- **FR-009**: When resume resolves an item to triage because its prior state
  could not be recovered, the run MUST record that fact and its reason, so a
  restarted item is distinguishable from a fresh one.

- **FR-010**: A run that selects no issue, and a run that selects one and
  then does no downstream work, MUST be distinguishable from each other in
  the run's own record — the live failure produced six `skipped` jobs and no
  statement that anything was wrong.

- **FR-011**: The in-flight decision MUST live in exactly one place, and the
  comment explaining it MUST be canonical with every other site pointing at
  it, per this repository's single-home rule.
  [NEEDS CLARIFICATION: should that home be the existing eligibility
  decision module — which already owns classification and exclusion and
  already has a fixture-driven gate — or a separate decision of its own?
  Folding it in reuses the gate and keeps one definition of "eligible";
  keeping it separate keeps the eligibility module free of any dependency
  on marker parsing].

- **FR-012**: The in-flight decision MUST be covered by checked-in fixtures
  asserting its exact result for at least: no marker anywhere; marker with a
  non-terminal step; marker with a terminal step; marker on an excluded
  issue; unparsable marker; two issues with non-terminal markers; and an
  unrelated open pull request citing an eligible issue with no marker
  present. The gate MUST fail loudly when a fixture file is missing rather
  than skipping it (Constitution VIII).

### Key Entities

- **Board item marker**: the loop's own record on an issue, carrying the
  step it reached, the round, the pull request number it opened, the branch
  it opened, and the base commit. Already defined by spec 057; this feature
  changes who reads it, not its shape.
- **In-flight candidate**: an open, non-excluded issue whose marker says the
  loop has unfinished work on it.
- **Step**: the loop's position in triage → route → fix → review →
  readiness → prove, plus the terminal outcomes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With any number of unrelated open fix pull requests citing
  eligible issues, and no board item marker present, the loop selects the
  issue the oldest-first eligibility scan returns — 100% of the time,
  demonstrated by fixture and by one re-driven scheduled run.
- **SC-002**: Zero runs finish with every downstream job `skipped` while an
  issue was selected; any run that selects an issue either does work on it
  or states, in its own summary, why it did not.
- **SC-003**: Replaying the conditions of run 35839986595 (open pull
  requests #467 and #469, no markers) selects by eligibility rather than
  pinning to issue #396.
- **SC-004**: Every branch of the in-flight decision named in FR-012 is
  covered by a checked-in fixture, and deliberately breaking the decision
  fails the PR-time gate suite.
- **SC-005**: A loop item interrupted mid-flight and resumed on a later run
  continues from its recorded step without opening a second branch or a
  second pull request (spec 057 FR-054), across at least one full
  interrupt-and-resume cycle.

## Assumptions

- The board item marker is written early enough in an item's life that any
  item worth resuming has one. Where it is not, FR-008's triage fallback is
  the correct and safe outcome: re-running triage on an item is cheap
  compared with stalling the board.
- "Terminal step" is a property the loop already knows from its own step
  list; this feature does not introduce a new vocabulary of step names.
- The existing exclusion rule (closed, `disposition:*`, `board:stalled`,
  `stage:*`, `spec:*`) is correct as written and is reused unchanged — the
  defect is what feeds it a candidate, not how it judges one.
- The oldest-first eligibility scan is correct as written and is not
  modified by this feature.
- Marker parsing already degrades to `None` on missing or malformed input
  and never raises; this feature relies on that behaviour rather than adding
  its own error handling.
- The loop's own concurrency group (FR-048) makes two simultaneous in-flight
  items an anomaly rather than a supported state, so FR-005 reports rather
  than reconciles.
- Fixing this does not require changing how or when the marker is written —
  only who reads it and what they read instead of pull request bodies.

## Dependencies

- Spec 057 (`specs/057-autonomous-board-loop`): the board item marker
  contract, the eligibility and selection contract, FR-048 and FR-054. This
  feature is a correction inside that feature's boundary.
- The board loop workflow's `select` and `resume` jobs, and the eligibility
  decision module and its gate.

## Out of Scope

- Changing the oldest-first ordering, the eligibility classification, or the
  exclusion list.
- Changing the marker's fields or when it is written.
- Changing the kill switch, the stand-down check, or the stop-comment
  handling.
- Retrofitting markers onto items the loop worked before this change.
