# Feature Specification: Tasks Stage — Plan to Task List

**Feature Branch**: `spec-draft/003-tasks-stage`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Please spec out stage 3 as per the architecture doc." (from docs/architecture.md: when a plan pull request merges into a specification's persistent working branch, the pipeline should generate a task list from the plan, either committing it directly or presenting it for review depending on configuration, then hand off to the implementation stage and keep the lifecycle issue current.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Accepted plan becomes a task list and implementation begins (Priority: P1)

An implementation plan has just been accepted: its pull request was merged into the specification's persistent working branch. In the default configuration, without anyone doing it by hand, a task list derived from the plan is committed to that branch and the implementation stage starts working through it.

**Why this priority**: This is the pipeline's third stage — the bridge between "here is how we'll build it" and "code is being written." Nothing downstream (implementation, convergence, finalization) can begin until a task list exists.

**Independent Test**: Merge a plan pull request into a specification's persistent working branch with the default configuration and verify that a task list appears on that branch, a summary is posted to the lifecycle issue, and the implementation stage begins automatically with no human performing the task-drafting or hand-off steps.

**Acceptance Scenarios**:

1. **Given** a plan pull request is merged into a specification's persistent working branch, **When** task generation runs under the default configuration, **Then** a task list derived from the accepted plan is committed directly to that branch.
2. **Given** the task list has been committed under the default configuration, **When** the commit completes, **Then** the implementation stage is started for that specification at its first iteration.
3. **Given** the task list has been committed, **When** it is created, **Then** the durable lifecycle record for the specification is updated to reflect that it has advanced to the tasks stage.

---

### User Story 2 - Lifecycle issue stays current through task generation (Priority: P2)

Once a task list is generated, the feature's lifecycle issue reflects that the feature has moved from "plan" to "tasks": its stage label updates, and a comment summarizes the generated tasks, so anyone following the issue knows where things stand without having to inspect the repository directly.

**Why this priority**: The lifecycle issue is the single place requesters and maintainers check on progress; without an update here, the pipeline's third stage would be invisible to anyone not already watching the persistent branch.

**Independent Test**: After a task list is generated for a specification, verify its lifecycle issue's stage label changes and a comment summarizing the tasks appears.

**Acceptance Scenarios**:

1. **Given** a task list has been generated for a specification, **When** it is created, **Then** the specification's lifecycle issue receives a comment summarizing the tasks.
2. **Given** a task list has been generated, **When** it is created, **Then** the lifecycle issue's stage label is updated to show the feature is in the tasks stage.

---

### User Story 3 - Maintainer requires human review of generated tasks (Priority: P3)

A repository can be configured to require a human to review the generated task list before implementation starts. When this review mode is active, the generated task list is presented as a pull request against the specification's persistent working branch instead of being committed directly; implementation only begins after a maintainer merges that pull request.

**Why this priority**: Some teams want a checkpoint between planning and implementation to catch a poorly-scoped task breakdown before automated implementation starts consuming it; this priority is lower because the default (fully automatic) path already delivers the pipeline's core value.

**Independent Test**: With the review-required configuration active, merge a plan pull request and verify a task-list pull request is opened against the persistent working branch instead of tasks being committed directly, and that the implementation stage does not start until that pull request is merged by a human.

**Acceptance Scenarios**:

1. **Given** the repository is configured to require task review, **When** a plan pull request merges, **Then** the generated task list is presented as a pull request targeting the specification's persistent working branch rather than being committed directly.
2. **Given** a task-list review pull request has been opened, **When** a maintainer merges it, **Then** the implementation stage is started for that specification at its first iteration.
3. **Given** a task-list review pull request has been opened, **When** it has not yet been merged, **Then** the implementation stage does not start.

---

### Edge Cases

- The merged plan pull request cannot be unambiguously matched to a single specification (e.g., its files or lifecycle record are missing or inconsistent): the pipeline reports the failure rather than guessing which specification to generate tasks for.
- The same plan merge event is observed more than once (e.g., a retried or duplicated notification): task generation must not produce a second task list, a second review pull request, or a second implementation-stage hand-off for the same merge.
- A task-list review pull request is closed without being merged: the specification is marked stalled and its lifecycle issue reflects that the tasks stage did not complete, rather than silently remaining marked as "in tasks" forever or starting implementation anyway; a maintainer must manually restart the tasks stage.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect when a plan pull request merges into a specification's persistent working branch and identify which specification it corresponds to.
- **FR-002**: The system MUST generate a task list derived from the accepted implementation plan.
- **FR-003**: The system MUST support a repository-level configuration choosing between two review modes for the generated task list: committing it directly, or presenting it as a pull request for human review.
- **FR-004**: Under the direct-commit review mode, the system MUST commit the generated task list directly to the specification's persistent working branch.
- **FR-005**: Under the direct-commit review mode, the system MUST automatically start the implementation stage for the specification, at its first iteration, once the task list is committed.
- **FR-006**: Under the review-required mode, the system MUST present the generated task list as a pull request targeting the specification's persistent working branch, and MUST NOT commit it directly or start the implementation stage until that pull request is merged.
- **FR-007**: Under the review-required mode, once the task-list review pull request is merged, the system MUST start the implementation stage for the specification at its first iteration, the same as the direct-commit mode does after committing.
- **FR-008**: The system MUST update the durable lifecycle record for the specification to reflect that it has advanced to the tasks stage.
- **FR-009**: The system MUST update the lifecycle issue's stage label and post a comment summarizing the generated tasks.
- **FR-010**: The system MUST NOT merge or approve a task-list review pull request itself — a human reviews and merges it.
- **FR-011**: The system MUST treat a repeated or duplicate plan-merge notification for the same specification idempotently, without producing a second task list, a second review pull request, or a second implementation-stage hand-off for the same merge event.
- **FR-012**: When the system cannot unambiguously identify which specification a merged plan pull request corresponds to, it MUST report the failure rather than acting on an incorrect specification.
- **FR-013**: When a task-list review pull request is closed without merging, the system MUST mark the specification as stalled — updating the lifecycle record and lifecycle issue to reflect that the tasks stage did not complete — and MUST NOT start the implementation stage or automatically regenerate a new task list; resuming the tasks stage requires manual maintainer action.

### Key Entities

- **Task list (tasks artifact)**: The structured, dependency-ordered breakdown of work derived from the accepted implementation plan; committed to or reviewed against the specification's persistent working branch.
- **Review mode (configuration)**: The repository-level setting choosing whether generated task lists are committed directly or presented as a pull request for human review; defaults to direct-commit.
- **Task-list review pull request**: Present only under the review-required mode; the reviewable proposal containing the generated task list, targeting the specification's persistent working branch.
- **Lifecycle record (spec metadata)**: The durable association between a specification, its issue, its current stage, and its branches; updated to record the transition into the tasks stage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Under the default configuration, after a plan pull request merges, the implementation stage begins with zero human performing task-drafting or hand-off steps by hand.
- **SC-002**: Under the review-required configuration, 100% of generated task lists are reviewed via a pull request before the implementation stage begins.
- **SC-003**: A maintainer can determine a specification's tasks-stage status entirely from its lifecycle issue, without inspecting the persistent working branch or pull requests directly.
- **SC-004**: Repeated or duplicate plan-merge notifications for the same specification never result in more than one task list, more than one review pull request, or more than one implementation-stage hand-off for that merge event.

## Assumptions

- "Persistent working branch" refers to the same per-specification branch created and reused by the plan stage's specification, matching the term used there.
- The review mode is a repository-level configuration (not per-specification), and defaults to direct-commit — the fastest path from plan to implementation — matching the pipeline's general preference for automation with human checkpoints as an opt-in.
- The project's task-generation tooling defines the structure and content of the task list; this specification concerns when and how task generation is triggered, reviewed, and reported, not the task list's internal format.
- Starting the implementation stage means dispatching it for the specification at its first iteration; the implementation stage's own internal behavior is out of scope for this specification.
- A human reviews and merges the task-list review pull request when review mode is active; merging it is the signal that the tasks stage is accepted and the implementation stage may proceed, matching the pattern established by the plan stage.
- Trusted repository members and the original requester are the same audience defined by the intake stage's specification; this stage does not introduce new categories of permitted actors.
