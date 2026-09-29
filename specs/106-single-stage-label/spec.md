# Feature Specification: One Stage Label Per Lifecycle Issue Across a Stall

**Feature Branch**: `spec-draft/106-single-stage-label`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "When finalize has already flipped the lifecycle label to `stage:review` and a later step fails, the `stalled` job adds `stage:stalled` without removing `stage:review`. The issue then carries two stage labels. That happened on spec 069's lifecycle #516, and the branch froze for two days. Any reader that selects on a single `stage:*` label, including the board's eligibility check, the watchdog's spec-meta comparison and a maintainer's filter, sees contradictory state. The fix needs a decision: stall replaces the stage label, so `stage:review` is removed on stall and restored on restart; or a post-PR failure doesn't stall at all, since the PR is already open for review. #781 narrowed the trigger with a retry on the most common case, but the dual-label state itself is unchanged."

## Overview

The `stage:*` label family is the pipeline's public, human-readable statement
of *where a specification is right now*. Everything that reads it — a
maintainer's issue filter, the board loop's eligibility check, the watchdog's
comparison of a run against the recorded lifecycle state, and the cleanup
stage's own idempotency guard — assumes at most one such label answers that
question. The stall path does not maintain that assumption.

When a stage's survivor job posts its "stage did not start" notice, it adds
`stage:stalled` and removes *one specific* label the caller named. For the
finalize stage the caller names `stage:finalize` — a label no part of the
pipeline ever applies — while the label actually on the issue is
`stage:review`, written moments earlier by finalize's own successful work.
The removal is a permanent no-op and the issue ends up carrying both
`stage:review` and `stage:stalled`, with no signal that anything is wrong.
Observed on the lifecycle issue of specification 069 (#516), where the
specification sat frozen for two days.

Two other stall call sites name no label at all and therefore remove nothing,
so the same contradictory state is reachable from more than one stage. Two
*other* places in the pipeline — finalize's own successful stage flip and the
cleanup stage's stalled arm — already solve this correctly by sweeping every
other `stage:*` label off the issue. The pipeline therefore already contains
the shape of the answer; it is simply not applied on the stall path.

Change #781 reduced how often the finalize stall is reached, by retrying the
most common triggering failure. It did not change what the labels look like
once a stall does happen, which is what this specification addresses.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stalled specification reports one unambiguous state (Priority: P1)

A maintainer opens the lifecycle issue for a specification whose finalize run
failed after the final pull request was already opened. The issue states
exactly one stage, and that stage is the truth about what the maintainer must
do next. Every automated reader that selects on a single `stage:*` label
reaches the same conclusion the maintainer does.

**Why this priority**: This is the reported defect. Contradictory labels are
what froze #516 — no reader, human or automated, could tell whether the
specification was awaiting review or awaiting a restart, so none of them
acted. Fixing this alone restores the pipeline's core promise that a
specification's state is legible from its lifecycle issue.

**Independent Test**: Drive a stage to the point where its post-agent work has
already flipped the stage label, force a later step to fail, and read the
issue's labels. Exactly one `stage:*` label is present.

**Acceptance Scenarios**:

1. **Given** a lifecycle issue carrying `stage:review` because finalize opened
   the final pull request, **When** a step after that flip fails and the
   stalled path runs, **Then** the issue carries exactly one `stage:*` label
   and a maintainer reading only the labels can tell which action is owed.
2. **Given** a lifecycle issue carrying `stage:plan` because the tasks stage
   has not yet flipped it, **When** the tasks stage stalls, **Then** the issue
   again carries exactly one `stage:*` label — the same rule, not a
   finalize-only special case.
3. **Given** a stalled lifecycle issue, **When** the board loop's eligibility
   check, the watchdog's lifecycle-state comparison, and the cleanup stage's
   idempotency guard each read the issue, **Then** all three derive the same
   single stage and none of them observes a label combination it has no rule
   for.
4. **Given** the stall path names a stage label for removal, **When** that
   name is compared against the set of stage labels the pipeline actually
   applies, **Then** it is a label something writes — a name nothing ever
   applies is not accepted as a removal target.

---

### User Story 2 - Restarting a stalled specification returns it to one correct label (Priority: P2)

A maintainer resolves the cause of a stall and re-drives the stage. The
lifecycle issue stops advertising a stall and returns to naming the stage the
specification is actually in, in a single label, without the maintainer
editing labels by hand.

**Why this priority**: A fix that only cleans up on the way *into* a stall
leaves a new asymmetry on the way out — the issue would then carry
`stage:stalled` plus the restored stage label, which is the same defect with
different operands. It is P2 rather than P1 because a maintainer who can at
least read an unambiguous stalled state can restart by hand; they cannot act
at all on a contradictory one.

**Independent Test**: Take a lifecycle issue in the stalled state, re-dispatch
the stage, and read the labels once the re-driven stage completes its own
label write. Exactly one `stage:*` label is present and `stage:stalled` is
gone.

**Acceptance Scenarios**:

1. **Given** a lifecycle issue carrying only `stage:stalled` after a finalize
   stall, **When** finalize is re-dispatched and reaches the point where it
   writes its stage label, **Then** the issue carries only the label naming
   the stage it is now in.
2. **Given** a stage whose entry path today removes some previous stage labels
   but not `stage:stalled`, **When** that stage is re-driven after a stall,
   **Then** `stage:stalled` does not survive alongside the new stage label.
3. **Given** a stall whose cause is never resolved, **When** no restart
   occurs, **Then** the issue keeps its single stalled label indefinitely and
   nothing silently clears it.

---

### Deferred: Preventing the rule from regressing

A deterministic check that fails a pull request which reintroduces a second
concurrent `stage:*` label, or names a removal target no writer ever applies,
is required by FR-011 and covered by SC-004 — but it is a property of the
whole change rather than an independently demonstrable user journey, so it is
not written as a separate user story. The repository's existing convention
(Constitution VIII, and `CLAUDE.md`'s "single home" rule about adding the
check to the nearest existing gate) governs where it lives.

### Edge Cases

- **The lifecycle record cannot be written.** The stall path marks the
  specification's lifecycle record stalled before it touches labels, and that
  write can fail (an unavailable branch, an unreadable record, a rejected
  push). Today the stage-label removal is *conditional on that write having
  succeeded*, so the degraded case is exactly the case that leaves two
  labels. FR-005 decides what the labels say when the record and the labels
  cannot be made to agree.
- **The issue carries no `stage:*` label at all.** A stall during the very
  first stage, before any stage label has been applied, must add the stalled
  label and remove nothing, without erroring.
- **The issue already carries `stage:stalled`.** A second stall on the same
  specification must be a no-op with respect to labels, not a duplicate add
  or a removal of the stalled label it just re-added.
- **The specification has already shipped.** A stall arriving on an issue that
  is closed or carries `stage:done` must not resurrect it into a stalled
  state; the cleanup stage already refuses this and the same refusal applies
  here.
- **Label writes fail.** Label operations are best-effort on the stall path
  today and must not begin failing the job — a stall notice that cannot post
  because a label edit was rejected is strictly worse than the current
  defect. A label write that does not land must be visible, not silent.
- **A stall arrives while the final pull request is open.** This is the
  reported case, and the two directions in FR-001 treat it differently: one
  re-labels the issue as stalled, the other leaves it as `stage:review` on
  the grounds that the review the label advertises is genuinely available.
- **Pipeline pull requests mirror the issue's labels.** Stage workflows copy
  the lifecycle issue's label set onto the pull request they open, so a
  contradictory pair on the issue propagates to the pull request. The
  invariant must hold on whatever the mirror copies.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A stall MUST resolve the lifecycle issue to a single,
  non-contradictory stage statement.
  [NEEDS CLARIFICATION: which of the two directions the issue names —
  (a) a stall replaces whatever stage label is present, so `stage:review` is
  removed when the stall is recorded and restored when the stage is
  re-driven; or (b) a failure occurring after the final pull request is
  already open does not stall at all, leaving `stage:review` in place and
  reporting the failure some other way?]
- **FR-002**: A lifecycle issue MUST carry at most one `stage:*` label at any
  time, including while stalled. This is the invariant every reader named in
  FR-008 already assumes.
- **FR-003**: When the stall path removes stage labels, it MUST remove every
  `stage:*` label other than the one it is establishing, rather than a single
  caller-supplied name. The repository already uses this sweep shape in the
  finalize stage's successful label flip and in the cleanup stage's stalled
  arm; the stall path MUST NOT introduce a third, different shape.
- **FR-004**: The stall path MUST NOT accept, as a removal target, a
  `stage:*` label that no part of the pipeline ever applies. The finalize
  stage's stall currently names `stage:finalize`, which nothing writes, so
  its removal has never had any effect.
- **FR-005**: The label outcome MUST be well-defined when the lifecycle
  record could not be marked stalled.
  [NEEDS CLARIFICATION: should the stage-label sweep still run when the
  record write failed — labels are what every reader selects on, so leaving
  them contradictory in the degraded case defeats the fix — or should the
  sweep stay gated on a successful record write so that labels and record
  never disagree, at the cost of preserving today's dual-label state in
  exactly that case?]
- **FR-006**: Re-driving a stage after a stall MUST leave the lifecycle issue
  with only the label naming the stage it is now in; `stage:stalled` MUST NOT
  survive the restart. This MUST hold for every stage that can be re-driven
  after a stall, not only those whose entry path happens to clear it today.
- **FR-007**: The rule MUST apply to every path that can put a lifecycle
  issue into the stalled state.
  [NEEDS CLARIFICATION: is the scope the shared stall path used by every
  stage — which fixes the reported finalize case and the other stages' call
  sites in one place, consistent with the repository's "shared logic has
  exactly one home" rule — or only the finalize stage's own stall, leaving
  the other call sites for a later change?]
- **FR-008**: After the change, every reader of the `stage:*` family MUST see
  a consistent state for a stalled specification: the board loop's
  eligibility selection, the watchdog's comparison of an inspected run
  against the recorded lifecycle state, the cleanup stage's already-stalled
  idempotency guard, and a maintainer's issue filter.
- **FR-009**: Label operations on the stall path MUST remain best-effort with
  respect to the job's outcome — a rejected label edit MUST NOT prevent the
  stall notice from being posted, and MUST NOT turn a stalled stage into a
  failed one.
- **FR-010**: A label operation that does not succeed MUST be reported in the
  run's own output rather than discarded silently, so a repeat of the
  original defect is traceable to the run that caused it.
- **FR-011**: A deterministic check MUST fail a pull request that
  reintroduces a stall path capable of leaving two concurrent `stage:*`
  labels, or that names a removal target no writer ever applies. Per
  Constitution VIII the check MUST be reachable from the gate registry, MUST
  run identically locally and in CI, and every failure branch it ships MUST
  be exercised by a checked-in fixture.
- **FR-012**: The documented description of the `stage:*` family MUST state
  the one-label invariant and what a stall does to it, so the contract a
  reader relies on is written down rather than inferred from behaviour.
- **FR-013**: The change MUST NOT alter the wording, ordering, or posting
  behaviour of the stall notice itself, nor the lifecycle record's own
  `stage` field semantics, beyond what FR-001 and FR-005 decide. Existing
  checks byte-compare parts of that notice.

### Key Entities

- **Lifecycle issue**: The GitHub issue a specification is tracked on. Holds
  the `stage:*` family, the `spec:<NNN-slug>` identity label, and the
  pipeline's status comments. The subject of this feature's invariant.
- **Stage label (`stage:*`)**: The single-valued statement of where a
  specification is. Documented members include `stage:spec`,
  `stage:clarify`, `stage:plan`, `stage:tasks`, `stage:implement`,
  `stage:review` and `stage:done`; `stage:stalled` is created on demand and
  is not pre-created by adopters.
- **Stall record**: The lifecycle record's `stage` field set to the stalled
  value, written on the specification's branch before labels are touched.
  Can fail independently of the label writes, which is what makes FR-005 a
  real decision.
- **Stage survivor path**: The per-stage path that runs when a stage
  terminates abnormally, and that posts the stall notice, marks the record,
  and writes the labels. Shared across stages, with per-stage inputs — which
  is how the finalize stage came to name a label nothing writes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across every stage that can stall, and both the healthy and the
  degraded record-write case, a stalled lifecycle issue carries exactly one
  `stage:*` label — 100% of observed stall outcomes, zero exceptions.
- **SC-002**: Re-driving a stalled specification leaves exactly one `stage:*`
  label, with no manual label editing by a maintainer in any case.
- **SC-003**: Every automated reader of the stage family — board eligibility,
  the watchdog's lifecycle comparison, and the cleanup idempotency guard —
  derives the same single stage for a stalled specification, with zero
  readers encountering a label combination they have no rule for.
- **SC-004**: A deliberately reintroduced dual-label stall path, and a
  deliberately reintroduced removal target that no writer applies, are each
  caught by a checked-in fixture and fail the pull request; neither reaches
  the default branch.
- **SC-005**: Zero regressions in the stall notice's posted content: the
  existing checks over the notice body and over the stall path's structure
  pass unchanged.
- **SC-006**: A maintainer looking only at a stalled lifecycle issue's labels
  can name the single next action within 30 seconds, without opening the run
  or the specification's record.
- **SC-007**: The time a specification can sit in a contradictory state goes
  to zero; the two-day freeze observed on #516 is not reproducible by the
  same sequence of events.

## Assumptions

- The reported defect is exercised through the finalize stage but is not
  finalize-specific: two other stall call sites name no removal target at all
  and so leave whatever stage label was present. The specification therefore
  treats the invariant as pipeline-wide, with FR-007's marker deciding
  whether the *fix* is delivered pipeline-wide or finalize-first.
- The sweep shape FR-003 requires is already the repository's own idiom, used
  by the finalize stage's successful flip and by the cleanup stage's stalled
  arm. No new convention is being invented.
- `stage:stalled` remains a member of the `stage:*` family rather than moving
  to a separate label namespace. A namespace change would make the two labels
  non-contradictory by construction but would break every existing reader and
  every adopter's saved filter, so it is out of scope.
- The lifecycle record's `stage` field and the `stage:*` label are two views
  of the same state and are expected to agree. FR-005 exists precisely
  because they can be made to disagree when one write succeeds and the other
  does not.
- Change #781's retry stays as it is. It reduces the frequency of the
  triggering failure and is orthogonal to the labelling outcome; this feature
  neither depends on it nor modifies it.
- Adopting repositories are not required to pre-create `stage:stalled`; the
  pipeline creates it on demand, and that behaviour is unchanged.
- No change to how the final pull request itself is reviewed or merged is in
  scope. Only the lifecycle issue's labels, the restart path's label
  handling, the governing check, and the documented description of the label
  family are.
