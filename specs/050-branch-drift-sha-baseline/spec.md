# Feature Specification: Exact-SHA Branch-Drift Baseline for Dispatched Implement Runs

**Feature Branch**: `050-branch-drift-sha-baseline`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description (lifecycle issue #331): "#327 (#322) measures a dispatched implement run on `spec/<slug>` by counting commits whose committer date is at or after the run was created, because the run's head SHA is `main`'s tip and not a point on the measured branch. Two miss cases are permanent and documented rather than closed: a `rebase.yml` force-push between the run and its inspection rewrites committer dates and inflates the count (run 34709026525 reads 22 after a rebase, 16 before); and a later run on the same branch (a retry, the next cycle) that has already pushed by the time this one is inspected adds its own commits to the open-ended window. Both err toward a missed detection, never a false one, but they are baked in. Proposed change (design trade-off; spec-request shape): have the implement stage record the spec branch's tip at cycle start (`before_sha`) and after its push (`after_sha`) in its own metrics record (specs/043 schema, `wing-commander-metrics-summary`), so branch-drift compares exact SHAs for dispatched runs as it does for a spec-branch head, closing both miss cases. This touches the metrics-record contract and a second stage workflow, and the record schema gate (`verify-metrics-record-schema.py`) and Gate 39/41 invariants, so it needs the owner to weigh the schema change; the alternative is to keep the timestamp baseline and accept the two misses. Found by the code review of #327."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A dispatched implement run that pushed nothing is caught even after a rebase (Priority: P1)

The watchdog inspects a completed implement run. That run was dispatched, so the run's own metadata names the default branch as its head — the branch the stage actually pushes to is the spec branch, and the only way the watchdog can say "this cycle pushed nothing" today is to count commits by their committer date since the run started. In between the run finishing and the watchdog looking, the scheduled rebase force-pushed the spec branch and rewrote every committer date on it. The date-based count now reports a healthy number of commits for a cycle that in fact pushed none, and the maintainer is never told the work was lost.

**Why this priority**: This is the detection the collector exists to make, and the rebase that defeats it is scheduled automation that runs on its own cadence — the miss is not an exotic race, it is the ordinary interleaving of two pipeline mechanisms. It was observed on a real run (34709026525 reads 22 commits after a rebase where 16 landed before it).

**Independent Test**: Drive a dispatched implement run that completes without pushing to the spec branch, force-push a rebase of that branch before the watchdog inspects it, and confirm the watchdog still reports lost-progress for that cycle — naming the branch and the two SHAs it compared — where the timestamp baseline reports nothing.

**Acceptance Scenarios**:

1. **Given** a dispatched implement run whose record carries the spec branch's tip at cycle start and after its push, **When** those two SHAs are equal, **Then** a lost-progress signal is emitted naming the branch, both SHAs, and the commit count the stage recorded for that cycle.
2. **Given** the same run, **When** the spec branch is force-pushed by an unrelated mechanism between the run finishing and the watchdog inspecting it, **Then** the reported outcome is unchanged — the comparison reads the run's own recorded SHAs and is not affected by what the branch looks like at inspection time.
3. **Given** a dispatched implement run that did push commits to the spec branch, **When** the watchdog inspects it, **Then** the two recorded SHAs differ and no lost-progress signal is emitted.
4. **Given** a dispatched implement run whose lifecycle already marks the spec stalled, **When** the two recorded SHAs are equal, **Then** the signal is emitted with the existing already-handled attribution rather than as a fresh lost-progress class, exactly as the timestamp-baseline path does today.

---

### User Story 2 - A second run on the same branch does not mask the first run's lost cycle (Priority: P1)

Two runs touch the same spec branch in sequence — a retry, or simply the next cycle of the loop. The first pushed nothing; the second pushed normally and did so before the watchdog got around to inspecting the first. Because the timestamp window is open-ended, the second run's commits fall inside the first run's measurement window, and the first run reads as healthy.

**Why this priority**: The pipeline is a loop, so back-to-back runs on one branch are the normal case, not the exception; this miss applies to every cycle that is inspected late. It is the same root cause as User Story 1 — a window rather than a pair of points — and is closed by the same recorded pair.

**Independent Test**: Drive two consecutive implement cycles on one spec branch where the first pushes nothing and the second pushes commits, delay the watchdog's inspection of the first until after the second has pushed, and confirm the first run is still reported as lost-progress and the second is not.

**Acceptance Scenarios**:

1. **Given** two runs on one spec branch where the earlier pushed nothing, **When** the watchdog inspects the earlier run after the later one has pushed, **Then** the earlier run is reported as lost-progress and the later run's commits are not attributed to it.
2. **Given** the same pair, **When** the watchdog inspects the later run, **Then** the later run reports no lost-progress signal.
3. **Given** two findings arising from the same branch across different runs, **When** both are filed, **Then** they deduplicate by the same identity the collector uses today — this feature changes what is measured, not how findings are grouped.

---

### User Story 3 - A run whose recorded SHAs are absent degrades visibly, never silently (Priority: P2)

Not every run the watchdog inspects will carry the recorded SHAs: records produced before this feature existed, runs whose artifact has expired past retention, a cycle whose push step never reached the point where a tip could be recorded, and adopting repositories still pinned to an older pipeline version all produce a record without them. The watchdog must state which baseline it used for that run, so a maintainer reading the step summary or the finding can tell a measured result from an unmeasurable one.

**Why this priority**: The precision of the collector rests on the reader being able to trust what it says; a baseline that silently varies between exact and approximate would make every future report ambiguous. It ranks below the two detection stories because it changes reporting, not detection.

**Independent Test**: Inspect a run whose metrics record carries no branch SHAs and confirm the watchdog's step summary names the since-created timestamp baseline it fell back to for that run, and that the collector still reports a successful outcome rather than an untrusted read.

**Acceptance Scenarios**:

1. **Given** a dispatched implement run whose metrics record marks the branch SHAs unavailable, **When** the watchdog inspects it, **Then** the run is measured with the since-created timestamp baseline, the step summary states that the exact-SHA baseline was unavailable and names that fallback, and the collector's outcome is still recorded as successful.
2. **Given** a record from a pipeline version that predates this feature, **When** a reader of that record consumes it, **Then** every field that reader already relied on is present and unchanged — the record remains readable by consumers written against the current schema version.
3. **Given** a run for a stage that is not the dispatched-implement case, **When** the watchdog inspects it, **Then** the existing baseline choice for that stage is unchanged — a spec-branch head still compares against the run's own head SHA and a non-push-expected stage is still skipped.

---

### Edge Cases

- **The branch did not exist at cycle start.** The first cycle of a feature can create the spec branch. There is no tip to record as the "before" point; the record must express that explicitly rather than recording an empty string that a reader could mistake for a SHA.
- **The push is rejected.** A cycle that computes commits but has its push rejected (a concurrent force-push) has a "before" point and no successfully pushed "after" point. This is exactly the condition the collector should catch, and the record must distinguish it from "the stage never got far enough to record anything".
- **The stage pushes more than once in a cycle.** Implement pushes the agent's work and, separately, deterministic bookkeeping commits. The recorded "after" point must be the branch tip the cycle finished with, not the tip after the first of several pushes.
- **Recorded SHAs are no longer resolvable.** A force-push can orphan the commits the recorded SHAs name, so a later attempt to walk between them can fail even though both SHAs are known. Neither the verdict nor the commit count depends on that walk: the verdict compares the two recorded values, and the count is recorded by the stage at push time, when it still holds both commits.
- **Both SHAs present but the "after" is an ancestor of the "before".** A cycle that reset the branch backwards is not "no progress", but it is not forward progress either; the recorded count is zero while the two points differ, and the collector must not silently report that pairing as healthy.
- **A record carrying the new fields reaches a consumer that does not know them.** The persisted metrics history is read by more than the watchdog; an unknown field must be retained and ignored, never cause a reader to drop or fail on the record.
- **Several records per run.** An implement run emits more than one metrics record (its cycle and its progress steps). Only the record that describes the pushing cycle can carry a meaningful branch pair; the others must not be mistaken for it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The implement stage MUST record, in its own metrics record for a cycle, the spec branch's tip commit as observed at the start of that cycle ("before"), the spec branch's tip commit as observed after the cycle's final push ("after"), and the number of commits the cycle added to that branch between those two points, counted by the stage at the moment it holds both commits.
- **FR-002**: Each recorded branch point, and the recorded commit count, MUST be accompanied by an explicit availability marker following the record's existing convention, so a reader can distinguish "not measurable for this run" from "measured and equal" or "measured as zero".
- **FR-003**: The record MUST also name the branch the pair refers to, recorded explicitly by the stage that pushed it and never derived by a reader from a slug, a configurable prefix, or a review mode.
- **FR-004**: When the spec branch did not exist at cycle start, the record MUST mark the "before" point as unavailable rather than recording a placeholder value.
- **FR-005**: When the cycle's push does not land, the record MUST mark the "after" point as the branch tip the cycle actually achieved, distinguishable from a cycle that never reached the recording point at all.
- **FR-006**: The record change MUST be additive within the current schema version — no existing field removed, renamed, retyped, or given a new meaning — so every existing consumer of a record continues to read it unchanged.
- **FR-007**: The published record contract MUST be updated to describe the new fields — branch name, "before" point, "after" point, and commit count — including their availability semantics, the not-yet-created-branch and failed-push cases, and the statement that the fields are stage-neutral and may later be populated by stages other than implement, so a reader of the contract alone knows the full shape.
- **FR-008**: The gate that validates record conformance MUST require the new fields at the same strictness as existing fields, with positive and negative fixtures covering: both points present and different, both present and equal, "before" unavailable, "after" unavailable, a recorded count of zero alongside two differing points, the count unavailable while both points are present, and a wrong-typed value for each new field.
- **FR-009**: The gate that validates the persistence/append behaviour MUST continue to hold for records carrying the new fields — appending, deduplicating, and retrying a record MUST behave identically whether or not the new fields are present.
- **FR-010**: For a dispatched implement run whose record carries both branch points as available, the watchdog's branch-drift collector MUST decide lost-progress by comparing those two recorded points, not by counting commits in a time window.
- **FR-011**: The watchdog MUST report the branch, both compared points, and the recorded commit count in the signal it emits, so the finding names the exact evidence it decided on.
- **FR-012**: The watchdog MUST NOT change its behaviour for any case other than the dispatched-implement case: a run whose head branch is the branch the stage pushes to still compares against the run's own head SHA, a non-push-expected stage is still skipped, and a skipped or cancelled run is still suppressed.
- **FR-013**: When a dispatched implement run's record does not carry usable branch points, the watchdog MUST state in its step summary which baseline it used instead, and MUST still record the collector as trustworthy — an absent optional field is data, not a failed read.
- **FR-014**: The watchdog MUST preserve today's coexistence behaviour: a spec whose lifecycle already marks it stalled produces the already-handled attribution rather than a bare lost-progress class.
- **FR-015**: The comments in the watchdog that document the two miss cases MUST be replaced by comments describing the mechanism that actually ships, so the checked-in explanation matches the checked-in behaviour.
- **FR-016**: The feature MUST add no agent turns: recording the branch points and comparing them are deterministic steps, and the decision that files a finding stays in deterministic code.
- **FR-017**: An adopting repository that consumes an older pipeline version, or whose records predate this feature, MUST continue to work — the watchdog MUST NOT fail, and MUST NOT report a false lost-progress, when the fields are absent.
- **FR-018**: When a dispatched implement run's metrics record carries no usable branch points, the watchdog MUST fall back to today's since-created timestamp baseline for that run alone — detection never drops below what the timestamp baseline achieves today, and the two documented miss cases survive only for runs whose record lacks the fields. Both arms MUST keep checked-in fixtures, and the step summary MUST name which arm measured the run (FR-013).
- **FR-019**: The emitted signal MUST carry the commit count the implement stage recorded, alongside the branch and the two points. The watchdog MUST NOT derive the count at inspection time — it performs no walk of the recorded range and therefore does not depend on the recorded commits still resolving after a force-push. When the recorded count alone is unavailable, the signal reports the branch, the two points, and the equal/not-equal verdict without a count rather than computing one.
- **FR-020**: Only the implement stage records the branch advance pair and count in this feature. The new fields MUST be stage-neutral in name and semantics — the pushed branch is recorded explicitly (FR-003), never implied by the stage or a review mode — so the plan and tasks stages can populate the same fields later without a contract change; until then those stages' records carry the fields as unavailable and the watchdog's behaviour for them is unchanged (FR-012). The plan/tasks gap MUST be filed as a follow-up issue from this spec.

### Key Entities

- **Agent run metrics record**: the durable per-run, per-step record the pipeline already emits and persists. Gains a description of the branch this run advanced, the two points it advanced it between, and how many commits it added, each with its own availability marker.
- **Branch advance pair**: the "before" and "after" tip commits of the branch a stage pushes to for one cycle, together with the branch's name and the count of commits added between them. The unit of evidence that replaces the time window.
- **Branch-drift signal**: the normalized signal the watchdog emits when a push-expected run advanced its branch by nothing. Its facts change from `{branch, since, after-sha, commits}` to `{branch, before-sha, after-sha, commits}`, where the count is the one the stage recorded rather than one walked at inspection time.
- **Record contract**: the published document describing the record's shape and its compatibility rules. The normative statement of what the new fields mean.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A dispatched implement cycle that pushes nothing is reported as lost-progress in 100% of seeded cases, including the case where the spec branch is force-pushed between the run finishing and the watchdog inspecting it, and the case where a later run on the same branch has already pushed.
- **SC-002**: Across a corpus of dispatched implement runs that did push work, the collector emits zero lost-progress signals — the change adds no false detection to runs that were healthy before it.
- **SC-003**: The watchdog's decision for a dispatched implement run with available branch points is independent of when the inspection happens: inspecting the same run twice, before and after an intervening force-push and an intervening later cycle, produces the same verdict both times.
- **SC-004**: Every one of the record's new-field states — both points available, "before" unavailable, "after" unavailable, both unavailable, the count available, and the count unavailable — is exercised by a checked-in fixture, so no state is proven only by a live run.
- **SC-005**: A record produced by the pipeline after this change validates against the record contract, and a record produced before this change is still retained and read by every consumer without error.
- **SC-006**: Adding this feature changes the number of agent invocations per implement cycle and per watchdog run by zero.
- **SC-007**: A maintainer reading a filed lost-progress finding can state the branch, the two commits compared, and how many commits the cycle pushed without opening any artifact the watchdog read.
- **SC-008**: The checked-in explanation of the branch-drift baseline contains no surviving description of a miss case the shipped mechanism has closed.

## Assumptions

- The two recorded points are captured by the stage's own deterministic steps, inside the run, so they describe what that run observed and are not re-derived later from a branch that other mechanisms may have rewritten.
- Recording the branch points is treated as best-effort in the same sense the rest of the record is: a failure to read the branch tip degrades that field to unavailable and does not fail the cycle.
- The additive-only compatibility rule of the current record schema version applies, so no new schema version is minted for this change and no consumer is required to change in lockstep.
- The signal identity used for deduplication is unchanged; both the old and the new fact shapes project to the same identity, so a finding filed under one shape and a later one under the other still group together.
- Recording only helps runs from this version forward. Historical records are not backfilled, and runs against them keep the since-created timestamp baseline FR-018 specifies.
- The implement stage can count the commits it pushed exactly and without cost at push time, because it holds both the "before" and the "after" commit locally at that moment; the recorded count therefore describes what the cycle pushed, not what the branch contains at inspection time.
- "Dispatched implement run" continues to mean the case the collector already identifies today: an implement run whose head branch is not the branch the stage pushes to, with the spec identity resolved from the run's own metrics record.
- The lifecycle-issue and finding-filing paths downstream of the collector are unchanged; this feature changes only what the collector measures and what it reports as evidence.

## Out of Scope

- Changing how findings are filed, deduplicated, or routed to a lifecycle issue.
- Backfilling branch points into records already persisted.
- Making the watchdog measure branches for stages that do not push as their primary job.
- Having the plan and tasks stages populate the branch advance pair (FR-020 defers this to a follow-up issue; the contract is shaped so they can adopt it without changing).
- Any new agent-facing surface, prompt, or judgment step.
- Changing the rebase mechanism's behaviour to avoid rewriting committer dates.
