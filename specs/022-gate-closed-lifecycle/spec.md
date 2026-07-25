# Feature Specification: A Closed Lifecycle Is Inert — Gate Comment-/Label-Triggered Stages on Issue State

**Feature Branch**: `022-gate-closed-lifecycle`

**Created**: 2026-07-25

**Status**: Draft

**Input**: User description (GitHub issue #109): a post-mortem investigation of the watchdog's two `denied-tool` findings (#105/#106). The denials were real but incidental; the investigation surfaced three defects, in descending severity: (1) comment-/label-triggered stages do not gate on whether the lifecycle issue is still open, so a stage fired on the *closing* comment of an already-closed lifecycle — resurrecting a torn-down spec branch, editing a closed PR, posting an "action needed" callout on a closed issue, and inventing clarification resolutions from an unrelated closing comment; (2) tool allowlists shape *how* an agent writes, not *whether* it may — authorization belongs at the trigger level, allowlists are friction not fences; (3) the watchdog's denied-tool collector mislabels result-record array indexes as "turns" and overcounts denials rather than trusting the terminal result record's own `permission_denials`.

## Overview

The pipeline's later stages are triggered by ordinary GitHub activity on a
lifecycle issue: a maintainer comment answers a clarification, a label approves
tasks, a comment kicks off finalize or converge, a label admits an issue to
intake. Each of these comment-/label-triggered stages already gates on *who*
acted (maintainer or requester, never a bot) and on *what* the issue is (a real
lifecycle issue carrying the right stage/identity labels). **None of them checks
whether the lifecycle issue is still open.**

The consequence, observed live: a lifecycle that had just been closed — with its
spec PR closed and its draft branch torn down by cleanup — still fired a
comment-triggered stage on its own *closing comment*. All the who/what gates
passed, so the stage ran to completion and undid the teardown: it re-pushed the
deleted branch, edited the closed PR's body, posted an "action needed" callout on
the closed issue, and — because it treated the closing comment as if it were
maintainer answers — invented resolutions to open clarification questions that
appeared nowhere in that comment. The denials the watchdog originally flagged
only *delayed* these zombie writes; they did not prevent them, because a tool
allowlist governs the *form* of a command, not the agent's *authority* to act.
The authority gate was simply missing.

This feature makes a **closed lifecycle inert**: once a lifecycle issue is
closed, no further comment or label on it may cause any pipeline stage to act.
The gate belongs at the trigger, before any agent runs or any write can occur —
not in a downstream allowlist. The same missing gate is audited and closed across
every comment-/label-triggered entry point, not only the one where the failure
was observed.

The feature also corrects the accuracy defect that the same investigation
exposed in the watchdog's denied-tool collector, so that its reports describe
what actually happened. This is a **defect fix and hardening**, not a redesign:
the who/what gates, the stages' existing behavior, and the watchdog's contract
are all preserved; only the missing state gate and the collector's mislabeling
are corrected.

## User Scenarios & Testing *(mandatory)*

Today a maintainer who closes a lifecycle issue — because it is finished, or
because it was a false positive — reasonably expects that closing it ends its
activity. Instead, ordinary GitHub activity on the closed issue (including the
maintainer's own closing comment) can still wake a stage that writes to branches,
PRs, and the issue as though the lifecycle were live. The maintainer then has to
notice and clean up work that should never have run.

### User Story 1 - A closed lifecycle issue is inert to further activity (Priority: P1)

As a maintainer, once I close a lifecycle issue, I want any later comment or
label on it — including my own closing comment — to be ignored by every pipeline
stage, so that closing an issue reliably ends its lifecycle and nothing runs
against it afterward.

**Why this priority**: This is the defect. A closed lifecycle that can still be
driven by comments produces exactly the observed harm — resurrected branches,
edits to closed PRs, callouts on closed issues, and invented resolutions — and
silently reverses the maintainer's decision to close. Closing an issue is the
constitution's sanctioned way to cancel a spec; if it is not honored, that
control is broken. Every other item in this feature is secondary to restoring it.

**Independent Test**: Close a lifecycle issue, then add a comment and a label to
it in the ways that normally trigger stages, and confirm no stage runs and no
side effects occur (no branch created or re-pushed, no commit, no PR edit, no
comment posted by the pipeline).

**Acceptance Scenarios**:

1. **Given** a lifecycle issue that has been closed, **When** a maintainer or the requester comments on it in a way that would normally trigger a stage, **Then** no pipeline stage runs and the issue, its branches, and its PRs are left untouched by the pipeline.
2. **Given** a lifecycle issue closed at the same moment its closing comment is posted, **When** that closing comment would normally trigger a stage, **Then** the stage does not act on it — reproducing the reported scenario with the opposite outcome.
3. **Given** a closed lifecycle whose spec branch was already torn down by cleanup, **When** a later comment would normally cause a stage to commit and push, **Then** no branch is resurrected and no push occurs.
4. **Given** a label is added to a closed lifecycle issue in a way that would normally admit it to a stage (e.g. intake on `labeled`), **When** the trigger fires, **Then** the stage does not proceed.

---

### User Story 2 - The state gate is enforced at the trigger, consistently across every entry point (Priority: P1)

As a maintainer, I want the "issue must be open" check applied at the point where
a stage is triggered — before any agent starts or any command can run — and
applied uniformly to *every* comment-/label-triggered stage, so that no entry
point is left as a hole and no stage relies on downstream tool allowlists to stop
it from acting on a closed lifecycle.

**Why this priority**: The investigation's central lesson is that allowlists
shape *how* an agent writes, not *whether* it may: the observed run was denied
several commands, retried them in allowlist-passing forms, and still landed its
writes. Authorization must live at the trigger. And because the same gate is
missing from more than one wrapper, fixing only the wrapper where the failure was
seen would leave the identical defect open elsewhere. This is co-equal with US1:
the gate is only trustworthy if it is at the right layer and has no gaps.

**Independent Test**: Enumerate every comment-/label-triggered stage entry point,
confirm each refuses to proceed against a closed lifecycle issue, and confirm the
refusal happens before any agent runs or any write is attempted (not as a
side-effect of a command being denied).

**Acceptance Scenarios**:

1. **Given** the set of all comment-/label-triggered stage entry points (clarify, tasks-approval, the finalize and converge comment paths, and intake's label trigger), **When** each is triggered against a closed lifecycle issue, **Then** every one of them declines to act.
2. **Given** a stage declines because the lifecycle is closed, **When** the decision is made, **Then** it is made at the trigger — no agent is launched and no command is attempted — rather than being enforced only by which commands the agent's allowlist happens to reject.
3. **Given** a stage is triggered against an *open* lifecycle issue, **When** the state gate is evaluated, **Then** the stage proceeds exactly as before, so the gate blocks only closed lifecycles and does not narrow normal behavior.

---

### User Story 3 - The watchdog's denied-tool report describes what actually happened (Priority: P2)

As a maintainer reading a watchdog denied-tool finding, I want its denial count
and its per-denial location labels to match the run's own record, so that I can
trust the finding instead of reconciling impossible "turn" numbers and a count
that disagrees with the run result.

**Why this priority**: The same investigation showed a denied-tool finding
claiming "3 denials across turns 28, 116, 118" for a run whose result record says
20 turns and 2 denials — turn numbers that cannot exist in that run, drawn from
result-record array indexes rather than turns, and a count that overreports. An
inaccurate detector erodes trust in the watchdog. This is a real accuracy defect,
but it is reporting quality on an already-working detector, so it ranks below
restoring the missing authority gate.

**Independent Test**: Run the denied-tool collector against a run whose terminal
result record reports a known denial count and known turns, and confirm the
reported count equals the result record's count and the per-denial labels are not
presented as turn numbers they are not.

**Acceptance Scenarios**:

1. **Given** a run whose terminal result record reports a definite number of permission denials, **When** the collector reports denials for that run, **Then** the reported count equals the result record's count and does not overcount.
2. **Given** a per-denial location is drawn from a position in the result-record log, **When** it is reported, **Then** it is not labeled as a "turn" number it does not represent.
3. **Given** a run whose terminal result record does not report a denial count, **When** the collector reports denials, **Then** it falls back to scanning the log and says so, rather than silently presenting scan-derived numbers as authoritative.

---

### Edge Cases

- **Reopened issue**: A lifecycle issue that is closed and later reopened is open again; activity on it after reopening should be actionable again, because the gate reflects the issue's *current* state rather than the fact that it was once closed.
- **Race at close time**: The reported failure was a trigger firing on the very comment that closed the issue. The gate must evaluate the issue's state at the moment the stage would act, so a close-and-comment in the same instant is treated as closed.
- **Open lifecycle, unrelated comment**: A comment on an *open* lifecycle that does not actually answer a pending question is out of the state gate's scope; whether the pipeline should also guard against acting on such comments is called out as a clarification below.
- **Closed lifecycle, benign comment**: An ordinary human comment on a closed lifecycle (e.g. a thank-you or a note) must not wake any stage; inertness applies to all triggers, not only stage-shaped ones.
- **Collector with no terminal result record**: If a run's evidence lacks a terminal result record entirely, the collector must degrade to its log-scan fallback rather than fail or fabricate a count.
- **Remediation of the specific orphan**: The draft branch torn down and then resurrected by the zombie run (bearing an orphan "resolve clarifications" commit atop a closed PR's history) must be removed as part of delivering this fix, since it exists today only because the defect ran.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every comment-triggered and label-triggered pipeline stage MUST decline to act on a lifecycle issue whose current state is closed; a closed lifecycle issue MUST be inert to all further comments and labels with respect to pipeline behavior.
- **FR-002**: The closed-state check MUST be enforced at the trigger level — before any agent is launched and before any command can run — and MUST NOT be left to be enforced only by downstream tool allowlists, which govern the form of a command rather than the agent's authority to act.
- **FR-003**: When a stage declines because the lifecycle is closed, it MUST produce no side effects: no branch created or re-pushed, no commit or push, no PR body or PR state edited, and no callout or status comment posted by the pipeline.
- **FR-004**: The closed-state gate MUST be applied consistently to every comment-/label-triggered entry point. At minimum this covers the clarify stage, the tasks-approval trigger, the finalize and converge comment paths, and intake's `labeled` trigger; any other comment-/label-triggered wrapper MUST be audited and gated the same way, so no entry point is left without the gate.
- **FR-005**: The gate MUST reflect the issue's current open/closed state, so a lifecycle issue that is reopened after being closed becomes actionable again; closing is not a permanent, irreversible retirement of the issue.
- **FR-006**: When a stage is triggered against an open lifecycle issue, its behavior MUST be unchanged by this feature; the gate blocks only closed lifecycles and MUST NOT narrow, delay, or alter the normal open-lifecycle path.
- **FR-007**: The specific scenario reported in issue #109 — a comment-triggered stage firing on the closing comment of an already-closed lifecycle, resurrecting a torn-down branch, editing a closed PR, and posting a callout on the closed issue — MUST no longer occur, and MUST be guarded against silent recurrence.
- **FR-008**: The watchdog's denied-tool collector MUST report a denial count that matches the run's terminal result record's own permission-denial count when that record is present, and MUST NOT overcount relative to it.
- **FR-009**: When a terminal result record with a permission-denial count is present, the collector MUST source the count from it; only when it is absent may the collector fall back to scanning the execution log, and it MUST make clear that a fallback count is not authoritative.
- **FR-010**: The collector MUST NOT label a per-denial location drawn from a result-record array position as a "turn" number. It MUST either report those positions under an accurate name (e.g. record index) or report genuine turn numbers, so that the reported locations are consistent with the run's own turn count. [NEEDS CLARIFICATION: report the positions under an accurate "record index" name (minimal fix), or invest in deriving and reporting genuine turn numbers?]
- **FR-011**: The draft branch resurrected by the reported zombie run — carrying the orphan "resolve clarifications" commit on top of a closed PR's history — MUST be removed as part of delivering this fix, restoring the state that cleanup had already established before the defect ran.
- **FR-012**: When a comment- or label-triggered stage declines to act on a closed lifecycle, the pipeline's response MUST be defined: either it stays entirely silent, or it leaves a single brief, non-actionable note that the lifecycle is closed and no action was taken. [NEEDS CLARIFICATION: stay completely silent on closed lifecycles, or post one brief "lifecycle closed — no action taken" note so a human commenter is not left wondering?]
- **FR-013**: Whether this feature also hardens comment-triggered agents against acting on comments that do not actually answer the pending question (the "invented resolutions" symptom observed even though it was reached only via the closed-issue path) MUST be decided. [NEEDS CLARIFICATION: is invented-resolution hardening on open lifecycles in scope for this feature, or is it a separate follow-up and this feature is limited to the state gate plus the collector fix?]

### Key Entities *(include if data involved)*

- **Lifecycle issue**: The GitHub issue that represents a spec's lifecycle; its open/closed state is the authority signal this feature adds to comment-/label-triggered stage triggers.
- **Comment-/label-triggered stage**: A pipeline stage whose entry point fires on an issue comment or a label change — clarify, tasks-approval, the finalize and converge comment paths, and intake's label trigger — each of which must gate on the lifecycle issue being open.
- **Trigger gate**: The set of conditions checked before a stage acts (who acted, what the issue is, and — added here — whether it is open); the layer at which authorization must live, as distinct from an agent's tool allowlist.
- **Denied-tool finding**: The watchdog collector's report of permission denials in an inspected run; its count and per-denial location labels are what this feature makes accurate.
- **Terminal result record**: The inspected run's own final result record, which reports the authoritative turn count and permission-denial count the collector must trust when present.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In verification, 100% of comment-/label-triggered stage entry points decline to act when triggered against a closed lifecycle issue, and produce zero side effects (no branch, commit, push, PR edit, or comment) in doing so.
- **SC-002**: The reported scenario — a stage firing on a closing comment of a just-closed lifecycle — is reproduced and, after the fix, results in no stage action in 100% of reproduction attempts.
- **SC-003**: Zero comment-/label-triggered entry points remain without the closed-state gate after the audit; the count of ungated such entry points is 0.
- **SC-004**: For an open lifecycle, 100% of the previously-passing comment-/label-triggered stage behaviors still pass, confirming the gate blocks only closed lifecycles.
- **SC-005**: For runs whose terminal result record reports a permission-denial count, the watchdog's reported denial count matches that record in 100% of cases, with zero overcounts.
- **SC-006**: The watchdog no longer presents any per-denial location as a "turn" number that exceeds the run's own reported turn count; the count of impossible turn labels is 0.
- **SC-007**: The specific orphaned draft branch identified in the report no longer exists after the fix is delivered.

## Assumptions

- **Closing an issue is the sanctioned cancel**: Consistent with the constitution's "close to cancel," a closed lifecycle issue is treated as a deliberate end of that lifecycle, and honoring it is the intended behavior — not a new capability.
- **The who/what gates stay as they are**: This feature adds a state gate; it does not change the existing maintainer/requester authorization, the never-react-to-bots rule, or the label/identity checks. It only closes the missing "is it open" hole.
- **State reflects the moment of action**: The gate reads the issue's state at the time the stage would act, so a reopened issue is actionable and a race at close time is treated as closed.
- **Allowlists remain, but are not the fence**: Tool allowlists stay in place as friction and least-privilege hygiene; this feature does not rely on them for authorization and does not broaden or tighten them to achieve the gate.
- **The collector fix is accuracy-only**: The denied-tool collector's detection continues to work as designed; this feature corrects only how it counts and labels denials and does not change what it detects or the watchdog's contract from `specs/015-pipeline-watchdog/` and `specs/020-fix-watchdog/`.
- **Remediation is one-time**: Deleting the resurrected orphan branch is a one-time cleanup of state the defect created; it is included here because it exists only as a result of the defect this feature fixes.
- **Intake itself is unaffected as a producer**: This spec is produced by intake and does not modify intake's own spec-writing behavior; where it names intake's `labeled` trigger, it is as one of the entry points to audit for the state gate, not a change to how intake writes specs.
