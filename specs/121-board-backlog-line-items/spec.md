# Feature Specification: Board Loop Works Maintenance Backlog Lines

**Feature Branch**: `spec-draft/121-board-backlog-line-items`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Board loop works Maintenance backlog lines, one unchecked #889 line per item (#1080). Problem: the board loop (`board-loop.yml`) works open defect issues on its own through triage, route, fix, review and readiness, and under spec 115 merges them too. But CLAUDE.md keeps small defects out of issues: stages, reviews and the watchdog record each one as a checklist line on the Maintenance backlog, the open `disposition:tracking` issue titled 'Maintenance backlog' (#889). `board_eligibility.is_excluded()` skips every `disposition:*` issue, so the loop never touches those lines; about 140 were open on 2026-10-22 and move only when a local session takes a batch by hand. Proposal: let the board loop take one unchecked Maintenance backlog line as its work item when no eligible issue is waiting, using the same pipeline and safety checks as an issue. Each tick would select one unchecked line by a deterministic order, skipping lines already claimed or held; give the line a stable identity that survives edits to the rest of the issue (a content hash, or a short id the loop writes into the line when it claims it); work it by treating the line's text as the issue body for triage, route, fix, review and readiness, with board state kept on #889 or another surface clarify should choose; mark progress on the line (in progress while held by the loop, ticked with '(fixed by #PR)' when the fix merges, the same reason a `board:stalled` issue would get when held); route spec-shaped lines to a `spec-proposal` that the line points at; and edit #889 only by read-modify-write that tolerates its other writers (local sessions, stage findings). Questions for clarify: line identity; order (oldest first, priority marker, or the 'Before enabling …' lines first); where the board item marker for a line lives; whether lines are taken only when the issue queue is empty or interleaved; how a line that cites several files or bundles two defects is handled. Dependencies: most useful once the App has the Workflows permission and `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS=true`; merging without a human also needs `WING_COMMANDER_BOARD_AUTO_MERGE`, after the 'Before enabling' lines on #889 are fixed. Requested by the owner on 2026-10-22 as option (a) of three; the others were a scheduled session routine and splitting the backlog lines into issues."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An idle board loop fixes one backlog line (Priority: P1)

The board loop runs, finds no eligible issue waiting, and instead takes one unchecked line from the Maintenance backlog. It claims the line (the line visibly shows the loop holds it), triages the line's text against current `main`, routes it as fix-shaped, opens a fix PR, gets an independent review to zero open findings, and reaches readiness exactly as it would for an issue. When the fix PR merges — by the loop under `WING_COMMANDER_BOARD_AUTO_MERGE`, or by a human — the line is ticked and reads "(fixed by #PR)". The Maintenance backlog issue itself stays open throughout.

**Why this priority**: This is the whole point — about 140 lines move today only when a local session works them by hand. One line fixed end to end without the owner is the MVP.

**Independent Test**: With an empty eligible-issue queue and one unchecked, fix-shaped line on the backlog, let the loop run until the PR merges; observe the line was marked in progress during the work, is ticked with "(fixed by #PR)" afterwards, the PR did not close the backlog issue, and no other line on the issue changed.

**Acceptance Scenarios**:

1. **Given** no eligible issue is waiting and the backlog has at least one unchecked, unclaimed, unheld line, **When** the loop selects its work item, **Then** it takes exactly one line chosen by the deterministic order (FR-004), marks it in progress on the backlog, and records its board state against that line's identity.
2. **Given** an eligible issue is waiting, **When** the loop selects its work item, **Then** it takes the issue, not a backlog line.
3. **Given** a claimed line whose fix PR merged, **When** the loop next observes it, **Then** the line is ticked and carries "(fixed by #PR)", and the backlog issue remains open.
4. **Given** a line the loop holds, **When** a fix PR is opened for it, **Then** the PR body names the line (its identity and text) and the backlog issue as a reference that does not close the issue.

---

### User Story 2 - A line that is already fixed, or needs a design decision, is cleared without a fix PR (Priority: P2)

Triage reads the line against current `main`. When the defect is already fixed, the loop ticks the line with the evidence it read (the fixing commit) instead of opening a PR. When route finds the line spec-shaped (it needs the owner to decide a trade-off, spans several stages, or would benefit from clarify's questions), the loop files a `spec-proposal` as it already does for issues, and the line points at that proposal and is no longer selected.

**Why this priority**: Many old lines are stale or design-shaped; clearing them honestly is half the value and keeps the loop from repeatedly selecting a line it can never fix.

**Independent Test**: Seed one line describing a defect whose fix is already on `main` and one design-shaped line; run the loop twice; observe the first ticked with the fixing commit quoted and the second annotated with a link to a new `spec-proposal`, both now skipped by selection.

**Acceptance Scenarios**:

1. **Given** a claimed line whose defect deterministic triage evidence shows is already fixed on `main`, **When** triage completes, **Then** the line is ticked with that evidence and no PR is opened.
2. **Given** a claimed line route classifies as spec-shaped, **When** route completes, **Then** a `spec-proposal` issue is filed (never `spec-request`), the line is annotated with a pointer to it, the line is not ticked, and selection skips it from then on.

---

### User Story 3 - A line the loop cannot finish is held with a reason (Priority: P2)

When the loop cannot finish a line — it touches a workflow file the loop's credential cannot push, the fix breaches the size-and-path backstop, review does not converge, or any other reason a `board:stalled` issue would be held — the line is annotated as held with the same reason text, released from in progress, and skipped by selection until a maintainer clears the hold.

**Why this priority**: Without a visible hold, a stuck line would either be retried every run (burning the shared usage window) or silently abandoned.

**Independent Test**: Seed a line whose fix must touch `.github/workflows/` while `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` is off; run the loop; observe the line annotated as held with the workflow-permission reason and not selected on the next run.

**Acceptance Scenarios**:

1. **Given** a claimed line that hits any hold condition an issue would be held for, **When** the loop holds it, **Then** the line carries the same reason a `board:stalled` issue would carry and is skipped by selection.
2. **Given** a held line whose hold annotation a maintainer removes, **When** the loop next selects, **Then** the line is eligible again.

---

### User Story 4 - Concurrent writers to the backlog never lose each other's edits (Priority: P1)

The backlog issue has other writers: local sessions add and tick lines, and the stage-findings composite appends lines. Every edit the loop makes to the backlog changes only the one line it is working on, re-reads the current body immediately before writing, and if the body changed in between, re-applies its one-line change to the newer body rather than overwriting it.

**Why this priority**: A lost edit on #889 silently deletes recorded defects — worse than the loop doing nothing. This is a precondition for enabling the feature at all.

**Independent Test**: Between the loop's read and its write, append a new line and tick an unrelated line on the backlog; observe that after the loop's edit both concurrent changes are still present and only the loop's line changed in the loop's own edit.

**Acceptance Scenarios**:

1. **Given** another writer changes the backlog between the loop's read and write, **When** the loop writes, **Then** the other writer's change survives and the loop's one-line change is applied to the newer body.
2. **Given** the loop's line was deleted or rewritten beyond recognition by another writer, **When** the loop tries to update it, **Then** it does not write a line back, stands down from that item, and reports the loss on the backlog issue.
3. **Given** concurrent edits keep defeating the write after a bounded number of retries, **When** retries are exhausted, **Then** the loop leaves the body unchanged and reports the failure loudly rather than forcing the write.

---

### Edge Cases

- A line is ticked by a human while the loop holds it: the loop stands down from that line at its next re-derivation, leaves any open fix PR for a maintainer, and says so.
- A line's text is edited by a human while the loop holds it: its identity (FR-003) still matches; the loop continues from the line's current text only at its next triage, never mid-fix.
- Two lines with identical text: each has a distinct identity, and only one is claimed per run.
- A line bundles two defects or cites several files: worked as one item while its fix fits the size-and-path backstop; a fix that breaches the backstop holds the line with the backstop reason, and route may classify a line whose parts need different decisions as spec-shaped.
- A fix PR for a line must never carry a closing keyword for the backlog issue; merging it must never close the backlog issue.
- The backlog issue is closed, renamed, loses `disposition:tracking`, or a second open issue carries the same title: the loop takes no line and reports why (no guessing which issue is the backlog).
- The backlog body is empty or has no unchecked lines: the loop is idle, as today.
- Lines inside a fenced code block, quoted text, or prose that merely looks like a checkbox are not work items; only top-level checklist lines in the issue body are.
- Comments on the backlog issue are never a source of lines, whoever wrote them.
- The board loop kill switch (`WING_COMMANDER_BOARD_LOOP_PAUSED`) is set: no line is claimed or edited.
- A line's text contains instruction-like content aimed at an AI: it is treated as defect description data only.
- A line that a waiver register cites through the backlog issue number: ticking a line never closes the backlog issue, so gate 124's open-tracker check is unaffected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The board loop MUST take a Maintenance backlog line as its work item only when no eligible issue is waiting; while any eligible issue is waiting, issues take precedence. *(Default from the proposal's "when no eligible issue is waiting"; interleaving is out of scope.)*
- **FR-002**: The loop MUST identify the Maintenance backlog by deterministic signals — exactly one open issue carrying `disposition:tracking` and titled "Maintenance backlog", authored by a maintainer or the pipeline's own App — and MUST take no line when that resolution is ambiguous or fails.
- **FR-003**: Each line MUST have a stable identity that survives edits to every other line of the issue and distinguishes lines with identical text, by [NEEDS CLARIFICATION: line identity — a content hash of the line text, or a short id the loop writes into the line when it claims it?].
- **FR-004**: Line selection MUST be deterministic over the issue body as read and MUST skip lines that are ticked, claimed, held, or routed to a `spec-proposal`, choosing among the rest by [NEEDS CLARIFICATION: order — oldest (topmost/first-appended) first, an explicit priority marker, or the "Before enabling …" lines first?].
- **FR-005**: Only top-level unchecked checklist lines in the backlog issue's body MUST be candidates; comments, quoted text and fenced blocks MUST NOT be.
- **FR-006**: The loop MUST work at most one line per run, under the same global concurrency group, kill switch and one-item-at-a-time rule as issues, and a held line MUST count as the loop's current item exactly as a claimed issue does.
- **FR-007**: A line MUST pass through the same triage, route, fix, review, readiness and (under spec 115) merge steps, with the same deterministic gates, backstop and authorization checks as an issue, with the line's text in the role of the issue body.
- **FR-008**: The line's text MUST be framed as untrusted defect-description data in every agent prompt, never as instructions.
- **FR-009**: The loop's board state for a line (the board item marker and its re-derivation inputs) MUST be keyed by the line's identity and stored on [NEEDS CLARIFICATION: where the board item marker for a line lives — a loop-authored comment on the backlog issue, a dedicated loop-owned board-state issue, or another surface?], and every field MUST be re-derived from live state before any durable action, as for issues.
- **FR-010**: While the loop holds a line, the line MUST visibly show it is in progress (and by which fix PR once one exists).
- **FR-011**: When the line's fix PR merges, the line MUST be ticked and carry "(fixed by #PR)".
- **FR-012**: When triage finds the defect already fixed on evidence deterministic code read, the line MUST be ticked with that evidence quoted, and no PR opened.
- **FR-013**: When route classifies a line as spec-shaped, the loop MUST file a `spec-proposal` (never apply `spec-request`), annotate the line with a pointer to it, leave the line unticked, and skip it in later selection.
- **FR-014**: When the loop holds a line for any reason a `board:stalled` issue would be held, the line MUST carry that same reason and be skipped by selection until a maintainer removes the hold annotation.
- **FR-015**: Every edit the loop makes to the backlog body MUST be a read-modify-write that changes only the one line it works, re-reads the body immediately before writing, re-applies its change to any newer body, and preserves every other writer's concurrent change; after a bounded number of conflicting attempts it MUST leave the body unchanged and report the failure.
- **FR-016**: If the worked line is ticked, deleted, or no longer matches its identity, the loop MUST stand down from it without writing it back and report this on the backlog issue.
- **FR-017**: A fix PR for a line MUST reference the backlog issue without a closing keyword, and no step of this feature may close, relabel or retitle the backlog issue.
- **FR-018**: Board status and run reporting that today names the current issue MUST name the current line (backlog issue plus line identity) when a line is the work item.
- **FR-019**: Each new branch — selection, skip conditions, the read-modify-write conflict path, the stand-down path, the ambiguous-backlog path, and every line annotation — MUST be covered by a checked-in fixture a gate exercises.
- **FR-020**: With the backlog empty of candidate lines, or the feature's lines unreachable, the loop's behaviour MUST be exactly today's.

### Key Entities

- **Maintenance backlog**: The single open `disposition:tracking` issue titled "Maintenance backlog" (#889 at the 2026-10-01 reset). Never closed or relabelled by this feature.
- **Backlog line**: One top-level checklist line in the backlog body. Attributes: identity, text, state (unchecked, in progress, held with reason, routed to a proposal, ticked with fix or evidence).
- **Line identity**: The stable key that names one line across edits to the rest of the body (FR-003).
- **Line board state**: The board item marker and progress for a line, keyed by its identity (FR-009).
- **Line annotation**: The visible text the loop adds to a line to show in-progress, held (with reason), routed (with proposal link), or fixed (with PR or evidence).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With no eligible issue waiting and at least one candidate line, every board-loop run that has capacity takes a line — the backlog moves without a local session.
- **SC-002**: 100% of lines the loop finishes end in exactly one visible terminal state on the line: ticked with "(fixed by #PR)", ticked with already-fixed evidence, pointing at a `spec-proposal`, or held with a reason.
- **SC-003**: 0 concurrent edits by other writers are lost across the loop's backlog edits, demonstrated by a fixture that interleaves a concurrent write.
- **SC-004**: 0 runs in which the loop works a line while an eligible issue was waiting.
- **SC-005**: The backlog issue is never closed, relabelled or retitled by the loop, and no merged line fix closes it.
- **SC-006**: Over the first 30 days enabled, the count of open backlog lines falls, with no line selected again after reaching a terminal state.

## Assumptions

- Lines are taken only when the issue queue is empty (FR-001) — the proposal's own wording; interleaving is a later decision.
- A bundled or multi-file line is worked as one item bounded by the existing size-and-path backstop; it is not split by the loop.
- Authorization: lines come only from the body of a backlog issue a maintainer or the App authored; GitHub restricts editing an issue body to its author and collaborators with write access, so every body line was written by a maintainer, a collaborator, or the pipeline. Whether constitution Principle X's entry rule ("an issue a maintainer authored or labeled") already covers a line on such an issue, or needs a clarifying amendment, is for plan to confirm; an amendment would be its own human-merged PR.
- Workflow-touching line fixes stay held under the existing `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` rule until the App gets the Workflows permission; autonomous merge stays governed by `WING_COMMANDER_BOARD_AUTO_MERGE` (spec 115). Neither switch is changed here.
- Existing triage evidence rules (API 429, upstream action bump, fixing commit on `main`), route classification, the independent review, the readiness evaluation and the prove-after-merge entry (spec 096) are reused unchanged.
- The Roadmap issue's "Proposed" list is updated for a line-born `spec-proposal` the same way it is for an issue-born one.
- No new opt-in switch is added; the feature runs whenever the board loop runs. If plan finds a separate switch is needed for safe rollout, it should mirror the `WING_COMMANDER_BOARD_*` family and default to off.
