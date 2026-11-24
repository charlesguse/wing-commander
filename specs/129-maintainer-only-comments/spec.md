# Feature Specification: Comment-Triggered Stages Act Only on Maintainers

**Feature Branch**: `129-maintainer-only-comments`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Comment-triggered stages act only on maintainers. Implements constitution 3.0.0 (PR #1194): a comment-triggered stage acts on a comment only when its author is a maintainer (OWNER, MEMBER or COLLABORATOR) and never a bot; an issue's own author who is not a maintainer gets no exception."

## Context

Owner decision (2026-11-23): only maintainers steer comment-triggered stages. "Authorized" means `OWNER`, `MEMBER` or `COLLABORATOR`. A requester who is not a maintainer answers through one, and the owner relays their words when needed. Constitution 3.0.0 (PR #1194) states the rule in Principles IV and V, and this feature makes every surface match it.

Today an issue's own author is treated like a maintainer in four places, whatever their association:
- the clarify wrapper's actor gate;
- the Spec Kit updater's comment-reply gate;
- the shared comment trust filter that intake and the board loop read;
- the auto-release end-to-end test's clarify decision.

Several docs and live contracts describe that exception. Pipeline entry (the maintainer-applied `spec-request` label), pr-conversation (already maintainers-only, FR-019 of spec 033) and Principle X's board-loop entry (the maintainer's own authorship) are not changed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A non-maintainer's reply does not steer clarify (Priority: P1)

A lifecycle issue in `stage:spec` or `stage:clarify` was opened by someone who is not a maintainer. That author replies with answers to the clarification questions. No clarify run folds those answers into the draft spec. A maintainer's reply on the same issue still starts a clarify run.

**Why this priority**: This is the rule the constitution now states. It is the only path by which someone without maintainer access steers an agent run.

**Independent Test**: Post a reply from the issue's author with association `NONE`, and check that no clarify agent step runs. Post a reply from a maintainer, and check that clarify runs and folds it.

**Acceptance Scenarios**:

1. **Given** a lifecycle issue whose author has association `NONE` or `CONTRIBUTOR`, **When** that author comments, **Then** no clarify agent step runs and the draft spec is unchanged.
2. **Given** the same issue, **When** an `OWNER`, `MEMBER` or `COLLABORATOR` comments, **Then** clarify runs as it does today.
3. **Given** an issue opened by a maintainer, **When** that maintainer comments, **Then** clarify runs. Their association qualifies them, not their authorship.

---

### User Story 2 - Specs and board-loop work are built only from maintainers' comments (Priority: P2)

When intake drafts a spec, or a board-loop agent reads an issue's discussion, the comments passed to the agent are only those from non-bot maintainers. A comment from the issue's author who is not a maintainer is excluded and counted with the other excluded comments.

**Why this priority**: It applies the same rule to what an agent reads, not only to what starts a run.

**Independent Test**: Run the shared comment filter on an issue with comments from a maintainer, from the non-maintainer author, and from a bot. Only the maintainer's comment is passed on, and the excluded human count is 1.

**Acceptance Scenarios**:

1. **Given** an issue whose non-maintainer author commented, **When** intake runs, **Then** that comment is not in the agent's context. The "did not qualify" callout counts it and describes qualifying comments as "from a maintainer".
2. **Given** an issue with only maintainer comments, **When** intake or the board loop runs, **Then** the comments passed on are byte-identical to today's.

---

### User Story 3 - The Spec Kit updater's comment replies follow the same rule (Priority: P3)

A reply on the Spec Kit updater's tracking issue drives its comment-reply path only when the commenter is a maintainer.

**Why this priority**: It is the third comment-triggered wrapper. Its tracking issues are opened by the pipeline's own bot, so the exception is unused there in practice.

**Independent Test**: Run the comment-reply gate with an association of `NONE` and a commenter id equal to the issue author's id: the path does not run. Run it with `COLLABORATOR`: it runs.

**Acceptance Scenarios**:

1. **Given** a non-maintainer commenter whose id equals the issue author's id, **When** they reply, **Then** the comment-reply job does not run.
2. **Given** a caller that still passes `issue-author-id`, **When** the workflow is called, **Then** the call is accepted and the input has no effect.

---

### Edge Cases

- **A maintainer who opened the issue** qualifies through their association; nothing about authorship is consulted.
- **A bot comment** never qualifies, whoever the bot is, as today.
- **A requester whose association changes** (for example, they are added as a collaborator) qualifies from then on. Each comment is judged by its own association when the stage reads it.
- **An org member whose membership is private** may be reported with an association other than `MEMBER`. That member is treated as a non-maintainer. Making the membership public, or adding them as a collaborator, makes them qualify.
- **An adopter's existing wrapper that still carries the exception.** See FR-006.
- **The auto-release end-to-end test** posts its clarification answers with the maintainer token, so its verdict does not change.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The clarify wrapper's actor gate MUST start a clarify run for a comment only when its `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR` and its author is not a bot. It MUST have no clause that admits the issue's author.
- **FR-002**: The Spec Kit updater's comment-reply gate MUST admit a commenter only when their association is `OWNER`, `MEMBER` or `COLLABORATOR`.
  - The `issue-author-id` input MUST stay declared, so existing callers do not fail.
  - The input MUST be documented as ignored.
- **FR-003**: The shared comment trust filter MUST qualify a comment only when its author is not a bot and its association is `OWNER`, `MEMBER` or `COLLABORATOR`.
  - Every comment it does not qualify MUST be counted as excluded.
  - Its outputs and file formats are otherwise unchanged.
- **FR-004**: Intake's "did not qualify" callout MUST describe qualifying comments as "from a maintainer", with no mention of the original reporter.
- **FR-005**: The auto-release end-to-end clarify decision MUST apply the same rule as FR-001, so it asserts the shipped behaviour.
- **FR-006**: [NEEDS CLARIFICATION: Does the clarify stage itself (the published reusable workflow) also verify the triggering comment's association and stop when it is not a maintainer? That would make every adopter's copied wrapper, including one that still has the exception, obey the rule from the next release: a published behaviour change. Or is the wrapper the only gate, as today?]
- **FR-007**: [NEEDS CLARIFICATION: Must the clarify agent be unable to read other comments on the issue? Today its grant includes `gh issue view`, although its prompt says thread reads are not granted. The alternative is that only the triggering comment, already staged by the stage, reaches it.]
- **FR-008**: [NEEDS CLARIFICATION: When a non-maintainer comments on a lifecycle issue in `stage:spec` or `stage:clarify`, is the comment ignored silently, as the clarify wrapper and the Spec Kit updater do today? Or does the stage post a notice that only maintainers can direct it, as pr-conversation does (FR-019 of spec 033)?]
- **FR-009**: docs/adoption.md, docs/architecture.md and the live contracts MUST describe the maintainers-only rule. No live text may describe the issue-author exception as current behaviour. The live contracts are:
  - `specs/010-reusable-pipeline/contracts/stage-interfaces.md`;
  - `specs/029-intake-issue-comments/contracts/comment-trust-gate.md`;
  - the `specs/027-auto-update-spec-kit` workflow contract.

  Workflow comments that contrast pr-conversation with clarify and intake MUST be updated to match.
- **FR-010**: A gate MUST fail when any comment-triggered wrapper, stage, or the shared comment trust filter admits a comment through its author's identity rather than its association. The gate MUST fail on a mutant that reintroduces the exception.
- **FR-011**: Pipeline entry, pr-conversation's actor gate and Principle X's board-loop entry MUST NOT change.

### Key Entities

- **Comment author association**: GitHub's relation of a comment's author to the repository. Only `OWNER`, `MEMBER` and `COLLABORATOR` qualify.
- **Comment-triggered stage**: a stage started by a comment: clarify, the Spec Kit updater's comment reply, and pr-conversation.
- **Shared comment trust filter**: the one place that selects which issue comments an agent may read (intake, board loop).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a lifecycle run, the issue's non-maintainer author replying to clarification questions starts zero clarify agent steps, and a maintainer's reply starts one.
- **SC-002**: Zero comment-triggered wrappers, stages or comment filters admit a comment by author identity, as reported by the FR-010 gate on the shipped tree. The gate's mutant that reintroduces the exception fails.
- **SC-003**: On an issue where only maintainers commented, intake and the board loop pass the agent exactly the comments they passed before this change.
- **SC-004**: The auto-release end-to-end verification still passes its clarification step on its next scheduled run after merge.
- **SC-005**: Zero live docs or contracts describe the issue-author exception as current behaviour.

## Assumptions

- Constitution 3.0.0 (PR #1194) merges before this feature's pull request.
- GitHub reports `author_association` for every comment in the event payload and in the comments API, and the stages already read it.
- The Spec Kit updater's tracking issues are opened by the pipeline's bot, so FR-002 changes no outcome in practice.
- Requesters without maintainer access reach the owner through ordinary comments, which the owner relays.
