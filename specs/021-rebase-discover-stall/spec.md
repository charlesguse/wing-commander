# Feature Specification: Resolve the Stalled `rebase/discover` Step Signal

**Feature Branch**: `021-rebase-discover-stall`

**Created**: 2026-07-25

**Status**: Draft

**Input**: Lifecycle issue #102 (watchdog: step-stalled) — "The 'rebase / discover' job matched the 'stalled' sentinel, indicating the discovery step did not complete normally. This prevents downstream pipeline stages from running."

## User Scenarios & Testing *(mandatory)*

The rebase stage begins with a **discovery** step: it enumerates the pipeline's
per-spec integration branches, reads each branch's own lifecycle state, and
decides which branches should be rebased. Branches that are themselves in a
stalled lifecycle state are a routine, expected exclusion — the discovery step
reports them as excluded and moves on. Only after discovery selects a set of
branches do the downstream rebase stages run.

The pipeline's watchdog inspects finished runs and raises an alert when a job's
evidence matches a known failure signal (a "sentinel"). In the motivating
incident the watchdog raised **step-stalled** against the `rebase/discover` job:
the job's evidence matched the "stalled" signal. Because discovery gates every
downstream rebase stage, a discovery step that is believed to have not completed
normally is reported as blocking the rest of the pipeline.

Two readings of this signal are possible, and they have different scope:

1. **False positive.** Discovery completed normally but legitimately reported one
   or more *spec branches* as "stalled" exclusions; the watchdog's signal-matching
   treated that routine word as evidence that the *discovery job itself* stalled.
2. **Genuine stall.** Discovery genuinely did not finish (hang, timeout, or exit
   before emitting its normal completion signal), and downstream stages were in
   fact blocked.

This feature makes the `rebase/discover` step's health **legible and correct**:
a maintainer should be able to trust that a step-stalled alert against discovery
reflects a real stall, and a genuine stall should be surfaced clearly enough to
act on — without routine, healthy discovery runs being reported as failures.

### User Story 1 - Healthy discovery is never misreported as stalled (Priority: P1)

As a maintainer, when the discovery step completes normally — even when it
excludes one or more genuinely stalled spec branches — I want no step-stalled
alert raised against `rebase/discover`, so that my lifecycle issues are not
polluted with false alarms and I keep trusting the watchdog.

**Why this priority**: A watchdog that cries wolf on healthy runs is worse than no
watchdog — maintainers learn to ignore it, and real stalls get missed. Removing
the false positive is the irreducible core of this fix and delivers value on its
own: the recurring noise stops immediately.

**Independent Test**: Run discovery in a state where at least one spec branch is
in the stalled lifecycle state (a normal exclusion) and confirm the run finishes
cleanly and produces no step-stalled alert against the discovery job.

**Acceptance Scenarios**:

1. **Given** discovery completes normally and excludes one or more spec branches
   for being in a stalled lifecycle state, **When** the watchdog inspects the run,
   **Then** no step-stalled alert is raised against `rebase/discover`.
2. **Given** discovery completes normally and selects zero branches (a clean
   no-op), **When** the watchdog inspects the run, **Then** no step-stalled alert
   is raised and downstream stages are correctly reported as skipped rather than
   blocked.
3. **Given** discovery completes normally and selects one or more branches,
   **When** the run finishes, **Then** the selected downstream rebase stages run.

---

### User Story 2 - A genuine discovery stall is surfaced accurately (Priority: P2)

As a maintainer, when the discovery step genuinely fails to complete, I want a
clear, correct step-stalled alert that tells me discovery — not a spec branch it
was inspecting — is the thing that stalled, so that I can act on the real problem
without first ruling out a false alarm.

**Why this priority**: Correct detection is the other half of trust. Once false
positives are gone (Story 1), the remaining alerts must be trustworthy and
unambiguous; otherwise the fix has only moved the confusion. This depends on
Story 1 being in place so that "stalled" unambiguously means the job, not its
inputs.

**Independent Test**: Simulate a discovery step that does not finish normally and
confirm the watchdog raises exactly one step-stalled alert attributed to
`rebase/discover`, with evidence pointing to the discovery job rather than to an
excluded spec branch.

**Acceptance Scenarios**:

1. **Given** the discovery step does not complete normally, **When** the watchdog
   inspects the run, **Then** a step-stalled alert is raised and its evidence
   identifies the discovery job as the stalled component.
2. **Given** a genuine discovery stall has already been reported for an unchanged
   situation, **When** a later run inspects the same condition, **Then** no
   duplicate alert is filed.

---

### Edge Cases

- Discovery reports multiple stalled-branch exclusions in one run — must still be
  treated as a healthy run, not as a stalled job.
- The word "stalled" appears in discovery's evidence both as a routine
  spec-branch exclusion reason and (hypothetically) as a genuine job outcome —
  the system must distinguish the two rather than matching the bare word.
- A discovery run that emits no exclusions and no selections (empty repository or
  no spec branches) must be recognized as a healthy no-op.
- Historical runs already flagged by the prior behavior must not be re-alerted
  once the corrected behavior is in place (no retroactive duplicate churn).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The watchdog MUST NOT raise a step-stalled alert against the
  `rebase/discover` job when that job completed normally, including when it
  reported one or more spec branches as routine stalled-lifecycle exclusions.
- **FR-002**: The system MUST distinguish a *genuinely stalled discovery job*
  from *discovery reporting a stalled spec branch as a routine exclusion*, rather
  than treating any occurrence of the "stalled" wording as evidence of a stalled
  job.
- **FR-003**: When the discovery step genuinely does not complete normally, the
  watchdog MUST raise a step-stalled alert whose evidence identifies the
  discovery job itself as the stalled component.
- **FR-004**: A healthy discovery run that selects zero branches MUST be reported
  as a clean no-op, and downstream stages that are consequently not run MUST be
  reported as skipped rather than as blocked by a failure.
- **FR-005**: The watchdog MUST NOT file duplicate alerts for the same unchanged
  discovery condition across successive runs.
- **FR-006**: The lifecycle issue for a discovery-stall alert MUST clearly state
  which of the two conditions (genuine stall vs. routine exclusion) was detected,
  so a maintainer can act without re-deriving it from raw evidence.
- **FR-007**: The corrected behavior MUST NOT retroactively re-alert on
  historical runs that were flagged under the prior behavior.
- **FR-008**: The desired resolution behavior when a *genuine* discovery stall is
  detected MUST be [NEEDS CLARIFICATION: on a genuine stall, should the pipeline
  (a) only report it accurately and leave remediation to a maintainer, (b)
  automatically retry the discovery step, or (c) both report and attempt a bounded
  auto-retry before escalating?].

### Key Entities *(include if data involved)*

- **Discovery step (`rebase/discover`)**: The gating step that enumerates spec
  integration branches, decides which to rebase, and records exclusions and
  selections. Its health (completed-normally vs. stalled) is the subject of this
  feature.
- **Sentinel / failure signal**: A pattern the watchdog matches against a run's
  evidence to classify a failure. The "stalled" signal is the one at issue.
- **Spec branch lifecycle state**: The per-branch state discovery reads; a
  "stalled" branch state is a routine exclusion input to discovery, not an
  outcome of discovery.
- **Step-stalled alert**: The lifecycle-issue notification the watchdog raises
  when it believes a step did not complete normally.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero step-stalled alerts are raised against `rebase/discover` for
  runs in which discovery completed normally, across a representative set of runs
  that includes runs with stalled-branch exclusions.
- **SC-002**: 100% of genuine discovery stalls (as reproduced in test) produce
  exactly one step-stalled alert correctly attributed to the discovery job.
- **SC-003**: For any single unchanged discovery condition, at most one alert
  exists on the lifecycle issue (no duplicates) regardless of how many runs
  observe it.
- **SC-004**: A maintainer reading a discovery-stall alert can determine, without
  opening raw run artifacts, whether the cause was a genuine stall or a routine
  exclusion.
- **SC-005**: After the change ships, the recurring false-positive alert that
  motivated issue #102 does not reappear on subsequent scheduled runs.

## Assumptions

- The routine reporting of a stalled *spec branch* as an exclusion is correct,
  expected behavior of discovery and is out of scope to change; only the
  misclassification of the *job* is in scope.
- The watchdog's existing triage-ladder, deduplication, and lifecycle-issue
  reporting mechanisms remain the delivery mechanism for alerts; this feature
  corrects the discovery-stall signal within that framework rather than replacing
  it.
- "Completed normally" for discovery has an observable, deterministic indicator
  the system can rely on to tell a finished run from a stalled one.
- [NEEDS CLARIFICATION: the primary intended fix — should this correct how the
  watchdog *detects/matches* a discovery stall, change how discovery *emits* its
  completion/exclusion evidence so the two can't be confused, or both?]
- No change to who receives alerts or how maintainers interact with them (still
  the lifecycle issue) is intended.

## Out of Scope

- Changing the discovery step's branch-selection or exclusion logic itself.
- Reworking the watchdog's broader triage ladder or its handling of failure
  classes other than the discovery step-stalled signal.
- Retroactively re-processing or re-alerting historical runs.
