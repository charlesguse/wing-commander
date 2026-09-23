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

## Clarifications

### Session 2026-09-23

- Q: Is a non-terminal marker step sufficient on its own to make an item in
  flight, or must the marker's recorded pull request also still resolve to
  an open pull request? → A: Split by step. Steps before the fix step
  (triage, route) qualify on the non-terminal step alone, because no pull
  request exists yet at those steps; the fix step and every step after it
  additionally require the recorded pull request to still be open. Requiring
  an open pull request everywhere would drop an item interrupted during
  triage or route out of in-flight status on every run; requiring one
  nowhere would leave an item whose pull request was closed without merging
  pinned in flight forever — the reported failure shape, relocated from "no
  marker" to "a stale marker". (FR-002, FR-012)
- Q: Should resume retain any pull-request search as a fallback for the case
  where the marker is missing but a prior run did open a pull request — and
  if so, narrowed by what? → A: Keep a fallback, narrowed to open pull
  requests carrying a label the loop applies to its own pull requests at
  creation time, and which cite the item's issue. The fix job creates the
  pull request and records the marker in separate steps, so a run cancelled
  or killed in that window leaves a real pull request no marker names; with
  no fallback the next run would open a second pull request for the same
  issue. A label applied at creation is an explicit, self-applied ownership
  signal, unlike a branch-naming convention that has to be hand-kept in sync
  with the fix job — the same quiet-drift shape that produced this defect.
  (FR-007, FR-013, FR-014)
- Q: Should the in-flight decision fold into the existing eligibility
  decision, or stand alone? → A: Fold it in, alongside the existing
  classification and exclusion logic, with selection consulting it first.
  This keeps one definition of "which issue does the loop act on" and reuses
  the eligibility gate's existing fixture harness for the new branches; the
  cost is that the eligibility decision's inputs grow to include each
  issue's own comments, where the marker lives. Leaving the rule inline in
  the selecting job's shell is ruled out by this repository's single-home
  rule — it is the shape that let this defect ship. (FR-011, FR-012)

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
4. **Given** issue A carries a marker recording a pre-fix step (triage or
   route) and naming no pull request, **When** the loop selects, **Then**
   it selects issue A on the strength of the step alone.
5. **Given** issue A carries a marker recording the fix step or a later one
   whose pull request has since been closed without merging, **When** the
   loop selects, **Then** issue A does not qualify as in flight and
   selection falls through to the oldest-first eligibility scan.

---

### User Story 2 - Resume recovers the loop's own item, or declares it fresh (Priority: P1)

The loop resumes an item it started on a previous run. It reads the item's
own marker for the branch and pull request it opened, re-derives both
against live GitHub state, and continues from the recorded step. Where no
marker was ever recorded — a run that died between opening a pull request
and writing the marker — it can still recognise its own pull request by the
ownership label it applied when it created it, and continues on that rather
than opening a second one. When it cannot establish that any prior work of
its own exists, it starts the item from triage — it never leaves the step
unresolved, because an unresolved step silently skips every downstream job.

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
2. **Given** a selected issue with no marker and no open pull request
   carrying the loop's ownership label that cites it, **When** resume runs,
   **Then** the step resolves to triage and no pull request from an
   unrelated issue is adopted as this item's pull request.
3. **Given** a selected issue with no marker but an open pull request that
   carries the loop's ownership label and cites it — a run that died
   between opening the pull request and recording the marker — **When**
   resume runs, **Then** it adopts that pull request and its branch,
   records that it recovered them by the label fallback rather than from a
   marker, and does not open a second pull request.
4. **Given** a selected issue with a marker whose branch no longer exists
   and whose recorded pull request no longer exists, **When** resume runs,
   **Then** the step resolves to triage.
5. **Given** a selected issue with a marker recording the fix step or a
   later one whose recorded pull request has been closed or merged, **When**
   resume runs, **Then** the step resolves to triage and the run records
   why, rather than continuing against a pull request that is gone.
6. **Given** any selected issue in any state, **When** resume finishes,
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
  while its step is still non-terminal.** At a fix-or-later step the item no
  longer qualifies as in flight (FR-002); selection falls through to the
  oldest-first scan, and if the issue is still eligible it is picked up
  again and resumed from triage with the reason recorded (FR-008, FR-009)
  rather than being pinned forever to a dead pull request.
- **Marker records a pre-fix step (triage, route) and names no pull
  request.** The item is in flight on the strength of its step alone
  (FR-002) — this is the ordinary shape of an item interrupted before the
  fix step.
- **A pull request was opened but the run died before its marker was
  recorded.** The pull request carries the loop's ownership label (FR-013),
  so resume's narrowed fallback (FR-007) finds it and continues on it
  instead of opening a second one.
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
  marker whose recorded step is not terminal, with the recorded step
  deciding what else is required:
  - **Steps before the fix step** (triage, route) qualify on the
    non-terminal step alone. No pull request exists yet at those steps, so
    demanding one would drop every item interrupted during triage or route
    out of in-flight status on every subsequent run.
  - **The fix step and every step after it** (fix, review, readiness,
    prove) additionally require the marker's recorded pull request to still
    resolve to an **open** pull request. A recorded pull request that is
    closed, merged, or no longer resolvable disqualifies the item, so a
    marker left behind by an abandoned pull request cannot pin the loop to
    one issue forever — the same failure shape this feature exists to
    remove, relocated from "no marker" to "a stale marker".

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
  request on the strength of an unrestricted repository-wide body or text
  search. Resume MAY, and only when the item has no usable marker, fall
  back to a search restricted to open pull requests carrying the ownership
  label the loop applies to its own pull requests (FR-013); a pull request
  is adopted only when it carries that label **and** cites this item's
  issue — the label establishes that the pull request is the loop's, the
  citation establishes which item it belongs to. The fallback MUST NOT be
  widened by pull request body text alone, by title, by author, or by head
  branch naming convention, none of which distinguish the loop's own work
  from a third party's or stay in sync with the fix step by themselves.

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
  it, per this repository's single-home rule. That home MUST be the
  existing eligibility decision that already owns issue classification and
  exclusion, with selection consulting the in-flight answer before the
  oldest-first scan — so the loop keeps one definition of "which issue does
  the loop act on" and the in-flight branches are covered by that
  decision's existing fixture-driven gate rather than a second harness. The
  eligibility decision's inputs accordingly grow to include each issue's
  own comments, where the marker lives, alongside the issues and label
  events it already takes. The in-flight decision MUST NOT be left inline
  in the selecting job's shell, where no fixture can exercise it — that
  shape is what let this defect ship.

- **FR-012**: The in-flight decision MUST be covered by checked-in fixtures
  asserting its exact result for at least: no marker anywhere; marker at a
  pre-fix step (triage, route) with no pull request recorded; marker at a
  fix-or-later step whose recorded pull request is open; marker at a
  fix-or-later step whose recorded pull request is closed without merging;
  marker at a fix-or-later step whose recorded pull request is merged;
  marker with a terminal step; marker on an excluded issue; unparsable
  marker; two issues with non-terminal markers; and an unrelated open pull
  request citing an eligible issue with no marker present. The gate MUST
  fail loudly when a fixture file is missing rather than skipping it
  (Constitution VIII).

- **FR-013**: The loop MUST mark every pull request it opens as its own
  with an ownership label, applied as part of creating the pull request
  rather than in a later step. A run cancelled, killed, or failed between
  creating a pull request and recording its marker must still leave an
  unambiguous record that the pull request is the loop's — otherwise the
  next scheduled run has no memory of it and the fix step opens a second
  pull request for the same issue.

- **FR-014**: When resume recovers a pull request through the FR-007
  fallback rather than from a marker, the run MUST record that it did so
  and why, and MUST continue with that pull request and its branch rather
  than opening a second branch or a second pull request for the item (spec
  057 FR-054).

### Key Entities

- **Board item marker**: the loop's own record on an issue, carrying the
  step it reached, the round, the pull request number it opened, the branch
  it opened, and the base commit. Already defined by spec 057; this feature
  changes who reads it, not its shape.
- **In-flight candidate**: an open, non-excluded issue whose marker says the
  loop has unfinished work on it — at a pre-fix step on the marker's step
  alone, at the fix step or later only while the marker's recorded pull
  request is still open.
- **Loop ownership label**: a label the loop applies to every pull request
  it opens, at creation time, marking that pull request as its own. It is
  the loop's only ownership signal that survives a run dying before the
  marker is recorded, and it makes "which open pull requests did the loop
  open?" answerable without reading pull request bodies.
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
- **SC-006**: An item whose pull request was opened but whose marker was
  never recorded is resumed onto that same pull request — zero second pull
  requests opened for an issue that already has an open loop-owned one.
- **SC-007**: An item whose marker records the fix step or later and whose
  pull request has since been closed or merged never blocks selection: the
  run that follows selects by the oldest-first scan, demonstrated by
  fixture.

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
- Fixing this does not require changing the marker's fields, or how and when
  the marker is written — only who reads it and what they read instead of
  pull request bodies. The one write this feature does add is the ownership
  label of FR-013, which is applied to the pull request itself at creation
  and carries no marker content.
- The ownership label exists in the repository (or is created before first
  use), so labelling at creation time cannot fail the pull request it is
  attached to.
- Pull requests the loop opened before this change carry no ownership label
  and so are invisible to the FR-007 fallback. That is acceptable: those
  items either still carry a marker, or fall back to triage as they do
  today.
- An item whose marker records the fix step or later and whose pull request
  is gone resolves to triage (FR-008) with its reason recorded (FR-009);
  re-running triage is cheap compared with stalling the board, and the
  existing "re-derive against live GitHub state" rule (spec 057 FR-054)
  governs what the fix step does with any branch that survived.

## Dependencies

- Spec 057 (`specs/057-autonomous-board-loop`): the board item marker
  contract, the eligibility and selection contract, FR-048 and FR-054. This
  feature is a correction inside that feature's boundary.
- The board loop workflow's `select` and `resume` jobs, and the eligibility
  decision module and its gate — which this feature extends rather than
  duplicates (FR-011), including its fixture harness and the issue-comment
  input the marker needs.
- The board loop workflow's fix job, at the point where it creates the pull
  request, for the ownership label of FR-013.

## Out of Scope

- Changing the oldest-first ordering, the eligibility classification, or the
  exclusion list.
- Changing the marker's fields or when it is written.
- Changing the kill switch, the stand-down check, or the stop-comment
  handling.
- Retrofitting markers onto items the loop worked before this change, or
  the ownership label onto pull requests it opened before this change.
- Using the ownership label for anything beyond resume's narrowed fallback
  (FR-007) — it does not become an eligibility input, a routing signal, or a
  substitute for the marker.
