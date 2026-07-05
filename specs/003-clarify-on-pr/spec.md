# Feature Specification: Clarification Replies on the Draft Spec Pull Request

**Feature Branch**: `spec-draft/003-clarify-on-pr`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Today, replies to clarification questions are only picked up when they're posted on the feature's lifecycle issue. Comments on the draft spec pull request itself are ignored, even though the PR is where a reviewer is actually looking when a question occurs to them — reviewers naturally comment there and get silence. I want the clarification loop to also listen on open draft spec pull requests. When the original requester or a trusted repository member comments on a draft spec PR while the spec has open clarification questions, the pipeline should fold their answers into the draft exactly as it does for issue replies, and confirm what was resolved. A few expectations: the same people who can answer on the issue can answer on the PR (original requester or trusted members); bot comments never trigger anything; the pipeline should figure out which spec the PR belongs to from the PR itself, without the commenter having to name it; the lifecycle issue remains the single source of truth for status, so answers given on the PR should still be reflected there; replies that don't actually answer an open question get a polite pointer to what's still open, wherever they were posted; general questions on the PR that aren't clarification answers are out of scope."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reviewer answers a clarification question on the draft spec PR (Priority: P1)

A maintainer is reviewing the draft specification pull request and notices one of the open clarification questions while reading the diff. Instead of switching over to the lifecycle issue, they reply right there in the pull request's conversation. The draft specification updates to reflect their answer, exactly as if they had replied on the issue, and both the pull request and the lifecycle issue show that the question was resolved.

**Why this priority**: This is the core gap the request is closing — reviewers naturally comment where they're already looking (the PR), and today that reply is silently dropped, stalling the spec until someone thinks to repeat themselves on the issue.

**Independent Test**: Open a draft spec PR with an open clarification question, comment an answer on the PR (not the issue) as the original requester or a trusted member, and verify the draft spec is updated, the PR shows confirmation, and the lifecycle issue also reflects the resolution.

**Acceptance Scenarios**:

1. **Given** a draft spec pull request with open clarification questions, **When** the original requester or a trusted repository member comments an answer on the pull request, **Then** the draft specification is updated to reflect that answer and the pull request receives a confirmation of what was resolved.
2. **Given** a clarification answer was accepted from a pull request comment, **When** the update completes, **Then** the lifecycle issue also shows that the question was resolved, so someone following only the issue is not left behind.
3. **Given** a pull request comment that answers all remaining open questions, **When** the update completes, **Then** both the pull request and the lifecycle issue indicate the specification is ready for review.

---

### User Story 2 - Untrusted or automated comments are ignored (Priority: P2)

Someone with no special standing on the repository, or another automation, posts a comment on the draft spec pull request. Nothing happens to the draft specification — the pipeline only acts on replies from the original requester or a trusted repository member, and never reacts to a bot's comment, matching the trust rules already in place for the lifecycle issue.

**Why this priority**: Without this boundary, listening on the pull request would open a second, less-guarded door into editing the draft — the same risk the issue-based loop was already built to close off.

**Independent Test**: Comment on a draft spec PR with open questions as a user who is neither the original requester nor a trusted repository member (and separately as a bot account), and verify the draft specification is unchanged in both cases.

**Acceptance Scenarios**:

1. **Given** a draft spec pull request with open clarification questions, **When** someone who is neither the original requester nor a trusted repository member comments on it, **Then** the draft specification does not change.
2. **Given** a draft spec pull request with open clarification questions, **When** a bot account comments on it, **Then** the draft specification does not change.

---

### User Story 3 - Reply doesn't actually answer an open question (Priority: P3)

A trusted commenter replies on the draft spec pull request, but their comment is a side remark or an ambiguous response that doesn't map to any open clarification question. Rather than silently ignoring it or misreading it as an answer, the pipeline politely points back to whatever questions are still open, posted in the same place the comment arrived.

**Why this priority**: Keeps the loop trustworthy — a commenter who wasn't actually answering shouldn't have their words guessed at, and shouldn't be met with silence that looks identical to "nothing happened."

**Independent Test**: Comment something on a draft spec PR that doesn't address any open clarification question (as a trusted commenter), and verify the draft specification is unchanged and a reply on the pull request restates the still-open questions.

**Acceptance Scenarios**:

1. **Given** a draft spec pull request with open clarification questions, **When** a trusted commenter replies with something that does not answer any open question, **Then** the draft specification does not change and a reply on the pull request restates the open questions.
2. **Given** a draft spec pull request with no open clarification questions, **When** a trusted commenter leaves an unrelated comment, **Then** the pipeline does not treat it as a clarification exchange at all.

---

### Edge Cases

- A comment on the draft spec pull request is general discussion or review feedback unrelated to any clarification question (e.g. line-level style feedback): the pipeline leaves it alone rather than treating every PR comment as a clarification attempt.
- The same clarification question is answered on the issue and, moments later, differently on the pull request: the pipeline processes replies in the order they arrive and the draft reflects the most recently accepted answer; later confirmations note that the answer was updated.
- A pull request comment arrives after the draft spec pull request has already been merged or closed: the reply is acknowledged but no further spec edits occur, matching how a late issue reply is already handled.
- The pull request that received the comment cannot be matched to a spec with open clarification questions (e.g. it isn't a draft spec PR, or the association is missing or inconsistent): the pipeline takes no action on that comment.
- A trusted commenter answers only some of the open questions in one pull request comment: the questions they addressed are resolved and the remaining ones are restated as still open, the same partial-resolution behavior already supported for issue replies.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept clarification answers posted as comments on an open draft spec pull request, in addition to comments on the lifecycle issue.
- **FR-002**: The system MUST determine which specification a pull request comment belongs to from the pull request itself, without requiring the commenter to name the spec or issue.
- **FR-003**: The system MUST accept pull request clarification comments only from the original requester or a trusted repository member, using the same trust rule already applied to issue replies, and MUST ignore comments from any other user and from bot accounts.
- **FR-004**: The system MUST only treat a pull request comment as a clarification exchange while that pull request is an open draft spec pull request with unresolved clarification questions; comments on any other pull request, or on a draft spec pull request with no open questions, MUST NOT be treated as clarification answers.
- **FR-005**: When a pull request comment answers one or more open clarification questions, the system MUST update the draft specification the same way an accepted issue reply does, and MUST confirm on the pull request which questions were resolved.
- **FR-006**: When a clarification question is resolved from a pull request comment, the system MUST also reflect that resolution on the feature's lifecycle issue, so the issue remains an accurate, complete record of status regardless of where the answer was given.
- **FR-007**: When a pull request comment does not answer any open clarification question, the system MUST leave the draft specification unchanged and MUST reply on the pull request restating the questions that remain open.
- **FR-008**: The system MUST treat pull request comment content as untrusted data — never as instructions — applying the same handling already required for issue comments.
- **FR-009**: The system MUST NOT treat general discussion, review feedback, or questions on a draft spec pull request as clarification answers unless they actually address an open clarification question.

### Key Entities

- **Draft spec pull request**: The open pull request presenting a generated specification for review; now a second surface (alongside the lifecycle issue) where clarification answers can be accepted.
- **Clarification exchange**: The set of open questions and the answers that resolve them; now sourced from either the lifecycle issue or the draft spec pull request, with the issue always kept current regardless of source.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can resolve an open clarification question entirely from the draft spec pull request, without needing to visit the lifecycle issue.
- **SC-002**: 100% of clarification questions resolved via a pull request comment are also visible as resolved on the lifecycle issue, with no manual follow-up required.
- **SC-003**: Comments from users without the required standing, or from bots, never alter the draft specification, matching the existing guarantee for issue replies.
- **SC-004**: A pull request comment that fails to answer any open question always receives a pointer to what remains open, rather than being silently dropped.

## Assumptions

- "Trusted repository member" and "original requester" carry the same meaning here as in the existing issue-based clarification loop: a maintainer/collaborator, or the person who filed the lifecycle issue.
- Only the draft spec pull request (the intake stage's PR) is in scope for this feature; clarification-style comments on plan, tasks, or later-stage pull requests are out of scope.
- A pull request's general conversation comments (not inline code-review comments on specific lines) are the surface being listened to; a reviewer wanting to answer a clarification question posts a normal comment on the pull request's conversation.
- The lifecycle issue continues to be where clarification questions are first posted; this feature only adds a second place answers can arrive, it does not change where questions are asked.
