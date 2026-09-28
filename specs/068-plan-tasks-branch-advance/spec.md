# Feature Specification: The Plan and Tasks Stages Record Their Own Branch Advance

**Feature Branch**: `spec-draft/068-plan-tasks-branch-advance`

**Created**: 2026-09-24

**Status**: Draft

**Input**: Lifecycle issue #511 — "plan/tasks stages: populate
`branch_advance` in their metrics records (FR-020 follow-up to #331)".
The issue carries no drafted body; it was routed from the board loop as
the follow-up `specs/050-branch-drift-sha-baseline` FR-020 requires to be
filed, and its subject is the gap that spec deliberately left open.

## Overview

`specs/050-branch-drift-sha-baseline` replaced the watchdog's
commits-in-a-time-window baseline with an exact pair of commits the
pushing stage recorded for itself: the branch it advanced, that branch's
tip before its work, the tip after its last push, and the count of
commits in between. It shipped that mechanism for the **implement stage
only**, and shaped the record group to be stage-neutral on purpose:

> **FR-020**: Only the implement stage records the branch advance pair
> and count in this feature. The new fields MUST be stage-neutral in name
> and semantics … so the plan and tasks stages can populate the same
> fields later without a contract change; until then those stages'
> records carry the fields as unavailable and the watchdog's behaviour
> for them is unchanged (FR-012). The plan/tasks gap MUST be filed as a
> follow-up issue from this spec.

This feature is that follow-up. Today the gap is total rather than
partial: the watchdog's `collect-branch-drift` step names plan, tasks and
implement as the three push-expected stages, and then measures **none of
plan's or tasks' runs at all**. A plan run is triggered by a pull request,
so it reports the draft branch as its head; a tasks run is only ever
dispatched, so it reports the default branch. Neither head is ever the
branch the stage pushes to, so both fall into the step's "the head branch
owes no commits — skipping" arm, and the only stage with an escape from
that arm is implement (`watchdog.yml`, the
`[ "$RUN_NAME" != "Wing Commander · 5 implement" ]` guard). A plan run
that burns its turn budget and pushes no plan, or a tasks run that pushes
no `tasks.md`, produces no signal from this collector at any time, under
any baseline.

The evidence needed to close that is already contractually in place. The
record group is stage-neutral, the publishing composite already accepts
the branch/before/after/commits quadruple as inputs, and the watchdog's
record lookup deliberately filters on the group's own `available` flag
rather than on a stage, a step index or a run label — its checked-in
comment says so in as many words: *"a future non-implement populator must
be picked up here with no collector change."* What is missing is the two
stages capturing and recording the quadruple, and the one guard upstream
of that lookup that still turns every non-implement run away before the
lookup is reached.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A plan or tasks run that pushed nothing is caught (Priority: P1)

A plan run starts, the agent works, and the run finishes without ever
pushing the planning artifacts to the branch it was supposed to advance —
it exhausted its turn budget mid-edit, its push was rejected by a
concurrent force-push, or it reported success while having committed
nothing. Today the lifecycle issue shows a completed run and the
branch-drift collector says nothing, because plan's head branch is the
draft branch and the collector skips it. The maintainer discovers the
missing plan only when the next stage fails on an artifact that was never
produced. With the run recording the branch it advanced and the two tips
it advanced it between, the same zero-progress cycle is reported the way
an implement cycle's is.

**Why this priority**: This is the whole point of the follow-up — plan and
tasks are named as push-expected stages by the collector and are the two
it can never actually measure. Everything else in this feature is in
service of making this detection possible or trustworthy.

**Independent Test**: Drive a plan run and a tasks run that each complete
without pushing to their target branch, and confirm each is reported as
lost-progress, naming the stage, the branch, and the two identical commits
it compared — where today both are silently skipped.

**Acceptance Scenarios**:

1. **Given** a completed plan run whose record carries the branch it
   advanced plus a "before" and "after" tip, **When** the two tips are
   equal, **Then** a lost-progress signal is emitted naming the branch,
   both commits, and the commit count the stage recorded.
2. **Given** a completed tasks run in the same shape, **When** the two
   tips are equal, **Then** the same signal is emitted for it.
3. **Given** either run, **When** it did push commits to its branch,
   **Then** the two recorded tips differ and no lost-progress signal is
   emitted.
4. **Given** either run whose lifecycle already marks the spec stalled,
   **When** the two tips are equal, **Then** the existing already-handled
   attribution is used rather than a fresh lost-progress class, exactly as
   the implement path does today.

---

### User Story 2 - The verdict does not change with when the watchdog looks (Priority: P1)

The scheduled rebase force-pushes the spec branch, or the next stage in
the pipeline pushes to it, between a plan or tasks run finishing and the
watchdog inspecting it. Because the two compared commits are the ones the
run itself observed and recorded, nothing that happens to the branch
afterwards can turn a lost cycle into a healthy-looking one — the two miss
cases spec 050 closed for implement are closed for these two stages by the
same mechanism, and are never opened for them in the first place.

**Why this priority**: Plan and tasks are followed immediately by another
stage that pushes to the same branch in `auto` review mode, so the
"a later run's commits land inside the earlier run's window" miss is the
ordinary case for them, not an exotic race. Adopting the exact-pair
baseline and the timestamp window at the same time would ship a known-bad
measurement.

**Independent Test**: Inspect the same completed plan run twice — once
before and once after an intervening force-push of its branch and an
intervening later push by the next stage — and confirm both inspections
produce the same verdict.

**Acceptance Scenarios**:

1. **Given** a plan or tasks run whose two recorded tips are equal,
   **When** its branch is force-pushed before the watchdog inspects it,
   **Then** the reported outcome is unchanged.
2. **Given** a plan or tasks run whose two recorded tips differ, **When** a
   later run pushes to the same branch before the watchdog inspects the
   earlier one, **Then** the earlier run is still reported as healthy and
   the later run's commits are not attributed to it.
3. **Given** either run, **When** the commits the recorded tips name have
   been orphaned by a force-push, **Then** the verdict and the reported
   count are still produced — neither depends on walking the recorded
   range at inspection time.

---

### User Story 3 - The capture has exactly one home (Priority: P2)

A maintainer fixes a defect in how the branch advance is captured — the
"after" tip is read before the last push, or a fetch failure is not
degraded to unavailable. With the capture living in one place that all
three stages consume, that fix lands once. With it pasted into a second
and a third workflow, the fix lands once and silently fails to land twice,
and nothing in the gate suite notices the drift until the next detection
is missed.

**Why this priority**: This repository's standing rule is that shared
`run:` logic has exactly one home, with a gate behind the rule; the cost
line that was once pasted into twelve run-blocks across nine workflows is
the recorded example. Copying implement's capture block into plan and
tasks is precisely the move the rule exists to prevent. It ranks below the
detection stories because it changes maintainability, not behaviour.

**Independent Test**: Search the repository for the capture logic and
confirm it appears exactly once; add a second copy to a workflow and
confirm the gate suite fails on it.

**Acceptance Scenarios**:

1. **Given** the shipped feature, **When** the repository is searched for
   the branch-advance capture, **Then** exactly one home holds it and
   implement, plan and tasks all consume that one home.
2. **Given** a change that re-pastes the capture into a workflow, **When**
   the gate suite runs, **Then** it fails and names the offending file.
3. **Given** the single home, **When** implement's own records are
   inspected after the change, **Then** they carry the same quadruple,
   with the same values, that they carried before it.

---

### User Story 4 - A run that cannot be measured degrades visibly (Priority: P2)

Not every plan or tasks run can produce a usable pair: a run from a
pipeline version that predates this feature, a run whose artifact has aged
out of retention, a run whose read of either point failed and degraded to
unavailable, an adopting repository still pinned to an older release. The
reader of the step summary must be able to tell "measured and healthy"
from "not measurable", and an unmeasurable run must never be reported as
lost progress or as a failed read.

**Why this priority**: A silently varying baseline makes every future
report ambiguous, and a false lost-progress finding on a healthy run is
worse than no finding at all. It ranks below the detection stories because
it changes reporting rather than detection.

**Independent Test**: Inspect a plan run whose record carries no usable
branch evidence and confirm the step summary names what it did instead,
that no lost-progress signal is emitted, and that the collector's outcome
is still recorded as trustworthy.

**Acceptance Scenarios**:

1. **Given** a plan or tasks run whose record marks the branch evidence
   unavailable, **When** the watchdog inspects it, **Then** the step
   summary states that the exact-pair evidence was unavailable and what
   the collector did instead, and the collector's outcome is recorded as
   successful rather than failed.
2. **Given** a record produced before this change, **When** any consumer
   of the persisted metrics history reads it, **Then** every field that
   consumer already relied on is present and unchanged, and no consumer
   fails on the record.
3. **Given** a run for any stage other than plan, tasks and implement,
   **When** the watchdog inspects it, **Then** its treatment is exactly
   what it is today.

---

### Edge Cases

- **The target branch does not exist when the run starts.** A plan run in
  `pr` review mode creates its review branch inside the run; the first
  plan run of a feature can also be the one that creates the persistent
  spec branch. The branch has no tip yet, so the "before" point is the
  commit the branch is created from — never a placeholder a reader could
  mistake for something else — which keeps such a run measurable by the
  same comparison as every other run.
- **The review mode decides the branch.** Plan and tasks push to the
  persistent spec branch in `auto` review mode and to their own review
  branch in `pr` mode. Both modes populate the group. The record names the
  branch the run actually pushed to; no reader may infer it from a prefix,
  a slug or a mode, because the record does not carry the mode.
- **The run is refused as a duplicate attempt.** A plan or tasks run that
  stops because a prior attempt's branch already exists runs no agent
  step and pushes nothing. That is a correct refusal, not a lost cycle,
  and it must not produce a lost-progress signal.
- **The run is skipped or cancelled.** Nothing executed, so "this stage
  should have pushed" was never in force — the existing suppression for
  that case continues to apply.
- **The push is rejected.** A run whose work is committed but whose push
  loses a race has a "before" point and an "after" point equal to it.
  This is exactly the condition the collector should catch, and it must
  be distinguishable from a run that never reached the recording point at
  all.
- **The agent pushes more than once.** The recorded "after" point must be
  the tip the run finished with, not the tip after the first of several
  pushes — including any deterministic bookkeeping push that follows the
  agent's own.
- **The agent is the pusher, not a deterministic step.** Unlike implement,
  plan and tasks push from inside the agent step. The recorded points
  must still be observed by deterministic steps around that agent step, so
  no agent judgment can influence what is recorded.
- **The run emits more than one record.** A stage whose job publishes
  several records must not leave a reader unable to tell which one carries
  the branch evidence; the group's own availability marker remains the
  only filter a reader needs.
- **A record carrying the group reaches a consumer that does not know
  it.** An unknown field must be retained and ignored, never cause a
  reader to drop or fail on the record.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The plan stage MUST record, in its own metrics record for a
  run, the branch that run advanced, that branch's tip as observed before
  the run's work ("before"), that branch's tip as observed after the last
  push the run could make ("after"), and the number of commits added
  between those two points, counted by the stage at the moment it holds
  both.
- **FR-002**: The tasks stage MUST record the same four values for its own
  run, with identical semantics.
- **FR-003**: Each recorded point, and the recorded count, MUST carry its
  own explicit availability marker following the record's existing
  convention, so a reader can distinguish "not measurable for this run"
  from "measured and equal" and from "measured as zero".
- **FR-004**: The branch each record names MUST be the branch that run
  actually pushes to for the review mode it ran in, recorded literally by
  the stage and never derived by a reader from a prefix, a slug, or a
  review mode. Both review modes populate the group: an `auto`-mode run
  records the persistent spec branch, and a `pr`-mode run records its own
  review branch (`plan/<slug>`, `tasks/<slug>`). No run of either stage is
  excluded from the group because of the mode it ran in.
- **FR-005**: When the branch a run advances did not exist at the moment
  the run's work began, the record MUST NOT store a placeholder value in
  the "before" point; it MUST record the commit the branch was created
  from as the "before" point, so a run that creates its branch is
  measurable by the same comparison as a run that advances an existing
  one. The "before" point is therefore "the point the run advanced the
  branch from" — for a branch that already existed that is its tip at the
  moment the run's work began, and for a branch the run creates it is the
  commit the creation started from. A single verdict rule covers both.
- **FR-006**: The "after" point MUST be observed after every push the run
  could make, including any deterministic bookkeeping push that follows
  the agent's own, so it is the tip the run finished with.
- **FR-007**: The recorded points MUST be observed by the stage's own
  deterministic steps inside the run. No recorded value may originate from
  an agent's report, and the feature MUST add no agent turns and no agent
  judgment to either stage.
- **FR-008**: Capture MUST be best-effort in the same sense the rest of
  the record is: a failure to read any point degrades that field to
  unavailable, MUST NOT fail the run, and MUST NOT prevent any step that
  follows it from running.
- **FR-009**: The record change MUST be additive within the current schema
  version — no field removed, renamed, retyped, and no new schema version
  minted — so every existing consumer of a record continues to read it
  unchanged. The one definitional change permitted is the generalization of
  the "before" point required by FR-005, which MUST be a widening only:
  every value an already-persisted record carries in that field MUST remain
  correct under the widened definition, and no consumer's reading of an
  existing record may change.
- **FR-010**: The published record contract MUST be updated so it describes
  what ships: implement, plan and tasks all populate the group, in both
  review modes, and the "before" point is defined as the point the run
  advanced the branch from — including the case of a run that creates the
  branch it advances. A reader of the contract alone MUST be able to tell
  which stages populate the group, which branch each names, and when the
  group is unavailable.
- **FR-011**: The capture MUST have exactly one home shared by implement,
  plan and tasks, rather than a second and third copy of the implement
  stage's block. Implement's own recorded values MUST be unchanged by the
  move.
- **FR-012**: A deterministic check MUST fail when a copy of the capture
  reappears in a workflow or in another shared component, naming the
  offending file — the single-home rule ships with a gate behind it, not
  as prose.
- **FR-013**: The watchdog's branch-drift collector MUST decide
  lost-progress for a plan or tasks run from that run's own recorded pair
  when the record carries one, comparing the two recorded points rather
  than counting commits in a time window or reading the branch's current
  state. Extending the collector to consume that evidence is in scope for
  this feature: the feature both populates the records and widens the
  collector's exact-pair arm to plan and tasks, so the evidence it adds is
  read by the run that emitted it rather than by a later feature.
- **FR-014**: The signal emitted for a plan or tasks run MUST name the
  stage, the branch, both compared points, and the count the stage
  recorded. The count MUST be read verbatim from the record and never
  re-derived at inspection time, so the verdict does not depend on the
  recorded commits still resolving after a force-push. When only the count
  is unavailable, the signal reports the branch, the two points and the
  equal/not-equal verdict without a count.
- **FR-015**: The watchdog MUST NOT change its behaviour for any case
  other than plan and tasks runs carrying the new evidence: the implement
  case is unchanged, a stage that is not push-expected is still skipped, a
  skipped or cancelled run is still suppressed, and a run whose head
  branch is the branch its stage pushes to still uses today's comparison.
- **FR-016**: A plan or tasks run whose record carries no usable pair MUST
  keep exactly today's outcome for that run, MUST NOT produce a false
  lost-progress signal, and MUST leave the collector's outcome recorded as
  trustworthy — an absent optional field is data, not a failed read. The
  step summary MUST state which basis was used for the run.
- **FR-017**: An adopting repository running an older pipeline version, and
  any record that predates this change, MUST continue to work unchanged —
  no reader may fail, and no false detection may be produced, because the
  group is absent or unavailable.
- **FR-018**: A plan or tasks run that is refused as a duplicate attempt,
  skipped, or cancelled MUST NOT produce a lost-progress signal, and MUST
  NOT be recorded as an unmeasurable read.
- **FR-019**: The identity by which findings are deduplicated MUST be
  unchanged; a finding filed from a plan or tasks run's evidence groups
  with findings for the same branch exactly as findings do today.
- **FR-020**: The gate that validates record conformance MUST cover the new
  populators' record states with checked-in fixtures at the same strictness
  as the implement populator's: both points present and different, both
  present and equal, "before" unavailable, "after" unavailable, a count of
  zero alongside two differing points, the count unavailable while both
  points are present, the whole group unavailable, a run that created the
  branch it advanced — whose "before" point is the commit the branch was
  created from — and a wrong-typed value for each field. The fixtures MUST
  include a record naming a persistent spec branch and one naming a review
  branch, so neither review mode is proven only by a live run.
- **FR-021**: The gate that exercises the branch-drift collector MUST gain
  fixture-backed cases for a plan run and a tasks run on both arms — a
  recorded pair present, and no usable evidence — so neither arm is proven
  only by a live run.
- **FR-022**: Every check this feature adds MUST be wired into the
  repository's existing gate registry, so coverage that stops being run is
  itself a failure.
- **FR-023**: The checked-in comments that state plan and tasks runs are
  skipped because their head branch is not the branch they push to MUST be
  replaced by comments describing the mechanism that actually ships, so the
  explanation in the file matches the behaviour in the file.

### Key Entities

- **Agent run metrics record**: the durable per-run, per-step record the
  pipeline already emits and persists. Gains nothing new in shape; gains
  two new stages that populate its branch-advance group.
- **Branch advance pair**: the "before" and "after" tips of the branch a
  stage pushed to for one run, with the branch's name and the count of
  commits added between them. Already defined by the record contract; this
  feature adds populators, not fields.
- **Review mode**: the per-stage setting that decides whether a plan or
  tasks run pushes to the persistent spec branch or to its own review
  branch. Not carried in the record, which is why the branch is recorded
  literally.
- **Branch-drift signal**: the normalized signal the watchdog emits when a
  push-expected run advanced its branch by nothing. Gains plan and tasks
  as sources whose facts are exact recorded pairs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of plan runs and tasks runs that reach the point where
  their metrics record is emitted produce a record whose branch-advance
  group either names the branch that run pushed to with at least one
  recorded point, or is explicitly marked unavailable — no run emits a
  record that is silently ambiguous about which branch it advanced.
- **SC-002**: A plan run and a tasks run that push nothing are each
  reported as lost-progress in 100% of seeded cases, including the case
  where the branch is force-pushed between the run finishing and the
  inspection, the case where a later stage has already pushed to the same
  branch, and the case of a `pr`-mode run whose review branch the run
  itself was to create.
- **SC-003**: Across a corpus of plan and tasks runs that did push their
  work, zero lost-progress signals are emitted — the change adds no false
  detection to runs that were healthy before it.
- **SC-004**: Inspecting the same completed plan or tasks run twice, before
  and after an intervening force-push and an intervening later push,
  produces the same verdict both times.
- **SC-005**: Every state of the branch-advance group for the two new
  populators is exercised by a checked-in fixture, so no state is proven
  only by a live run.
- **SC-006**: The branch-advance capture appears exactly once in the
  repository, and a re-pasted copy fails the gate suite.
- **SC-007**: The number of agent invocations and agent turns per plan run
  and per tasks run changes by zero.
- **SC-008**: A record produced before this change is still retained and
  read without error by every consumer, and an implement record produced
  after it carries the same values it carried before.
- **SC-009**: A maintainer reading a filed lost-progress finding for a plan
  or tasks run can state the stage, the branch, the two commits compared,
  and how many commits the run pushed, without opening any artifact the
  watchdog read.
- **SC-010**: The checked-in explanation of the branch-drift baseline
  contains no surviving description of a skip the shipped mechanism has
  removed.

## Assumptions

- The record contract's compatibility rules make this change additive: the
  group already exists, is already documented as stage-neutral, and is
  already accepted as input by the component that publishes records, so no
  new schema version is minted and no consumer changes in lockstep.
- Generalizing the "before" point to "the point the run advanced the branch
  from" (FR-005) does not invalidate any persisted record: for a branch that
  already existed, the point the run advanced from is the tip it observed at
  start, which is exactly what implement records today.
- The two points a run records are captured by that run's own deterministic
  steps, so they describe what the run observed and are never re-derived
  later from a branch other mechanisms may have rewritten.
- Recording only helps runs from this version forward; historical records
  are not backfilled.
- The stage knows its own review mode and therefore its own target branch
  at capture time, so the branch can be recorded literally without a reader
  ever inferring it.
- The watchdog's treatment of implement runs, of non-push-expected stages,
  and of skipped or cancelled runs is untouched by this feature; only the
  plan and tasks arms change.
- The lifecycle-issue and finding-filing paths downstream of the collector
  are unchanged; this feature changes what can be measured and what is
  reported as evidence, not how a finding is filed or routed.
- The commit count a run records describes what that run pushed, not what
  the branch contains at inspection time.

## Out of Scope

- Changing how findings are filed, deduplicated, or routed to a lifecycle
  issue.
- Backfilling branch evidence into records already persisted.
- Adding the branch-advance group to stages that do not push as their
  primary job — the push-expected set stays plan, tasks and implement.
- Changing the record's schema version, or any field's shape or
  availability convention. The only definitional change in scope is the
  widening of the "before" point required by FR-005 and FR-010.
- Changing the timestamp-window baseline that survives for implement runs
  whose records predate spec 050.
- Any new agent-facing surface, prompt, or judgment step in either stage.
- Changing which branch either stage pushes to, or how its review mode is
  configured.
