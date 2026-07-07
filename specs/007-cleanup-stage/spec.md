# Feature Specification: Cleanup Stage — Lifecycle Teardown on Final Merge or Draft Rejection

**Feature Branch**: `spec-draft/007-cleanup-stage`

**Created**: 2026-07-07

**Input**: User description: "Spec out stage 6 (cleanup) as per the architecture doc. Triggered when a pipeline pull request closes, with two paths. When a specification's final pull request (its persistent working branch into the main line) is merged, delete that specification's pipeline branches (draft, working, plan, and implementation branches), advance its lifecycle label to done, and close its lifecycle issue with a written completion summary. When a specification's draft pull request is closed without being merged (a rejection), delete the draft branch, remove the specification's lifecycle stage and identity labels, and comment on the lifecycle issue that the specification was rejected. Until now every lifecycle has been closed by hand; this stage closes that gap so a merged or rejected specification tears itself down automatically."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A merged specification closes its own lifecycle automatically (Priority: P1)

A human has reviewed a specification's final pull request and merged it into the main line. Without anyone doing it by hand, the pipeline tears the specification down: it deletes the specification's pipeline branches, advances the lifecycle label to the done state, and closes the lifecycle issue with a short written completion summary of what the merged feature delivered. The maintainer who was following the lifecycle issue sees it close itself with a legible record, instead of having to remember to delete branches, relabel, and close the issue manually.

**Why this priority**: This is the stage that ends a specification's life cleanly. Until now every lifecycle has been closed by hand, and lifecycles have been left stranded open at the review stage even after their final pull request merged. Automating this teardown is the entire point of the stage — it removes the last standing manual step in the pipeline and keeps the branch list and issue tracker honest about what is still in flight.

**Independent Test**: Merge a specification's final pull request from its persistent working branch into the main line and verify that the specification's pipeline branches are deleted, the lifecycle label advances to the done state, and the lifecycle issue is closed carrying a completion summary — all with no human performing the branch deletion, relabeling, summary, or issue-closing steps.

**Acceptance Scenarios**:

1. **Given** a specification's final pull request from its persistent working branch to the main line, **When** that pull request is merged, **Then** the specification's pipeline branches (draft, persistent working, plan, and implementation branches) are deleted.
2. **Given** the final pull request has merged, **When** the stage runs, **Then** the lifecycle label is advanced to the done state, replacing the previous stage label.
3. **Given** the final pull request has merged, **When** the stage runs, **Then** the lifecycle issue is closed with a written completion summary of what the merged feature delivered.

---

### User Story 2 - A rejected draft specification is torn down cleanly (Priority: P2)

A maintainer decides a specification should not proceed and closes its draft specification pull request without merging it. The pipeline treats this as a rejection: it deletes the draft branch, removes the specification's lifecycle stage and identity labels, and comments on the lifecycle issue that the specification was rejected. The repository is left without an orphaned draft branch or a specification carrying stage labels it no longer earns, and the lifecycle issue carries a clear record of why it stopped.

**Why this priority**: Rejection is the other way a specification's life ends, and it should be as tidy as a successful merge. Leaving a rejected draft's branch and labels behind clutters the repository and misrepresents the specification's state to anyone reading the issue tracker. This is second to the merge path only because most specifications are expected to proceed, not be rejected.

**Independent Test**: Close a specification's draft specification pull request without merging it and verify that the draft branch is deleted, the specification's stage and identity labels are removed, and a rejection comment is posted to the lifecycle issue.

**Acceptance Scenarios**:

1. **Given** a specification's draft specification pull request, **When** it is closed without being merged, **Then** the draft branch is deleted.
2. **Given** the draft specification pull request is closed unmerged, **When** the stage runs, **Then** the specification's lifecycle stage and identity labels are removed.
3. **Given** the draft specification pull request is closed unmerged, **When** the stage runs, **Then** a comment stating the specification was rejected is posted to the lifecycle issue.

---

### User Story 3 - The stage acts only on the pull requests it owns, and never fails on already-clean state (Priority: P3)

The stage reacts to pull-request-close events across the repository, but it only acts when the closed pull request is one it owns — a specification's final or draft pipeline pull request — and it identifies which specification is involved from the pull request itself rather than guessing. When some of the teardown work is already done (for example, a branch was auto-deleted on merge, or an event is delivered twice), the stage completes without error and without duplicating comments, so its behavior is safe to run automatically on every close event.

**Why this priority**: A teardown stage that fired on the wrong pull request, guessed the wrong specification, or errored on already-deleted branches would be worse than the manual process it replaces. Correct scoping and idempotency are what make it safe to leave running unattended, but they are a robustness layer on top of the two core teardown behaviors.

**Independent Test**: Deliver close events for pull requests the stage does not own (and re-deliver an owned event) and verify that the stage takes no action on the unowned events, identifies the correct specification for the owned event, and completes owned teardown without error or duplication even when branches are already absent or the event repeats.

**Acceptance Scenarios**:

1. **Given** a closed pull request that is not one of this stage's pipeline pull requests (for example, an ordinary pull request, or one whose merge target is not the main line), **When** the close event is delivered, **Then** the stage takes no teardown action.
2. **Given** an owned pull request close event, **When** the stage runs, **Then** it identifies the specification and its lifecycle issue from the pull request rather than guessing.
3. **Given** one or more of the specification's branches are already absent, **When** the stage performs teardown, **Then** it completes successfully rather than failing on the missing branches.
4. **Given** the same owned close event is delivered more than once, **When** the stage runs again, **Then** it does not post a duplicate comment or otherwise repeat already-completed teardown.

---

### Edge Cases

- The closed pull request's head branch matches a pipeline branch naming convention but the pull request is not actually an owned pipeline pull request (for example, its merge target is not the main line): the stage must not perform teardown.
- The specification's persistent working branch is auto-deleted when the final pull request merges: the stage must treat the already-deleted branch as success, not as a failure.
- The closed pull request cannot be matched to a valid specification or lifecycle issue (its slug, identity label, or lifecycle record is missing or inconsistent): the stage must decline to act and record why rather than guessing which specification to tear down.
- A specification's final pull request is closed **without** being merged: this is a rejection of an already-built specification, which is distinct from the draft-rejection path — see FR-012 [NEEDS CLARIFICATION].
- A non-final pipeline pull request (a plan, tasks, or implementation-stage pull request) is closed and its head branch matches a pipeline prefix the trigger listens on — see FR-013 [NEEDS CLARIFICATION].
- The specification's lifecycle issue is already closed when a merge event arrives (for example, closed by hand earlier): closing it again is a no-op and must not error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST trigger on a pipeline pull request closing, and MUST determine from the closed pull request whether the case is a merged final pull request or an unmerged (rejected) draft specification pull request.
- **FR-002**: When a specification's final pull request (its persistent working branch merged into the main line) is merged, the system MUST delete that specification's pipeline branches — its draft specification branch, its persistent working branch, its plan branch, and its implementation branches.
- **FR-003**: On that merge, the system MUST advance the specification's lifecycle stage label to the done state, replacing whatever prior stage label was present.
- **FR-004**: On that merge, the system MUST close the specification's lifecycle issue.
- **FR-005**: When it closes the lifecycle issue, the system MUST include a written completion summary describing what the merged feature delivered.
- **FR-006**: When a specification's draft specification pull request is closed without being merged, the system MUST delete that specification's draft specification branch.
- **FR-007**: On that draft rejection, the system MUST remove the specification's lifecycle stage label and its lifecycle identity label.
- **FR-008**: On that draft rejection, the system MUST post a comment to the specification's lifecycle issue stating that the specification was rejected.
- **FR-009**: The system MUST identify the specification and its lifecycle issue from the closed pull request (for example, from its branch slug and the specification's identity label) rather than guessing; when it cannot make that match to a valid specification and lifecycle issue, it MUST decline to act and record why rather than tearing down an incorrect or nonexistent specification.
- **FR-010**: The system MUST NOT perform teardown when the closed pull request is not one of its owned pipeline pull requests (for example, an ordinary pull request, or one whose merge target is not the main line).
- **FR-011**: The system MUST behave idempotently: teardown steps whose result is already in place — a branch already absent, an issue already closed — MUST be treated as success, and a repeated close event MUST NOT produce a duplicate comment or repeat already-completed teardown.
- **FR-012**: When a specification's final pull request is closed **without** being merged (a rejection of an already-built specification, distinct from the draft-rejection path), the system MUST [NEEDS CLARIFICATION: is this case in scope for the cleanup stage, and if so what teardown applies — full teardown of all pipeline branches like the draft rejection, marking the specification stalled/rejected without deleting the persistent working branch, or leaving it untouched for a human? The architecture describes only "final merged" and "draft closed unmerged"; this case is undefined.].
- **FR-013**: When a non-final pipeline pull request (a plan, tasks, or implementation-stage pull request) closes and its head branch matches a prefix the stage's trigger listens on, the system MUST [NEEDS CLARIFICATION: does the cleanup stage act on these events at all, or are they entirely out of scope because each of those stages already handles its own pull-request-close outcome (e.g. marking the specification stalled)? If out of scope, the stage should no-op on them.].
- **FR-014**: For the draft-rejection path, after the rejection comment is posted, the system MUST [NEEDS CLARIFICATION: should the lifecycle issue be closed as well, or left open so the requester can revise and re-enter the pipeline? The architecture specifies only that a rejection comment is posted, not whether the issue is closed.].

### Key Entities

- **Pipeline pull request close event**: The signal that starts this stage — a pull request whose head branch follows a pipeline branch naming convention closing, carrying whether it was merged and what its merge target was.
- **Final pull request**: A specification's review pull request from its persistent working branch into the main line; its **merge** drives the successful-teardown path.
- **Draft specification pull request**: A specification's initial pull request from its draft branch into the main line; its **unmerged close** drives the rejection path.
- **Specification pipeline branches**: The set of branches a specification accumulates across the pipeline — its draft branch, its persistent working branch, its plan branch, and its implementation branches — which the successful-teardown path deletes.
- **Lifecycle issue**: The per-specification issue that every stage reports to; the successful path closes it with a completion summary, the rejection path comments on it.
- **Lifecycle labels**: The specification's stage label (its current pipeline stage) and identity label (which specification the issue belongs to); the successful path advances the stage label to done, the rejection path removes both.
- **Completion summary**: The short written account of what the merged feature delivered, attached to the lifecycle issue when it is closed on the successful path.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every specification whose final pull request is merged has its pipeline branches deleted, its lifecycle label advanced to the done state, and its lifecycle issue closed — with no human performing any of those steps.
- **SC-002**: A maintainer following only the lifecycle issue can see, from the issue closing with its completion summary, that the specification is complete — without inspecting the branch list or the merged pull request.
- **SC-003**: Every specification whose draft pull request is closed unmerged has its draft branch deleted, its stage and identity labels removed, and a rejection record on its lifecycle issue.
- **SC-004**: After the stage runs, the repository retains no pipeline branches and no specification-stage labels for any specification that has been merged or rejected.
- **SC-005**: The stage never performs teardown on a pull request it does not own, and never tears down a specification it cannot unambiguously identify.
- **SC-006**: The stage completes successfully on repeated or partially-applied teardown (already-deleted branches, already-closed issues, re-delivered events) without erroring or duplicating comments.

## Assumptions

- "Persistent working branch," "draft branch," "plan branch," "implementation branches," "the main line," "lifecycle issue," "lifecycle labels," and "final / draft pull request" refer to the same per-specification branches, primary integration branch, issue, labels, and pull requests established by the earlier pipeline stages; this stage introduces no new such concepts and only tears them down.
- The successful-teardown path is entered by a human merging the final pull request into the main line; the human merge is the hand-off from the finalize stage to this stage, and the finalize stage's own behavior is out of scope here.
- Composing the completion summary uses a cost-appropriate summarization capability consistent with the pipeline's model-tiering conventions (a lightweight model is sufficient — no heavier model is needed for a completion summary), and the stage runs with the least-privilege tool set it needs; these specifics are design concerns, not requirements of this specification.
- Specifications already in flight when this stage lands whose close events have already fired will still need one final manual teardown; only specifications closed after this stage is active tear themselves down. This backfill is an operational note, not a requirement of the stage.
- The stage reacts to pull-request-close events repository-wide and self-selects the ones it owns; it is expected to run and no-op harmlessly on unowned close events rather than being prevented from triggering.
- The stage neither merges nor approves anything; it acts only after a pull request has already been closed or merged by a human.
