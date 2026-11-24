# Feature Specification: Review findings — fix now, record only what fails silently, drop the rest

**Feature Branch**: `spec-draft/128-review-finding-triage`

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "Review findings: fix now, record only what fails silently, drop the rest" (lifecycle issue #1189, owner direction 2026-11-24, following an analysis of the Maintenance backlog #889)

## Context

The Maintenance backlog grows much faster than it shrinks: since mid-October about 184 lines were added and about 12 fixed (286 open when the issue was written). Nearly all new lines come from code reviews of lifecycle PRs; five PRs alone added about 75. Many are nits that cannot change any output, or that would fail loudly enough to be filed when they actually happen.

The owner approved this rule (quoted verbatim; it is the governing wording for this spec):

> **Filing review findings.** Sort each finding by the first of these that fits:
>
> 1. **Fix it now** when it is in scope, or when the fix is a line or two in a file the PR already changes. It goes in the same PR, with a test, as now.
> 2. **Record it** as a Maintenance backlog line only when it is outside the PR's scope and it can fail *silently*: produce a wrong result, a wrong reading or a wrong decision, or skip a check, with no error, red gate or "unreadable" to show it. Say in the line how it fails silently.
> 3. **Drop it** when it is outside scope and can only fail *loudly* (a crash, a red gate, a visible error), or cannot change any output at all (naming, wording, style, "could be clearer"). Name it in the review report as dropped, with that reason, so a later pass doesn't rediscover it as new.
>
> A loud failure is filed when it happens, from the evidence of that run. A finding marked important or security is never dropped: fix it or record it.

A separate fix PR applies this wording to CLAUDE.md and the `review-until-clean` skill for review sessions. **This spec covers the stage agents only**: the stage-findings filing path, the PR-conversation stage's routing of review findings (including the lifecycle-review-gate findings it folds), and the lifecycle review gate's in-scope / out-of-scope split.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The lifecycle review gate records only silent out-of-scope findings (Priority: P1)

The owner watches the Maintenance backlog. When the lifecycle review gate reviews a lifecycle PR, its in-scope findings are folded back into the pipeline as today, but of its out-of-scope findings only those that can fail silently reach the backlog. Out-of-scope findings that can only fail loudly, or cannot change any output, are dropped and listed as dropped, with the reason, in that round's review report.

**Why this priority**: Lifecycle PR reviews are the source of nearly all new backlog lines; this story alone addresses most of the growth.

**Independent Test**: Feed the gate's routing a review result holding one in-scope finding, one out-of-scope silent finding, one out-of-scope loud finding and one out-of-scope no-output finding. Only the in-scope finding is folded, only the silent finding is recorded (with its silent-failure description), and the other two appear in the round's report as dropped with their reasons.

**Acceptance Scenarios**:

1. **Given** an out-of-scope finding classified as able to fail silently, **When** the gate routes the round, **Then** it is recorded as a backlog entry whose text says how it fails silently.
2. **Given** an out-of-scope finding classified as able to fail only loudly, **When** the gate routes the round, **Then** nothing is recorded and the round's report names it as dropped with the reason "fails loudly".
3. **Given** an out-of-scope finding classified as unable to change any output, **When** the gate routes the round, **Then** nothing is recorded and the report names it as dropped with the reason "no output change".
4. **Given** an out-of-scope finding marked important or security, **When** it would otherwise be dropped, **Then** it is recorded instead, never dropped.
5. **Given** an in-scope finding, **When** the gate routes the round, **Then** it is folded into the PR's work exactly as today, regardless of its failure class.

---

### User Story 2 - The PR-conversation stage routes review findings by the same rule (Priority: P2)

When the PR-conversation stage handles review findings on a lifecycle PR — including findings it folds from the lifecycle review gate — it applies the same three-way sort: fix in the PR when in scope or a line or two in a file the PR already changes, record when out of scope and silent, drop (and name as dropped) otherwise.

**Why this priority**: The second route by which review findings reach the backlog; must agree with the gate so a finding is not dropped by one path and recorded by the other.

**Independent Test**: Give the stage's routing the same four-finding mix as Story 1 and check the outcomes match Story 1's exactly.

**Acceptance Scenarios**:

1. **Given** a finding the gate already dropped, **When** the PR-conversation stage folds the gate's result, **Then** it does not resurrect the finding as a backlog entry.
2. **Given** an out-of-scope finding whose fix is a line or two in a file the PR already changes, **When** the stage routes it, **Then** it is treated as fix-now, not recorded.
3. **Given** the same finding reaching both the gate and the PR-conversation stage, **When** both route it, **Then** both reach the same outcome.

---

### User Story 3 - Stage-found defects follow the record/drop rule (Priority: P3)

Stage agents (intake through finalize) that notice a defect outside their own task propose it through the stage-findings filing path. That path files only proposals that can fail silently (or are marked important/security), and lists every other proposal in the run summary as dropped with its reason.

**Why this priority**: A smaller volume than review findings, but the same noise; keeps one rule across every route into the backlog.

**Independent Test**: Submit three proposals (silent, loud, no-output) through the filing path; only the silent one is filed, and the run summary lists the other two as dropped with reasons.

**Acceptance Scenarios**:

1. **Given** a stage proposal classified loud, **When** the filing path runs, **Then** nothing is filed and the run summary names it as dropped with the reason.
2. **Given** a stage proposal classified silent, **When** the filing path runs, **Then** it is filed as today, with its silent-failure description included.
3. **Given** a proposal with no classification at all, **When** the filing path runs, **Then** it is handled by the defined default (FR-009), never silently discarded.

---

### Edge Cases

- A finding is both out of scope and marked security, and classified "no output change": it is recorded, never dropped (the important/security override wins).
- A finding classified silent but with no description of how it fails silently: it is still recorded, and the missing description is visible in the entry rather than invented.
- A loud-only finding is dropped, then the loud failure actually happens in a later run: it is filed then from that run's evidence by the existing failure-reporting paths; nothing in this feature blocks that.
- A later review pass rediscovers a finding an earlier round dropped: the earlier round's report names it, so the pass can recognise it as already dropped rather than new.
- Existing open backlog lines that this rule would drop: see FR-012.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every review finding and stage-found defect proposal MUST be sorted into exactly one of three outcomes — fix now, record, drop — by the first rule of the owner-approved wording that fits.
- **FR-002**: "Fix now" MUST apply when the finding is in scope for the PR, or when its fix is a line or two in a file the PR already changes; such findings stay in the PR's own work, as today.
- **FR-003**: "Record" MUST apply only when the finding is out of scope and can fail silently — produce a wrong result, reading or decision, or skip a check, with no error, red gate or "unreadable" state to show it.
- **FR-004**: A recorded finding's entry MUST state how it fails silently.
- **FR-005**: "Drop" MUST apply when the finding is out of scope and can only fail loudly, or cannot change any output at all.
- **FR-006**: A dropped finding MUST be named in the routing stage's own report (the review round's report, or the stage run's summary) with its drop reason ("fails loudly" or "no output change"), so a later pass can recognise it.
- **FR-007**: A finding marked important or security MUST never be dropped; it is fixed or recorded.
- **FR-008**: The lifecycle review gate, the PR-conversation stage's review-finding routing, and the stage-findings filing path MUST apply the same rule and reach the same outcome for the same finding.
- **FR-009**: The way a finding's failure class (silent / loud / none) is determined MUST be [NEEDS CLARIFICATION: Should each finding carry a structured field (e.g. failure: silent | loud | none) that deterministic code routes on, or is the record/drop call the reviewing agent's judgment expressed in prose?]. Whichever is chosen, a finding with no determinable class MUST be recorded rather than dropped (fail toward visibility).
- **FR-010**: The way a finding is marked important or security MUST be [NEEDS CLARIFICATION: How are "important" and "security" marked so the never-drop override is reliable — a severity field on the finding, a category value, or a label applied when recorded?].
- **FR-011**: A deterministic check MUST fail when a stage drops a finding without naming it and its reason in that stage's report. (Default chosen for open question 2: yes, gate it — the "rule with no gate behind it" principle in the project instructions.)
- **FR-012**: Open Maintenance backlog lines that this rule would drop MUST be handled by [NEEDS CLARIFICATION: a one-time sweep that removes them (naming each removal and its reason), or left in place with the rule applying to new findings only? A separate stale/duplicate/real triage of #889 is already running.].
- **FR-013**: Dropping MUST NOT suppress any existing failure-reporting path (watchdog, durable-failure issues, red gates); a loud failure is filed when it happens.
- **FR-014**: The published contracts for the affected filing and routing paths MUST be updated in the same change as their behaviour, and the reference document MUST be updated where it lists the affected defaults or switches.

### Key Entities

- **Finding**: a review finding or stage-found defect proposal. Attributes relevant here: scope (in / out), failure class (silent / loud / none), important/security marking, silent-failure description, and its routing outcome.
- **Routing outcome**: fix now, record, or drop; for drop, a reason.
- **Review report / run summary**: the per-round or per-run record in which dropped findings are named with their reasons.
- **Maintenance backlog entry**: a checklist line recording an out-of-scope silent finding, including how it fails silently.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the 30 days after this ships, the number of Maintenance backlog lines added from lifecycle-PR reviews and stage findings falls by at least half compared with the 30 days before.
- **SC-002**: 100% of backlog entries added by these paths after this ships state how the finding fails silently, or carry an important/security marking.
- **SC-003**: 0 findings marked important or security are dropped, across all routing paths.
- **SC-004**: 100% of dropped findings appear by name, with a reason, in the report of the round or run that dropped them; a deterministic check enforces it.
- **SC-005**: For a fixed set of test findings, the three routing paths reach identical outcomes.

## Assumptions

- The owner-approved wording quoted in Context is fixed; this spec does not reword it.
- The CLAUDE.md and `review-until-clean` skill change for review sessions is a separate fix PR and out of scope here.
- "Scope" for a lifecycle PR keeps its current meaning in the lifecycle review gate (the existing in-scope / out-of-scope split); this feature adds the silent / loud / none split only on the out-of-scope side.
- "A line or two in a file the PR already changes" is judged by the reviewer; this spec does not define a line-count threshold.
- Stage-found defects already go through a single filing path; no new filing destination is introduced.
- The existing cap on findings filed per run still applies after the drop step, so dropped findings no longer consume cap slots.
