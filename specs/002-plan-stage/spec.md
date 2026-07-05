# Feature Specification: Plan Stage — Spec to Implementation Plan

**Feature Branch**: `spec-draft/002-plan-stage`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Spec out stage 2, the plan stage" (from docs/architecture.md: when a draft spec pull request merges into the mainline, the pipeline should create a persistent working branch for that specification, generate an implementation plan from it, present the plan as a pull request for review, and keep the lifecycle issue current.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Accepted spec becomes a plan pull request (Priority: P1)

A specification has just been accepted: its draft pull request was merged into the mainline. Shortly after, without anyone doing it by hand, a persistent working branch for that feature appears, and a pull request containing an implementation plan derived from the specification is opened against that branch for a maintainer to review.

**Why this priority**: This is the pipeline's second stage — the bridge between "we agreed what to build" and "here is how we'll build it." Nothing downstream (tasks, implementation) can begin until a plan exists.

**Independent Test**: Merge a draft spec pull request into the mainline and verify that a persistent feature branch is created, a pull request containing a plan targeting that branch appears, and no human performed the branching or plan-drafting steps by hand.

**Acceptance Scenarios**:

1. **Given** a draft specification pull request is merged into the mainline, **When** the merge completes, **Then** a persistent working branch for that specification is created (if it does not already exist).
2. **Given** the persistent working branch exists, **When** plan generation runs, **Then** a pull request containing an implementation plan derived from the specification is opened, targeting the persistent branch (not the mainline).
3. **Given** the plan pull request exists, **When** it is created, **Then** the durable lifecycle record for the specification is updated to reflect that it has advanced to the planning stage.

---

### User Story 2 - Lifecycle issue stays current through planning (Priority: P2)

Once a plan pull request appears, the feature's lifecycle issue reflects that the feature has moved from "spec" to "plan": its stage label updates, and a comment summarizes the plan and links to the pull request, so anyone following the issue knows where things stand without having to watch pull requests directly.

**Why this priority**: The lifecycle issue is the single place requesters and maintainers check on progress; without an update here, the pipeline's second stage would be invisible to anyone not already watching pull request activity.

**Independent Test**: After a plan pull request is created for a specification, verify its lifecycle issue's stage label changes and a comment summarizing the plan with a link to the pull request appears.

**Acceptance Scenarios**:

1. **Given** a plan pull request has been opened for a specification, **When** it is created, **Then** the specification's lifecycle issue receives a comment summarizing the plan and linking to the pull request.
2. **Given** a plan pull request has been opened, **When** it is created, **Then** the lifecycle issue's stage label is updated to show the feature is in planning.

---

### User Story 3 - Hand-submitted specs get a lifecycle issue during planning (Priority: P3)

A specification that was written by hand and submitted directly as a pull request (skipping the issue-based intake flow) has no lifecycle issue yet when its pull request merges. When the plan stage picks it up, a lifecycle issue is created for it first, so the planning update — and everything reported after it — has somewhere to go.

**Why this priority**: Keeps the pipeline's reporting consistent regardless of how a specification originated, so later stages never need to special-case "no issue exists."

**Independent Test**: Merge a hand-written specification pull request that has no associated lifecycle issue, and verify a lifecycle issue is created, labeled with the feature's identity and planning stage, and cross-linked with the plan pull request once planning completes.

**Acceptance Scenarios**:

1. **Given** an accepted specification with no existing lifecycle issue, **When** the plan stage begins working on it, **Then** a lifecycle issue is created and labeled with the feature's identity before the planning stage reports anything.

---

### Edge Cases

- The merged pull request cannot be unambiguously matched to a single specification (e.g., its files or lifecycle record are missing or inconsistent): the pipeline reports the failure rather than guessing which specification to plan.
- The same specification's merge event is observed more than once (e.g., a retried or duplicated notification): planning must not create a second persistent branch or a second plan pull request for the same planning attempt.
- The persistent working branch for the specification already exists (e.g., from a prior run): planning reuses it rather than failing or recreating it.
- The plan pull request is closed without being merged: the specification's stage and lifecycle issue must reflect that planning did not complete, rather than silently remaining marked as "in planning" forever.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect when a draft specification pull request merges into the mainline and identify which specification it corresponds to.
- **FR-002**: The system MUST create a persistent working branch dedicated to that specification if one does not already exist, and MUST NOT create a duplicate if one does.
- **FR-003**: The system MUST generate an implementation plan derived from the accepted specification.
- **FR-004**: The system MUST present the generated plan as a pull request targeting the specification's persistent working branch, not the mainline.
- **FR-005**: The system MUST update the durable lifecycle record for the specification to reflect that it has advanced to the planning stage.
- **FR-006**: The system MUST update the lifecycle issue's stage label and post a comment summarizing the plan with a link to the plan pull request.
- **FR-007**: When a specification has no existing lifecycle issue at the time planning begins, the system MUST create and label one before reporting any planning progress.
- **FR-008**: The system MUST NOT merge or approve the plan pull request itself — a human reviews and merges it.
- **FR-009**: The system MUST treat a repeated or duplicate merge notification for the same specification idempotently, without creating a second branch or a second plan pull request for the same planning attempt.
- **FR-010**: When the system cannot unambiguously identify which specification a merged pull request corresponds to, it MUST report the failure rather than acting on an incorrect specification.
- **FR-011**: The system MUST [NEEDS CLARIFICATION: should plan generation proceed if the merged specification still contains unresolved clarification markers, or must it refuse and report back that clarification is incomplete?]
- **FR-012**: When a plan pull request is closed without merging, the system MUST [NEEDS CLARIFICATION: does the specification revert to the prior stage so a new plan can be generated, does it require a manual re-trigger, or is the feature considered stalled pending maintainer action?]

### Key Entities

- **Persistent working branch**: The long-lived branch for one specification that survives across the planning, tasks, and implementation stages; created once per specification.
- **Implementation plan (plan artifact)**: The structured description of how the accepted specification will be built; derived from the specification's content.
- **Plan pull request**: The reviewable proposal containing the implementation plan, targeting the specification's persistent branch.
- **Lifecycle record (spec metadata)**: The durable association between a specification, its issue, its current stage, and its branches; updated to record the transition into planning.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a specification's draft pull request is merged, its plan pull request appears with zero human performing branching or plan-drafting steps by hand.
- **SC-002**: 100% of accepted specifications — whether issue-originated or hand-submitted — reach the planning stage with a lifecycle issue reporting their status.
- **SC-003**: A maintainer can determine a specification's planning status entirely from its lifecycle issue, without inspecting pull requests directly.
- **SC-004**: Repeated or duplicate merge notifications for the same specification never result in more than one persistent branch or more than one plan pull request for that planning attempt.

## Assumptions

- "Mainline" refers to the repository's main integration branch, matching the term used by the intake stage's specification.
- The persistent working branch is scoped to one specification and is expected to be reused by later pipeline stages (tasks, implementation), not recreated per stage.
- The project's planning tooling defines the structure and content of the implementation plan; this specification concerns when and how planning is triggered and reported, not the plan's internal format.
- A human reviews and merges the plan pull request; merging it is the signal that planning is accepted and later stages may proceed, matching the pattern established by the intake stage.
- Trusted repository members and the original requester are the same audience defined by the intake stage's specification; this stage does not introduce new categories of permitted actors.
