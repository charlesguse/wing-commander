# Feature Specification: Board loop messages explain the line

**Feature Branch**: `spec-draft/130-board-messages-explain-line`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Board loop messages explain the line: the issue, why it matters, what the fix does and does not decide" (issue #1215, owner direction 2026-11-25, following a walk-through of the board loop's comments on #1202). The issue also put in scope a "fix, but needs one decision" route for a backlog line that needs one small decision; the owner split that route out on 2026-11-25 into the follow-up spec-proposal #1249, which depends on this feature's explanation renderer.

## Background

The board loop works Maintenance backlog lines (#889) into fix PRs. Its comments on those PRs say which step it reached but not what the work was about, and three kinds of message mislead the owner today:

- **A bare "No findings."** review comment. The line came from the backlog, so someone already judged it a finding; "No findings" does not say what was asked, what the review checked, or why nothing is open.
- **No explanation of the line.** Neither the PR body nor the first comment says what the issue is, why it is or might be a problem, or what the alternative would be.
- **Stale fixed wording.** Fixed-text messages state things that are not true for the run: a readiness comment that said the loop "never merges, approves, or enables auto-merge" while auto-merge was on (being removed by a separate quick fix), and a proof note that cites "the merged PR's own required checks" when main has no required checks (no branch protection, no rulesets, confirmed 2026-11-25).

**Named parts.** Two messages are built from named parts, and every requirement below uses these names:

- **Explanation parts** (the first comment, Story 1): *Line* (the backlog line, quoted), *Code* (the files, functions or gates concerned), *Issue*, *Why it matters*, *Options* (or "options follow"), *What this PR does*.
- **Review parts** (the review comment, Story 2): *Asked*, *Checked*, *Decided*, *Not decided*, *Open*.

## Clarifications

### Session 2026-11-25

- Q1: Review agent output form? → A: structured named parts (asked / checked / decided / not decided / open) in the review agent's result schema, with a gate that fails a comment missing any part (answered from the `wc_session_record.py` precedent, recorded 2026-11-24). → FR-008, Story 2.
- Q2: Where is a one-decision question posted and how is the answer picked up? → A: a comment on the Maintenance backlog issue (#889) against the line's `bl-` identifier; the owner answers by replying with that identifier and the chosen option. → FR-013, Story 4. *(Note: moved to the follow-up spec-proposal #1249 by the owner's 2026-11-25 split; FR-013 and Story 4 are no longer in this spec.)*
- Q3: Which surfaces do the message rules cover? → A: board-loop fix PRs only, for now. Lifecycle-review-gate rounds, pr-conversation and the watchdog may be added by a later spec; the named-parts schema and gate stay general enough for that but those surfaces are not built now. → FR-016, FR-008.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The first comment explains the line (Priority: P1)

The owner opens a board-loop fix PR and, from its first comment alone, learns what backlog line it addresses (quoted), what code it concerns, why that is or might be a problem, what the alternatives are, and which alternative this PR takes.

**Why this priority**: Without it the owner cannot judge any later message on the PR; every other story builds on knowing what the line was about.

**Independent Test**: Drive the board loop on one backlog line to a fix PR and read only the first loop-authored comment: it carries every explanation part (Line, Code, Issue, Why it matters, Options or "options follow", What this PR does), each filled or marked as a gap.

**Acceptance Scenarios**:

1. **Given** a backlog line selected by the board loop, **When** the loop opens its fix PR, **Then** the first loop-authored comment on that PR contains every explanation part: Line, Code, Issue, Why it matters, Options, What this PR does.
2. **Given** the loop has not yet worked out the alternatives when it opens the PR, **When** it posts the first comment, **Then** the comment says the options follow, and a later loop comment on the same PR lists them; readiness does not wait for it *(owner decision, 2026-11-28)*.
3. **Given** the example line bl-b9677278 (#1202), **When** the first comment is posted, **Then** it reads in the shape of the owner-reviewed draft: Issue (Gate 12 silently skips cross-repository `gh api` calls, writes included), Why it matters (the skip is silent and its reason doesn't say whether it was deliberate), Options ((a) documented deliberate skip, (b) check cross-repository writes), and What this PR does ((a), no behaviour change).
4. **Given** the loop cannot fill an explanation part (for example the line names no code), **When** it posts the first comment, **Then** that part carries gap text saying what is missing and why, and is never left out.
5. **Given** a backlog line or agent-written text that contains Markdown, HTML or a fence, **When** the first comment is posted, **Then** that text sits inside the repository's existing fencing for untrusted and agent text, and only the part labels and the loop's fixed text sit outside it.

---

### User Story 2 - The review comment reports against the line's own question (Priority: P1)

The owner reads the board loop's review comment and sees what was asked, what the review checked, what the fix does and does not decide, and why nothing is open or what is open. The comment never says a bare "No findings".

**Why this priority**: The bare "No findings" is the message the owner found most misleading; a clean review that does not say what it looked at gives the owner nothing to trust.

**Independent Test**: Run the loop's review step on a fix PR whose review returns no findings, and on one whose review returns findings; in both cases the posted comment contains the five review parts, and neither contains "No findings" as its whole verdict.

**Acceptance Scenarios**:

1. **Given** a review that returns no findings, **When** the loop posts the review comment, **Then** the comment names the line's identifier ("no open findings on the fix for bl-…") and contains: Asked, Checked, Decided (the option the fix takes), Not decided (what the fix leaves to the owner and how the owner would choose otherwise, e.g. by reverting), and Open (other candidates, or why nothing is open).
2. **Given** a review that returns findings, **When** the loop posts the review comment, **Then** the same five parts appear and the open findings are listed under Open.
3. **Given** a review agent output that lacks any of the five parts, **When** the loop renders the comment at posting time, **Then** the renderer puts gap text (for example "the review did not say what it checked") in place of the missing part; it never posts a comment with a part silently omitted.
4. **Given** the checked-in fixtures for the review schema and renderer, including one fixture with each part missing, **When** the registered `verify-*` gate runs in CI, **Then** it fails if any rendered fixture lacks a part, neither filled nor marked as a gap.

---

### User Story 3 - Fixed-text messages tell the truth about what happens next (Priority: P2)

Every fixed-text message the board loop posts (readiness, merge, proof, stand-down, hold notes) states what the loop will actually do next, given the auto-merge switch (`WING_COMMANDER_BOARD_AUTO_MERGE`), the kill switch, and the PR's class.

**Why this priority**: A false statement in a fixed message is repeated on every PR until someone notices; it erodes trust in all the loop's messages.

**Independent Test**: For each combination of auto-merge on/off, kill switch engaged/not, and each PR class the loop distinguishes, render each fixed-text message and check that every claim about next actions and about main's protections matches that configuration.

**Acceptance Scenarios**:

1. **Given** auto-merge is on and the PR's class is one the loop merges, **When** the readiness comment is posted, **Then** it says the loop will merge once the merge gate holds (or that it has merged), and does not say it never merges.
2. **Given** auto-merge is off, or the PR's class requires the owner, **When** the readiness comment is posted, **Then** it says the PR waits for a human merge and why.
3. **Given** main has no required checks, **When** a proof note explains why a change needs no re-drive, **Then** it does not cite "required checks"; it cites the checks that actually ran on the merged PR's head.
4. **Given** the kill switch is engaged, **When** any message about next steps is posted, **Then** it says the loop is stopped and does not promise a next step.

---

### Edge Cases

- A backlog line with no named code (a prose-only defect): the first comment says no code location was named and what the loop searched.
- A backlog line that is ticked as resolved without a PR (duplicate, already fixed on main): no first-comment-on-PR applies; the existing disposition note still explains why the line is closed.
- The review step fails or times out: the loop posts that the review did not complete, not a review comment, and never a "no findings" wording.
- A very long explanation (many code locations, long evidence): the length rule (see FR-018) applies.

## Requirements *(mandatory)*

### Functional Requirements

**Explaining the line**

- **FR-001**: The first loop-authored comment on every board-loop fix PR MUST carry the explanation parts as named parts: Line (the backlog line, verbatim) and Code (file and, where the line names one, function or gate).
- **FR-001a**: A board-loop fix PR born from an open issue rather than a backlog line treats that issue as its Line: the Line part carries the issue's title and `#N` (rendered under FR-003a's fencing rule), and `#N` is the identifier wherever a requirement names the line's `bl-` id. Every requirement and success criterion here applies to issue-born and line-born fix PRs alike. The board loop's Spec Kit bump PRs are out of scope: they carry the updater's verification record instead. *(Owner, spec review round 3, 2026-11-25.)*
- **FR-002**: That comment MUST carry Issue (what the issue is) and Why it matters (why it is or might be a problem).
- **FR-003**: That comment MUST carry What this PR does (which option it takes) and Options: either the alternatives ("what might be expected otherwise") or "options follow"; when they follow, a later loop comment on the same PR lists them, and readiness does not wait for it *(owner decision, 2026-11-28)*.
- **FR-003a**: When the loop cannot fill an explanation part, it MUST put gap text saying what is missing in that part's place rather than omit the part. The Line text and every agent-written part MUST be rendered under the repository's existing fencing rule for untrusted and agent text (the board loop's fenced sections, issue #580); only the part labels and the loop's fixed text sit outside the fences. *(Spec review round 1, 2026-11-25.)*
- **FR-004**: The PR body MUST carry a short summary of the same explanation (the issue in one sentence and what the PR does) and point at the first comment for the full explanation. The summary is agent-written text: it MUST be rendered under the same fencing as FR-003a, and it is subject to spec 121's closing-keyword refusal for the PR body, so a summary that carries a closing keyword (for example "fixes #N") is refused like any other PR-body text. *(Default for the issue's open question 1; see Assumptions. Fencing and closing-keyword rule: spec review round 2, 2026-11-25.)*

**Review comment**

- **FR-005**: The loop's review comment MUST contain the five review parts: Asked (in the line's own terms), Checked (what the review checked), Decided (what the fix decides), Not decided (what it leaves to the owner, and how the owner would choose a different option), and Open (what is open, or why nothing is open).
- **FR-006**: The review comment MUST name the line's backlog identifier and MUST NOT consist of, or reduce to, a bare "No findings" verdict.
- **FR-007**: At posting time, when the review output lacks one of the five parts, the renderer MUST put gap text in that part's place rather than omit the part; the loop MUST never post a review comment with a part missing. The same untrusted-text fencing as FR-003a applies to agent-written parts.
- **FR-008**: The review agent's output MUST be structured with the five review parts in the review agent's result schema. A registered `verify-*` gate MUST exercise the schema and the renderer against checked-in fixtures, including one fixture with each part missing, and MUST fail when a rendered fixture lacks any part (neither filled nor marked as a gap). The gate checks fixtures in CI, never a posted comment; the posting-time refusal is FR-007's. The schema and the gate MUST be defined independently of the board loop, so that a later spec can apply them to other surfaces (see FR-016) without reworking them. *(Answered from the precedent of `wc_session_record.py`, which refuses to build a record with a named part missing, 2026-11-24; confirmed by the owner 2026-11-25, Q1 option A.)*
- **FR-008a**: The review parts are a rendering layer over the review result, not a second review record. They map onto spec 127's review record: Asked to its purpose source (127 FR-006); Checked, Decided and Not decided to its purpose answers (127 FR-008); Open to its open findings. A later move of the board review onto spec 127's shared reviewer keeps the parts unchanged and fills them from that record. Spec 127's FR-005 still holds: this feature changes only the board review job's output schema and comment, and does not move that job onto the shared reviewer. *(Spec review round 1, 2026-11-25.)*

**Truthful fixed text**

- **FR-009**: Every fixed-text message the board loop posts MUST describe what the loop will actually do next given the auto-merge switch, the kill switch, and the PR's class; no fixed sentence may assert a next action that one of those configurations contradicts.
- **FR-010**: No fixed-text message may assert a repository protection (required checks, branch protection, rulesets) that the repository does not have; the proof note's "merged PR's own required checks" wording MUST be replaced with a description of what actually ran.
- **FR-011**: The set of fixed-text messages and the configurations they depend on MUST be enumerable so that each message can be checked against each configuration.

**Scope, length and backlog record**

- **FR-016**: These message rules MUST apply to the board loop's own messages only: its fix PRs and its line records on the Maintenance backlog issue (FR-017). Lifecycle-review-gate rounds, pr-conversation replies and watchdog comments are out of scope for this feature and MUST NOT be changed by it; the owner may extend the rules to them in a later spec, which is why FR-008's schema and gate stay surface-independent. The one-decision question on #889 and its Board status entry belong to the follow-up spec-proposal #1249, not to this feature. *(Clarified 2026-11-25, Q3 option A, owner's choice "for now"; narrowed by the owner's 2026-11-25 split.)*
- **FR-017**: When the loop ticks a backlog line as fixed, the ticked line MUST carry a one-line record of what was decided and a link to the explaining comment, so #889 keeps the "why". *(Default for the issue's open question 4.)*
- **FR-018**: Each explaining or review comment MUST lead with its labelled parts (fenced as FR-003a requires) in a section that fits on one screen; supporting evidence beyond that (long quotes, file lists, logs) MUST go in a collapsed `<details>` section rather than be cut. *(Default for the issue's open question 5.)*

### Key Entities

- **Backlog line**: a checklist line on the Maintenance backlog issue, with a stable identifier (`bl-…`), text, and tick state; source of every board-loop fix.
- **Explanation**: the explanation parts (Line, Code, Issue, Why it matters, Options, What this PR does), each filled or marked as a gap — attached to one backlog line and one fix PR.
- **Review report**: the review parts (Asked, Checked, Decided, Not decided, Open), each filled or marked as a gap — attached to one review pass of one fix PR; a rendering layer over the review result (FR-008a).
- **Fixed-text message**: a loop message whose wording is fixed in code, with the switch and PR-class conditions under which each variant is posted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On 100% of board-loop fix PRs opened after the change, the first loop-authored comment carries every explanation part, each filled or marked as a gap.
- **SC-002**: Zero board-loop review comments after the change consist of a bare "No findings"; 100% contain the five review parts of FR-005.
- **SC-003**: For every combination of auto-merge switch, kill switch and PR class, every fixed-text message's claims about next steps and repository protections match that combination (checked by enumeration, zero mismatches).
- **SC-005**: The owner can tell, from a board-loop PR's comments alone and without opening the backlog or the code, what the line asked and what the PR chose — confirmed on the #1202 example against the owner-reviewed draft.

## Assumptions

- **Explanation location (open question 1)**: defaulted to both — the full explanation in the first comment (the owner's stated requirement) and a short summary in the PR body pointing at it, so the PR stays readable from the PR list.
- **Backlog record (open question 4)**: defaulted to yes, a one-line "decided" note with a link on the ticked line; it is cheap and keeps #889 self-explaining.
- **Length (open question 5)**: defaulted to a one-screen lead with a collapsed `<details>` for evidence, matching conventions already used in the repository's comments.
- The removal of the "never merges, approves, or enables auto-merge" sentence is being done by a separate quick fix; this spec covers the general rule (FR-009) and any remaining instances, not that one edit.
- Main has no required checks, branch protection or rulesets (confirmed by the owner 2026-11-25); the truthfulness rule applies to that state and to any later one.
- The board loop's existing switches (`WING_COMMANDER_BOARD_AUTO_MERGE`, the kill switch) and PR classes are unchanged by this feature; only the messages describing them change.
- Scope is board-loop fix PRs only (FR-016); extending the rules to lifecycle-review-gate rounds, pr-conversation and the watchdog is a possible later spec, decided once the owner has seen this one in use.
- The "fix, but needs one decision" route (formerly Story 4, FR-012–FR-015, FR-019–FR-022, SC-004) was split out by the owner on 2026-11-25 into the follow-up spec-proposal #1249, which reuses this feature's explanation renderer for its question; FR numbers here are not renumbered, so the gaps are deliberate.
- The owner-reviewed #1202 / bl-b9677278 draft in the issue is the reference shape for both the first comment and the review comment.
