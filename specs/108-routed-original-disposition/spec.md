# Feature Specification: Routed-Original Disposition

**Feature Branch**: `108-routed-original-disposition`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "board-loop: routing an issue to a spec-request leaves the original open, so every routed issue counts twice on the board"

## Clarifications

### Session 2026-09-29 — answered on lifecycle issue #791

- Q1: Which disposition — (a) close the originating issue at route time,
  (b) keep it open and close it when the spec's final PR merges, or (c)
  relabel the original as the spec-request rather than filing a new issue?
  → A: **(a) Close the originating issue at route time**, as a duplicate of
  the new spec-request. Re-admission becomes "a maintainer reopens the
  original", and the contract text naming the removal of `board:stalled` as
  the sole re-eligibility condition is updated to name reopening as well.
  The check that holds every site to the rule extends the existing
  spec-request-site gate's check rather than standing up a second gate.
  (FR-001, FR-006, FR-012, FR-014, FR-015, User Stories 1–3)
- Q2: Is a one-time reconciliation of the existing pairs in scope, or does
  this feature cover only routings made after it ships? → A: **Out of
  scope.** The pairs outstanding when the request was filed have already
  been reconciled by hand — #661, #660, #609, #602, #551, #536 and #527
  closed as duplicates, #662 and #604 closed by their fixes — and the one
  pair left, #633/#768, closes when #634 merges. This feature covers
  routings made after it ships. (FR-016, SC-007)
- Q3: When a spec-request is closed without its work landing, does the
  disposed originating issue return to the board, stay disposed, or become
  a maintainer's manual call? → A: **It stays disposed, under a notice.**
  The original stays closed and a notice is posted on it stating that
  reopening it returns the request to the board. This reuses Q1's
  re-admission path and keeps the surviving manual step visible on the
  issue rather than silently assumed, as Principle IV requires. (FR-017,
  Edge Cases)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The board counts a routed request once (Priority: P1)

A maintainer opens the issue list to see how much work is outstanding. Some
of those issues were routed by the board loop to the spec pipeline: the
loop filed a new spec-request carrying the same title and left the
original open with a `board:stalled` label and a comment. The maintainer
sees the same request twice and cannot tell, from the list alone, which of
the two is the live one.

After this feature, one routed request contributes exactly one open issue
to the board: the spec-request, which is the live one a maintainer acts
on. The originating issue is closed as a duplicate of it, with the reason
stated on the issue and a link to its counterpart.

**Why this priority**: This is the reported defect. Ten of roughly
ninety-three open issues are duplicate pairs, so the board's size
overstates the outstanding work by about a tenth, and it keeps growing
because every route adds another pair.

**Independent Test**: Route one issue to a spec-request and count the open
issues attributable to that request before and after. Before: two. After:
one. No other board behaviour needs to change for this to deliver value.

**Acceptance Scenarios**:

1. **Given** an eligible open issue the board loop's route step judges
   spec-shaped, **When** the route files its spec-request, **Then** the
   spec-request is the only one of the two open once the route step
   finishes, and the originating issue is closed as a duplicate of it with
   that reason recorded on it.
2. **Given** the fix job's post-push backstop breach files a spec-request
   for the originating issue, **When** that site finishes, **Then** the same
   single-open-issue outcome holds as in scenario 1.
3. **Given** the readiness job's backstop breach files (or reuses) a
   spec-request for the originating issue, **When** that site finishes,
   **Then** the same single-open-issue outcome holds as in scenario 1.
4. **Given** a routed request whose remaining open issue is later resolved,
   **When** a maintainer reads either issue, **Then** each one links to the
   other, so the history of the request is legible from whichever one they
   found first.

---

### User Story 2 - The loop's state survives the disposition (Priority: P1)

The originating issue carries the board loop's own state: a `board:stalled`
label, step markers the loop posts as comments, and the comment thread a
maintainer's stop request is read from. Disposing of that issue must not
strand any of it — a disposed issue must not be silently re-admitted to the
board, and must not become a place where a maintainer's stop request is
posted but never read.

**Why this priority**: Equal to US1 because it is the risk US1 creates.
Today, removing `board:stalled` is the sole re-eligibility condition, and
that marker lives on the originating issue. Getting US1 without US2
trades a cosmetic board-size problem for a loop that can re-route a
request it already routed, or that can ignore a stop.

**Independent Test**: Put an issue through a route, then exercise each
reader of the originating issue's state — re-admission, the step-marker
read, the stop-request read — and confirm each behaves as specified for a
disposed issue.

**Acceptance Scenarios**:

1. **Given** an originating issue disposed of by a route, **When** the
   board loop next selects work, **Then** that issue is not selected and
   not treated as an in-flight board item of the loop's.
2. **Given** an originating issue disposed of by a route, **When** a
   maintainer removes `board:stalled` from it without reopening it,
   **Then** it is still not re-admitted to the board on that ground alone.
3. **Given** a request whose remaining open issue is the live one, **When**
   a maintainer posts a stop request, **Then** the stop is read from an
   issue the loop is still reading, and the loop halts before its next
   durable action.
4. **Given** a maintainer who wants a disposed request reconsidered,
   **When** they reopen the originating issue — the documented
   re-admission action — **Then** the request re-enters the board exactly
   once, without a second spec-request being filed for it.

---

### User Story 3 - A gate holds every spec-request site to the rule (Priority: P2)

The loop files spec-requests from three places. A rule that only one of
them follows is a rule that decays at the next site added.

**Why this priority**: The behaviour in US1/US2 is worth having from the
first site; the gate is what keeps it from drifting back. It is P2 because
it protects the change rather than delivering it.

**Independent Test**: Feed the gate a fixture workflow whose spec-request
site omits the close-the-original step and confirm the gate fails on it;
feed it the real workflow and confirm it passes.

**Acceptance Scenarios**:

1. **Given** a workflow in which a spec-request site files its request but
   never closes the originating issue, **When** the gate suite runs,
   **Then** the gate fails and names the offending site.
2. **Given** a workflow in which every spec-request site closes its
   originating issue, **When** the gate suite runs, **Then** the gate
   passes.
3. **Given** a workflow with no spec-request site at all, **When** the gate
   runs, **Then** it fails rather than passing vacuously.

---

### Edge Cases

- **The original is disposed while spec 097's stop point or spec 100's
  re-admission semantics apply to it.** Disposition supersedes both. A
  closed original is never a stop-request source (FR-008 directs a
  maintainer to the spec-request), and re-admission of a disposed original
  follows FR-006 rather than spec 100's label-removal path.
- **The spec-request is filed but the disposition step then fails.** The
  request must not end up with zero open issues, and a later run must not
  file a second spec-request for it. The outcome must be a state a
  maintainer can see and a later run can finish.
- **The disposition step runs but the spec-request was never filed.** The
  originating issue must be left in a state a later run retries, never
  disposed of with nothing to point at — the existing create-guard
  behaviour at each site (a failed create leaves the issue unstalled so a
  later run retries) must continue to hold.
- **The readiness site reuses a spec-request a previous run already filed.**
  The disposition must be idempotent: running it a second time on an
  already-disposed issue is not an error and does not produce a second
  comment or a second spec-request.
- **The spec-request is closed without its work landing** — a maintainer
  declines it, or intake cannot produce a specification from it. The
  originating issue stays closed; a notice is posted on it stating that
  reopening it returns the request to the board, so the manual step is
  visible where a maintainer will find it (Clarification Q3).
- **The originating issue was authored by someone other than a
  maintainer.** Disposing of it is a visible action taken on another
  person's issue, so the reason must be stated on the issue itself, not
  only in the run log.
- **The originating issue is already closed when a site reaches its
  disposition step** (a maintainer closed it mid-run). The step must treat
  the close as already satisfied rather than failing the job, while still
  recording the reason and the cross-link if it has not already done so.
- **The ten pairs that already exist.** They predate this feature and are
  not produced by it; they were reconciled by hand outside it, and this
  feature covers only routings made after it ships (Clarification Q2).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The board loop MUST dispose of the originating issue whenever
  it files a spec-request for it, by closing that issue as a duplicate of
  the spec-request at the time the spec-request is filed, so that exactly
  one open issue — the spec-request — represents that request on the board.
- **FR-002**: FR-001 MUST hold at every site from which the loop files a
  spec-request: the route step's spec verdict, the fix job's post-push
  backstop breach, and the readiness job's backstop breach.
- **FR-003**: The disposition MUST be performed by deterministic code, not
  by an agent's judgment, and MUST be recorded on the issue it disposes of
  with a stated reason and a link to the counterpart issue.
- **FR-004**: The disposed issue and its counterpart MUST each link to the
  other, through the loop's existing single cross-link mechanism rather
  than a second hand-written link format.
- **FR-005**: The board loop MUST NOT select, or treat as an in-flight item
  of its own, an issue it has disposed of under FR-001.
- **FR-006**: Removing `board:stalled` from a disposed issue MUST NOT, on
  its own, re-admit it to the board. The documented way to reconsider a
  disposed request is a maintainer reopening the originating issue. The
  loop MUST treat an open originating issue whose newest route/stall
  marker names a closed spec-request as re-admitted, notwithstanding
  `board:stalled`, and MUST route it afresh at most once per reopen. While
  the linked spec-request is still open, a reopen MUST NOT file a second
  spec-request.
- **FR-007**: Every reader of the originating issue's loop state — step
  markers, the stop-request scan, and the re-admission decision — MUST
  continue to reach a correct answer after the disposition, either by
  reading the issue that remains open or by treating the disposed issue's
  state as settled.
- **FR-008**: A maintainer's stop request MUST remain effective for a
  routed request: it MUST be honoured when posted on whichever issue the
  loop still reads, and the issue a maintainer is directed to MUST be that
  one.
- **FR-009**: The disposition MUST be idempotent: applying it to an issue
  already disposed of for the same spec-request MUST succeed without
  filing a second spec-request, posting a duplicate comment, or failing
  the job.
- **FR-010**: A failure of the disposition step after the spec-request was
  successfully filed MUST leave a state that a maintainer can read and that
  a later run resolves without filing a second spec-request; it MUST NOT
  leave the request with zero open issues.
- **FR-011**: A failure to file the spec-request MUST leave the originating
  issue undisposed and retryable, preserving each site's existing
  create-guard behaviour.
- **FR-012**: A gate MUST fail when any spec-request site in the board-loop
  workflow files a request without also closing the originating issue, MUST
  fail rather than pass when it finds no spec-request site to check, and
  MUST ship a checked-in fixture for each failure branch it can report.
  This check MUST extend the existing gate check that already enumerates
  the spec-request sites, rather than standing up a second gate over the
  same subject.
- **FR-013**: The gate in FR-012 MUST be reachable from the gate registry
  and MUST run the same subject with the same arguments locally as it does
  in CI.
- **FR-014**: The documentation describing the board loop's routing
  behaviour MUST be updated to match the chosen disposition: the contract
  text stating what a route does to the originating issue MUST say the
  original is closed as a duplicate of the spec-request, and every place
  naming the removal of `board:stalled` as the sole re-eligibility
  condition MUST also name a maintainer's reopening of a disposed original.
- **FR-015**: The disposition MUST be option (a) of the three the request
  enumerates: the originating issue is closed at route time as a duplicate
  of the new spec-request. Option (b) — keeping it open until the spec's
  final PR merges — and option (c) — relabelling the original instead of
  filing a new issue — MUST NOT be implemented.
- **FR-016**: Pairs that already exist on the board when this feature ships
  are out of scope: this feature MUST cover routings made after it ships,
  and MUST NOT ship a one-time reconciliation of the pre-existing pairs,
  which were reconciled by hand outside it.
- **FR-017**: When a spec-request is closed without its work landing, its
  disposed originating issue MUST stay closed, and a notice MUST be posted
  on that issue stating that reopening it returns the request to the board
  — the same re-admission path as FR-006, so the surviving manual step is
  reported on the issue rather than silently assumed. The closure MUST be
  detected by the board loop's scheduled scan (a spec-request this loop
  filed that is closed with no merged final PR), and the notice MUST be
  idempotent: one notice per closure. The same notice MUST also be posted
  on the closed spec-request, so the surviving manual step is reported
  where its lifecycle ended (Principle IV).

### Key Entities

- **Originating issue**: the issue the board loop selected and routed. It
  carries the loop's state today — `board:stalled`, step markers posted as
  comments, and the comment thread a stop request is read from.
- **Spec-request**: the issue the loop files to hand the request to the
  spec pipeline, labelled so intake picks it up, its body built from the
  route agent's drafted request or the originating issue's trust-filtered
  context.
- **Disposition**: the durable action that reduces the pair to one open
  issue — closing the originating issue as a duplicate of the spec-request,
  with the reason stated on it — together with the cross-link that makes
  each issue reachable from the other.
- **Spec-request site**: one place in the board loop that files a
  spec-request. There are three: route's spec verdict, fix's post-push
  breach, and readiness's backstop breach.
- **Re-admission**: the condition under which a disposed request returns to
  the board's eligible set — a maintainer reopening the closed originating
  issue. Removing `board:stalled` alone no longer suffices for a disposed
  issue.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a request is routed to the spec pipeline, exactly one
  open issue on the board represents it — down from two today.
- **SC-002**: All three spec-request sites dispose of their originating
  issue; a reviewer can confirm this by reading the sites, and a gate fails
  if any one of them stops doing it.
- **SC-003**: Every failure branch the disposition can take is exercised by
  a checked-in fixture, so no branch is proved only by a manual
  demonstration.
- **SC-004**: A maintainer reading either issue of a routed request reaches
  the other in one click, and the closed one states why it was closed.
- **SC-005**: No routed request can be routed twice: a disposed request
  produces no second spec-request unless a maintainer reopens the
  originating issue after its linked spec-request has closed, and then at
  most one per reopen.
- **SC-006**: A maintainer's stop request on a routed request halts the
  loop before its next durable action, as it does today.
- **SC-007**: The count of open issues attributable to duplicate routing
  pairs is zero for routings made after this feature ships.

## Assumptions

- The three spec-request sites named in the request (route's spec verdict,
  fix's post-push breach, readiness's backstop breach) are the complete set
  at the time of writing; the gate in FR-012 is what keeps a fourth from
  being added without a disposition.
- `board:stalled` continues to exist and continues to mean "the loop has
  handed this item to a human"; this feature changes what routing does to
  the originating issue, not what the stall marker means for the other
  stall paths (review inconclusive, round budget spent, gate suite red).
- Retry and idempotency work at these same sites is tracked separately
  (issues #527 and #701) and is not re-specified here; this feature must
  not make that work harder, which is why FR-009/FR-010/FR-011 state the
  properties it must preserve rather than redesigning the retry.
- The issue's claim that ten pairs exist and that the board holds roughly
  ninety-three open issues is a snapshot from the time of filing; the exact
  counts will differ when this ships, and no requirement here depends on
  them.
- Closing an issue as a duplicate, and reopening one, are ordinary GitHub
  actions available to the pipeline's credential. The close uses the REST
  API's `state_reason: duplicate` rather than a `gh issue close` flag whose
  support varies by gh version.
- The feature changes this repository's own board behaviour; it does not
  widen or break the published stage-workflow contract.

## Dependencies

- The board loop's eligibility and selection logic, which decides what the
  loop may act on and what it excludes.
- The board loop's step-marker mechanism, which records where an item is.
- The stop-request scan, which reads a maintainer's stop from an issue's
  comments.
- The spec-request body builder and the issue-context composite that feeds
  it, which keep building the filed request unchanged under the chosen
  disposition (Q1a closes the original; it does not relabel it).
- The existing gate that enumerates the spec-request sites — Gate 93's
  check 3 — which Q1 names as the home for the FR-012 check.
- The board loop's scheduled scan, which detects a spec-request it filed
  that is closed with no merged final PR (no workflow listens for
  `issues: closed` today), and from which FR-017's notices are posted.
