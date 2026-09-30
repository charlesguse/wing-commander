# Feature Specification: A Spent Review Budget Stops, and a Re-raised Finding Stays Open

**Feature Branch**: `114-spent-budget-reraised-finding`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue #833 — "lifecycle-review-gate: once the round
marker reads (#826), budget exhaustion re-reviews every new head and an
unfixed re-raised finding records 'clean'". Two spec 062 behaviours that
were unobservable while the `review_gate` marker always read as `{}` (so
every round looked like round 1) become live once that read is fixed:
round-budget exhaustion does not actually stop the loop, and a finding
that survives into a second round untouched is deduplicated away and
recorded as a clean round.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A spent round budget stops, and stops costing (Priority: P1)

A lifecycle pull request has spent its review rounds without converging.
The maintainer expects exactly what the pipeline told them on the
lifecycle issue: the gate has handed this pull request to a human and is
done with it. No further review rounds are paid for, and nothing the
pipeline itself does to that branch — least of all a rebase when `main`
moves — quietly puts it back in the queue.

**Why this priority**: This is the failure mode with a cost attached. The
exhausted record names the head SHA it was written against, so the next
head — from a human push or from the pipeline's own rebase of the spec
branch — makes the pull request selectable again, pays for a full reviewer
run, records exhaustion again, and climbs the round counter past its own
budget. The bound spec 062 FR-022 promises is not a bound at all, and the
loop it was written to stop runs indefinitely at one reviewer run per new
head.

**Independent Test**: Seed a lifecycle pull request whose round record is
at the budget with findings open, move its head (a rebase, then a push),
and confirm across several gate runs that no reviewer runs, no round is
recorded, the round counter does not climb, and the lifecycle issue says
why.

**Acceptance Scenarios**:

1. **Given** a lifecycle pull request whose latest round record is
   exhausted, **When** the gate runs, **Then** the pull request is not
   selected for a new round, no reviewer is invoked, and no cost is
   attributed to it.
2. **Given** that same pull request, **When** its head SHA moves for any
   reason — a pipeline rebase onto a moved `main`, or a push — **Then** it
   is still not selected, and the head change alone does not clear the
   exhausted state.
3. **Given** that same pull request, **When** the agreed human clearing
   action is taken, **Then** the pull request becomes selectable again and
   the lifecycle issue records who cleared it and what the round counter
   now is.
4. **Given** a lifecycle pull request with no round record at all, or one
   whose record cannot be read, **When** the gate runs, **Then** it is
   treated as never reviewed — never as exhausted.

---

### User Story 2 — A finding nobody fixed keeps the gate red (Priority: P1)

A round raises an in-scope finding; it is folded into `tasks.md` and
implement is re-dispatched. Implement does not actually fix it. The next
round raises the same finding again. The maintainer expects the gate to
stay red and the pull request to stay unmerged — not to be told the
review came back clean about a defect that is still sitting in the diff.

**Why this priority**: This one can merge a known defect. Cross-round
deduplication is deliberate (spec 062 FR-021, SC-003: never fold the same
finding twice), but the round's own outcome is derived from *newly folded*
findings alone, so a round whose only in-scope survivor was already folded
records `clean`, posts a passing commit status, and satisfies the
auto-merge precondition that no in-scope findings are open — while that
finding is open. Spec 062 FR-026 requires "the review round clean with
zero open in-scope findings" before a merge; today those two clauses can
disagree.

**Independent Test**: Drive two rounds against a pull request whose seeded
defect is folded in round 1 and left unfixed at round 2's head, and
confirm round 2 is not recorded clean, posts no passing status, folds
nothing a second time, and — with auto-merge enabled — merges nothing.

**Acceptance Scenarios**:

1. **Given** a finding folded in an earlier round, **When** a later round
   raises the same finding against the current head, **Then** the round's
   open in-scope finding count includes it, the round is not recorded
   clean, and no passing status is posted.
2. **Given** that same round, **When** its disposition completes, **Then**
   the finding is not folded or filed a second time and no duplicate task
   is written.
3. **Given** that same round and the auto-merge setting enabled, **When**
   the merge preconditions are re-derived, **Then** the merge is refused
   and the refusal names the open-findings condition.
4. **Given** a round whose only survivors are out-of-scope findings —
   including out-of-scope findings already filed in an earlier round —
   **When** its disposition completes, **Then** the round is still clean
   and the out-of-scope findings are not held against the pull request.
5. **Given** a finding that is reworded, or raised against a different
   file, **When** the round completes, **Then** it is a new finding and
   folds normally.

---

### User Story 3 — No passing status the budget did not permit (Priority: P2)

Whatever the budget rule turns out to be, exactly one rule applies to
every outcome path. A maintainer reading a green `lifecycle-review-gate`
status on a lifecycle pull request can rely on it meaning a round the
budget permitted came back clean.

**Why this priority**: The budget is consulted on the fold path only. The
zero-raw-findings fast path — the one that writes the passing status —
never looks at it, so a round past the budget can still be recorded clean
and become merge-eligible. Spec 062 FR-014 already names an exhausted
budget as a non-passing condition, so the two paths disagree with each
other and one of them disagrees with the spec.

**Independent Test**: Exercise both outcome paths against a round record
at the budget boundary in checked-in fixtures, and confirm each path
reaches the same verdict about whether that round was permitted.

**Acceptance Scenarios**:

1. **Given** a round record at the budget boundary, **When** the reviewer
   returns zero raw findings, **Then** the same budget rule the fold path
   applies decides whether a clean round and a passing status are
   recorded.
2. **Given** any round the budget did not permit, **When** the gate
   reports, **Then** no passing commit status exists for that head and the
   lifecycle issue states the reason by name.

---

### Edge Cases

- **The pipeline moves the head itself.** The spec branch is rebased when
  `main` moves; the new head must not be read as new work to review on an
  exhausted pull request.
- **A human pushes a fix to an exhausted pull request.** Whether that push
  alone resumes reviewing is the clearing question (FR-004); until it is
  answered, the safe reading is that a push is not a clearance.
- **A round that never reached a disposition.** A failed, rate-limited or
  unparseable round already leaves the prior record untouched. It must not
  advance the round counter, trip exhaustion, or count against the
  deduplication sets.
- **No round record, or an unreadable one.** Means no round has ever
  completed. Never exhausted.
- **The same finding raised a third time.** It is still one open finding,
  still folded once.
- **The reviewer re-raises a finding the fold did fix.** The pull request
  stays red on a finding a human may disagree with; the round budget and
  the human handoff remain the escape hatch, and no pipeline path may
  clear it by itself.
- **An exhausted pull request whose lifecycle issue or pull request is
  closed.** Nothing is posted onto a dead pull request; the existing
  closed-lifecycle gate keeps its behaviour.

## Requirements *(mandatory)*

### Functional Requirements — exhaustion is a state, not a per-round verdict

- **FR-001**: The gate MUST derive "this pull request's round budget is
  spent" from durable round state **before** any billable reviewer
  invocation, so a run that encounters an exhausted pull request costs
  nothing beyond the reads it already makes.
- **FR-002**: Exhaustion MUST be recorded when a completed round leaves at
  least one in-scope finding open and the round counter has reached the
  budget — not one round later, after a further reviewer run has already
  been paid for.
- **FR-003**: While a pull request is exhausted, a change of head SHA
  alone MUST NOT return it to selection, including a head the pipeline
  itself produced (a rebase of the spec branch onto a moved `main`).
- **FR-004**: The exhausted state MUST be cleared only by an explicit
  human action. [NEEDS CLARIFICATION: which human action clears an
  exhausted lifecycle pull request — the maintainer removing a label the
  gate added, a maintainer comment the gate recognises, a head SHA
  authored by a human rather than by the pipeline, or a combination?]
- **FR-005**: When the state is cleared, the round counter MUST restart so
  that the cleared pull request gets the full budget again, and the
  lifecycle issue MUST record the clearance, the counter's new value, and
  which action cleared it.
- **FR-006**: The exhausted state MUST be discoverable by a maintainer
  looking at the lifecycle issue's labels or the pull request's status —
  not only by reading a marker comment's payload.
- **FR-007**: A missing or unreadable round record MUST be read as "no
  round has completed", never as exhausted.
- **FR-008**: A round that did not reach a disposition — the reviewer
  failed, was rate-limited, or produced nothing parseable — MUST NOT
  advance the round counter and MUST NOT trip exhaustion; it stays
  retryable, exactly as it is today.
- **FR-009**: The round budget MUST remain a single-homed constant with
  one reader-visible value; this feature MUST NOT introduce a second
  budget, a second counter, or a per-pull-request override.

### Functional Requirements — one budget rule across every outcome path

- **FR-010**: Every outcome path MUST consult the same budget state: the
  zero-raw-findings fast path and the partition/fold path MUST reach the
  same verdict about whether a round was permitted, from one shared
  decision rather than two independent checks.
- **FR-011**: A round the budget did not permit MUST NOT produce a passing
  commit status on the reviewed head, and MUST NOT satisfy the auto-merge
  preconditions. [NEEDS CLARIFICATION: when the budget is spent, does a
  round that returns zero findings still earn its passing status and merge
  eligibility — exhaustion biting only while findings are open — or does
  exhaustion outrank a clean result?]

### Functional Requirements — a re-raised finding is an open finding

- **FR-012**: When a round raises an in-scope finding whose deduplication
  key matches one folded in an earlier round, the gate MUST count it
  toward this round's open in-scope finding count.
- **FR-013**: Such a finding MUST NOT be folded or filed a second time,
  and MUST NOT produce a duplicate task: spec 062 FR-021 and SC-003 are
  unchanged by this feature.
- **FR-014**: A round whose in-scope survivors are only already-folded
  re-raises MUST NOT be recorded as `clean`, MUST NOT post a passing
  status, and MUST NOT make the pull request merge-eligible.
- **FR-015**: The open in-scope finding count the round records MUST
  include those re-raises, so the merge precondition that no findings are
  open, the commit status, and the lifecycle issue's narration all state
  the same fact.
- **FR-016**: Because such a round cannot fold and so cannot make
  progress on its own, the pipeline MUST take a defined next step rather
  than looping silently. [NEEDS CLARIFICATION: what happens after a round
  whose only open in-scope findings are unfoldable re-raises — stop
  immediately and hand the pull request to a human with its own named
  outcome, keep the gate red and let further rounds run until the budget
  is spent, or re-dispatch implement against the task the earlier fold
  already wrote?]
- **FR-017**: Out-of-scope findings, including ones already filed in an
  earlier round, MUST NOT be counted as open against the pull request or
  its gate status: spec 062 FR-020 is unchanged.
- **FR-018**: "The same finding" MUST be decided by the existing
  deterministic deduplication key, never by the reviewing agent's
  judgment; a reworded finding, or one raised against a different file, is
  a new finding.

### Functional Requirements — legibility

- **FR-019**: Each outcome this feature touches — exhausted, open
  unfoldable re-raise, clean, not reached — MUST be distinguishable from
  the others and from "not yet run", on both the pull request's status and
  the lifecycle issue, and each MUST be exercised by a checked-in fixture.
- **FR-020**: The lifecycle issue's round-outcome narration MUST state
  only what the code enforces. The existing exhausted sentence — that the
  pull request "is not selected again until a human intervenes" — MUST
  become true, and MUST name the action that actually clears it.
- **FR-021**: The agreement between the narration, the commit status, the
  selection filter and the merge preconditions MUST be held by a check
  that fails when they drift, not by a reader.
- **FR-022**: Round state MUST continue to live on the lifecycle issue's
  own record and MUST NOT be written as a commit to the reviewed branch: a
  branch MUST NOT author the facts its own merge is judged by.

### Key Entities

- **Round record**: The durable per-pull-request state the gate reads and
  writes on the lifecycle issue — round number, reviewed head SHA,
  outcome, open finding count, and the folded/filed deduplication sets.
- **Round budget**: The bound on how many review-fold-implement rounds one
  pull request may take. Unchanged in value; changed in consequence.
- **Exhausted state**: A pull request the gate has handed to a human. Not
  a property of one head SHA, and not cleared by a new one.
- **Clearance action**: The human act that returns an exhausted pull
  request to the gate's queue (FR-004).
- **Re-raised finding**: A finding whose deduplication key matches one an
  earlier round already folded — evidence the folded work did not land.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across ten consecutive gate runs following an exhausted
  record — including runs where the head moved because the pipeline
  rebased the spec branch — the number of reviewer invocations
  attributable to that pull request is zero, and the round counter does
  not change.
- **SC-002**: The number of exhausted pull requests that return to
  reviewing without the clearance action of FR-004 is zero; every one that
  does return has a clearance recorded on its lifecycle issue.
- **SC-003**: The number of passing `lifecycle-review-gate` statuses
  posted for a round the budget did not permit is zero, measured across
  both outcome paths.
- **SC-004**: For a pull request with one finding folded in round 1 and
  unfixed at round 2's head: round 2's recorded outcome is not clean, no
  passing status exists on that head, exactly one task was ever written
  for that finding, and with auto-merge enabled the number of merges is
  zero.
- **SC-005**: Every outcome named in FR-019 is exercised by a checked-in
  fixture and is distinguishable from the others without reading workflow
  logs.
- **SC-006**: A deliberately introduced disagreement between the
  narration, the selection filter, the commit status and the merge
  preconditions is caught by a failing check rather than by a reader.
- **SC-007**: Spec 062 SC-009 still holds after this feature: at most one
  review round per distinct reviewed head SHA, and no head is reviewed
  twice.

## Assumptions

- The fix that makes the round record readable (#826, landed via #830) is
  a precondition: none of these behaviours are observable until a round
  record other than empty can be read. This feature assumes that fix is in
  place and does not re-do it.
- That a re-raised, still-open in-scope finding must not read as `clean`
  is taken as already settled by spec 062 FR-026 ("zero open in-scope
  findings") rather than re-opened here; the open question (FR-016) is
  what the pipeline does next, given that it must not fold the finding
  twice.
- The round budget keeps its current value and its current single-homed,
  pull-request-reviewed constant shape; only its consequences change.
- The gate's existing discipline holds unchanged: state on the lifecycle
  issue rather than the reviewed branch, one round in flight
  repository-wide, the kill switch re-read before any durable action, and
  the auto-merge switch off by default.
- `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` stays off until this feature ships,
  because both defects can hand a merge-eligible verdict to a pull request
  that has not earned one.
- No new credential, permission or identity class is introduced; the
  clearance action is something a maintainer can already do with the
  permissions they have.
- A re-raised finding is taken at face value as evidence the fold did not
  land. Judging whether the reviewer is right about it is out of scope.

## Out of Scope

- Changing the round budget's value, or making it a repository variable.
- Verifying, re-scoring or adjudicating findings — deciding whether a
  re-raised finding is correct.
- Changing the deduplication key itself (spec 076's scheme), or the
  fingerprint formula's single home.
- The human review path and the pull-request-conversation wrapper's
  bot-author exclusion, both unchanged.
- Turning auto-merge on, and any change to which classes of pull request
  the pipeline may merge.

## Dependencies

- `specs/062-lifecycle-review-gate` — the governing spec. FR-014 (a
  non-passing status whenever the budget is exhausted), FR-021 and SC-003
  (never fold or file a finding twice), FR-022 (rounds are bounded and
  exhaustion hands over to a human), FR-020 (out-of-scope findings are not
  held against the pull request), FR-026 (zero open in-scope findings
  before a merge) and SC-009 (at most one round per head SHA) all
  constrain this feature; FR-022 and FR-026 are the two it exists to make
  true.
- `specs/042-post-review-fold-loop` — the findings-to-tasks fold and
  re-dispatch path a re-raised finding must not duplicate.
- The lifecycle rebase path that rewrites a spec branch when `main` moves
  — the head-change source that makes exhaustion non-terminal today.
- The pipeline's existing human-handoff conventions (the stalled-stage
  label and notice) — the nearest precedent for what a "handed to a human"
  state looks like on the board, and a candidate answer to FR-004.
- The gate's selection filter, readiness decision and merge preconditions
  — the three deterministic readers that must agree with the round record
  after this change.
