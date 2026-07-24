# Feature Specification: Clear Next-Step Callouts in the Lifecycle Issue

**Feature Branch**: `019-next-step-callouts`

**Created**: 2026-07-24

**Status**: Draft

**Input**: User description: "When an implementation is ready for review, the issue shows a PR. That is good. But unless there are manual steps after the merge, there isn't a notification in the issue that a PR is ready for review. The system highlights the open PR for the spec phase but not for the implementation phase. Any time there is something for a human to do, call it out simply in the issue and directly link to the related pull request if there is one. If there are implementation tasks brought over into the issue from the PR, make sure to call out that these are implementation tasks after the merge (or whenever is appropriate for the tasks to be done). In other words, differentiate information being shared vs what the next step is for the person using Wing Commander."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See "you need to review this PR" at every review gate (Priority: P1)

A requester or maintainer following a lifecycle issue reaches a point where the pipeline has produced a pull request that only a human can advance — most importantly the final implementation PR at the end of the implement/finalize phase. Today the spec-phase PR is surfaced clearly, but the implementation-phase PR is not consistently announced as "ready for your review." The person should see a single, unmistakable callout in the issue that a PR is waiting on them, with a direct link to that PR, without having to scan through informational status comments or infer it from a label.

**Why this priority**: This is the core gap the requester reported and the highest-value slice. Per the project's automation-first principle, the requester should only ever need to review the spec PR and the final implementation PR — so both of those review gates must be announced unmistakably. Missing the implementation-review announcement means work silently stalls waiting on a human who was never told.

**Independent Test**: Drive a spec through to the point where the final implementation PR is opened. Confirm the lifecycle issue receives a clearly-marked "action needed: review this PR" callout that names and links the PR. Delivers value on its own: the requester is never left guessing whether it's their turn.

**Acceptance Scenarios**:

1. **Given** the implement/finalize phase has produced an open pull request awaiting human review, **When** that PR is opened, **Then** the lifecycle issue receives a callout that clearly states a human must review the PR and includes a direct link to it.
2. **Given** the spec-phase PR is opened, **When** the intake stage completes, **Then** the lifecycle issue likewise carries a clearly-marked review-needed callout with a direct link to the spec PR, using the same recognizable format as the implementation-phase callout.
3. **Given** a review-needed callout has been posted, **When** a person opens the lifecycle issue, **Then** they can identify the required action and reach the correct PR in one step, without reading other comments.

---

### User Story 2 - Tell information apart from action (Priority: P2)

A person skimming a busy lifecycle issue can immediately distinguish comments that merely share information (a stage started, a cycle converged, a summary of what changed) from comments that ask them to do something (review a PR, answer a clarification, perform a manual step). Action-required comments look and read differently from informational ones, so the reader's eye lands on "what do I need to do next" without effort.

**Why this priority**: The requester explicitly asked to "differentiate information being shared vs what the next step is." Even with P1's review callouts in place, they are easy to lose among informational chatter unless the two categories are visibly distinct. This raises the value of every action callout the pipeline posts.

**Independent Test**: Review the set of comments a spec accumulates across its lifecycle. Confirm every comment is recognizably one of two kinds — informational or action-required — by a consistent, human-visible convention, and that a reader can find the most recent outstanding action quickly.

**Acceptance Scenarios**:

1. **Given** a mix of informational and action-required comments on a lifecycle issue, **When** a person reads the issue, **Then** action-required comments are visibly distinguished from informational ones by a consistent convention.
2. **Given** an action-required comment, **When** it is read, **Then** it states plainly what the human must do and (if applicable) links directly to the relevant pull request.
3. **Given** an informational comment, **When** it is read, **Then** it does not present itself as requiring action.

---

### User Story 3 - Flag remaining manual/implementation tasks as post-merge to-dos (Priority: P3)

When the pipeline surfaces remaining manual work or implementation tasks into the lifecycle issue, each such item is clearly framed as a task for a human to perform, and states when it should be done — for example, after the PR is merged, or at whatever point is appropriate. The reader is never left unsure whether a listed task has already been handled by the pipeline or is still waiting on them, nor when they are expected to act on it.

**Why this priority**: The requester called this out specifically ("call out that these are implementation tasks after the merge"). It is lower priority than the review callouts because it applies only when residual manual work exists, but when it does exist it prevents the requester from either doing already-done work or missing a required follow-up.

**Independent Test**: Drive a spec whose finalize phase leaves residual manual work to the lifecycle issue. Confirm the surfaced tasks are labelled as human tasks, distinguished from work the pipeline already completed, and annotated with the appropriate timing (e.g., "after merge").

**Acceptance Scenarios**:

1. **Given** the finalize phase determines that manual work remains, **When** those items are surfaced to the lifecycle issue, **Then** they are presented as an action-required callout, framed as tasks for a human to perform.
2. **Given** remaining manual tasks are to be done only after the PR merges (or at another specific point), **When** they are surfaced, **Then** the appropriate timing is stated for the reader.
3. **Given** the finalize phase determines that no manual work remains, **When** the phase completes, **Then** the issue clearly communicates that nothing is required of the human on that front (an informational, not action-required, message).

---

### Edge Cases

- **No PR exists at an action moment**: If a human action is required but there is no associated pull request (for example, a clarification question), the callout still appears and reads as action-required, simply without a PR link. The requirement to "link directly to the related pull request" applies only when one exists.
- **Repeated or retried stages**: If a stage runs more than once (retry, re-trigger, or a new implement cycle) and re-produces the same review gate, the reader can still tell which callout reflects the current outstanding action rather than a superseded one.
- **Action already handled**: If a person has already acted (e.g., merged the PR) before or around the time a callout is posted, the callout does not mislead them into repeating a completed action.
- **Multiple concurrent specs**: A person watching several lifecycle issues at once can, per issue, tell whether that specific spec is waiting on them.
- **Failure/stall states**: When a stage fails or stalls and needs human intervention to restart, that too is a "something for a human to do" moment and is surfaced consistently with the action-required convention.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Whenever the pipeline reaches a point where a human must act before progress can continue, the system MUST post an action-required callout to the lifecycle issue that plainly states what the person needs to do.
- **FR-002**: When an action-required moment involves an open pull request awaiting review (including the final implementation/finalize PR and the spec-phase PR), the callout MUST identify that PR and include a direct link to it.
- **FR-003**: The system MUST announce the implementation/finalize-phase review gate in the lifecycle issue with the same clarity and recognizable convention already applied to the spec-phase review gate, so neither review gate is silently left to the human to discover.
- **FR-004**: Action-required callouts MUST be visibly distinguishable from purely informational status messages by a consistent, human-readable convention applied across all stages.
- **FR-005**: Informational status messages MUST NOT present themselves as requiring human action.
- **FR-006**: When the pipeline surfaces remaining manual work or implementation tasks into the lifecycle issue, each item MUST be framed as a human task and distinguished from work the pipeline has already completed automatically.
- **FR-007**: When remaining manual tasks are intended to be performed at a particular time (such as after the PR merges), the callout MUST state that timing to the reader.
- **FR-008**: When a review gate or other required action has no associated pull request, the action-required callout MUST still be posted and MUST read as action-required, omitting only the PR link.
- **FR-009**: When a phase completes with no human action required, the system MUST communicate that outcome as an informational message rather than an action-required callout.
- **FR-010**: A reader opening the lifecycle issue MUST be able to identify the current outstanding human action (if any) and reach the relevant pull request in a single step, without inferring it from labels or reading unrelated comments.
- **FR-011**: The action-required convention MUST be applied consistently across every human-action moment the pipeline can reach — the two PR review gates (spec-phase and implementation/finalize-phase), residual manual work, clarification-needed prompts, and failure/stall states requiring human intervention — so that the meaning of the convention is learnable once and trusted thereafter.
- **FR-012**: The chosen presentation for action-required callouts MUST make the latest outstanding action discoverable even on a long, busy issue. The system MUST post a fresh, clearly-marked action-required comment at each action moment (append-only); the most recent such comment reflects the current outstanding action, and earlier callouts remain in the issue history.

### Key Entities *(include if data involved)*

- **Action-required callout**: A message posted to the lifecycle issue signalling that the pipeline is waiting on a human. Carries a plain statement of the required action, an optional direct link to a related pull request, and, when applicable, the timing at which the action should be performed.
- **Informational status message**: A message posted to the lifecycle issue that shares progress or context (stage started, cycle converged, summary of changes) and explicitly does not require the reader to act.
- **Review gate**: A point in the lifecycle where an open pull request awaits human review before the pipeline can advance — currently the spec-phase PR and the final implementation/finalize PR.
- **Remaining manual task**: A unit of residual work the pipeline cannot perform automatically, surfaced into the lifecycle issue, framed as a human to-do with associated timing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every review gate a spec passes through (spec-phase and implementation/finalize-phase), the lifecycle issue contains exactly one clearly-marked action-required callout announcing that gate, each with a working direct link to the corresponding pull request — 100% of gates announced, versus the implementation-phase gate being unannounced today.
- **SC-002**: A person unfamiliar with the pipeline, shown a lifecycle issue, can correctly identify whether the pipeline is currently waiting on them and, if so, which action and which PR — in under 15 seconds and without opening any other page.
- **SC-003**: Given a completed lifecycle issue, a reader can classify every pipeline comment as either informational or action-required with no ambiguous cases.
- **SC-004**: When residual manual work exists, 100% of the surfaced tasks are recognizable as human to-dos with stated timing; when none exists, the issue states that no manual work remains.
- **SC-005**: No review gate reachable by the pipeline leaves the human uninformed that it is their turn (zero silent stalls attributable to a missing callout).

## Assumptions

- Interaction remains GitHub-native: callouts are ordinary issue comments (and/or existing labels), consistent with the principle that a spec's lifecycle is legible from its issue alone; no external dashboard is introduced.
- The existing stage-status and remaining-manual-work comments are the baseline this feature refines and makes consistent, rather than a wholly new notification channel.
- "Related pull request" refers to the pull request produced by the pipeline for that phase (the spec-draft PR for intake, the finalize PR for implementation); linking is by ordinary GitHub reference so GitHub renders it as a live link.
- The distinction between informational and action-required is conveyed by human-visible convention in comment content (and optionally existing labels); no new machine-readable protocol is required by this feature.
- Stage labels (e.g., a review-stage label) may continue to exist and complement callouts, but the callout — not the label alone — is what makes the next step legible, since FR-010 forbids requiring the reader to infer the action from labels.
