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
  and failing loudly when it cannot. Five arms across three other jobs
  posted the marker first: triage's already-fixed hand-over, route's
  spec-request verdict, and all three of review's stall arms (parse-failed,
  malformed-findings, budget-spent). A transient failure on the label call
  left the stalled marker newest with no label. #782 has since moved every
  stall site through one helper that adds the label first and renders no
  marker when the add fails, so this cause is closed on current `main`;
  FR-001–FR-005 are what holds it closed.
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
before the marker and fail loudly otherwise, which is what #603 established,
did not finish, and #782 finished. What re-admission should then *mean* was
the owner question, and it is why this is a spec and not a fix PR; the
answer (below) is that re-admission keeps today's rule, stated and gated
rather than emergent, refined (with spec 093) so an open PR whose head no
review has missed resumes at `readiness` rather than being reviewed again.

### 2. Readiness's own breach path can file a second spec-request (deferred)

Readiness files a `spec-request` on a backstop breach through two entries.
The `step=breach` retry entry (#530) first looks for a spec-request this App
already filed for this issue and PR since the PR opened, and reuses it. The
ordinary entry — a breach measured on the final diff *after* a converged
review — has no such lookup. Its create runs, and only then are the label
and the marker written; a failure on either leaves the marker at
`step=readiness` with its PR, which resumes straight back into readiness, re-
measures the same oversized diff, and files a second spec-request for the
same PR. #701 (spec 092 — bounded, idempotent `spec-request` filing) is the
open home for this across every filing site, readiness's breach path
included. The owner's answer to Q3 defers this defect there in full: it is
described here for the record and is out of scope for this feature.

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
steps with `paused != 'true'`; readiness alone laundered the stand-down
through a decision value. FR-051 asks the kill switch to stop the loop
"before any durable action" and FR-052 asks the same of a maintainer's
comment. #782 gated every readiness durable step on the re-check's `paused`
answer and records the stand-down on the step summary; FR-012–FR-015 are
what holds that.

### Where this stands on current `main`

The three defects above are the state of the loop when this spec was
drafted. Since then #782 has landed the label-before-marker ordering at
every stall site (defect 1's accidental cause) and readiness's per-write
stand-down gating (defect 3), each with Gate 97 cases and self-test
mutations. What remains live for this feature is: FR-006/FR-007's stated,
contract-visible re-admission rule and its gate, FR-009's budget statement,
FR-004's derived enumeration of stall sites, and FR-010/FR-011's bounds on
what a retry or a re-admission may spend and must record. The plan stage
re-derives what is already built rather than rebuilding it. Defect 2 is
deferred to #701.

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

#530 and #603 bought the two hardest stall sites the right ordering, with
error text explaining what a later run will do, and #782 carried that
reasoning to every remaining arm and to one canonical statement of it. None
of it is to be redesigned here. Likewise the stop check itself — its
two-token split, its target guards, its mutation-proven decision function
(specs 085, 087, 088) — is correct and is not the subject; only readiness's
consumption of its answer is.

## Clarifications

### Session 2026-09-29 — resolved on lifecycle issue #752

The three questions this draft carried were answered by the owner on #752.
No `[NEEDS CLARIFICATION]` marker remains.

- **Q1 (scope/behaviour, FR-006) — what re-admission after a stall does.**
  **Answer: option (b), today's behaviour, made explicit and gated.** A
  stalled item whose `board:stalled` label a maintainer removed resumes by
  the resume step's ordinary re-derivation from live state: `review` when an
  open `board:owned` pull request cites the issue, a fresh triage otherwise.
  What makes that safe is #782: every stall site now applies the label
  before it writes the marker and renders no marker when the add fails, so a
  `stalled` marker with no label can only mean a deliberate removal. The
  rule's canonical statement already lives at `add_stalled_label()` in
  `board_item_marker.py`. As answered, this feature documents and gates the
  rule without changing it. **Refined 2026-09-29 (maintainer, reconciling
  with spec 093 / #717):** when the open `board:owned` PR's head has not
  moved since its last review, the item resumes at `readiness` instead of
  `review`, so an already-reviewed head is not reviewed again; a moved head
  still resumes at `review`. This refinement *is* a change to the rule on
  `main` (`board-loop.yml:811-813` resolves the fallback to `review`
  unconditionally), and it is the one behaviour change FR-006 makes. The
  canonical statement at `add_stalled_label()` is updated to this combined
  rule.
- **Q2 (cost, FR-009) — the budget a re-admitted item may spend.**
  **Answer: a fresh review-round budget.** Re-admitting is the maintainer
  authorizing more spend, which is the same call the owner made on #717
  (Q3: B) and #724 (Q2: B), where re-admitted or human-touched work gets a
  fresh independent review.
- **Q3 (scope, FR-016) — where readiness's own-breach duplicate lookup
  lands.** **Answer: deferred entirely to #701** (spec 092, bounded and
  idempotent `spec-request` filing), which covers every `spec-request`
  filing site, readiness's breach path included. Defect 2 is therefore out
  of scope here, and US4 and its success criterion are removed with it.
- **Owner scope note (2026-09-29, #752).** Label-before-marker at every
  stall site and readiness's per-write stop gating landed in #782
  (`aaaa1405`) and are not re-specified: US1/US2, FR-001–FR-005 and
  FR-012–FR-015 are kept as invariants the implementation must preserve and
  gate, not as work to build. The note also listed defect 2 as open; Q3
  already deferred it, and spec 092 (merged) now covers both readiness
  entries (its FR-017), so it stays out of scope here.

### Status update 2026-09-30 — reconciled with current `main` and specs 092/093/108 (maintainer spec review)

- **Main still resolves every label-less stall to `review`.** The resume
  fallback at `board-loop.yml:811-813` sets `step = "review"` for any
  non-`breach` marker whose PR came from the `board:owned` fallback, and
  `add_stalled_label()`'s docstring (`board_item_marker.py:176-189`) states
  that rule. The `readiness` refinement is not built; FR-006 builds it. The
  eight stall sites are re-verified at `board-loop.yml:1427` (triage),
  `1906` (route), `2263`/`2467` (fix), `3306`/`3311`/`3319` (review) and
  `3913` (readiness), each through `--add-label "board:stalled"`.
- **One home for the combined rule (spec 093, merged).** Spec 093 FR-007
  requires the same `review`/`readiness` split for a label-removed item,
  and its 2026-09-29 status note names this spec's FR-006 as the rule's
  encoding. The rule, its resume clause in spec 061's `resume-recovery.md`,
  its `add_stalled_label()` statement and its gate are built once, here,
  and spec 093 consumes them (FR-006b). Whichever feature is implemented
  second re-derives, and does not rebuild, what the first landed.
- **What "the last review" is for a stall (FR-006b).** A `stalled` marker
  records no head SHA (`write_marker()` carries step, round, pr, branch and
  base-sha — `board_item_marker.py:139`), and FR-019 keeps that schema.
  Spec 093 answers the question from its not-ready record, which a stall
  does not write. FR-006b therefore requires the reviewed head to be
  established from live state or an existing record. By spec 093 FR-007's
  owner-chosen invariant — nothing is reported ready on a head whose
  commits no review has covered — the item resolves to `review` whenever
  that head cannot be established. A stall reached before any review (fix's
  gate-red and post-push breach) or from an inconclusive one (review's
  parse-failed, malformed-findings, and budget-spent arms — a spent budget
  never finished clearing the PR's findings, so it does not establish a
  reviewed head either) therefore resumes at `review`.
- **The two re-admission budgets differ on purpose.** Spec 093 FR-007
  *continues* the round budget when a held item's head moves. A label
  removal is the maintainer's explicit reset and gets a fresh budget (Q2,
  FR-009); spec 093's status note records FR-009 as unchanged.
- **Disposed stalls re-admit by reopen, not by label removal (spec 108,
  merged).** Spec 108 FR-001/FR-002 close the originating issue as a
  duplicate at the three sites that file a `spec-request`: route's spec
  verdict, fix's post-push breach and readiness's backstop breach. Its
  FR-006 makes removing `board:stalled` from a disposed issue re-admit
  nothing; a maintainer's reopen routes it afresh, once per reopen. FR-006
  and FR-007 here therefore govern an **undisposed** stalled issue: the
  triage hand-over, fix's gate-red stall, review's three arms, spec 093
  FR-008's not-ready handover, spec 092 FR-012's give-up stall, and any
  filing site whose disposition did not complete (spec 108 FR-010/FR-011).
  A disposed issue's re-admission belongs to spec 108 and is not restated
  here. FR-007 and US3 scenarios 2–3 are scoped accordingly.
- **New stall sites since drafting.** Spec 093 FR-008 (the not-ready
  threshold handover) and spec 092 FR-012 (the filing-cap give-up) each add
  a stall through `add_stalled_label()`. FR-004's derived enumeration covers
  them without a list edit. The "eight" in FR-001/SC-001 is today's count on
  `main`, not a bound.
- **Spec 092 is merged.** FR-016–FR-018's deferral of defect 2 now points
  at a written spec: its FR-003 existence check and FR-017, which covers
  both readiness entries. A spec 092 give-up stall at readiness that is
  re-admitted on an unmoved head re-enters readiness, re-measures the
  breach and retries the filing under spec 092 FR-014's fresh attempt
  budget.

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
5. **Given** a stalled item whose `board:stalled` label is still in place,
   **When** a later run selects, **Then** the item is not selected by either
   the in-flight path or the oldest-first fallback, so no reviewer
   invocation is spent on its open PR while the stall holds. A `stalled`
   marker with no label is a maintainer's deliberate re-admission and is
   governed by FR-006, not by this story.

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
exist: it resumes at the step FR-006 names — for an open `board:owned` pull
request citing the issue, `review` when its head moved since the last review
and `readiness` when it did not; a fresh triage against current `main`
otherwise — it never opens a second branch or PR beside the one
already open, and the run summary says which rule fired and why. A
re-admitted review-budget stall starts a fresh round budget (FR-009),
because the removal is the maintainer authorizing that spend.

**Why this priority**: It was the owner question, now answered — the rule is
today's behaviour, stated and gated rather than emergent, with spec 093's
`readiness` refinement for an unmoved head. US1 and US2 are correct without
it, so it ships last.

**Independent Test**: Drive resume against a stalled marker plus an open
loop-owned PR whose head moved since its last review and assert the
resolved step is `review`; with an unmoved head, assert `readiness`; drive it against a
stalled marker with no open PR and assert a fresh triage. In both, assert
the absence of a second branch or PR and the summary line.

**Acceptance Scenarios**:

1. **Given** an item stalled by review's spent budget with its PR still
   open, **When** the label is removed and the next run selects it, **Then**
   the item resumes at `review` with a fresh round budget regardless of
   whether the head has moved since the budget was spent — a budget-spent
   verdict never finished clearing the PR's findings, so it never
   establishes a reviewed head (FR-006b) — and the run summary records that
   it was re-admitted from a stall and which clause resolved the step.
2. **Given** an undisposed item stalled at readiness with its PR still
   open and its head unchanged since review converged (spec 092's give-up
   stall, or a breach whose spec 108 disposition did not complete), **When**
   the label is removed, **Then** the same rule applies and the loop resumes
   at `readiness` on that pull request without another review. (A breach
   stall whose original was disposed is re-admitted by a reopen, under spec
   108 FR-006, not by this rule.)
3. **Given** an item stalled by triage's already-fixed hand-over with no PR
   ever opened, **When** it is re-admitted, **Then** the loop triages it
   afresh against current `main` and does not adopt an unrelated PR.
4. **Given** any re-admitted item whose own PR is still open, **When** the
   resolved step would ordinarily cut a branch, **Then** no second branch or
   PR is created (FR-054 of spec 057 is preserved).
5. **Given** an item stalled by review's spent budget whose head has moved
   since that review, **When** it is re-admitted, **Then** it resumes at
   `review` with the round budget starting fresh, and **When** that
   fresh budget is spent with findings still open, **Then** the item stalls
   again on the same terms.

---

### Removed: a retried readiness breach files one spec-request, not two

This draft carried a fourth user story for defect 2 — readiness's own
backstop-breach filing performing the "already filed for this issue and this
pull request" lookup its `step=breach` retry entry performs. Q3 defers it
entirely to #701 (spec 092), which covers every `spec-request` filing site
at once. It is not built here; see Out of Scope.

---

### Edge Cases

- **A stall site's label add fails repeatedly.** The retry re-enters the job
  that stalled. For review that means another reviewer invocation and
  another review comment on the PR *per attempt*, and for the budget-spent
  arm it happens at a round the budget has already spent. FR-010 bounds
  this: the retry must reach the stall decision without spending another
  agent invocation.
- **A stalled marker exists with no label and no open PR.** The fallback
  finds nothing, so the item resolves to a fresh triage. FR-006 keeps that
  and states it: a fresh triage against current `main` is the re-admission
  rule for an undisposed stalled item with no open pull request, at every
  stall site. (A disposed original is closed and re-admitted by a reopen —
  spec 108 FR-006.)
- **A re-admitted open PR whose reviewed head cannot be established.** No
  record of a review exists (the stall came before one, or from an
  inconclusive one), or the lookup fails. FR-006b resolves to `review`,
  never to `readiness`, so nothing is reported ready on unreviewed commits.
- **An unmoved head re-admitted after review's spent budget.** A
  budget-spent verdict never finished clearing the PR's findings, so it
  never establishes a reviewed head (FR-006b) regardless of whether the
  head has since moved. The item resumes at `review` with a fresh round
  budget (FR-009), never at `readiness`, so a stall with findings still
  open is never reported ready.
- **The label is removed while a run is mid-flight on the item.** The run
  holds the item under the global concurrency group; the removal takes
  effect on the next run, not this one. Nothing in this feature re-reads the
  label mid-run.
- **The loop cannot distinguish "the label add failed" from "a maintainer
  removed it".** FR-030 of spec 057 rejects deciding eligibility from a
  timeline event, so resume would see one state with two causes. FR-001 and
  FR-002 resolve this by making the first cause unreachable — no marker is
  ever posted without the label — and FR-006 therefore reads a label-less
  `stalled` marker as the second cause: a deliberate re-admission. This is
  what lets FR-006 keep today's live-state re-derivation.
- **A stop lands between readiness's re-check and its first write.** The
  re-check is a point sample; this feature does not add a second one. The
  window is bounded by the same reasoning the other five jobs accept.
- **Readiness stands down while `ready` would have been true.** The PR is
  genuinely mergeable but no report is posted. The item is not lost: its
  marker still says `readiness`, so the next unpaused run reports it.
- **A `spec-request` search that returns more than one match for the same
  issue and PR.** The retry entry's existing rule — reuse the oldest —
  stands unchanged; how filing becomes idempotent everywhere is #701's
  subject, not this feature's.

## Requirements *(mandatory)*

### Functional Requirements

#### Stall integrity — the label precedes the marker, everywhere

- **FR-001**: Every site at which the loop records a `stalled` board-item
  marker MUST apply the `board:stalled` label before posting that marker.
  This MUST hold at all of them — eight on current `main`: triage's
  already-fixed hand-over, route's `spec-request` verdict, the fix job's
  gate-suite-red stall and its post-push backstop breach, each of review's
  three stall arms, and readiness's backstop breach.
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
  a stated rule, and that rule is the resume step's ordinary re-derivation
  from live state (Q1, option (b), as refined with spec 093): when an open
  `board:owned` pull request cites the issue, `review` if its head has moved
  since the last review and `readiness` if it has not; a fresh triage
  against current `main` otherwise. The rule MUST be stated in one canonical
  place and MUST be reachable from the contracts a maintainer reads, rather
  than left to be inferred from the resume fallback's clause order.
- **FR-006b**: The "has the head moved since the last review" determination
  MUST be made from live state or an existing record, without extending the
  stall marker (FR-019). It MUST be the single determination spec 093
  FR-007 also consumes, not a second one (CLAUDE.md "Shared logic has
  exactly one home"). When no reviewed head can be established — no review
  covered the PR, the stall came from an inconclusive review arm, or the
  lookup fails — the rule MUST resolve to `review`, never `readiness`
  (spec 093 FR-007's invariant).
- **FR-006a**: The rule MUST rest on FR-001/FR-002 explicitly: because no
  stall site can post a `stalled` marker without the label, a label-less
  `stalled` marker means a maintainer removed the label deliberately, and
  the loop MUST treat it as that instruction. A change that weakens
  FR-001/FR-002 therefore invalidates FR-006, and the statement of the rule
  MUST say so.
- **FR-007**: The rule MUST hold for every stall site whose originating
  issue stays open — no such site's stall gets a different re-admission —
  and MUST produce a defined step for a stalled item with no open PR as well
  as one with an open PR. An originating issue disposed of under spec 108
  FR-001 is re-admitted by spec 108 FR-006 (a maintainer's reopen), and this
  feature MUST NOT re-admit it on label removal.
- **FR-008**: A re-admitted item MUST NOT cause a second branch or a second
  pull request to be opened while its own pull request is still open (spec
  057's FR-054 is preserved whatever FR-006 resolves to).
- **FR-009**: The agent budget a re-admitted item may consume MUST be
  bounded and stated: a re-admitted item gets a full fresh review-round
  budget (Q2), the same bound a newly selected item gets, and MUST stall
  again on the same terms when that fresh budget is spent with findings
  still open. Removing `board:stalled` is the maintainer authorizing that
  spend, consistent with #717 (Q3) and #724 (Q2), where re-admitted or
  human-touched work gets a fresh independent review. The loop MUST NOT
  carry the spent count across a re-admission, and MUST NOT grant an
  unbounded or repeating budget within one re-admission.
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

#### One spec-request per breach — deferred to #701

- **FR-016**: This feature MUST NOT change how readiness's own
  backstop-breach `spec-request` is filed. Making that create idempotent —
  the "already filed for this issue and this pull request" lookup its
  `step=breach` retry entry performs — is deferred in full to #701 (spec
  092), which covers every `spec-request` filing site at once (Q3).
- **FR-017**: The `step=breach` retry entry's existing lookup MUST keep
  working exactly as it does today; nothing here may remove, narrow or
  duplicate it.
- **FR-018**: This feature MUST NOT introduce a second, differently-shaped
  duplicate check beside the retry entry's — one home, consumed by every
  entry, so that #701 has one thing to generalize (CLAUDE.md "Shared logic
  has exactly one home").

#### Contracts and scope

- **FR-019**: The live contracts that describe the behaviour changed here
  MUST be updated in the same change — the resume step-resolution contract,
  which is where FR-006's rule is stated, and the
  labels/readiness/review/route/triage contracts that describe a stall's two
  moves. FR-006 does not extend what a stall marker records, so the
  board-item-marker contract's schema is unchanged. The merged `spec.md`,
  `plan.md`,
  `research.md` and `tasks.md` of specs 057 and 061 MUST NOT be edited
  (CLAUDE.md: they are historical records).
- **FR-020**: FR-006 does not contradict spec 057's FR-030 — removing
  `board:stalled` remains the sole re-eligibility condition, and FR-006 only
  states what happens next. The live contract MUST record the two together
  so no later reader has to re-derive the relationship, and no second
  exclusion label or second re-eligibility mechanism may be introduced.
- **FR-021**: The published contract MUST be unchanged: no stage workflow's
  `workflow_call` inputs, outputs or secrets, and no published composite
  action's interface, may change (Constitution VII). `board-loop.yml` is the
  consuming instrument and is where this work lands.

### Key Entities

- **Stall**: the loop's hand-to-human. Two moves — the `board:stalled` label
  and a `stalled` board-item marker — which this feature makes ordered and
  atomic-or-loud.
- **Stall site**: one arm of one job that performs a stall. There are eight
  on current `main` across five jobs — triage's hand-over, route's spec
  verdict, the fix job's gate-red stall and its post-push breach, review's
  three stall arms, and readiness's backstop breach; FR-004 makes the set
  derivable rather than remembered, which is why no requirement here rests
  on the count.
- **Re-admission**: what happens after `board:stalled` is removed from an
  undisposed issue. An emergent property of the resume fallback today;
  FR-006 keeps that outcome except for an unmoved, already-reviewed head
  (resumed at `readiness`), and states it as a rule, resting on
  FR-001/FR-002 for the guarantee that a label-less stall is always
  deliberate.
- **Resume step resolution**: the ordered clauses that turn a marker plus
  live state into the step a run will execute. The `board:owned` fallback
  clause is the one this feature constrains.
- **Stand-down answer**: the stop check's per-job verdict, already computed
  correctly; FR-012 makes readiness consume it at every write rather than at
  one decision.
- **Already-filed lookup**: the search for a `spec-request` this App filed
  for a given issue and pull request. One home today, at the `step=breach`
  retry entry; generalizing it to every filing site is #701's subject, not
  this feature's.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every stall site the workflow has (eight on current
  `main`), a checked-in case shows the `board:stalled` label applied before
  the `stalled` marker, and a second case shows a failed label application
  producing no marker and a failed run.
- **SC-002**: Reverting any one stall site to marker-before-label causes the
  gate suite to fail and to name that site; no site is covered by narrative
  alone.
- **SC-003**: Adding one more stall site that posts the marker first is
  caught without editing a list of sites.
- **SC-004**: While a stall holds — the `stalled` marker newest and
  `board:stalled` present — no board-loop run spends a reviewer invocation,
  a fix invocation, a push, or a second pull request on that item. Once the
  label is removed, what the run spends is what FR-006's stated rule and
  FR-009's budget allow, and nothing more.
- **SC-005**: A maintainer can predict, from one stated rule read in one
  place, what removing `board:stalled` will make the loop do next, for an
  undisposed stall at any site and with or without an open pull request —
  on the open
  loop-owned PR, `review` if its head moved since the last review and
  `readiness` if not; a fresh triage otherwise.
- **SC-006**: A re-admitted item's additional agent budget is a stated
  number — one full round budget, the same as a newly selected item — and a
  checked-in case shows the item stalling again once it is spent.
- **SC-007**: With the stop check answering stand down, a readiness run
  makes zero durable GitHub writes — no comment, no issue created, no label
  applied, no cross-link — in both the backstop-holds and backstop-breaches
  cases.
- **SC-008**: Removing the stand-down gate from any one of readiness's
  durable steps causes at least one checked-in case to fail, and the failure
  names that step.
- **SC-009**: Every re-admission, every FR-002 retry, and every readiness
  stand-down appears on the run summary; a maintainer reconstructing what the
  loop did needs no log archaeology.
- **SC-010**: `python .github/scripts/run-local-gates.py` passes with no gate
  skipped, waived, or weakened to accommodate this change.
- **SC-011**: An adopter pinning the published release sees no interface
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
- The eight stall sites enumerated in FR-001 are the complete set on current
  `main` (#782 moved all of them through one helper). The implementation
  re-derives the set rather than trusting this count, which is what FR-004
  asks for.
- #701 (spec 092) is the home for bounding `spec-request` filing retries and
  making filing idempotent at every site, readiness's breach path included.
  This feature files nothing new and changes no filing path (Q3).
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

- `.github/workflows/board-loop.yml` — the resume step's step resolution,
  every stall site, and the readiness job's durable steps.
- `.github/scripts/board_eligibility.py` — `PRE_FIX_STEPS`,
  `FIX_OR_LATER_STEPS`, `TERMINAL_STEPS`, `select()` and
  `in_flight_candidate()`, which together decide that a `stalled` marker
  keeps an item out of the in-flight path but not out of the oldest-first
  fallback.
- `.github/scripts/board_item_marker.py` — `write_marker`/`read_marker`, and
  `add_stalled_label()`, which is where #782 put the canonical statement of
  the stall rule and of the re-admission FR-006 now states.
- `.github/scripts/board_readiness.py` — the readiness decision, whose
  `kill_switch_paused` parameter FR-015 keeps as redundant defence behind
  the per-write gating (FR-012/FR-013).
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
- Merged specs on the same surface: spec 092 (bounded, idempotent
  `spec-request` filing — defect 2's home and a new give-up stall site),
  spec 093 (not-ready board release — FR-007's shared re-admission rule and
  FR-008's new stall site), spec 108 (routed-original disposition — reopen
  as the re-admission of a disposed original).
- Prior art this change must not undo: #530 (the `breach` step and its
  fallback carve-out), #603 (label-before-marker at the two hardest sites),
  #782 (label-before-marker at every site, the readiness stand-down gating,
  and Gate 97's cases for both — the work US1 and US2 describe), #532
  (`awaiting-merge`), #555 (marker ownership), #526, #499, #583 (review's
  inconclusive stall arms), #462/#461/#465 (the stop-check idiom).

## Out of Scope

- Bounding `spec-request` filing retries, and making any filing site
  idempotent — including readiness's own backstop-breach create (defect 2,
  the draft's US4). Deferred in full to #701 / spec 092 (Q3).
- Changing what counts as a stop request, who may issue one, or how the stop
  baseline is computed.
- Any change to the size-and-path backstop's thresholds or to what counts as
  widening the published contract.
- Changing the round budget's default value; FR-009 is about what a
  re-admitted item may spend, not about the budget itself.
- Introducing a second exclusion label or a second re-eligibility mechanism
  beside `board:stalled`. FR-006 resolved to today's behaviour plus spec
  093's refinement, so this feature does not amend spec 057's FR-030
  (FR-020). Spec 108's reopen of a disposed original is that feature's
  amendment, not this one's.
- Changing what a re-admitted item does beyond FR-006's `readiness`
  refinement; any other rule is a separate feature.
- Re-admission of an originating issue disposed of under spec 108 (reopen,
  spec 108 FR-006).
- The wording of stall notices, including whether each states the
  re-eligibility condition FR-030 requires.
- Closing or de-duplicating `spec-request` issues already filed in duplicate
  before this change.
