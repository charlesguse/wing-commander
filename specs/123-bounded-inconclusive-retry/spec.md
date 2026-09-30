# Feature Specification: A Round That Cannot Conclude Stands Down — Bounding the Retry of an Inconclusive Review Round

**Feature Branch**: `spec-draft/123-bounded-inconclusive-retry`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue #869 — "lifecycle-review-gate: an inconclusive
round is retried hourly at the same head with no bound" (found by the code
review of #868)

## Overview

The lifecycle review gate (spec 062) runs on a schedule, picks at most one
ready lifecycle pull request per run, and reviews it. A round that reaches a
disposition — clean, findings, or budget-exhausted — records the head SHA it
covered, and the gate never spends a second round on that SHA. That is the
invariant spec 062 states twice: "the gate MUST NOT re-review a head SHA a
round already covered" and "never more than one round per SHA".

A round that *cannot* reach a disposition is deliberately exempt from that
invariant. The reviewer may hit a rate limit, time out, exhaust its turn
budget, produce a findings list nothing can parse, or the disposition job
itself may fail before it reports anything. None of those outcomes tells the
pipeline anything about the diff, so none of them is allowed to count as
coverage: nothing is recorded, the previous head SHA stays in place, and the
next scheduled run tries the same head again. Spec 062's edge cases ask for
exactly that — "a rate-limited round is retryable rather than counted as a
converged one."

The exemption has no floor. The gate has no memory that it already tried this
head and failed, so "retryable" means "retried forever". A reviewer that
fails **deterministically** on one pull request — the most likely cause being
a diff large enough to exhaust the turn budget every single time — is not
recovered by patience. It is re-run once an hour, at the same SHA, at full
review cost, for as long as the pull request stays open: roughly two dozen
paid reviews a day, none of which can ever succeed, all of them drawing on
the same usage window the rest of the pipeline and the maintainers' own
sessions share.

This feature gives the exemption a floor. An inconclusive round stays
retryable, but the gate remembers how many times it has already tried the
head in front of it, and stands down — visibly, with the reason and the
count stated — once it has tried enough times to conclude that retrying is
not going to help. The distinction this feature must hold is between a
failure that another attempt fixes and a failure that another attempt only
pays for again.

### Why this is a specification and not a fix

Three things about the shape make this the owner's decision rather than a
plumbing correction:

- **Which failures are worth retrying is a policy choice, not a fact.** The
  gate already has a classified verdict for each reviewer run — healthy,
  exhausted, rate-limited, failed, unclassifiable — and today it collapses
  every non-healthy one into a single unbounded retry. Splitting them, or
  bounding them uniformly, or backing off, are different products with
  different failure modes.
- **It changes a stated invariant.** Spec 062's "at most one round per
  reviewed head SHA" becomes "at most one *conclusive* round, plus a bounded
  number of inconclusive attempts, per reviewed head SHA." That is a
  restatement of a success criterion and of two live contracts, and the
  spend ceiling per pull request moves with it.
- **It decides who is left holding the pull request.** A bound that stands
  the gate down permanently at one head can strand a pull request on a
  transient outage; a bound that never stands down permanently is the bug
  this feature is fixing. Where that line sits is a trade-off about how much
  the pipeline may spend before asking a human.

### What this feature does not change

Nothing about a round that *does* reach a disposition. A clean round still
records its head and clears the gate; a findings round still folds and
re-dispatches; the round budget and its human hand-off are untouched.
Nothing about the kill switch, the auto-merge setting, the merge
preconditions, or the fold path. The gate's cadence stays what it is. The
only behaviour that changes is what happens on the *second and subsequent*
inconclusive attempt at one unchanged head SHA.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The gate stops paying for a review that cannot succeed (Priority: P1)

A lifecycle pull request reaches the ready point with a diff the reviewer
cannot get through: every attempt runs out of turns before it produces a
findings list. The first attempt fails, and is retried — the gate cannot
know yet that the failure is deterministic. After a small number of attempts
at the same unchanged head, the gate stops selecting that pull request,
states on the lifecycle issue that it stood down, which head it stood down
at, how many attempts it spent, and what the last failure was. The
maintainer reads one comment and knows the pull request needs a human,
rather than finding two dozen identical failure comments and a spent usage
window.

**Why this priority**: this is the defect. Until the retry has a floor, the
gate can consume the repository's entire review spend on a single pull
request it will never clear, and the signal a maintainer needs is buried in
its own repetition.

**Independent Test**: drive the gate against a fixture whose reviewer step
always fails at one head and confirm the number of paid review invocations
at that head is bounded, that the final run posts a stand-down naming the
head and the count, and that subsequent runs select nothing.

**Acceptance Scenarios**:

1. **Given** a ready lifecycle pull request at head SHA `A` whose reviewer
   step fails inconclusively, **When** the gate runs repeatedly with no new
   commits, **Then** the number of reviewer invocations at `A` never exceeds
   the attempt ceiling, and every attempt after the first is visible as an
   attempt rather than as a first try.
2. **Given** the attempt ceiling has been reached at head `A`, **When** the
   gate runs again with `A` still the head, **Then** no reviewer is invoked,
   no cost is incurred beyond selection, and the pull request is not
   selected.
3. **Given** the attempt ceiling has been reached at head `A`, **When** the
   stand-down is recorded, **Then** the lifecycle issue names the head SHA,
   the number of attempts spent, and the classified reason for the last
   failure, in a form distinguishable from a clean round, a findings round,
   and round-budget exhaustion.
4. **Given** the attempt ceiling has been reached at head `A`, **When** a
   maintainer reads the pull request's checks, **Then** the gate's status at
   `A` is a non-passing state that says the gate could not reach a verdict —
   never a pass, and never the absence of a status.

---

### User Story 2 - A transient failure still recovers without a human (Priority: P1)

The reviewer hits a rate limit on its first attempt at a head. No human does
anything. A later scheduled run tries the same head again, the reviewer gets
through, and the round reaches its normal disposition — clean, or findings
folded back into the lifecycle. The bound this feature adds never converts a
recoverable outage into a stranded pull request.

**Why this priority**: it is the property spec 062 already requires and the
reason the exemption exists at all. A bound that sacrifices it trades one
defect for a worse one, so it has to ship in the same slice as the bound.

**Independent Test**: drive the gate against a fixture that fails
inconclusively once and succeeds on the next attempt at the same head, and
confirm the successful round's disposition is reached with zero human
actions and that the earlier attempt left no residue in the round budget or
the dedup fingerprint sets.

**Acceptance Scenarios**:

1. **Given** an inconclusive attempt at head `A` below the ceiling, **When**
   the next scheduled run selects the same pull request, **Then** head `A`
   is reviewed again and the attempt is charged to `A`'s attempt count.
2. **Given** a later attempt at head `A` reaches a disposition, **Then** the
   round is recorded exactly as it is today — head, round number, outcome,
   fingerprint sets — and the accumulated inconclusive attempts do not
   change that round's number, its outcome, or the round budget it charges
   against.
3. **Given** any number of inconclusive attempts at head `A`, **Then** none
   of them adds to or removes from the folded or filed fingerprint sets, so
   a later conclusive round dedupes against exactly the set it would have
   seen without them.

---

### User Story 3 - A new head starts over (Priority: P2)

Implement pushes a fix, or a maintainer pushes a commit, and the pull
request's head moves from `A` to `B`. Whatever the gate spent trying to
review `A` — including a stand-down at `A` — does not suppress or
pre-charge `B`. The gate reviews `B` on its next run as it would any
newly-ready head.

**Why this priority**: the attempt ledger is only correct if it is keyed to
the head it was accrued at. Without this, one bad diff would permanently
disable the gate for the pull request, which is the opposite of the fix.

**Independent Test**: reach the ceiling at head `A`, advance the head to
`B`, and confirm the next run selects the pull request and invokes the
reviewer with a fresh attempt count.

**Acceptance Scenarios**:

1. **Given** a stand-down recorded at head `A`, **When** the head becomes
   `B`, **Then** the next scheduled run selects the pull request and the
   attempt count applied to `B` starts from zero.
2. **Given** a stand-down recorded at head `A`, **When** the head becomes
   `B` and a round at `B` comes back clean, **Then** the gate clears at `B`
   and nothing about `A`'s stand-down blocks it.

---

### User Story 4 - A stand-down never authorizes a merge (Priority: P2)

Auto-merge is switched on. A pull request has stood down at the attempt
ceiling, so the gate's most recent record at that head says "could not
reach a verdict." No merge happens. The merge path still requires a round
that came back clean at the exact head being merged, and a stand-down is not
one.

**Why this priority**: the marker is what the merge preconditions read. Any
new record written at a head is a new opportunity for the merge gate to
mistake it for coverage, and a wrong answer here merges unreviewed code.

**Independent Test**: construct a marker whose only record at the current
head is a stand-down, run the merge preconditions against it, and confirm
the unmet condition is named and no merge is attempted.

**Acceptance Scenarios**:

1. **Given** a stand-down recorded at the current head and auto-merge on,
   **When** the merge preconditions are re-derived, **Then** they report
   unmet and name the condition, and no merge is performed.
2. **Given** a stand-down recorded at the current head, **When** anything
   reads the gate's state for that head, **Then** "a clean round was
   recorded at this head" is false.

---

### Edge Cases

- **The gate declines before the reviewer runs.** A run that stands down for
  the kill switch, finds a readiness condition unmet, or fails during
  selection has not tried to review anything. It must not consume an
  attempt — otherwise a paused week silently spends the ceiling.
- **The round fails after the reviewer succeeded.** The reviewer produced a
  parseable findings list, but the disposition job failed before reporting an
  outcome. Nothing was folded or filed, so the round is still inconclusive
  and still retryable — but the attempt was paid for, so it counts.
- **A marker written before this feature exists.** It carries a round
  record and no attempt ledger. It must read as zero attempts spent at its
  recorded head, never as a crash and never as an already-exhausted ledger.
- **The marker cannot be read at all.** Unchanged from today: selection stops
  rather than treating a failed read as "no round yet." A failed read must
  not be read as a fresh attempt ledger either.
- **The head moves mid-attempt.** The attempt belongs to the head the
  reviewer was actually pointed at, not to whatever the head became by the
  time the outcome is recorded.
- **The round budget and the attempt ceiling are both in play.** A pull
  request that has spent conclusive rounds and then starts failing
  inconclusively must be bounded by both, and the reason stated on the
  lifecycle issue must say which bound stopped it.
- **A rate limit outlasts the ceiling.** If every attempt inside the
  ceiling lands inside one rate-limit window, the pull request stands down
  for a reason that would have cleared on its own. Whether the gate may try
  again at the same head after such a stand-down is the open question Q3
  below.
- **Two different heads of the same pull request.** The ledger holds one
  head at a time; a new head replaces it rather than accumulating a history.
- **The pull request or its lifecycle issue is closed.** Unchanged from
  today: the round stops without posting onto a dead pull request, and a
  closed subject needs no ledger entry.

## Requirements *(mandatory)*

### Functional Requirements — the attempt ledger

- **FR-001**: The gate MUST record how many inconclusive attempts it has
  spent at a given head SHA, keyed to that head SHA.
- **FR-002**: That record MUST live in the same durable home as the existing
  round record, written by the same single writer, so the gate's state for a
  pull request remains readable from one place.
- **FR-003**: Recording an inconclusive attempt MUST NOT record that the head
  was covered by a conclusive round, MUST NOT advance the round number, and
  MUST NOT alter the folded or filed fingerprint sets.
- **FR-004**: An inconclusive attempt MUST NOT count against the round
  budget.
- **FR-005**: Only an attempt in which the reviewer was actually invoked MUST
  count against the ceiling. A run that declined for the kill switch, for an
  unmet readiness condition, or before a pull request was selected MUST NOT
  consume an attempt.
- **FR-006**: A record carrying no attempt ledger MUST be read as zero
  attempts spent, so markers written before this feature keep working.
- **FR-007**: A record whose attempt ledger is keyed to a head SHA other than
  the pull request's current head MUST be read as zero attempts spent at the
  current head.
- **FR-008**: A failure to read the gate's recorded state MUST continue to
  stop selection rather than be read as either "no round yet" or "no attempts
  yet".

### Functional Requirements — the bound

- **FR-009**: While the attempts spent at the current head are below the
  ceiling, the gate MUST continue to select and re-review that head exactly
  as it does today.
- **FR-010**: When the attempts spent at the current head reach the ceiling,
  the gate MUST stop selecting that pull request at that head, and MUST NOT
  invoke the reviewer for it again at that head.
- **FR-011**: The ceiling MUST have exactly one home in the repository — one
  named constant the gate and its verifier both read — never a value pasted
  into more than one site. [NEEDS CLARIFICATION: Q2 — what is the ceiling's
  value, and is it a PR-reviewed constant like the existing round budget or a
  repository variable a maintainer can change without a PR?]
- **FR-012**: Which inconclusive outcomes are retried, and how the retry is
  spaced, MUST be stated as one policy the gate applies uniformly. [NEEDS
  CLARIFICATION: Q1 — a per-head attempt ceiling applied to every
  inconclusive outcome, an exponential back-off per head, retrying only a
  rate-limited outcome and treating every other inconclusive outcome as
  covering the head, or a combination?]
- **FR-013**: The classification that decides whether an outcome is retryable
  MUST be derived by deterministic code from the recorded run evidence the
  gate already classifies, never from an agent's own account of what happened
  (constitution IX).
- **FR-014**: What makes the gate willing to try the same head again after a
  stand-down MUST be stated and MUST be checkable. [NEEDS CLARIFICATION: Q3 —
  does a stand-down at a head hold until the head moves or a human
  intervenes, mirroring round-budget exhaustion, or may the gate try that
  head again after a stated cooldown or once a recorded rate-limit reset time
  has passed?]

### Functional Requirements — what the stand-down says

- **FR-015**: A stand-down MUST be stated on the lifecycle issue, naming the
  head SHA, the number of attempts spent, and the classified reason for the
  last failure.
- **FR-016**: A stand-down MUST be distinguishable, on both the lifecycle
  issue and the pull request's status, from a clean round, a findings round,
  and round-budget exhaustion.
- **FR-017**: A stand-down MUST NOT be reported as a pass, and MUST NOT be
  reported as the absence of a status.
- **FR-018**: A stand-down MUST NOT satisfy any merge precondition. The
  condition "a round came back clean at this exact head" MUST remain false at
  a head whose only record is a stand-down.
- **FR-019**: Each inconclusive attempt below the ceiling MUST remain
  distinguishable on the lifecycle issue from the first attempt at that head,
  so a maintainer reading the issue can see a retry loop forming before the
  ceiling ends it.

### Functional Requirements — keeping the record honest

- **FR-020**: The live contracts of spec 062 that state the retry behaviour —
  the round-budget and marker-writing sections of the workflow contract, and
  the retryability paragraph of the review-and-findings contract — MUST be
  updated to state the bound, so no live contract contradicts the workflow it
  describes.
- **FR-021**: The invariant spec 062 expressed as "never more than one round
  per SHA" MUST be restated here in the form this feature makes true, and the
  restatement MUST be the version any new gate checks.
- **FR-022**: Every failure branch this feature adds — ceiling reached,
  attempt recorded below the ceiling, ledger keyed to a stale head, absent
  ledger — MUST be exercised by a checked-in fixture, and the check that
  exercises them MUST be reachable through the gate registry and run the same
  subject with the same arguments locally as in CI (constitution VIII).

### Key Entities

- **Attempt ledger**: the count of inconclusive reviewer invocations spent
  at one head SHA, together with the head SHA it was accrued at and the
  classified reason for the most recent failure. Lives alongside the existing
  round record; replaced wholesale when the head moves.
- **Inconclusive outcome**: a round that reached no disposition — the
  reviewer failed, timed out, was rate-limited, exhausted its turns, produced
  an unparseable result, or the disposition failed before reporting. Carries
  the classified verdict the gate already derives for the run.
- **Stand-down**: the gate's recorded decision to stop trying one head,
  naming the head, the attempts spent, and the reason. Not a round, not a
  pass, and not a merge authorization.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a lifecycle pull request whose review fails
  inconclusively at every attempt, the total number of paid reviewer
  invocations at one unchanged head SHA is bounded by the ceiling and does
  not grow with elapsed time — down from roughly one per scheduled run for
  as long as the pull request stays open.
- **SC-002**: A pull request whose first attempt at a head is inconclusive
  and whose next attempt succeeds reaches its normal disposition with zero
  human actions.
- **SC-003**: 100% of stand-downs are legible from the lifecycle issue alone:
  the head SHA, the attempts spent, and the reason, without reading a run
  log.
- **SC-004**: The number of pipeline merges authorized by a head whose only
  record is a stand-down is zero.
- **SC-005**: Across any sequence of inconclusive attempts, the round number,
  the round budget consumed, and the folded/filed fingerprint sets are
  identical to what the same sequence of conclusive rounds alone would have
  produced.
- **SC-006**: A new head SHA following a stand-down is reviewed on the next
  scheduled run, with no human action.
- **SC-007**: A deliberately broken bound — the ceiling removed, raised in
  one of two places, or the ledger keyed to something other than the head —
  is caught by a failing check rather than by a reader.
- **SC-008**: Every failure branch this feature adds is exercised by a
  checked-in fixture, and the local gate suite and CI run that fixture
  identically.

## Assumptions

- The gate's existing per-run classified verdict for a reviewer invocation
  (healthy, exhausted, rate-limited, failed, unclassifiable) is the evidence
  the retryability decision is derived from; this feature reuses it rather
  than introducing a second classification.
- The gate's existing durable record on the lifecycle issue is the right home
  for the attempt ledger, and that record's single-writer discipline is
  preserved rather than relaxed.
- The gate's schedule, its one-pull-request-per-run selection, its
  repository-wide concurrency group, and its kill switch are unchanged.
- The round budget, its value, and its human hand-off are unchanged; the
  attempt ceiling is a second, independent bound.
- Spec 062's merged `spec.md` is a historical record and is not edited by
  this feature; its `contracts/` are live and are (FR-020).
- The auto-merge setting's default-off state and every existing merge
  precondition are unchanged; this feature only adds a state that must not
  satisfy them.
- A maintainer reading a stand-down will decide what to do about the pull
  request by hand; this feature does not attempt to diagnose *why* the
  reviewer could not get through, or to shrink the diff for it.

## Out of Scope

- Making the reviewer succeed on a diff that currently exhausts it — chunking
  the diff, raising the turn budget, or selecting a different model. A
  stand-down says the gate gave up; making it give up less often is a
  separate feature.
- Changing the round budget, its value, or its hand-off.
- Any change to the fold path, the finding fingerprint scheme, or the
  out-of-scope filing path.
- Applying the same bound to any other pipeline stage's retries.
- Notifying anyone outside the lifecycle issue and the pull request status.

## Dependencies

- The lifecycle review gate of spec 062, its durable round record, and its
  selection and readiness logic.
- The existing agent-verdict classification that produces the retryable /
  not-retryable evidence (FR-013).
- The merge preconditions that read the gate's recorded state (FR-018).
- Spec 062's live contracts (FR-020) and the gates that read them (FR-022).
