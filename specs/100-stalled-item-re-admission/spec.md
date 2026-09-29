# Feature Specification: A Stall Holds Until a Maintainer Re-Admits It — and a Stop Halts Readiness's Filing

**Feature Branch**: `spec-draft/100-stalled-item-re-admission`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #752 — "board-loop: a `stalled` marker without
the `board:stalled` label resumes into review; a stop request doesn't gate
readiness's filing" (routed from board-loop.yml; originating issue #604,
found by the code review of #603, itself the fix for #530)

## Overview

The board loop hands an item to a human in two moves: it applies the
`board:stalled` label, and it posts a `stalled` board-item marker. The label
is what keeps the item out of selection; the marker is what tells a later
run where the item got to. FR-030 of spec 057 makes removing the label "the
sole condition that makes the item eligible again".

Between those two moves there is a gap, and on the far side of it the loop
does not stand down — it reviews. Three coupled defects sit in that gap and
in the one job that never learned to gate on the stop check.

### 1. A stall with no label resumes into a review round

The resume step's step resolution has a fallback clause: when no
marker-named PR resolved but an open `board:owned` pull request cites the
issue, `step` becomes `review` (except for a `breach` marker, carved out by
#530). A `stalled` marker is always written with `pr=None`, so it *always*
reaches that clause. The only thing standing between a stalled item and a
fresh review round is the label — and `select()`'s oldest-first fallback
skips a `prove` marker, an `awaiting-merge` marker and an unowned-open-PR
marker, but not a `stalled` one. The label is load-bearing and alone.

Two ordinary events open the gap:

- **The label add fails after the marker was posted.** #603 fixed exactly
  two of the loop's stall sites — the fix job's post-push breach and
  readiness's backstop breach — by applying the label *before* the marker
  and failing loudly when it cannot. Five arms across three other jobs still
  post the marker first: triage's already-fixed hand-over, route's
  spec-request verdict, and all three of review's stall arms (parse-failed,
  malformed-findings, budget-spent). A transient failure on the label call
  leaves the stalled marker newest with no label.
- **A maintainer removes the label**, which spec 057's `data-model.md`
  defines as the re-admission path and every review stall notice advertises
  in as many words.

What follows is identical in both cases, and in neither is it obviously
right: the next run re-selects the item, adopts the open PR, and spends a
full reviewer invocation on it — then posts another review on a PR a human
was asked to look at, and re-stalls. For a readiness-backstop stall the PR
under review is one a `spec-request` already covers. For a budget-spent
stall the round budget restarts at zero.

The minimum is not in question: every stall site should apply the label
before the marker and fail loudly otherwise, which is what #603 established
and did not finish. What re-admission should then *mean* is an owner
question, and it is why this is a spec and not a fix PR.

### 2. Readiness's own breach path can file a second spec-request

Readiness files a `spec-request` on a backstop breach through two entries.
The `step=breach` retry entry (#530) first looks for a spec-request this App
already filed for this issue and PR since the PR opened, and reuses it. The
ordinary entry — a breach measured on the final diff *after* a converged
review — has no such lookup. Its create runs, and only then are the label
and the marker written; a failure on either leaves the marker at
`step=readiness` with its PR, which resumes straight back into readiness, re-
measures the same oversized diff, and files a second spec-request for the
same PR. #527 is the open home for bounding these retries and making filing
idempotent; this one site is the asymmetry #527's design has to cover.

### 3. A stop request does not stop readiness from filing

Readiness re-checks the kill switch and any maintainer stop request
immediately before its own durable action, exactly as the other five jobs
do. It then feeds that answer into one place: the readiness *decision*,
where a stand-down can only make `ready` false. Every durable write below
sits behind `ready != 'true'` instead — so a stop that lands mid-run does not
halt the item, it reroutes it into the not-ready branch, which comments on
the issue and, if the backstop does not hold, creates the `spec-request`,
applies `board:stalled`, and cross-links the artifact. A maintainer who
types `stop` to keep the loop from filing something gets the filing.

Triage exits early on `PAUSED`; route, fix and review gate their durable
steps with `paused != 'true'`; readiness alone launders the stand-down
through a decision value. FR-051 asks the kill switch to stop the loop
"before any durable action" and FR-052 asks the same of a maintainer's
comment.

### Why this is worth doing

These three are one story told at three points on the same path: the loop's
hand-to-human must be a place the loop actually stops. Today the strongest
signals a maintainer has — a label a contract tells them to remove, and a
comment the docs call a stop — either resume an agent round on a PR they
asked to inspect or fail to prevent the filing they were trying to prevent.
Each is a usage-window cost paid with no forward progress (Principle II),
and defect 3 is a Principle IX breach in the narrowest sense: judgment that
gates durable actions is computed correctly and then not consulted.

### What must not be spent

#530 and #603 already bought the two hardest stall sites the right ordering,
with error text explaining what a later run will do. Their reasoning is the
model for the remaining five arms, not something to redesign. Likewise the
stop check itself — its two-token split, its target guards, its mutation-
proven decision function (specs 085, 087, 088) — is correct and is not the
subject; only readiness's consumption of its answer is.

## Clarifications

### Open questions carried to lifecycle issue #752

Three questions are unresolved in this draft and are carried to the
lifecycle issue for the clarify stage. They are marked in place as
`[NEEDS CLARIFICATION]` on FR-006, FR-009 and FR-016.

- **Q1 (scope/behaviour, FR-006)**: What does re-admission after a stall
  *do*? Nothing in the loop today makes that choice deliberately — the step
  a re-admitted item resumes at is a side effect of whether an open
  `board:owned` PR happens to exist.
- **Q2 (cost, FR-009)**: When a review-budget stall is re-admitted, what
  happens to the round budget? It restarts at zero today, which lets one
  label removal buy a whole fresh budget.
- **Q3 (scope, FR-016)**: Does readiness's own-breach duplicate lookup land
  in this feature, or is defect 2 left entirely to #527?

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A failed label add never turns a stall into a review round (Priority: P1)

The loop decides an item must go to a human. It applies `board:stalled`
first; only once that has landed does it post the `stalled` marker. If the
label cannot be applied, the run fails loudly and posts no stalled marker at
all, so the item's newest marker still describes the step it was at, and a
later run retries that step and re-stalls. There is no window in which a
stalled marker exists without the label that excludes it.

**Why this priority**: This is the half of defect 1 with no design question
attached, and it is what closes the accidental path into the gap. It is also
the path that costs the most when it fires — a reviewer invocation and a
second review comment on a PR a maintainer has already been asked to look
at.

**Independent Test**: Drive each stall site with a stubbed label call that
fails, and assert the issue carries no `stalled` marker and the run failed;
then with the label call succeeding, assert the label's application precedes
the marker comment.

**Acceptance Scenarios**:

1. **Given** review's round budget is spent with in-scope findings open,
   **When** the stall is recorded, **Then** `board:stalled` is applied before
   the stall notice carrying the `stalled` marker is posted.
2. **Given** the same stall, **When** applying `board:stalled` fails,
   **Then** no `stalled` marker is posted, the run fails with an error naming
   what a later run will do, and the item's newest marker is still the
   `review` marker it had.
3. **Given** route has filed a `spec-request` for a spec-shaped issue,
   **When** applying `board:stalled` fails, **Then** no `stalled` marker is
   posted and the run fails loudly — the already-filed `spec-request` is
   named in the error so the retry can reuse it.
4. **Given** triage hands over an already-fixed-on-`main` proposal, **When**
   the stall is recorded, **Then** the label precedes the marker on the same
   terms.
5. **Given** a stalled marker that nonetheless exists with no label — from a
   pre-existing item, or a write the loop did not make — **When** the next
   run resumes that item, **Then** it does not spend a reviewer invocation on
   the open PR before FR-006's re-admission rule has decided what to do.

---

### User Story 2 - A maintainer's stop halts readiness before it files anything (Priority: P2)

A maintainer comments `stop` on the in-flight item, or sets the kill switch,
while readiness is running. Readiness's re-check sees it and the job stands
down: it posts no readiness report, no not-ready comment, creates no
`spec-request`, applies no label, cross-links nothing, and leaves the item's
marker exactly as it was. The stand-down is recorded on the run summary, and
the next run after the stop is lifted resumes readiness on the same PR.

**Why this priority**: It is the defect with no open question and a
one-shaped answer — make readiness gate its durable steps the way the other
five jobs already do. It ships independently of everything else here.

**Independent Test**: Run readiness against a stub where the stop check
answers "stand down", once with the backstop holding and once breaching, and
assert zero durable calls in both.

**Acceptance Scenarios**:

1. **Given** the backstop breaches on the final diff, **When** the stop
   check answers stand down, **Then** no `spec-request` is created, no
   `board:stalled` label is applied, no comment is posted, and nothing is
   cross-linked.
2. **Given** every readiness condition holds, **When** the stop check
   answers stand down, **Then** the ready report is not posted and no
   `awaiting-merge` marker is written.
3. **Given** the backstop holds but a check is not green, **When** the stop
   check answers stand down, **Then** the "not ready, picked up later"
   comment is not posted either.
4. **Given** readiness stood down, **When** the stop is lifted and a later
   run selects the item, **Then** it resumes at readiness on the same PR,
   because its marker was never advanced.
5. **Given** a stand-down, **When** a maintainer reads the run, **Then** the
   summary records that readiness stood down and at which point — the loop
   never stands down silently.

---

### User Story 3 - A maintainer's label removal does what they meant (Priority: P3)

A maintainer removes `board:stalled` from a stalled item. What the loop does
next is a rule the loop states, not an accident of which artifacts happen to
exist: it resumes at the step FR-006 names, it never opens a second branch or
PR beside the one already open, and the run summary says which rule fired and
why. Whatever that step is, a re-admitted item cannot consume more agent
budget than FR-009 allows.

**Why this priority**: It is the owner question. It can only be built after
Q1 and Q2 are answered, and US1 and US2 are correct without it.

**Independent Test**: With the answer to Q1 encoded, drive resume against a
stalled marker plus an open loop-owned PR and assert the resolved step, the
absence of a second branch or PR, and the summary line.

**Acceptance Scenarios**:

1. **Given** an item stalled by review's spent budget with its PR still
   open, **When** the label is removed and the next run selects it, **Then**
   the item resumes at the step FR-006 names and the run summary records that
   it was re-admitted from a stall.
2. **Given** an item stalled by readiness's backstop breach, **When** it is
   re-admitted, **Then** the loop does not review the oversized PR the
   existing `spec-request` already covers.
3. **Given** an item stalled by route with no PR ever opened, **When** it is
   re-admitted, **Then** the loop does not adopt an unrelated PR.
4. **Given** any re-admitted item whose own PR is still open, **When** the
   resolved step would ordinarily cut a branch, **Then** no second branch or
   PR is created (FR-054 of spec 057 is preserved).

---

### User Story 4 - A retried readiness breach files one spec-request, not two (Priority: P4)

Readiness breaches the backstop on a converged PR's final diff and files a
`spec-request`. A later write fails, and a later run resumes readiness on the
same PR. It finds the `spec-request` already filed for this issue and PR,
reuses it, and files nothing new.

**Why this priority**: It is the smallest of the three and the one already
half-built — the retry entry's lookup is the shape to reuse. It is also the
one whose home is itself a question (Q3).

**Independent Test**: Run readiness's breach path twice against the same
issue and PR with a stubbed issue-search and assert exactly one create call.

**Acceptance Scenarios**:

1. **Given** readiness's own backstop breach with a `spec-request` already
   filed for this issue and PR, **When** readiness breaches again, **Then**
   the existing request is reused and named in the run summary and no second
   one is created.
2. **Given** the same breach, **When** the lookup for an existing request
   cannot be performed, **Then** nothing is filed and the run fails, so a
   later run retries rather than risking a duplicate.

---

### Edge Cases

- **A stall site's label add fails repeatedly.** The retry re-enters the job
  that stalled. For review that means another reviewer invocation and
  another review comment on the PR *per attempt*, and for the budget-spent
  arm it happens at a round the budget has already spent. FR-010 bounds
  this: the retry must reach the stall decision without spending another
  agent invocation.
- **A stalled marker exists with no label and no open PR.** The fallback
  finds nothing, so the item resolves to a fresh triage today. FR-006's rule
  must say whether that is still correct.
- **The label is removed while a run is mid-flight on the item.** The run
  holds the item under the global concurrency group; the removal takes
  effect on the next run, not this one. Nothing in this feature re-reads the
  label mid-run.
- **The loop cannot distinguish "the label add failed" from "a maintainer
  removed it".** FR-030 of spec 057 rejects deciding eligibility from a
  timeline event, so resume sees one state with two causes. Whatever FR-006
  names must be safe for both, or FR-001/FR-002 must make the first cause
  unreachable and FR-006 may then assume the second.
- **A stop lands between readiness's re-check and its first write.** The
  re-check is a point sample; this feature does not add a second one. The
  window is bounded by the same reasoning the other five jobs accept.
- **Readiness stands down while `ready` would have been true.** The PR is
  genuinely mergeable but no report is posted. The item is not lost: its
  marker still says `readiness`, so the next unpaused run reports it.
- **A `spec-request` search that returns more than one match for the same
  issue and PR.** The oldest is reused, matching the retry entry's existing
  rule; the extras are not closed by this feature.

## Requirements *(mandatory)*

### Functional Requirements

#### Stall integrity — the label precedes the marker, everywhere

- **FR-001**: Every site at which the loop records a `stalled` board-item
  marker MUST apply the `board:stalled` label before posting that marker.
  This MUST hold at all of them: triage's already-fixed hand-over, route's
  `spec-request` verdict, each of review's stall arms, the fix job's
  post-push backstop breach, and readiness's backstop breach.
- **FR-002**: When the label cannot be applied, the site MUST fail the run
  loudly and MUST NOT post a `stalled` marker. The error MUST name what a
  later run will do with the item, and — at sites that already filed a
  `spec-request` — MUST name that request so the retry can reuse it rather
  than file a second.
- **FR-003**: The ordering in FR-001 and the failure behaviour in FR-002
  MUST be enforced by deterministic code, not by a comment or a convention.
  A site that posts the marker before the label, or that continues past a
  failed label application, MUST fail that check.
- **FR-004**: The check MUST enumerate the loop's stall sites from the
  workflow itself rather than from a hand-maintained list, or MUST fail when
  its enumeration and the workflow's actual stall sites disagree — so a
  stall site added later is covered without anyone remembering to add it.
- **FR-005**: The check's own failure branch MUST be exercised by a
  checked-in fixture: reverting any one site to marker-before-label MUST
  fail it, and the check MUST name the site (Constitution VIII).

#### Re-admission — one stated rule, not a side effect

- **FR-006**: The loop MUST resolve a re-admitted stalled item to a step by
  a stated rule, and MUST NOT resolve it to a step merely because an open
  `board:owned` pull request citing the issue happens to exist.
  [NEEDS CLARIFICATION: what re-admission after a stall does — (a) a fresh
  triage against current `main`, adopting the existing PR rather than cutting
  a second; (b) review of the existing PR, today's behaviour, made explicit
  and documented; (c) the step the stall itself came from, recorded on the
  stall marker so a review stall resumes review, a readiness breach resumes
  readiness, and a route or triage stall resumes triage; (d) a hold that
  requires an explicit maintainer instruction, which would amend spec 057's
  FR-030 rule that removing the label is the sole re-eligibility condition]
- **FR-007**: The rule MUST be stated for every stall site, and MUST produce
  a defined step for a stalled item with no open PR as well as one with an
  open PR.
- **FR-008**: A re-admitted item MUST NOT cause a second branch or a second
  pull request to be opened while its own pull request is still open (spec
  057's FR-054 is preserved whatever FR-006 resolves to).
- **FR-009**: The agent budget a re-admitted item may consume MUST be
  bounded and stated. [NEEDS CLARIFICATION: on re-admission of a
  budget-spent review stall, does the round budget restart at zero (today's
  behaviour: one label removal buys a full fresh budget), continue from the
  spent count (the item re-stalls immediately, with no reviewer invocation
  spent), or grant a smaller, named number of additional rounds?]
- **FR-010**: Re-entering a job after FR-002's loud failure MUST NOT spend
  an additional agent invocation per attempt. The stall decision MUST be
  reachable from the marker's own recorded state before any agent runs.
- **FR-011**: Every re-admission and every FR-002 retry MUST be recorded on
  the run summary, naming the item, the rule that fired, and the resolved
  step. The loop MUST NOT re-admit or retry silently.

#### Readiness stands down on a stop, before every write

- **FR-012**: Every durable action readiness takes MUST be gated on the
  stand-down answer from its own pre-action re-check of the kill switch and
  stop requests — the ready report and its marker, the not-ready comment,
  the `spec-request` create, the `board:stalled` label, and the artifact
  cross-link. None MAY be reached on a stand-down.
- **FR-013**: A readiness stand-down MUST NOT be expressed as an unmet
  readiness condition. A paused or stopped run MUST NOT post "not ready" to
  the issue, and the gating of the writes MUST NOT depend on the readiness
  decision's own reason text.
- **FR-014**: On a stand-down readiness MUST leave the item's marker
  unchanged, so a later unpaused run resumes readiness on the same pull
  request, and MUST record the stand-down on the run summary.
- **FR-015**: The readiness decision MUST continue to refuse `ready` while
  paused, as deliberately redundant defence behind FR-012; removing FR-012's
  gate from any one durable step MUST cause at least one checked-in case to
  fail, and that failure MUST be attributable to the missing gate and not to
  the decision's refusal (Constitution VIII/IX).

#### One spec-request per breach

- **FR-016**: Readiness's own backstop-breach `spec-request` create MUST be
  preceded by the same "already filed for this issue and this pull request"
  lookup its `step=breach` retry entry performs, and MUST reuse a match
  rather than create a second request. [NEEDS CLARIFICATION: does this land
  in this feature — the asymmetry is one step and the lookup already exists
  next to it — or is every filing-idempotency change deferred to #527 so one
  design covers all spec-request sites at once?]
- **FR-017**: If FR-016 lands here, a lookup that cannot be performed MUST
  fail the step with nothing filed, matching the retry entry's existing
  rule, and the reuse MUST be recorded on the run summary.
- **FR-018**: Whatever FR-016 resolves to, this feature MUST NOT introduce a
  second, differently-shaped duplicate check beside the retry entry's — one
  home, consumed by both entries (CLAUDE.md "Shared logic has exactly one
  home").

#### Contracts and scope

- **FR-019**: The live contracts that describe the behaviour changed here
  MUST be updated in the same change — the resume step-resolution contract,
  the board-item-marker contract if FR-006 extends what a stall marker
  records, and the labels/readiness/review/route/triage contracts that
  describe a stall's two moves. The merged `spec.md`, `plan.md`,
  `research.md` and `tasks.md` of specs 057 and 061 MUST NOT be edited
  (CLAUDE.md: they are historical records).
- **FR-020**: If FR-006's answer contradicts spec 057's stated re-eligibility
  rule, the contradiction MUST be resolved explicitly in the live contract
  and named in the implementation PR, never left as two documents
  disagreeing.
- **FR-021**: The published contract MUST be unchanged: no stage workflow's
  `workflow_call` inputs, outputs or secrets, and no published composite
  action's interface, may change (Constitution VII). `board-loop.yml` is the
  consuming instrument and is where this work lands.

### Key Entities

- **Stall**: the loop's hand-to-human. Two moves — the `board:stalled` label
  and a `stalled` board-item marker — which this feature makes ordered and
  atomic-or-loud.
- **Stall site**: one arm of one job that performs a stall. There are seven
  today across five jobs — triage's hand-over, route's spec verdict, review's
  three stall arms, the fix job's post-push breach and readiness's backstop
  breach; FR-004 makes the set derivable rather than remembered.
- **Re-admission**: what happens after `board:stalled` is removed. Currently
  an emergent property of the resume fallback; FR-006 makes it a rule.
- **Resume step resolution**: the ordered clauses that turn a marker plus
  live state into the step a run will execute. The `board:owned` fallback
  clause is the one this feature constrains.
- **Stand-down answer**: the stop check's per-job verdict, already computed
  correctly; FR-012 makes readiness consume it at every write rather than at
  one decision.
- **Already-filed lookup**: the search for a `spec-request` this App filed
  for a given issue and pull request. One home, two breach entries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For all seven stall sites, a checked-in case shows the
  `board:stalled` label applied before the `stalled` marker, and a second
  case shows a failed label application producing no marker and a failed
  run.
- **SC-002**: Reverting any one stall site to marker-before-label causes the
  gate suite to fail and to name that site; no site is covered by narrative
  alone.
- **SC-003**: Adding an eighth stall site that posts the marker first is
  caught without editing a list of sites.
- **SC-004**: No board-loop run spends a reviewer invocation, a fix
  invocation, a push, or a second pull request on an item whose newest
  marker is `stalled` — provable from the resolved step alone, with no
  reference to whether the label happens to be present.
- **SC-005**: A maintainer can predict, from one stated rule, what removing
  `board:stalled` will make the loop do next, for a stall at any site and
  with or without an open pull request.
- **SC-006**: A re-admitted item's maximum additional agent budget is a
  stated number, and a checked-in case shows the item stalling again once it
  is spent.
- **SC-007**: With the stop check answering stand down, a readiness run
  makes zero durable GitHub writes — no comment, no issue created, no label
  applied, no cross-link — in both the backstop-holds and backstop-breaches
  cases.
- **SC-008**: Removing the stand-down gate from any one of readiness's
  durable steps causes at least one checked-in case to fail, and the failure
  names that step.
- **SC-009**: Two readiness runs that both breach on the same pull request
  produce exactly one `spec-request` for it.
- **SC-010**: Every re-admission, every FR-002 retry, and every readiness
  stand-down appears on the run summary; a maintainer reconstructing what the
  loop did needs no log archaeology.
- **SC-011**: `python .github/scripts/run-local-gates.py` passes with no gate
  skipped, waived, or weakened to accommodate this change.
- **SC-012**: An adopter pinning the published release sees no interface
  change.

## Assumptions

- `board-loop.yml`, the scripts under `.github/scripts/` and the board-loop
  composites are this repository's consuming instrument, not the published
  adopter-pinned surface (Constitution VII). Changing the resume step
  resolution or a stall site's shell is therefore not a breaking change;
  FR-021 holds the published surface fixed regardless.
- The contracts under `specs/057-autonomous-board-loop/contracts/` and
  `specs/061-marker-owned-in-flight/contracts/` are live documents fixed like
  code (CLAUDE.md), while those features' `spec.md`/`plan.md`/`tasks.md` are
  frozen records. FR-019 follows that split.
- The seven stall sites enumerated in FR-001 are the complete set on current
  `main`. The implementation re-derives the set rather than trusting this
  count, which is what FR-004 asks for.
- #527 remains the home for *bounding* spec-request filing retries. This
  feature touches filing idempotency at one site only, and only if Q3
  resolves that way; it does not adopt #527's scope.
- The stop check's own decision function and composite are correct and out of
  scope (specs 085, 087, 088). Only readiness's consumption of the `paused`
  answer changes.
- A stall notice's wording is not this feature's subject. Whether every
  notice that applies the label states the re-eligibility condition, as spec
  057's FR-030 requires, is an adjacent defect reported separately by the
  intake run that wrote this spec.
- The loop's global serializing concurrency group and its one-item-at-a-time
  selection are unchanged; no requirement here depends on two board-loop runs
  overlapping.

## Dependencies

- `.github/workflows/board-loop.yml` — the resume step's step resolution, the
  six stall sites, and the readiness job's durable steps.
- `.github/scripts/board_eligibility.py` — `PRE_FIX_STEPS`,
  `FIX_OR_LATER_STEPS`, `TERMINAL_STEPS`, `select()` and
  `in_flight_candidate()`, which together decide that a `stalled` marker
  keeps an item out of the in-flight path but not out of the oldest-first
  fallback.
- `.github/scripts/board_item_marker.py` — `write_marker`/`read_marker`, and
  the marker schema FR-006 option (c) would extend.
- `.github/scripts/board_readiness.py` — the decision function whose
  `kill_switch_paused` parameter is the only consumer of the stand-down
  today (FR-013/FR-015).
- `.github/actions/wing-commander-board-stop-check/action.yml` — the
  `paused` output readiness must gate on; unchanged by this feature.
- `specs/061-marker-owned-in-flight/contracts/resume-recovery.md` — the "Step
  resolution" clause list, including clause 2's `board:owned` fallback and
  #530's `breach` carve-out.
- `specs/057-autonomous-board-loop/contracts/` — `board-item-marker.md`,
  `eligibility-and-selection.md`, `labels-and-cross-links.md`,
  `readiness-report.md`, `review-and-findings.md`, `route-backstop.md`,
  `triage.md`, `gates.md`.
- The gate suite entry points that must cover the new checks:
  `verify-board-eligibility.py`, `verify-board-readiness.py`,
  `verify-board-loop-resume-gating.py`, and the spec-request-site gate
  (Gate 93) whose rules the stall sites already answer to.
- Prior art this change must not undo: #530 (the `breach` step and its
  fallback carve-out), #603 (label-before-marker at the two hardest sites),
  #532 (`awaiting-merge`), #555 (marker ownership), #526, #499, #583
  (review's inconclusive stall arms), #462/#461/#465 (the stop-check idiom).

## Out of Scope

- Bounding spec-request filing retries in general, or making every
  spec-request site idempotent — #527's subject.
- Changing what counts as a stop request, who may issue one, or how the stop
  baseline is computed.
- Any change to the size-and-path backstop's thresholds or to what counts as
  widening the published contract.
- Changing the round budget's default value; FR-009 is about what a
  re-admitted item may spend, not about the budget itself.
- Introducing a second exclusion label or a second re-eligibility mechanism
  beside `board:stalled`, unless FR-006 resolves to option (d), in which case
  FR-020 governs how the contradiction with spec 057's FR-030 is recorded.
- The wording of stall notices, including whether each states the
  re-eligibility condition FR-030 requires.
- Closing or de-duplicating `spec-request` issues already filed in duplicate
  before this change.
