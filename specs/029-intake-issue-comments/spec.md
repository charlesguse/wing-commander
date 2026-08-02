# Feature Specification: Include Follow-Up Comments in Intake Specification

**Feature Branch**: `029-intake-issue-comments`

**Created**: 2026-08-02

**Status**: Draft

**Input**: User description: "Intake specifies an issue from its title and body only. Every follow-up comment on the issue — analysis that narrows the problem, rules out approaches, or records constraints discovered after filing — is invisible to the stage. A maintainer who applies the entry-gate label to a well-discussed issue silently gets a spec built from the original, least-informed version of the request. The current workaround is to hand-rewrite the body to fold the comments back in before labeling; that is manual, easy to forget, and destroys the distinction between the original report and what was later learned. Make intake take the discussion into account. The crux: comment authorship is not gated the way the label is — anyone can comment on a public issue, so naively feeding every comment to intake would let a non-maintainer place content into a spec the maintainer believes they approved by reading the body. Prior art exists in the clarify stage: an author gate (only OWNER/MEMBER/COLLABORATOR or the issue author, never a bot) and an untrusted-data-to-file pattern (comment bodies fetched from the API and written to a file, never shell-interpolated, never pasted into the prompt)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A discussed issue is specified from what the discussion settled on (Priority: P1)

A maintainer files or receives an issue, then works through it in the comments — narrowing the problem, ruling out a proposed direction after investigating it, and recording a constraint discovered only after filing. When the discussion has finally settled what the work is, the maintainer applies the entry-gate label. The maintainer expects the resulting specification to reflect what the discussion concluded, not the original, least-informed version of the request captured in the body.

**Why this priority**: This is the core value of the feature. The entry gate is a deliberate human decision made at a moment of the maintainer's choosing — often long after filing, precisely *because* discussion has settled the work. The longer and more productive the discussion, the more a body-only spec diverges from reality, and the more the maintainer must fall back on the manual body-rewrite workaround. Making intake read the settled discussion delivers value on its own.

**Independent Test**: Take an issue whose comments rule out a direction that the body proposes, add a constraint in a later comment, then run intake. Confirm the specification excludes the ruled-out direction and includes the later constraint — without anyone having edited the body first.

**Acceptance Scenarios**:

1. **Given** an issue whose body lists a possible direction and a later qualifying comment that rules that direction out, **When** intake specifies the issue, **Then** the specification does not scope in the ruled-out direction.
2. **Given** an issue whose body omits a constraint that a later qualifying comment establishes, **When** intake specifies the issue, **Then** the specification reflects that constraint.
3. **Given** an issue with no follow-up comments, **When** intake specifies the issue, **Then** the specification is produced from the title and body exactly as it is today.

---

### User Story 2 - The entry-gate label keeps gating what it appears to gate (Priority: P1)

The entry-gate label is a maintainer-only approval. Anyone can comment on a public issue. A maintainer approving an issue for specification must be able to trust that the specification is built only from content that a person with approval authority stands behind — not from arbitrary comments left by anyone who happened to pass by.

**Why this priority**: This is the crux of the feature and the reason a naive "feed all comments" approach is unsafe. If ungated comment content could reach the specification, the label would no longer gate what it appears to gate: a non-maintainer could place content into a spec the maintainer believes they approved by reading the body. Getting the trust boundary right is as important as reading the comments at all — hence also P1.

**Independent Test**: Add a substantive comment from a user who is neither a maintainer (OWNER/MEMBER/COLLABORATOR) nor the original issue author, then run intake. Confirm that comment's content does not appear in or influence the specification.

**Acceptance Scenarios**:

1. **Given** a comment from a user whose association does not qualify under the trust gate, **When** intake specifies the issue, **Then** that comment's content is not incorporated into the specification.
2. **Given** a comment authored by a bot (for example a pipeline stage or the watchdog commenting on the lifecycle issue), **When** intake specifies the issue, **Then** that comment is excluded regardless of the bot's association.
3. **Given** an issue where every substantive comment comes from qualifying authors, **When** intake specifies the issue, **Then** those comments are incorporated.

---

### User Story 3 - Comment text is treated as untrusted data, not instructions (Priority: P2)

Comments — even from maintainers — may contain text that looks like instructions to an AI, tool requests, or attempts to change the stage's behavior. Intake's existing security posture already frames the issue body as untrusted user data; comments must get the same framing so that no comment can cause intake to run a command, fetch a URL, or edit a file.

**Why this priority**: The feature widens intake's input surface from one maintainer-authored body to a discussion thread. That is only safe if the new input is handled with the same discipline as the existing input. It is a required property of the feature rather than the feature's headline value, so P2.

**Independent Test**: Add a qualifying comment whose body contains text phrased as instructions to an AI (for example, a request to run a command or fetch a URL). Run intake and confirm the text is specified as part of the feature description where relevant, and that no command was run, URL fetched, or file edited because the comment asked.

**Acceptance Scenarios**:

1. **Given** a qualifying comment containing text resembling instructions to an AI, **When** intake specifies the issue, **Then** the text is treated only as content to be specified, and no side effect it requests is performed.
2. **Given** any comment body, **When** intake ingests it, **Then** the body is handled as data (not shell-interpolated and not pasted into the prompt as trusted instructions).

---

### Edge Cases

- **No comments**: intake behaves exactly as it does today (body-only).
- **Only bot comments**: all excluded; intake is body-only.
- **Mixed authorship**: qualifying comments are incorporated; non-qualifying and bot comments are ignored, in the same pass.
- **A comment contradicts the body**: intake surfaces the conflict as a [NEEDS CLARIFICATION] marker rather than silently picking a side (see FR-006).
- **A very long discussion thread**: the composite input can be far larger than a single body; the specification must still respect the maximum-3 clarification-marker cap.
- **Substantive comments exist but are all excluded by the trust gate**: the maintainer should not silently believe the discussion was used (see FR-008).
- **Edited comments or an edited body**: only current text is available; edit history is not fetched (see Assumptions).
- **Low-signal qualifying comments** (for example "+1" or "thanks"): incorporated as description text but contribute nothing actionable, which is acceptable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Intake MUST retrieve the follow-up comments on the lifecycle issue in addition to its title, body, and author.
- **FR-002**: Intake MUST incorporate a comment into the feature description only when the comment's author association qualifies under the stage's trust gate. The qualifying authors are those with an OWNER, MEMBER, or COLLABORATOR association, plus the original issue author — matching the clarify stage's author gate.
- **FR-003**: Intake MUST exclude comments authored by bots, regardless of the bot account's association (pipeline stages and the watchdog comment on lifecycle issues, and none of that is feature description).
- **FR-004**: Intake MUST treat every ingested comment body as untrusted user data — it MUST NOT execute, shell-interpolate, or paste comment text into the prompt as trusted instructions; comment bodies MUST be handled as data (for example fetched from the API and staged to a data file), mirroring the clarify stage's untrusted-comment handling.
- **FR-005**: Intake MUST assemble the feature description from the issue body together with the qualifying comments, so that the specification reflects the full settled discussion rather than the body alone.
- **FR-006**: When a qualifying comment conflicts with the issue body (or with an earlier comment), intake MUST surface the conflict as a [NEEDS CLARIFICATION] marker in the generated specification rather than silently picking a side, subject to the three-marker cap.
- **FR-007**: When no qualifying comments exist, intake MUST produce the same specification it produces today from the title and body alone.
- **FR-008**: When substantive comments exist on the issue but none qualify for incorporation (excluded by the trust gate or as bots), intake MUST make that visible rather than silent — for example, a note on the lifecycle issue that non-qualifying comments were not used and the body may need updating first. This visible notice is in scope for this feature.
- **FR-009**: The entry-gate label's meaning MUST be preserved: no content originating from a non-qualifying author may influence a specification that a maintainer approved by applying the label.

### Key Entities *(include if feature involves data)*

- **Lifecycle issue**: the GitHub issue carrying the request; has a title, body, original author, and an ordered set of comments.
- **Comment**: a single follow-up on the issue; carries its author, the author's association to the repository, whether the author is a bot, a creation time (for ordering/precedence), and a body of untrusted text.
- **Feature description**: the composite input handed to the specification skill, derived from the body plus the qualifying comments.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an issue whose qualifying comments rule out a direction the body proposes, the generated specification contains zero requirements that scope in the ruled-out direction.
- **SC-002**: Maintainers can label a well-discussed issue for specification without first hand-editing the body, and the specification still reflects the discussion — eliminating the manual body-rewrite workaround.
- **SC-003**: Content originating from non-qualifying authors (non-gated users and bots) appears in 0% of generated specifications.
- **SC-004**: For issues with no qualifying comments, the generated specification is equivalent to the one produced under the previous body-only behavior.
- **SC-005**: No comment can cause intake to run a command, fetch a URL, or edit a file — 100% of side-effect-shaped comment text is treated as data only.

## Assumptions

- **Bot exclusion is a fixed default**: comments from bot accounts are never feature description (the watchdog and the pipeline's own stages comment on lifecycle issues), so they are excluded outright rather than being subject to the trust-scope clarification.
- **Comment ordering**: comments are ordered by creation time, and "later" for any precedence purpose means later creation time.
- **Edit history is out of scope**: both comments and the body may carry an edit history that is not fetched; only current text is used. This matches the issue's own framing of edit history as a possibly-separate defect.
- **Existing permissions suffice**: the stage's tool allowlist already permits requesting comments, so this is a prompt/behavior change, not a permissions change.
- **Reuse of clarify's patterns**: the author gate and the untrusted-comment-to-data-file handling are modeled on the existing clarify stage rather than invented anew.
- **The three-marker cap still applies**: even when the input is an entire discussion thread, the specification respects the maximum of three [NEEDS CLARIFICATION] markers; excess ambiguity is resolved with documented informed guesses.
