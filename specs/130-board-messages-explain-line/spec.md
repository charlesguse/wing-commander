# Feature Specification: Board loop messages explain the line

**Feature Branch**: `spec-draft/130-board-messages-explain-line`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Board loop messages explain the line: the issue, why it matters, what the fix does and does not decide" (issue #1215, owner direction 2026-11-25, following a walk-through of the board loop's comments on #1202). Also in scope: a backlog line that needs one small decision gets a "fix, but needs one decision" route instead of a spec-proposal.

## Background

The board loop works Maintenance backlog lines (#889) into fix PRs. Its comments on those PRs say which step it reached but not what the work was about, and three kinds of message mislead the owner today:

- **A bare "No findings."** review comment. The line came from the backlog, so someone already judged it a finding; "No findings" does not say what was asked, what the review checked, or why nothing is open.
- **No explanation of the line.** Neither the PR body nor the first comment says what the issue is, why it is or might be a problem, or what the alternative would be.
- **Stale fixed wording.** Fixed-text messages state things that are not true for the run: a readiness comment that said the loop "never merges, approves, or enables auto-merge" while auto-merge was on (being removed by a separate quick fix), and a proof note that cites "the merged PR's own required checks" when main has no required checks (no branch protection, no rulesets, confirmed 2026-11-25).

Separately, the route agent cannot ask the owner anything, so a backlog line that needs even one small decision is filed as a `spec-proposal` (`reason=agent_proposed_spec`). On 2026-11-24 six lines went this way (#1174, #1185, #1204, #1209, #1210, #1211); four were small choices an owner's session would have settled under CLAUDE.md "Deciding without the owner", and the owner had them handled as fix PRs instead.

## Clarifications

### Session 2026-11-25

- Q1: Review agent output form? → A: structured named parts (asked / checked / decided / not decided / open) in the review agent's result schema, with a gate that fails a comment missing any part (answered from the `wc_session_record.py` precedent, recorded 2026-11-24). → FR-008, Story 2.
- Q2: Where is a one-decision question posted and how is the answer picked up? → A: a comment on the Maintenance backlog issue (#889) against the line's `bl-` identifier; the owner answers by replying with that identifier and the chosen option. → FR-013, Story 4.
- Q3: Which surfaces do the message rules cover? → A: board-loop fix PRs only, for now. Lifecycle-review-gate rounds, pr-conversation and the watchdog may be added by a later spec; the named-parts schema and gate stay general enough for that but those surfaces are not built now. → FR-016, FR-008.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The first comment explains the line (Priority: P1)

The owner opens a board-loop fix PR and, from its first comment alone, learns what backlog line it addresses (quoted), what code it concerns, why that is or might be a problem, what the alternatives are, and which alternative this PR takes.

**Why this priority**: Without it the owner cannot judge any later message on the PR; every other story builds on knowing what the line was about.

**Independent Test**: Drive the board loop on one backlog line to a fix PR and read only the first loop-authored comment: it quotes the line, names the code, states the problem, lists at least one alternative (or says alternatives follow in a later comment), and states which option the PR takes.

**Acceptance Scenarios**:

1. **Given** a backlog line selected by the board loop, **When** the loop opens its fix PR, **Then** the first loop-authored comment on that PR contains the backlog line quoted verbatim, the file(s) or function(s) concerned, a "why it might be a problem" statement, and a "what this PR does" statement.
2. **Given** the loop has not yet worked out the alternatives when it opens the PR, **When** it posts the first comment, **Then** the comment says the options follow, and a later loop comment on the same PR lists them before the PR is reported ready.
3. **Given** the example line bl-b9677278 (#1202), **When** the first comment is posted, **Then** it reads in the shape of the owner-reviewed draft: the issue (Gate 12 silently skips cross-repository `gh api` calls, writes included), why it might be a problem (the skip is silent and its reason doesn't say whether it was deliberate), the options ((a) documented deliberate skip, (b) check cross-repository writes), and what this PR does ((a), no behaviour change).

---

### User Story 2 - The review comment reports against the line's own question (Priority: P1)

The owner reads the board loop's review comment and sees what was asked, what the review checked, what the fix does and does not decide, and why nothing is open or what is open. The comment never says a bare "No findings".

**Why this priority**: The bare "No findings" is the message the owner found most misleading; a clean review that does not say what it looked at gives the owner nothing to trust.

**Independent Test**: Run the loop's review step on a fix PR whose review returns no findings, and on one whose review returns findings; in both cases the posted comment contains the four parts, and neither contains "No findings" as its whole verdict.

**Acceptance Scenarios**:

1. **Given** a review that returns no findings, **When** the loop posts the review comment, **Then** the comment names the line's identifier ("no open findings on the fix for bl-…") and contains: Asked, Checked, Not decided (what the fix leaves to the owner and how the owner would choose otherwise, e.g. by reverting), and Other candidates / open items.
2. **Given** a review that returns findings, **When** the loop posts the review comment, **Then** the same four parts appear and the open findings are listed under the open part.
3. **Given** a review agent output that lacks any of the four parts, **When** the loop would post it, **Then** the loop does not post a comment missing a part; it records the gap (for example "the review did not say what it checked") in place of the missing part rather than omitting it silently.
4. **Given** a review comment in which any named part is absent (neither filled nor marked as a gap), **When** the gate runs, **Then** the gate fails.

---

### User Story 3 - Fixed-text messages tell the truth about what happens next (Priority: P2)

Every fixed-text message the board loop posts (readiness, merge, proof, stand-down, hold notes) states what the loop will actually do next, given the auto-merge switch (`WING_COMMANDER_BOARD_AUTO_MERGE`), the kill switch, and the PR's class.

**Why this priority**: A false statement in a fixed message is repeated on every PR until someone notices; it erodes trust in all the loop's messages.

**Independent Test**: For each combination of auto-merge on/off, kill switch engaged/not, and each PR class the loop distinguishes, render each fixed-text message and check that every claim about next actions and about main's protections matches that configuration.

**Acceptance Scenarios**:

1. **Given** auto-merge is on and the PR's class is one the loop merges, **When** the readiness comment is posted, **Then** it says the loop will merge (or has enabled merge) and does not say it never merges.
2. **Given** auto-merge is off, or the PR's class requires the owner, **When** the readiness comment is posted, **Then** it says the PR waits for a human merge and why.
3. **Given** main has no required checks, **When** a proof note explains why a change needs no re-drive, **Then** it does not cite "required checks"; it cites the checks that actually ran on the merged PR's head.
4. **Given** the kill switch is engaged, **When** any message about next steps is posted, **Then** it says the loop is stopped and does not promise a next step.

---

### User Story 4 - A line needing one small decision is fixed, not turned into a spec (Priority: P2)

When a backlog line needs one small owner decision but is otherwise fix-shaped, the route step chooses "fix, but needs one decision" instead of filing a `spec-proposal`. The loop posts the question with its options, evidence and a recommendation in the explaining form of Story 1, holds the line until the owner answers, then fixes it per the answer.

**Why this priority**: Four of six spec-proposals on 2026-11-24 were of this kind; each costs a full spec lifecycle for an hour of fix work.

**Independent Test**: Feed the route step a backlog line whose only open point is one reversible choice; confirm it is routed as "needs one decision", that the question is posted with options/evidence/recommendation, that the line is not worked while unanswered, and that after an answer is recorded the loop produces a fix PR implementing the chosen option.

**Acceptance Scenarios**:

1. **Given** a backlog line that is deterministic except for one choice, **When** the route step runs, **Then** it records the outcome "fix, but needs one decision" and files no `spec-proposal`.
2. **Given** a line routed as needing one decision, **When** the loop posts its question, **Then** the question is a comment on the Maintenance backlog issue (#889) naming the line's `bl-` identifier and contains the quoted line, the issue, why it matters, two or more options with their implications, the evidence, and a recommendation.
3. **Given** the question is unanswered, **When** later loop cycles run, **Then** the line is held (not fixed, not re-asked, not re-routed to a spec).
4. **Given** the owner replies on #889 with the line's `bl-` identifier and a chosen option, **When** the next loop cycle runs, **Then** the loop picks up the answer, fixes the line per the chosen option, and the fix PR's first comment cites the question and the answer.
5. **Given** a line that is spec-shaped by CLAUDE.md's routing rule (a design trade-off across several stages, or work that needs clarify's questions), **When** the route step runs, **Then** it still files a `spec-proposal`.

---

### Edge Cases

- A backlog line with no named code (a prose-only defect): the first comment says no code location was named and what the loop searched.
- A backlog line that is ticked as resolved without a PR (duplicate, already fixed on main): no first-comment-on-PR applies; the existing disposition note still explains why the line is closed.
- The review step fails or times out: the loop posts that the review did not complete, not a review comment, and never a "no findings" wording.
- The owner answers a one-decision question with an option not offered ("Custom"): the loop fixes per the custom answer if it is fix-shaped, otherwise records that the answer makes the line spec-shaped and files a `spec-proposal` citing the answer.
- The owner never answers: the held line is listed among items waiting on the owner (Board status) rather than silently aging.
- Two backlog lines need the same decision: each question is posted separately unless the loop can cite the other; one answer must not silently apply to a line it was not asked about.
- A very long explanation (many code locations, long evidence): the length rule (see FR-018) applies.

## Requirements *(mandatory)*

### Functional Requirements

**Explaining the line**

- **FR-001**: The first loop-authored comment on every board-loop fix PR MUST quote the backlog line verbatim and name the code it concerns (file and, where the line names one, function or gate).
- **FR-002**: That comment MUST state what the issue is and why it is or might be a problem.
- **FR-003**: That comment MUST state what this PR does among the alternatives, and MUST either list the alternatives ("what might be expected otherwise") or say they follow; when they follow, a later loop comment on the same PR MUST list them before the loop reports the PR ready.
- **FR-004**: The PR body MUST carry a short summary of the same explanation (the issue in one sentence and what the PR does) and point at the first comment for the full explanation. *(Default for the issue's open question 1; see Assumptions.)*

**Review comment**

- **FR-005**: The loop's review comment MUST contain four parts: what was asked (in the line's own terms), what the review checked, what the fix does and does not decide (including how the owner would choose a different option), and what is open or why nothing is open.
- **FR-006**: The review comment MUST name the line's backlog identifier and MUST NOT consist of, or reduce to, a bare "No findings" verdict.
- **FR-007**: When the review output lacks one of the four parts, the loop MUST state the gap in that part's place rather than omit the part.
- **FR-008**: The review agent's output MUST be structured with named parts (asked / checked / decided / not decided / open) in the review agent's result schema, and a gate MUST fail a review comment that is missing any part. The schema and the gate MUST be defined independently of the board loop, so that a later spec can apply them to other surfaces (see FR-016) without reworking them. *(Clarified 2026-11-24, Q1 option A, from the precedent of `wc_session_record.py`, which refuses to build a record with a named part missing.)*

**Truthful fixed text**

- **FR-009**: Every fixed-text message the board loop posts MUST describe what the loop will actually do next given the auto-merge switch, the kill switch, and the PR's class; no fixed sentence may assert a next action that one of those configurations contradicts.
- **FR-010**: No fixed-text message may assert a repository protection (required checks, branch protection, rulesets) that the repository does not have; the proof note's "merged PR's own required checks" wording MUST be replaced with a description of what actually ran.
- **FR-011**: The set of fixed-text messages and the configurations they depend on MUST be enumerable so that each message can be checked against each configuration.

**One-decision route**

- **FR-012**: The route step MUST offer an outcome "fix, but needs one decision" for a line that is fix-shaped except for one reversible choice; only lines that are spec-shaped by CLAUDE.md's routing rule MAY be routed to `spec-proposal`.
- **FR-013**: For a line on that route, the loop MUST post one question containing the quoted line, the issue, why it matters, the options with implications, the evidence and a recommendation, and MUST hold the line until an answer is recorded. The question MUST be posted as a comment on the Maintenance backlog issue (#889) naming the line's `bl-` identifier; the owner answers by replying on that issue with the same identifier and the chosen option, and the loop recognises an answer by that identifier and picks it up on its next cycle. *(Clarified 2026-11-25, Q2 option A, owner's choice.)*
- **FR-014**: A held line MUST appear among the items waiting on the owner in the Board status report until answered.
- **FR-015**: After an answer is recorded, the loop MUST fix the line per the chosen option, and the fix PR's first comment MUST cite the question and the answer.

**Scope, length and backlog record**

- **FR-016**: These message rules MUST apply to board-loop fix PRs only. Lifecycle-review-gate rounds, pr-conversation replies and watchdog comments are out of scope for this feature and MUST NOT be changed by it; the owner may extend the rules to them in a later spec, which is why FR-008's schema and gate stay surface-independent. *(Clarified 2026-11-25, Q3 option A, owner's choice "for now".)*
- **FR-017**: When the loop ticks a backlog line as fixed, the ticked line MUST carry a one-line record of what was decided and a link to the explaining comment, so #889 keeps the "why". *(Default for the issue's open question 4.)*
- **FR-018**: Each explaining or review comment MUST lead with its parts in plain text that fits on one screen; supporting evidence beyond that (long quotes, file lists, logs) MUST go in a collapsed `<details>` section rather than be cut. *(Default for the issue's open question 5.)*

### Key Entities

- **Backlog line**: a checklist line on the Maintenance backlog issue, with a stable identifier (`bl-…`), text, and tick state; source of every board-loop fix.
- **Explanation**: the issue, why it matters, the options, and what the PR does — attached to one backlog line and one fix PR.
- **Review report**: asked, checked, decided / not decided, open — attached to one review pass of one fix PR.
- **Fixed-text message**: a loop message whose wording is fixed in code, with the switch and PR-class conditions under which each variant is posted.
- **One-decision question**: the question, options, evidence and recommendation for a held line, posted as a comment on #889 naming the line's `bl-` identifier, and the owner's reply on #889 carrying that identifier and the chosen option.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On 100% of board-loop fix PRs opened after the change, the first loop-authored comment quotes the backlog line and states the issue, why it matters, and what the PR does.
- **SC-002**: Zero board-loop review comments after the change consist of a bare "No findings"; 100% contain the four parts of FR-005.
- **SC-003**: For every combination of auto-merge switch, kill switch and PR class, every fixed-text message's claims about next steps and repository protections match that combination (checked by enumeration, zero mismatches).
- **SC-004**: Of backlog lines whose only open point is one reversible choice, none are routed to `spec-proposal`; replaying the four 2026-11-24 small-choice lines through the route step yields "fix, but needs one decision" for each.
- **SC-005**: The owner can tell, from a board-loop PR's comments alone and without opening the backlog or the code, what the line asked and what the PR chose — confirmed on the #1202 example against the owner-reviewed draft.

## Assumptions

- **Explanation location (open question 1)**: defaulted to both — the full explanation in the first comment (the owner's stated requirement) and a short summary in the PR body pointing at it, so the PR stays readable from the PR list.
- **Backlog record (open question 4)**: defaulted to yes, a one-line "decided" note with a link on the ticked line; it is cheap and keeps #889 self-explaining.
- **Length (open question 5)**: defaulted to a one-screen lead with a collapsed `<details>` for evidence, matching conventions already used in the repository's comments.
- The removal of the "never merges, approves, or enables auto-merge" sentence is being done by a separate quick fix; this spec covers the general rule (FR-009) and any remaining instances, not that one edit.
- Main has no required checks, branch protection or rulesets (confirmed by the owner 2026-11-25); the truthfulness rule applies to that state and to any later one.
- The board loop's existing switches (`WING_COMMANDER_BOARD_AUTO_MERGE`, the kill switch) and PR classes are unchanged by this feature; only the messages describing them change.
- "Deciding without the owner" in CLAUDE.md addresses the owner's own sessions, not the board loop; this feature does not let the loop decide the choice itself — it asks and waits.
- Scope is board-loop fix PRs only (FR-016); extending the rules to lifecycle-review-gate rounds, pr-conversation and the watchdog is a possible later spec, decided once the owner has seen this one in use.
- The owner-reviewed #1202 / bl-b9677278 draft in the issue is the reference shape for both the first comment and the review comment.
