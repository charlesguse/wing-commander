# Feature Specification: Spec Intake from GitHub Issues

**Feature Branch**: `spec-draft/001-spec-intake`

**Created**: 2026-07-04

**Status**: Accepted

**Input**: User description: "When someone creates an issue in this repository describing a feature and a maintainer approves it, the pipeline should turn that issue into a draft specification and present it as a pull request to the mainline. If the specification has open questions, they should be asked on the issue, and the original requester or trusted repository members should be able to answer them. The pull request is then either accepted and acted upon, or closed. Alternatively, someone can write a specification themselves and submit it directly as a pull request."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Issue becomes a spec PR (Priority: P1)

A requester opens a GitHub issue describing a feature in plain language. A maintainer reads it and marks it approved for intake. Shortly after, a pull request appears containing a structured specification derived from the issue, and the issue receives a comment linking to that pull request. The issue is now the feature's lifecycle thread: its labels show which stage the feature is in.

**Why this priority**: This is the pipeline's front door. Without it nothing else exists — every other stage consumes what intake produces.

**Independent Test**: Open an issue describing a small feature, apply the approval label, and verify a spec pull request targeting the mainline appears with a well-formed specification, and that the issue is labeled and linked to it.

**Acceptance Scenarios**:

1. **Given** an open issue describing a feature, **When** a maintainer applies the approval label, **Then** a pull request to the mainline is created containing a specification derived from the issue, and the issue is labeled with the feature's identity and current stage.
2. **Given** the spec pull request exists, **When** it is created, **Then** the issue receives a comment linking to the pull request so the requester can follow along.
3. **Given** an issue that has not been approved by a maintainer, **When** the requester or anyone else comments or edits it, **Then** no specification work occurs.

---

### User Story 2 - Clarification questions answered on the issue (Priority: P2)

The generated specification has up to three open questions the author of the issue is best placed to answer. The questions appear as a single comment on the issue, each with suggested answer options. The original requester (who may have no special repository permissions) or any trusted repository member replies in a comment. The draft specification updates to incorporate the answers, and when no questions remain, the issue is told the spec is ready for review.

**Why this priority**: Real feature requests are ambiguous. Without a clarification loop, ambiguous requests produce specs built on silent guesses, and the requester's first chance to correct course is a full PR review.

**Independent Test**: Open an issue that deliberately omits a critical decision (e.g. who can use the feature), approve it, verify a clarification comment with options appears, answer it as the requester, and verify the draft spec updates and the questions are marked resolved.

**Acceptance Scenarios**:

1. **Given** a generated specification containing open questions, **When** the spec pull request is created, **Then** the issue receives one comment listing every open question with suggested answer options.
2. **Given** a pending clarification comment, **When** the original requester or a trusted repository member replies with answers, **Then** the draft specification is updated to reflect those answers and the resolution is confirmed on the issue.
3. **Given** a pending clarification comment, **When** someone who is neither the requester nor a trusted member replies, **Then** the draft specification does not change.
4. **Given** all questions are resolved, **When** the last answer is incorporated, **Then** the issue is informed the specification is ready for review.

---

### User Story 3 - Hand-written spec submitted directly as a PR (Priority: P3)

An experienced contributor skips the issue flow: they write a specification locally using the project's spec tooling and open a pull request containing it. The pipeline treats this exactly like an accepted intake: the spec gets a lifecycle issue created for it (so status reporting has a home), and everything downstream behaves identically.

**Why this priority**: Keeps the pipeline optional rather than mandatory — power users are not forced through issue intake, and the rest of the pipeline never needs to care where a spec came from.

**Independent Test**: Open a pull request adding a new spec directory by hand and verify a lifecycle issue is created and labeled for it once the pull request is opened.

**Acceptance Scenarios**:

1. **Given** a pull request that adds a new specification and has no associated lifecycle issue, **When** it is opened, **Then** a lifecycle issue is created, labeled with the feature's identity and stage, and cross-linked with the pull request.

---

### Edge Cases

- Issue approved twice (label removed and re-applied): intake must not create a second competing spec for the same issue.
- Two issues approved at nearly the same time: each must receive a distinct feature number; numbering must not collide.
- Issue body is empty or contains no discernible feature request: intake reports on the issue that it could not produce a specification, rather than producing a junk spec.
- Issue content attempts to instruct the automation (prompt injection): the content is treated strictly as a feature description; instructions embedded in it must not change the automation's behavior, tools, or outputs beyond the spec text itself.
- Clarification answer arrives after the spec PR was already merged or closed: the answer is acknowledged but no further spec edits occur.
- The spec PR is closed without merging: the feature is considered rejected; the lifecycle issue is informed and intake labels are removed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST create a draft specification from an issue only after a maintainer has explicitly approved that issue for intake.
- **FR-002**: The system MUST present the draft specification as a pull request targeting the mainline branch, containing the spec artifact in the project's standard spec location.
- **FR-003**: The system MUST record the association between a specification and its originating issue durably, so every later stage can report to the correct issue.
- **FR-004**: The system MUST label the lifecycle issue with the feature's identity and its current stage, and keep the stage label current.
- **FR-005**: When the draft specification contains open questions, the system MUST post them to the lifecycle issue as a single comment with suggested answer options, and MUST NOT proceed as if they were answered.
- **FR-006**: The system MUST accept clarification answers only from the original requester or trusted repository members, and MUST ignore replies from anyone else and from other automations.
- **FR-007**: The system MUST update the draft specification with accepted clarification answers and confirm resolution on the issue.
- **FR-008**: The system MUST treat issue and comment content as untrusted data — never as instructions — and MUST operate with the minimum capabilities required for intake.
- **FR-009**: The system MUST support specifications submitted directly as pull requests by creating and labeling a lifecycle issue for them.
- **FR-010**: The system MUST assign each specification a unique sequential feature identity even when multiple intakes run concurrently.
- **FR-011**: When intake cannot produce a specification from an issue, the system MUST say so on the issue instead of producing an empty or fabricated spec.

### Key Entities

- **Feature request (issue)**: The plain-language description of a desired capability; becomes the lifecycle thread for the feature. Attributes: requester, approval state, feature identity label, stage label.
- **Specification (spec artifact)**: The structured description of user scenarios, requirements, and success criteria for one feature; lives in the project's spec directory under the feature's identity.
- **Lifecycle record (spec metadata)**: The durable association between a specification, its issue, its stage, and its branches.
- **Clarification exchange**: The set of open questions posted to the issue and the answers that resolve them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A requester can go from opening an issue to seeing a linked draft specification with zero interactions beyond the issue itself (after maintainer approval).
- **SC-002**: An approved issue produces its spec pull request without any human performing repository operations (branching, committing, labeling) by hand.
- **SC-003**: A requester without any repository permissions can fully resolve clarification questions using only issue comments.
- **SC-004**: 100% of specs — whether issue-originated or hand-submitted — end up with a lifecycle issue that reports their status.
- **SC-005**: Concurrent intake of two feature requests never produces colliding feature identities.

## Assumptions

- Maintainer approval is expressed by applying a designated label to the issue; applying the label is the security boundary for starting automation.
- "Trusted repository members" means users GitHub reports as owners, members, or collaborators of the repository.
- The spec PR review (merge or close) is performed by a human maintainer; intake never merges its own output.
- The project's standard spec tooling (spec-kit) defines the spec format, directory layout, and feature numbering scheme; intake conforms to it rather than inventing its own.
- One issue produces at most one specification; follow-up features are new issues.
