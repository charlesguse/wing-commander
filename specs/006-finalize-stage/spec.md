# Feature Specification: Finalize Stage — Final Pull Request & Manual-Task Report

**Feature Branch**: `spec-draft/006-finalize-stage`

**Created**: 2026-07-06

**Input**: User description: "Spec out stage 5 (finalize) as per the architecture doc. When the build stage hands a specification off (either because it converged or because it hit its cycle cap), summarize what changed on the specification's persistent working branch versus the main line, extract the remaining unchecked / manual items from the task list, open the specification's final pull request from its working branch to the main line — with a body covering what changed, how to see it, the remaining manual work, and a link to the lifecycle issue — post the same remaining-manual-work list to the lifecycle issue, and advance the lifecycle issue to the review stage. Humans, never the pipeline, merge that pull request."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A built specification becomes a review-ready final pull request automatically (Priority: P1)

A specification's work has been built on its persistent working branch and the build stage has handed it off to this stage. Without anyone doing it by hand, the pipeline compares the working branch against the main line, produces a human-readable summary of what changed, and opens the specification's final pull request from its working branch to the main line. The pull request's description tells a reviewer what changed, how to see it, what manual work still remains, and links back to the lifecycle issue. The lifecycle issue is advanced to the review stage. From there a human reviews and merges the pull request — the pipeline never merges it.

**Why this priority**: This is the stage that turns committed work into something a human can actually review and accept. Until the final pull request exists, the feature is stranded on a working branch with no review surface; everything the requester ultimately does (review and merge the implementation) depends on this pull request being opened and made legible.

**Independent Test**: Hand a specification with built work on its persistent working branch to this stage and verify that a final pull request from the working branch to the main line is opened automatically, that its description summarizes what changed, how to see it, the remaining manual work, and links the lifecycle issue, that the lifecycle issue advances to the review stage, and that the pipeline neither approves nor merges the pull request — all with no human performing the summary, pull-request creation, or hand-off steps.

**Acceptance Scenarios**:

1. **Given** a specification has been handed to this stage with built work on its persistent working branch, **When** the stage runs, **Then** a final pull request from the working branch to the main line is opened.
2. **Given** the final pull request is being opened, **When** its description is composed, **Then** it covers what changed, how to see it (a link to the changes and the key files touched), the remaining manual work, and a link to the lifecycle issue.
3. **Given** the final pull request has been opened, **When** the stage completes, **Then** the lifecycle issue is advanced to the review stage and the pipeline has neither approved nor merged the pull request.

---

### User Story 2 - The remaining manual work is reported on the lifecycle issue (Priority: P2)

Whoever follows the specification's lifecycle issue can see, without opening the pull request, exactly what human work still remains after the automated build — the unchecked and human-only items drawn from the task list. The same remaining-manual-work list that appears in the pull request description is posted to the lifecycle issue, so the single place people already watch stays the authoritative record of what is left to do by hand.

**Why this priority**: The lifecycle issue is the one place a maintainer checks to follow a specification. Surfacing the remaining manual work there — mirrored exactly from the pull request — means nobody has to open the pull request or read the raw task list to learn what still needs a human, which keeps the stage legible and honest about what automation did and did not finish.

**Independent Test**: Run the stage for a specification whose task list still contains unchecked or human-only items and verify that a comment listing exactly those items is posted to the lifecycle issue, and that the same list appears in the final pull request description.

**Acceptance Scenarios**:

1. **Given** the task list contains unchecked or human-only items, **When** the stage runs, **Then** those items are extracted and posted as a remaining-manual-work list on the lifecycle issue.
2. **Given** the remaining-manual-work list has been posted to the lifecycle issue, **When** it is compared to the final pull request description, **Then** the two lists match.
3. **Given** the task list contains no remaining unchecked or human-only items, **When** the stage runs, **Then** the report states that no manual work remains rather than omitting the report.

---

### User Story 3 - A specification that did not fully converge is still finalized and clearly flagged (Priority: P3)

Sometimes the build stage hands a specification off without fully converging — its cycle cap was reached while work still remained. This stage still opens the final pull request so the partial work is reviewable, but it makes the incomplete-convergence state clearly evident to the reviewer, so nobody merges partially-built work believing it was finished.

**Why this priority**: Guaranteeing that every specification reaching this stage ends in a reviewable pull request — converged or not — is what makes the pipeline safe to run automatically without stranding partial work. Distinguishing the not-converged case protects the human reviewer from mistaking incomplete work for complete work, but it is a refinement on top of the core "always produce a reviewable pull request" behavior.

**Independent Test**: Hand a specification to this stage flagged as not converged and verify that a final pull request is still opened and that its not-fully-converged state is clearly evident to a reviewer.

**Acceptance Scenarios**:

1. **Given** a specification is handed to this stage flagged as not converged, **When** the stage runs, **Then** a final pull request is still opened from the working branch to the main line.
2. **Given** a specification is handed to this stage flagged as converged, **When** the stage runs, **Then** the final pull request is opened without a not-converged indication.
3. **Given** a specification handed off not converged, **When** its final pull request is opened, **Then** a prominent note near the top of the pull request body (for example, a ⚠️ "Not fully converged — N tasks remain" callout) makes the incomplete-convergence state clearly evident to the reviewer.

---

### Edge Cases

- The same hand-off for a specification is observed more than once (for example, a retried or duplicated dispatch): the stage must not open a second final pull request or post a duplicate remaining-manual-work comment; a final pull request that already exists is reused rather than duplicated.
- The specification's working branch carries no changes against the main line (nothing to finalize): the stage reports the anomaly on the lifecycle issue rather than attempting to open an empty pull request.
- The hand-off cannot be matched to a valid specification (its target working directory, lifecycle record, task list, or working branch is missing or inconsistent): the stage reports the failure rather than guessing which specification to finalize.
- The stage's own work cannot complete (for example, the change summary or the pull-request creation fails): the failure is surfaced on the lifecycle issue rather than silently dropping the specification.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a specification is handed to this stage (identified by its target working directory, lifecycle issue, and its converged/not-converged flag), the system MUST open a final pull request from the specification's persistent working branch to the main line.
- **FR-002**: The system MUST produce a human-readable summary of what changed between the main line and the specification's persistent working branch.
- **FR-003**: The system MUST extract the remaining unchecked and human-only items from the specification's task list as the remaining-manual-work list.
- **FR-004**: The final pull request description MUST cover: what changed, how to see it (a link to the changes and the key files touched), the remaining-manual-work list, and a link to the lifecycle issue.
- **FR-005**: The system MUST post the same remaining-manual-work list that appears in the pull request description to the specification's lifecycle issue.
- **FR-006**: When the task list contains no remaining manual work, the system MUST state that no manual work remains rather than omitting the report from either the pull request or the lifecycle issue.
- **FR-007**: The system MUST advance the specification's lifecycle issue to the review stage.
- **FR-008**: The system MUST update the specification's durable lifecycle record to reflect that it has reached this stage / is awaiting review.
- **FR-009**: The system MUST open a final pull request whether the specification was handed off converged or not converged, so that every specification reaching this stage becomes reviewable exactly once.
- **FR-010**: When the specification is handed off flagged as not converged, the system MUST make the incomplete-convergence state clearly evident to a reviewer of the final pull request by including a prominent note near the top of the pull request body (for example, a ⚠️ "Not fully converged — N tasks remain" callout). No additional GitHub state (draft status or a distinct label) is required for this signal.
- **FR-011**: The system MUST NOT itself approve or merge the final pull request; merging into the main line is reserved for a human, and that human merge is what triggers the downstream cleanup stage.
- **FR-012**: The system MUST treat a repeated or duplicate hand-off for the same specification idempotently, without opening a second final pull request or posting a duplicate remaining-manual-work comment; an already-open final pull request is reused.
- **FR-013**: When the specification's working branch carries no changes against the main line, the system MUST report the anomaly on the lifecycle issue rather than opening an empty pull request.
- **FR-014**: When the hand-off cannot be matched to a valid specification, the system MUST report the failure rather than acting on an incorrect or nonexistent specification.
- **FR-015**: When the stage's own work fails to complete (for example, summarization or pull-request creation fails), the system MUST surface the failure on the specification's lifecycle issue rather than silently dropping the specification.

### Key Entities

- **Finalization hand-off**: The signal from the build stage that starts this stage, identifying the specification (target working directory and lifecycle issue) and carrying whether the work converged or was handed over not converged.
- **Final pull request**: The single review surface this stage opens from the specification's persistent working branch to the main line; its description is the reviewer's summary of the feature; a human, never the pipeline, merges it.
- **Change summary**: The human-readable account of what changed between the main line and the working branch, including how to see it (a link to the changes and the key files touched).
- **Remaining-manual-work list**: The unchecked and human-only items drawn from the task list, reported identically in the pull request description and on the lifecycle issue.
- **Convergence flag**: The converged / not-converged marker carried by the hand-off, which determines whether the final pull request signals incomplete convergence.
- **Lifecycle issue / record**: The per-specification issue and durable metadata established by earlier stages; the issue receives the remaining-manual-work report and is advanced to the review stage, and the record is updated to reflect arrival at this stage.
- **Persistent working branch**: The specification's long-lived integration branch that this stage's pull request draws from; the main line is its merge target.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every specification handed to this stage results in exactly one final pull request from its persistent working branch to the main line, whether it converged or not.
- **SC-002**: A reviewer can understand from the final pull request description alone what changed, how to view it, and what manual work remains, without reading the raw diff or the task list.
- **SC-003**: The remaining-manual-work list shown in the final pull request matches the list posted to the lifecycle issue.
- **SC-004**: A maintainer following only the lifecycle issue can see that the specification reached the review stage and what manual work remains, without opening the pull request.
- **SC-005**: No specification is merged into the main line by the pipeline itself; every final pull request waits for a human merge.
- **SC-006**: A specification handed off without fully converging is still finalized into a reviewable pull request, and its incomplete-convergence state is evident to the reviewer.
- **SC-007**: Repeated or duplicate hand-offs for the same specification never result in more than one final pull request or a duplicated remaining-manual-work report.

## Assumptions

- "Persistent working branch," "the main line," "lifecycle issue," "durable lifecycle record," and "task list" refer to the same per-specification branch, primary integration branch, issue, metadata, and task breakdown established by the earlier pipeline stages; this stage introduces no new such concepts.
- The converged / not-converged flag is supplied by the build stage's hand-off; this stage consumes it as given and does not re-judge convergence. When a specification is handed off not converged, the build stage has already reported its remaining work on the lifecycle issue; this stage's own report reflects the current state of the task list.
- "Remaining manual work" means task-list items that are still unchecked and items that inherently require a human, as recorded in the task list; this stage extracts them rather than deciding what is or is not manual.
- Composing the change summary and extracting the remaining-manual-work list use a cost-appropriate summarization capability consistent with the pipeline's model-tiering conventions (a lightweight model for summaries), and the stage runs with the least-privilege tool set it needs; the specifics are design concerns, not requirements of this specification.
- The final pull request targets the main line and does not close the lifecycle issue; the lifecycle issue is closed later, by the cleanup stage, after a human merges the final pull request.
- Handing off from this stage to cleanup is the human merge of the final pull request into the main line; the cleanup stage's own behavior (branch deletion, label finalization, issue closure) is out of scope for this specification.
- Starting this stage is itself a hand-off from the build stage; the build stage's behavior is out of scope here.
