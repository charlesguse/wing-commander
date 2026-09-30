# Feature Specification: A Not-Ready PR Releases the Board

**Feature Branch**: `spec-draft/093-not-ready-board-release`

**Created**: 2026-09-28

**Status**: Draft

**Input**: Lifecycle issue #717 — "board-loop: a PR that stays not-ready
keeps its item in flight, starving the board and re-posting 'Not ready'
hourly" (routed from board-loop.yml, originating issue #536, found by the
code review of the #532 fix on branch `fix/532-board-awaiting-merge`)

## Overview

The board loop works one issue at a time. Which issue it works is decided
by `board_eligibility.select()`, which consults
`in_flight_candidate()` **first**: an open, non-excluded issue whose newest
board-item marker names a fix-or-later step and a PR that resolves `OPEN`
outranks every other candidate, however old. That priority is what makes
the loop finish what it started instead of abandoning a half-fixed PR.

The readiness step has two outcomes. On `ready: true` the loop posts its
report and writes an `awaiting-merge` marker; that step is deliberately
excluded from the in-flight priority path and from the oldest-first
fallback, so the item **releases the board** and a human's merge is awaited
off the loop's critical path. That release is the whole point of the #532
fix.

On a not-ready outcome the loop posts "Not ready on PR #N: \<reason\>.
Picked up again on a later run." and writes **no marker at all**. The
newest marker is therefore still `step=readiness` with the PR still `OPEN`
— exactly the shape `in_flight_candidate()` prefers above everything else.
So every hourly run re-selects the same issue, re-resolves the same PR,
re-evaluates the same five conditions against the same head SHA, and
re-posts a byte-identical "Not ready" comment. Nothing else on the board is
ever reached.

This is fine when the unmet condition is something the next run clears on
its own — a `lint-workflows` run still in progress on the head the fix job
just pushed, which is the *common* case, since readiness is entered
immediately after review converges. It is a permanent wedge when the unmet
condition is one the loop cannot clear: a red required check that needs a
human's judgment, or a finding filed against the PR after review converged.
The item holds the board, the
issue accumulates one identical comment per hour, and the board stops
draining.

Spec 057's FR-067 ("the item is picked up again on a later run rather than
polled") and FR-009 ("the loop MUST select the oldest eligible open issue …
so the board drains in filing order") are both satisfiable only while the
unmet condition is self-clearing. Whenever it is not, they contradict each
other, and FR-067 wins by construction. This feature resolves that
contradiction: a not-ready outcome whose condition is durable releases the
board, the item is re-admitted on a signal that something actually changed —
through `review`, so the commits that changed it are reviewed before
anything is reported ready — and an unmet condition that will never clear on
its own reaches a human once, named, instead of being reported hourly to
nobody. A condition that clears itself, which is the common case, keeps
today's behaviour and is simply bounded.

### Observed facts (verified against main at c27d0cb; line numbers re-verified at c80476f)

- `.github/scripts/board_eligibility.py:209` skips only
  `TERMINAL_STEPS`, `"prove"` and `AWAITING_MERGE_STEP` when building the
  in-flight candidate list. `"readiness"` is in `FIX_OR_LATER_STEPS`
  (line 80), so a `readiness` marker whose PR resolves `OPEN` is an
  in-flight candidate, and `in_flight_candidate()`'s result is returned by
  `select()` before the oldest-first scan is reached (line 278).
- `.github/workflows/board-loop.yml:3919` (the `else` branch of the
  "Report the unmet condition (not ready)" step) posts
  `'Not ready on PR #%s: %s. Picked up again on a later run.'` and posts
  no marker. Compare the ready path at line 3792, which writes an
  `AWAITING_MERGE_STEP` marker precisely so the item stops being
  in-flight.
- `specs/057-autonomous-board-loop/contracts/readiness-report.md:57-58`
  states the current behaviour as a design choice: "A not-ready outcome
  leaves the marker as it was, so the next run picks the item up at
  `readiness` again."
- The unmet reason does not distinguish a check that is *still running*
  from one that *failed*. `.github/scripts/board_readiness.py:39-41`
  rejects any rollup entry whose state is not `SUCCESS`/`NEUTRAL`/
  `SKIPPED` — `PENDING`, `QUEUED` and `IN_PROGRESS` included — and the
  reason string is the single phrase
  `"checks not green on head_sha {0} (stale or failing)"` (line 87). No
  code-level signal today tells a self-clearing unmet condition from a
  durable one.
- The readiness job emits a metrics record on every run with
  `run-label: 'not ready'` (board-loop.yml:3951). A wedged item therefore
  produces one durable "not ready" record per scheduled run, indefinitely.
- The precedent for the terminal hand-to-human already exists and is
  named: spec 057 FR-030's `board:stalled` is "the loop's single
  hand-to-human marker", `is_excluded()` skips on it
  (board_eligibility.py:150), and removing it MUST be the sole condition
  that makes the item eligible again.
- The precedent for a fail-safe hold also exists:
  `_awaiting_merge_holds()` (board_eligibility.py:226-248) skips an item
  whose PR state is *unknown* rather than re-admitting it, on the stated
  ground that re-admitting would recreate the #532 wedge.

## Clarifications

Three decisions in this specification were the owner's, not the pipeline's.
They were posted on lifecycle issue #717 as the intake questionnaire and
answered there. All three are resolved and no `[NEEDS CLARIFICATION]`
marker remains.

- **Q1 (FR-004, FR-008)** — which release mechanism: bound the re-checks
  into a terminal stall, hold the item until its PR head moves, or both.
  **Resolved: both.** The item releases the board from its first not-ready
  outcome and is passed over while its PR head SHA is unchanged;
  separately, after **3** not-ready outcomes on the same PR it is handed to
  a human under `board:stalled`. Holding alone would leave an item nobody
  was told about; bounding alone would keep starving the board and
  re-posting until the bound was reached.
- **Q2 (FR-005)** — is a self-clearing unmet condition (a check still
  running on the head) treated the same as a durable one? **Resolved (A):
  no — exempt from the hold, still counted toward the threshold.** A check
  still running is exactly the case where "picked up again on a later run"
  is the right answer, so holding it would wedge the common case; a check
  that never leaves `in_progress` still consumes the threshold and so
  eventually reaches a human.
- **Q3 (FR-007)** — when a held item is re-admitted because its PR head
  moved, does it re-enter at `readiness` or go back through `review`?
  **Resolved (B): `review`.** A human's new commits get an independent
  review before anything is reported ready, keeping the constitution's "an
  independent review … has zero open findings" true of every commit a ready
  report covers. Re-admission continues the item's existing fix→review
  round budget rather than resetting it, so repeated human pushes cannot
  loop review without bound. This is the one answer that replaced the
  draft's recorded default (resume at `readiness`).

Q1 was answered A. The numbering and letters above are the questionnaire's
own, as posted on #717.

### Status update 2026-09-29 — reconciled with current `main`

- **Stand-down at readiness writes nothing (#782).** Every readiness
  durable step, the not-ready comment included, is now gated on the kill
  switch / stop-request re-check, so a paused run posts no "Not ready"
  comment and no record. FR-006 therefore already holds on `main` and must
  be preserved, not built; a kill switch is no longer a cause of the wedge.
- **`board:stalled` ordering is single-homed (#782).** Every stall site
  applies the label through `board_item_marker.add_stalled_label()` before
  rendering a marker; FR-008's handover uses that helper.
- **Merged specs are frozen records (#725, CLAUDE.md).** Spec 057's
  `spec.md` is not edited; FR-014 corrects only the live contracts.
- **The loop's concurrency is per-job (spec 060, #490)**, still with one
  board item in flight repository-wide.
- **Reconciled with spec 100 (maintainer decision, 2026-09-29).**
  `add_stalled_label()`'s docstring on `main` resumes a label-removed item
  at `review` whenever an open `board:owned` PR cites the issue, and spec
  100 (#752) gated that rule. The owner chose this spec's refinement: a
  label-removed item resumes at `review` when its PR head has moved since
  the last review, and at `readiness` when it has not (FR-007), so an
  unchanged, already-reviewed head is never reviewed again. Spec 100's
  FR-006 and its gate encode this combined rule, and `add_stalled_label()`'s
  canonical statement is updated to match; the fresh review-round budget on
  re-admission (spec 100 FR-009) is unchanged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The board keeps draining past a PR the loop cannot finish (Priority: P1)

A maintainer files three issues. The loop picks the oldest, fixes it,
reviews it, and reaches readiness on its PR — where a required check is red
for a reason only a human can resolve. The maintainer comes back the next
morning expecting the other two issues to have been worked. They have been:
the not-ready PR released the board on the run that reported it, and the
loop moved on.

**Why this priority**: this is the defect. Without it the loop's throughput
collapses to zero on the first unresolvable readiness outcome, and every
later issue waits on a human who has not been told anything is waiting.

**Independent Test**: fully testable through the eligibility decision's own
checked-in fixtures: a not-ready-held item plus a second eligible issue,
asserting the decision returns the second issue. No live run needed.

**Acceptance Scenarios**:

1. **Given** an issue whose newest marker records a **durable** not-ready
   outcome for an `OPEN` PR, and a second, newer eligible issue with no
   marker, **When** the selection decision runs, **Then** the held item is
   not the in-flight candidate and the second issue is selected.
2. **Given** the same board on the next scheduled run, **When** the run
   completes, **Then** no second "Not ready" comment has been added to the
   held issue and no readiness evaluation was performed on its PR.
3. **Given** a board on which the held item is the *only* non-excluded
   issue, **When** the run completes, **Then** it is a clean no-op that
   reports "nothing to do" and costs one cheap read — not a readiness
   re-evaluation, and not a failure.
4. **Given** a board on which two separate items are each held not-ready,
   **When** a third eligible issue exists, **Then** the third issue is
   selected; neither held item is chosen and neither blocks the other.
5. **Given** an item whose newest not-ready record names a **self-clearing**
   unmet condition — a required check still queued or in progress on the
   recorded head — **When** the selection decision runs, **Then** the item
   is *not* held and remains the in-flight candidate, so the common case
   still clears itself; the outcome is nevertheless counted toward the
   threshold, so it cannot be re-checked without bound.

---

### User Story 2 - An unmet condition that will never clear itself reaches a human, once, named (Priority: P1)

The red required check on the PR above needs a human decision. Rather than
appearing as the 40th identical comment on the issue, it appears once: a
notice naming the unmet condition, the head SHA it was measured on, and the
`board:stalled` label whose removal is the sole thing that puts the item
back in play.

**Why this priority**: releasing the board without a handover would trade a
starved board for a silently abandoned issue. The loop's bound is the shape
of the work, not its confidence (Constitution X); when the work leaves that
shape it hands over, and the handover is what makes the release safe.

**Independent Test**: testable by driving the readiness decision with a
fixture whose unmet condition is durable and asserting the handover
artifacts — label, notice text, terminal marker — are exactly the ones
FR-030 already defines, with no merge and no second PR.

**Acceptance Scenarios**:

1. **Given** a not-ready outcome whose unmet condition the loop cannot
   clear, **When** the handover threshold is reached, **Then** the issue
   carries `board:stalled`, the PR is left open and unmerged, and one
   notice names the unmet condition, the PR, the head SHA measured, and
   that removing the label is the sole condition that makes the item
   eligible again.
2. **Given** that handed-over item, **When** later runs select, **Then** it
   is excluded from selection entirely (the existing label exclusion), with
   no new comment of any kind.
3. **Given** a maintainer who removes `board:stalled` without touching the
   PR, **When** the next run selects, **Then** the item is eligible again
   and readiness is re-evaluated directly on the PR's current head — the
   head a review has already covered, so FR-007's invariant needs no review
   round here.
4. **Given** a readiness run that stands down on the kill switch or a stop
   request, **When** the run ends, **Then** no handover occurs and the item
   is not counted toward the handover threshold — an owner pausing the loop
   never stalls the items that were in flight (already true on `main`
   since #782, which writes nothing on a stand-down; preserved here).

---

### User Story 3 - A moved head brings the item back without a human (Priority: P2)

A human pushes the one-line fix that turns the red check green. On the next
scheduled run the loop notices the PR's head is no longer the head it
reported not-ready on and picks the item back up — at `review`, because the
human's commits have never been reviewed. The review returns no open
findings, readiness runs on that head, and the item is reported ready. No
label was removed by hand.

**Why this priority**: it is what keeps the release from costing a human
action in the recoverable case. Without it every not-ready item needs a
label removed by hand even when the underlying problem is already fixed.
Resuming at `review` rather than at `readiness` is what keeps the ready
report covering only commits an independent review has seen.

**Independent Test**: fixture pair over the same held item — one with
`pr_state_by_number`/head data matching the recorded head SHA (held), one
with a different head SHA (admitted) — asserting opposite selection
outcomes from the same decision, and asserting the admitted one resolves to
the `review` step.

**Acceptance Scenarios**:

1. **Given** a held item whose PR's current head SHA differs from the one
   the not-ready record names, **When** the selection decision runs,
   **Then** the item is admitted and is the in-flight candidate again, and
   the step it resolves to is `review` — not the `readiness` its marker
   names — with that resolution and its reason recorded.
2. **Given** a held item whose PR's current head SHA is unchanged, **When**
   the selection decision runs, **Then** the item is passed over by both
   the in-flight path and the oldest-first fallback.
3. **Given** a held item whose PR's current head SHA cannot be determined
   this run (a failed lookup, or an unparsable record), **When** the
   selection decision runs, **Then** the item is passed over rather than
   admitted, and the run records why.
4. **Given** a held item whose PR is closed or merged while held, **When**
   the selection decision runs, **Then** the existing stale-marker
   handling applies unchanged — the item is not held by this feature's rule
   for a PR that is no longer open.
5. **Given** a held item re-admitted on a moved head, **When** it resumes at
   `review`, **Then** it consumes the next round of the fix→review round
   budget it had already partly spent, rather than starting a fresh budget.
6. **Given** a held item whose head moves again after its round budget is
   exhausted, **When** it is re-admitted, **Then** spec 057 FR-030's
   existing exhausted-budget handover applies and no second, parallel
   handover is created beside it.

---

### User Story 4 - Every new rule is provable at PR time (Priority: P3)

A maintainer reviewing the implementing PR can see each new rule fail when
it is removed, without waiting for a scheduled run and without a live PR in
a red state.

**Why this priority**: the defect this feature fixes shipped because the
in-flight decision's fixtures covered `awaiting-merge`, `prove`, `breach`
and the unowned-PR hold, but no case where the *readiness* step itself is
the one that must release the board. A rule with no gate behind it lasts
until the next session (CLAUDE.md).

**Independent Test**: run the gate suite locally; every added fixture and
self-test mutation passes or fails on its own.

**Acceptance Scenarios**:

1. **Given** the extended eligibility gate, **When** the hold rule is
   deleted from the decision, **Then** at least one checked-in fixture
   fails with a clear message.
2. **Given** the extended eligibility gate, **When** the handover
   threshold is raised to infinity, **Then** at least one checked-in
   fixture fails.
3. **Given** the resume-gating gate's self-test, **When** the not-ready
   site's record write is dropped from the workflow, **Then** the self-test
   fails.
4. **Given** the full local gate suite, **When** it is run on the
   implementing branch, **Then** every existing board-loop fixture —
   `awaiting-merge-*`, `breach-*`, `prove-no-pr`, `unowned-open-pr`, the
   forged-marker cases — still passes unchanged.

---

### Edge Cases

- **A check still running on the head, which is the common case.**
  Readiness is entered immediately after review converges, so the fix
  job's own push frequently has a `lint-workflows` run in progress. A hold
  that treats this like a red check would wedge nearly every PR the loop
  produces, permanently, because the head never moves again. This is why
  Q2 was asked, and the owner's answer is that a self-clearing condition is
  exempt from the hold (FR-005): the item is re-checked, so the common case
  clears itself, while the threshold still bounds a check that never leaves
  `in_progress`.
- **The kill switch is the unmet condition.** An owner who pauses the loop
  for a day must not find every in-flight item stalled and needing a label
  removed by hand. The kill switch is an owner action, not a property of
  the item. Since #782 a stand-down at readiness posts nothing, so this
  holds today and must stay true.
- **The PR head moves because the loop itself pushed it.** Between a
  not-ready report and the next run the loop does not push to a held item's
  PR (it is not selected). A head that moved was moved by a human, so its
  new commits have never been through the loop's review — which is why Q3's
  answer resumes the item at `review` (FR-007), not at `readiness`.
- **The head moves repeatedly without ever going green.** A human pushing
  five failed attempts must not buy five more re-check cycles indefinitely.
  The handover threshold counts not-ready outcomes for the PR, not for a
  single head SHA. Because Q3's answer resumes at `review`, the same push
  pattern must also not buy unbounded review invocations: re-admission
  continues the item's existing fix→review round budget rather than
  resetting it (FR-007), so two bounds apply to the same PR and whichever
  is reached first hands the item over.
- **A backstop breach at readiness.** Already terminal today: it files a
  spec-request, applies `board:stalled`, and writes a `stalled` marker.
  This feature must not add a second, parallel handover beside it.
- **An open in-scope finding at readiness.** Possible only if a finding
  was filed after review converged. It is durable — no later run clears it
  without work — so it takes the durable path.
- **The record of the not-ready outcome is unreadable.** Missing,
  unparsable, or written by someone other than the loop's own App. It must
  degrade to the fail-safe (pass the item over, record why), never to
  admitting an item that would then re-post hourly, and never to raising.
- **A maintainer comments on the held issue.** A non-maintainer or
  maintainer comment is data, never a value that changes the recorded step,
  head SHA, or count (spec 057 FR-056).
- **`board:stalled` removed while the PR is still not ready.** The item is
  eligible again; it resumes at `readiness` if its head is the one the last
  review covered and at `review` if a human pushed to it as well (FR-007's
  invariant), and the not-ready threshold starts from the re-admission —
  removing the label is a deliberate "try again", not a request for one more
  identical comment. Note the asymmetry with FR-007: a *label removal* is a
  human's explicit reset of the not-ready count, whereas a *moved head* is
  not, and continues the round budget. The two are different signals and are
  counted differently on purpose.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A not-ready readiness outcome whose unmet condition is
  **durable** (FR-005) MUST release the board in the same run that reports
  it. On the next scheduled run the item MUST NOT be the in-flight
  candidate solely because its newest marker records a fix-or-later step
  with an `OPEN` PR. A **self-clearing** unmet condition is FR-005's
  exemption: the item stays in flight and is re-checked on later runs,
  bounded by FR-004's threshold rather than released by the hold.
- **FR-002**: The not-ready outcome MUST be recorded durably on the issue,
  by the loop's own deterministic code, carrying at minimum: the PR, the
  exact head SHA the decision was derived from, the unmet condition, and
  enough information for a later run to decide whether this feature's hold
  and threshold apply. The record MUST be machine-readable without parsing
  prose, and MUST accompany a human-legible outcome rather than being the
  comment's only content (spec 057 FR-044).
- **FR-003**: The decision "is this item held not-ready?" MUST be made in
  deterministic code (Constitution IX) inside the existing single home for
  in-flight detection — the module `select()` and `in_flight_candidate()`
  already live in — and MUST NOT be re-derived inline in a workflow `run:`
  step or in a second module (spec 057 FR-011; CLAUDE.md "Shared logic has
  exactly one home"). Both the in-flight priority path and the
  oldest-first fallback MUST consult that one rule, never a second,
  parallel copy of it.
- **FR-004**: The loop MUST release a not-ready item by **both** mechanisms
  together, so an item both releases the board immediately and is
  guaranteed to reach a human eventually:
  - **(a) the bound.** After a fixed number of not-ready outcomes on the
    same PR — **3**, recorded as a value in **Assumptions** — the loop MUST
    hand the item to a human (FR-008) and MUST stop re-checking it.
  - **(b) the hold.** While the PR's current head SHA is unchanged from the
    one the newest not-ready record names, the item MUST be passed over by
    both selection paths.

  FR-001 MUST hold from the first not-ready outcome — the release MUST NOT
  wait for the threshold to be reached. The two mechanisms MUST be one
  decision in one place (FR-003), not a hold rule and a counting rule with
  separate homes.
- **FR-005**: The readiness decision MUST expose, as a code-level value,
  whether the unmet condition is **self-clearing** (no work is required of
  anyone for a later run to reach a different outcome on the same head —
  a check still queued or in progress) or **durable** (a later run on the
  same head reaches the same outcome). A self-clearing unmet condition
  MUST be **exempt from FR-004(b)'s hold**, so the item is re-checked on
  later runs, and MUST **still be counted toward FR-004(a)'s threshold**,
  so a check wedged in progress forever is eventually handed over. A
  durable unmet condition MUST take both the hold and the count. The
  distinction MUST come from the rollup's own per-entry states, never from
  an agent's reading of them.
- **FR-006**: The kill switch being the unmet condition MUST NOT count
  toward any handover threshold and MUST NOT trigger a handover. A paused
  loop MUST leave the items that were in flight exactly as eligible as
  they were before the pause.
- **FR-007**: When a held item is re-admitted because its PR head moved,
  the run MUST resume it at **`review`**, not at `readiness`: the human's
  new commits go through an independent review before anything is reported
  ready, at the cost of one review agent invocation per human push. The
  invariant behind that choice MUST hold on every re-admission path, not
  only this one — **nothing is reported ready on a head whose commits no
  review has covered.** An item re-admitted by a human removing
  `board:stalled` therefore resumes at `review` too when its head has moved
  since the last review, and at `readiness` when it has not. Re-admission on
  a moved head MUST **continue** the item's existing fix→review round budget
  (spec 057 FR-030) rather than resetting it, so repeated human pushes
  cannot loop review without bound; an exhausted budget takes FR-030's
  existing handover and not a second one (FR-012). The run MUST record which
  step it resumed at and why (spec 061 FR-014's existing provenance rule for
  a resume that did not come straight from the marker).
- **FR-008**: When the handover threshold is reached, the loop MUST hand
  the item to a human using the mechanism spec 057 FR-030 already defines
  and no other: the PR is left open and unmerged, the issue carries the
  `board:stalled` label, one notice names the unmet condition, the PR and
  the head SHA it was measured on, the notice states that removing that
  label is the sole condition that makes the item eligible again, and a
  terminal marker is written. The label MUST be applied before the
  terminal marker is written, and a failed label application MUST fail the
  step — the ordering every stall site uses through
  `board_item_marker.add_stalled_label()` (#782). The threshold exists by
  FR-004(a); its numeric value is recorded in **Assumptions** as one more
  checked-in constant, not as a second mechanism.
- **FR-009**: The loop MUST NOT post an unmet-condition comment that is
  identical to the newest one already on the issue for the same PR, head
  SHA and unmet condition. At most one such comment MUST exist per
  (PR, head SHA, unmet condition) triple.
- **FR-010**: A held or handed-over item MUST NOT have a second branch or
  PR cut beside the one it already has (spec 057 FR-054), and the loop
  MUST NOT merge, approve, or enable auto-merge on it (spec 057 FR-068).
- **FR-011**: When the information this feature's rule needs cannot be
  determined on a given run — the record is missing, unparsable, or not
  from the loop's own App; the PR's current head SHA does not resolve —
  the item MUST be passed over rather than admitted, and the run MUST
  record why. Passing over costs this one item a delay; admitting it
  recreates the wedge, because the resume path would report the same
  outcome again with nothing changed (the `_awaiting_merge_holds()`
  precedent).
- **FR-012**: A readiness outcome that is a size-and-path backstop breach
  MUST keep its existing terminal path unchanged — spec-request,
  `board:stalled`, `stalled` marker — and MUST NOT additionally take this
  feature's hold or threshold path. There MUST be exactly one handover per
  item, never two notices for the same stop.
- **FR-013**: Every rule this feature adds MUST be exercised by
  checked-in fixtures in the existing eligibility gate (no new gate) and,
  where the rule lives in the workflow's own text, by a mutation in the
  existing resume-gating gate's self-test. At minimum: a held item passed
  over with a second issue selected instead; the same item admitted once
  its head moves; a re-admitted item resolving to `review` rather than
  `readiness`, with the resumed step and its reason recorded; a
  re-admission that continues rather than resets the round budget, and one
  whose continued budget is already exhausted, taking spec 057 FR-030's
  handover and not a second one; the unknown-head fail-safe; the threshold
  reached producing the handover; the kill-switch exemption; the
  self-clearing versus durable distinction, including a self-clearing item
  that is re-checked rather than held yet still consumes the threshold; and
  the backstop-breach path unchanged.
- **FR-014**: The governing prose MUST be corrected wherever it states the
  superseded behaviour, in the same change, in the live contracts (spec
  057's `spec.md` is a frozen record and is not edited — CLAUDE.md, #725):
  spec 057's `contracts/readiness-report.md` "A not-ready outcome leaves the
  marker as it was" sentence, and spec 061's `contracts/in-flight-detection.md`
  and `contracts/resume-recovery.md` where they enumerate which steps make
  an item in-flight. `contracts/resume-recovery.md`'s step-resolution clause
  list MUST additionally gain the clause FR-007 adds — a re-admitted
  not-ready item resolves to `review`, not to the marker's own `readiness`
  step — including its row in that contract's scenario table. The corrected
  statement MUST be canonical in one
  place, with every other site pointing at it rather than restating it
  (CLAUDE.md). FR-067's reconciliation with FR-009 MUST be stated
  explicitly in that contract — "picked up again on a later run" is bounded, not
  unconditional.
- **FR-015**: Existing behaviour that this feature does not govern MUST be
  unchanged and MUST be shown unchanged by the existing fixtures passing
  as they are: the `ready: true` handover to `awaiting-merge`, the `prove`
  skip, the `breach` step's in-flight treatment, the unowned-open-PR hold,
  the forged-marker author rule, and the five readiness conditions
  themselves.

### Key Entities

- **Not-Ready Record**: the durable, machine-readable record of one
  not-ready readiness outcome, written by the loop on the issue. Carries
  the PR it was evaluated on, the head SHA evaluated, the unmet condition,
  whether that condition was self-clearing or durable, and how many
  not-ready outcomes have accumulated for this PR. It is the only thing a
  later run reads to decide whether the item is held — never the issue's
  prose, never a comment's text, never a value captured earlier in the
  same run.
- **Hold**: the state of an item that has a **durable** not-ready record and
  is currently passed over by both selection paths. A hold is not a
  disposition and not a label — it is derived on each run from the record
  plus the PR's live head SHA, and it ends by itself. An item whose newest
  not-ready record is self-clearing is never held (FR-005).
- **Re-admission**: the end of a hold, on a run that finds the PR's current
  head SHA different from the one the record names. It resolves the item to
  the `review` step rather than the `readiness` its marker records (FR-007),
  and it continues the item's existing fix→review round budget.
- **Handover**: the terminal state of an item whose not-ready outcomes
  reached the threshold, or whose continued round budget was exhausted.
  Expressed only as spec 057 FR-030's existing
  `board:stalled` label plus notice plus terminal marker; cleared only by
  a human removing the label.
- **Unmet Condition Class**: `self-clearing` or `durable`, derived by code
  from the readiness inputs. The one input that distinguishes "wait" from
  "hand over".

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a board holding one not-ready item and at least one other
  eligible issue, the number of consecutive scheduled runs that select the
  held item is **0**. Before this feature it is unbounded.
- **SC-002**: Across any number of consecutive scheduled runs in which a
  held item's PR head and unmet condition do not change, the issue carries
  **exactly one** comment naming that unmet condition. Before this feature
  it carries one per run.
- **SC-003**: Every not-ready item reaches one of exactly three outcomes
  within a bounded number of scheduled runs: reported ready, closed or
  merged, or handed to a human under `board:stalled` with the unmet
  condition named. **No** item can remain in a state where the loop
  re-evaluates it on every run with no change of outcome.
- **SC-004**: A push that moves a held item's PR head brings the item back
  into selection within **one** scheduled run, with no human label action
  required, and the step it re-enters at is `review` in **100%** of those
  re-admissions.
- **SC-005**: A PR whose only unmet condition is a check still in progress
  reaches its ready report without any human action, in **100%** of cases
  where that check eventually goes green on the same head — the
  overwhelmingly common readiness outcome must not require a hand-over.
- **SC-006**: Deleting any single rule this feature adds causes **at least
  one** checked-in fixture or gate self-test mutation to fail; the full
  local gate suite passes on the implementing branch.
- **SC-007**: The count of board-loop `run-label: 'not ready'` metrics
  records produced for one PR is bounded by the handover threshold, not by
  the number of hours the PR stays open.
- **SC-008**: Every existing board-loop eligibility fixture and
  resume-gating self-test mutation passes unchanged, demonstrating **zero**
  regression in the `ready`, `awaiting-merge`, `prove`, `breach` and
  unowned-PR paths.
- **SC-009**: The number of review invocations one PR can consume across any
  number of human pushes is bounded by the item's own fix→review round
  budget, which re-admission continues rather than resets. A human pushing
  repeatedly to a held PR cannot raise that bound.
- **SC-010**: Every commit a ready report covers has been through an
  independent review — **100%** of ready reports, including those on a head
  a human pushed while the item was held.

## Assumptions

The three questions this specification carried are answered in
**Clarifications** and folded into the requirements; nothing below is a
placeholder for a decision still outstanding. The assumptions are the
remaining things taken as given.

- **Threshold value: 3 not-ready outcomes per PR.** Deliberately tighter
  than the fix→review round budget of 5 (spec 057 research.md D18): a
  round does work and can change the answer, whereas a not-ready re-check
  only re-measures, so more of them buys proportionally less. It is a
  value, not a design decision, so it was defaulted rather than asked, and
  the owner's Q1 answer named the same number; the bound belongs beside the
  backstop thresholds and the round budget as one more checked-in constant,
  not a second mechanism.
- **The two bounds on one PR are independent and neither is widened.** The
  not-ready threshold (3) bounds re-measurement; the fix→review round
  budget (5) bounds review work, and FR-007's re-admission continues it
  rather than resetting it. Whichever is reached first hands the item over,
  through spec 057 FR-030's one existing mechanism.
- **A review invocation per human push is an accepted cost.** Q3's answer
  buys the stronger guarantee (SC-010) at the price of one review agent
  invocation each time a human moves a held PR's head. The round budget is
  what keeps that price bounded, and a human who does not push pays nothing.
- The not-ready record is carried by the existing board-item marker
  mechanism and the existing issue-comment convention rather than a new
  store; whether that means a new marker field, a new step name, or both
  is the plan stage's decision, not this specification's.
- The loop continues to work one item at a time — one board item in flight
  repository-wide, under spec 060's per-job concurrency groups; this feature changes which item is chosen, never how
  many run at once.
- `board:stalled` remains the loop's single hand-to-human marker. This
  feature adds a reason for applying it, never a second label.
- The PR's current head SHA is available to the selection decision from
  the same per-PR lookup the select job already performs for the PR's
  state, so the hold costs no additional API round-trip per item.
- The head SHA the not-ready record names is also the head the last review
  covered, because readiness is entered immediately after review converges
  on that head. FR-007's "has the head moved since the last review?" is
  therefore answerable from the record plus that same lookup, with no
  separate record of the reviewed head and no additional round-trip.
- Scheduled runs are hourly, as today; no requirement here depends on the
  interval.

## Dependencies

- `specs/057-autonomous-board-loop` — FR-009, FR-030 (both the round budget
  FR-007's re-admission continues and the `board:stalled` handover FR-008
  reuses), FR-031, FR-036, FR-037, FR-044, FR-054, FR-066, FR-067, FR-068;
  `contracts/readiness-report.md`;
  `contracts/board-item-marker.md`; `contracts/eligibility-and-selection.md`.
  The readiness-report contract is amended by FR-014, which states there
  how FR-067 is superseded; spec 057's frozen `spec.md` is not edited.
- `specs/061-marker-owned-in-flight` — `contracts/in-flight-detection.md`
  (the single home for the in-flight decision, and the fixture layout this
  feature extends), `contracts/resume-recovery.md` (step resolution, whose
  clause list FR-007 adds the re-admitted-at-`review` clause to) and FR-014
  (the provenance rule for recording a resume that did not come straight
  from the marker).
- The existing eligibility gate and resume-gating gate, extended rather
  than duplicated (FR-013 requires no new gate).
- Constitution X (Bounded Autonomy — the loop hands over rather than
  widening its own bound) and IX (judgment that gates a durable action is
  deterministic code).
- Nothing outside this repository. No new external service, token scope,
  or permission.

## Out of Scope

- Merging. The loop still never merges, approves, or enables auto-merge on
  a fix PR (spec 057 FR-068). This feature only changes which item the
  loop selects and when it hands over.
- The five readiness conditions themselves. What "ready" means is
  unchanged; only the handling of "not ready" changes. FR-005's
  self-clearing/durable classification is a new *output* derived from the
  same inputs, not a new condition.
- The documented known limit on the ready path — a push to the PR head
  after a `ready` report does not bring the item back to readiness. It is
  the mirror image of this feature's re-admission rule and may be worth
  revisiting, but it is a separate decision on a separate path.
- The review round budget's own value (spec 057 FR-030's bounded number of
  rounds) and the review step's own behaviour. FR-007's resume-at-`review`
  answer does put the budget's **accounting across a re-admission** in
  scope — it continues rather than resets — but it changes neither the
  number nor what a review round does.
- The backstop-breach path's own behaviour, beyond FR-012's requirement
  that this feature not duplicate it.
- The watchdog's treatment of board-loop runs, and the metrics record's
  schema beyond SC-007's bound on how many records one PR produces.
- Any change to how issues become eligible in the first place
  (`classify_issue`, `is_excluded`) beyond the hold this feature adds in
  front of the existing scan.
