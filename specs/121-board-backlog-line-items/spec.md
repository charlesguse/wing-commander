# Feature Specification: Board Loop Works Maintenance Backlog Lines

**Feature Branch**: `spec-draft/121-board-backlog-line-items`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Board loop works Maintenance backlog lines, one unchecked #889 line per item (#1080). Problem: the board loop (`board-loop.yml`) works open defect issues on its own through triage, route, fix, review and readiness, and under spec 115 merges them too. But CLAUDE.md keeps small defects out of issues: stages, reviews and the watchdog record each one as a checklist line on the Maintenance backlog, the open `disposition:tracking` issue titled 'Maintenance backlog' (#889). `board_eligibility.is_excluded()` skips every `disposition:*` issue, so the loop never touches those lines; about 140 were open on 2026-10-22 and move only when a local session takes a batch by hand. Proposal: let the board loop take one unchecked Maintenance backlog line as its work item when no eligible issue is waiting, using the same pipeline and safety checks as an issue. Each tick would select one unchecked line by a deterministic order, skipping lines already claimed or held; give the line a stable identity that survives edits to the rest of the issue (a content hash, or a short id the loop writes into the line when it claims it); work it by treating the line's text as the issue body for triage, route, fix, review and readiness, with board state kept on #889 or another surface clarify should choose; mark progress on the line (in progress while held by the loop, ticked with '(fixed by #PR)' when the fix merges, the same reason a `board:stalled` issue would get when held); route spec-shaped lines to a `spec-proposal` that the line points at; and edit #889 only by read-modify-write that tolerates its other writers (local sessions, stage findings). Questions for clarify: line identity; order (oldest first, priority marker, or the 'Before enabling …' lines first); where the board item marker for a line lives; whether lines are taken only when the issue queue is empty or interleaved; how a line that cites several files or bundles two defects is handled. Dependencies: most useful once the App has the Workflows permission and `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS=true`; merging without a human also needs `WING_COMMANDER_BOARD_AUTO_MERGE`, after the 'Before enabling' lines on #889 are fixed. Requested by the owner on 2026-10-22 as option (a) of three; the others were a scheduled session routine and splitting the backlog lines into issues."

## Clarifications

### Session 2026-11-06

- Q: Line identity — a content hash of the line text, or a short id the loop writes into the line when it claims it? → A: A short id the loop writes into the line on claim; it survives edits to the line's text and keeps identical lines apart; the claim costs one read-modify-write; unclaimed lines carry no id (FR-003).
- Q: Selection order — oldest first, an explicit priority marker, or the "Before enabling …" lines first? → A: Oldest first (topmost/first-appended eligible line). The "Before enabling" lines were all cleared by #1084 on 2026-10-22; a priority marker may be added later if steering is needed (FR-004).
- Q: Where does a line's board item marker live? → A: A loop-authored comment on the backlog issue, keyed by the line's id, read by the existing board item marker reader (FR-009).

### Session 2026-11-06 (owner, after the spec PR review)

- Q: Does constitution Principle X need an amendment for holding a line with an annotation instead of `board:stalled`, and for acting on lines others add to a maintainer-authored backlog issue? → A: Yes. An amendment to X (version bump per the constitution's Governance section) names Maintenance backlog lines as a board-loop entry and the line annotation as the hold for a line. It is a separate human-merged PR that merges before this feature's final PR, the same arrangement the owner chose for spec 119 on 2026-10-26 (FR-022).
- Q: Does the feature get its own switch? → A: Yes. A `WING_COMMANDER_BOARD_BACKLOG_LINES` repository variable, default off, gates line selection. Board auto-merge and workflow-file fixes are already on, so without it the loop would start working the backlog the moment this merges (FR-023).
- Q: How is the backlog body protected from a writer that rewrites it from a stale copy? → A: Every pipeline and session edit to the backlog body goes through one shared helper that re-reads the body, re-applies only its own change, and reads it back; a CLAUDE.md "Working the issue board" rule requires sessions to use it, never a blind whole-body write. The loop's own read-back and stand-down (FR-015, FR-016) stay as the backstop (FR-024).

### Session 2026-11-06 (owner, after spec review 2)

- Q: What happens to a line already claimed when `WING_COMMANDER_BOARD_BACKLOG_LINES` is turned off? → A: (a) The switch stops only new claims. A claimed line is finished or held as usual, its PR merge still ticks it, and only then does the loop's behaviour return to today's. `WING_COMMANDER_BOARD_LOOP_PAUSED` remains the hard stop (FR-023).
- Q: What keeps the constitution amendment merging before this feature's final PR? → A: (a) Answered from precedent (spec 119, owner decision 2026-10-30, option (b)): line selection also refuses while Principle X of `.specify/memory/constitution.md` on the default branch does not contain the literal phrase the amendment PR names, read fresh at selection time; an unreadable constitution refuses (FR-022, FR-025).

### Session 2026-11-06 (owner, after spec review 4)

- Q: Should the closing-keyword check refuse a keyword for any issue, not only the backlog issue? Lines often cite other issues ("#747: …"), and a fixer commit "Fix #747: …" would close #747 on landing, skipping the waiver check CLAUDE.md requires before closing an issue. → A: **(a) Refuse any closing keyword** in a line-born PR's title, body and branch commit messages, for any issue. The line's tick is the only record a line fix needs (FR-017).

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

### User Story 2 - A line triage can close, or one that needs a design decision, is cleared without a fix PR (Priority: P2)

Triage reads the line against current `main`. When triage's deterministic code reads a close ground (an API 429 in a run the line cites, or an upstream action bump), the loop ticks the line with that evidence quoted instead of opening a PR. When the triage agent proposes that the defect is already fixed on `main`, the loop does what it does for an issue: it records the proposal and the named commit and holds the line with the triage-handover reason (FR-014) for a maintainer to confirm and tick, because spec 057's FR-012 defers that ground and the loop never closes on it. When route finds the line spec-shaped (it needs the owner to decide a trade-off, spans several stages, or would benefit from clarify's questions), the loop files a `spec-proposal` as it already does for issues, and the line points at that proposal and is no longer selected.

**Why this priority**: Many old lines are stale or design-shaped; clearing them honestly is half the value and keeps the loop from repeatedly selecting a line it can never fix.

**Independent Test**: Seed one line citing a run whose execution-output record carries a qualifying API 429, one line the triage agent proposes is already fixed, and one design-shaped line; run the loop three times; observe the first ticked with the 429 evidence quoted, the second held with the triage-handover reason and the proposed commit, and the third annotated with a link to a new `spec-proposal`, all three now skipped by selection.

**Acceptance Scenarios**:

1. **Given** a claimed line for which triage's code reads a close ground (FR-012), **When** triage completes, **Then** the line is ticked with that evidence quoted and no PR is opened.
2. **Given** a claimed line the triage agent proposes is already fixed on `main`, **When** triage completes, **Then** the line is held with the triage-handover reason and the proposed commit (FR-014), it is not ticked, and no PR is opened.
3. **Given** a claimed line route classifies as spec-shaped, **When** route completes, **Then** a `spec-proposal` issue is filed (never `spec-request`), the line is annotated with a pointer to it, the line is not ticked, and selection skips it from then on.

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

The backlog issue has other writers: maintainers and local sessions add, edit and tick lines by hand. (No pipeline step writes the body today; the stage-findings composite files issues, not lines.) Every edit the loop makes to the backlog changes only the one line it is working on, re-reads the current body immediately before writing, and if the body changed in between, re-applies its one-line change to the newer body rather than overwriting it.

**Why this priority**: A lost edit on #889 silently deletes recorded defects — worse than the loop doing nothing. This is a precondition for enabling the feature at all.

**Independent Test**: Between the loop's read and its write, append a new line and tick an unrelated line on the backlog; observe that after the loop's edit both concurrent changes are still present and only the loop's line changed in the loop's own edit.

**Acceptance Scenarios**:

1. **Given** another writer changes the backlog between the loop's read and write, **When** the loop writes, **Then** the other writer's change survives and the loop's one-line change is applied to the newer body.
2. **Given** the loop's line was deleted or rewritten beyond recognition by another writer, **When** the loop tries to update it, **Then** it does not write a line back, stands down from that item, and reports the loss on the backlog issue.
3. **Given** concurrent edits keep defeating the write after a bounded number of retries, **When** retries are exhausted, **Then** the loop leaves the body unchanged and reports the failure loudly rather than forcing the write.

---

### Edge Cases

- A line is ticked by a human while the loop has it claimed: the loop stands down from that line at its next re-derivation, leaves any open fix PR for a maintainer, and says so.
- A line's text is edited by a human while the loop has it claimed: its identity (the id written into the line, FR-003) still matches as long as the id is kept; the loop continues from the line's current text only at its next triage, never mid-fix.
- Two lines with identical text: oldest-first order (FR-004) picks the topmost; claiming writes a distinct id into that line only, so the two stay apart from then on, and only one is claimed per run.
- A line bundles two defects or cites several files: worked as one item while its fix fits the size-and-path backstop; a fix that breaches the backstop holds the line with the backstop reason, and route may classify a line whose parts need different decisions as spec-shaped.
- A fix PR for a line must never carry a closing keyword for the backlog issue, in its body, its title or any commit message on its branch: the repository's squash merges take the commit title from the PR title when the PR has more than one commit and the message from the branch's commit messages, and a closing keyword in a commit landing on `main` closes the issue. The issue path's `Fix #<issue>: <title>` PR title and the fixer agent's own commit messages (it is told the item's issue number) are the realistic carriers. Merging a line's PR must never close the backlog issue.
- The backlog issue is closed, renamed, loses `disposition:tracking`, or a second open `disposition:tracking` issue's title also begins with "Maintenance backlog": the loop takes no line and reports why (no guessing which issue is the backlog).
- The backlog body is empty or has no unchecked lines: the loop is idle, as today.
- Lines inside a fenced code block, quoted text, or prose that merely looks like a checkbox are not work items; only top-level checklist lines in the issue body are.
- Comments on the backlog issue are never a source of lines, whoever wrote them.
- The board loop kill switch (`WING_COMMANDER_BOARD_LOOP_PAUSED`) is set: no line is claimed or edited.
- A line's text contains instruction-like content aimed at an AI: it is treated as defect description data only.
- Two lines carry the same id (a maintainer copied a claimed line): the id no longer names one line, so the loop stands down from it as FR-016 requires and writes neither line.
- Every line lives on the one backlog issue, so nothing the issue path derives from the item issue's number or title (the `fix/<issue>-<slug>` branch, the resume step's branch check) can tell two lines apart; FR-007 derives those from the line's id instead.
- A line that a waiver register cites through the backlog issue number: ticking a line never closes the backlog issue, so gate 124's open-tracker check is unaffected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The board loop MUST take a Maintenance backlog line as its work item only when no eligible issue is waiting; while any eligible issue is waiting, issues take precedence. *(Default from the proposal's "when no eligible issue is waiting"; interleaving is out of scope.)*
- **FR-002**: The loop MUST identify the Maintenance backlog by deterministic signals — exactly one open issue carrying `disposition:tracking` whose title begins with "Maintenance backlog" (the rule Board status already uses; #889's title is "Maintenance backlog (one tracking issue for small defects)"), authored by a maintainer or the pipeline's own App — and MUST take no line when that resolution is ambiguous or fails.
- **FR-003**: Each claimed line MUST have a stable identity that survives edits to every other line of the issue, survives a human editing the line's own text, and distinguishes lines with identical text: a short id the loop writes into the line when it claims it. Writing the id is part of the claim and costs one read-modify-write of the backlog issue (FR-015). A line nobody has claimed carries no id; before its claim, a line is located only by its position in the body as read.
- **FR-004**: Line selection MUST be deterministic over the issue body as read and MUST skip lines that are ticked, claimed, held, or routed to a `spec-proposal`, choosing among the rest oldest first — the topmost eligible line in the body as read. Lines are filed under section headings, so body order is the only order the body records and stands in for append order. No priority marker is honoured; one may be added later if steering turns out to be needed.
- **FR-005**: Only top-level unchecked checklist lines in the backlog issue's body MUST be candidates; comments, quoted text and fenced blocks MUST NOT be.
- **FR-006**: The loop MUST work at most one line per run, under the same global concurrency group, kill switch and one-item-at-a-time rule as issues, and a claimed (in-progress) line MUST count as the loop's current item exactly as a claimed issue does. A line held under FR-014 does not; like a `board:stalled` issue, it releases the board.
- **FR-007**: A line MUST pass through the same triage, route, fix, review, readiness and (under spec 115) merge steps, with the same deterministic gates, backstop and authorization checks as an issue, with the line's text in the role of the issue body. The agent context for a line is that line's text, never the rest of the backlog body. Anything the issue path derives from the item issue's number or title (the fix branch name, which today is `fix/<issue>-<title slug>`, and the resume step's check that a marker's branch is the loop's own) MUST be derived for a line from the backlog issue number plus the line's id, so no two lines share a branch or adopt each other's.
- **FR-008**: The line's text MUST be framed as untrusted defect-description data in every agent prompt, never as instructions.
- **FR-009**: The loop's board state for a line (the board item marker and its re-derivation inputs) MUST be keyed by the line's identity and stored in a loop-authored comment on the backlog issue, keyed by the line's id and read by the existing board item marker reader, so the state lives beside the line; only comments the loop itself authored are read as board state (comments are never a source of lines, FR-005), and every field MUST be re-derived from live state before any durable action, as for issues.
- **FR-010**: While the loop has a line claimed, the line MUST visibly show it is in progress (and by which fix PR once one exists).
- **FR-011**: When the line's fix PR merges, the line MUST be ticked and carry "(fixed by #PR)".
- **FR-012**: Wherever triage would close an issue on evidence deterministic code read (an API 429 in the cited run, an upstream action bump: the two grounds `board_triage.py` implements), the line MUST instead be ticked with that evidence quoted, and no PR opened. Principle X also names "the fixing commit already on `main`", but spec 057's FR-012 defers that ground and triage hands such a proposal over under `board:stalled` instead of closing; for a line, that handover is the FR-014 hold, never a tick.
- **FR-013**: When route classifies a line as spec-shaped, the loop MUST file a `spec-proposal` (never apply `spec-request`), annotate the line with a pointer to it, leave the line unticked, and skip it in later selection. The issue path's duplicate disposition of the originating issue (spec 108) MUST NOT run for a line, since its originating issue is the backlog (FR-017); the line annotation and a cross-link on the proposal take its place.
- **FR-014**: When the loop holds a line for any reason a `board:stalled` issue would be held, the line MUST carry that same reason and be skipped by selection until a maintainer removes the hold annotation. This covers every site that today adds `board:stalled` to the item issue, among them the triage handover, a red gate suite at fix, the workflow-scope hold, the backstop, a review round that is unreadable, malformed or out of budget, the not-ready handover (spec 093), and a maintainer stop request recorded on the backlog issue. For a line, the annotation takes the label's place; the backlog issue is never labelled (FR-017).
- **FR-015**: Every edit the loop makes to the backlog body MUST be a read-modify-write that changes only the one line it works, re-reads the body immediately before writing, re-applies its change to any newer body, preserves every other writer's change that landed before that re-read, and reads the body back after writing to confirm its change landed (re-applying it if a later writer dropped it). GitHub's issue-update API offers no conditional write, so an edit landing between the re-read and the write cannot be detected; this requirement narrows that window, it does not close it. After a bounded number of conflicting attempts it MUST leave the body unchanged and report the failure.
- **FR-016**: If the worked line is ticked, deleted, or no longer matches its identity, the loop MUST stand down from it without writing it back and report this on the backlog issue.
- **FR-017**: A fix PR for a line MUST reference the backlog issue, and any issue the line cites, without a closing keyword, in its body, its title and every commit message on its branch (a squash merge carries the title or the commit messages onto `main`, where a closing keyword closes the issue); deterministic code MUST check the title and the branch's commit messages before every push to the line's branch (the fix push and every review-fixup push, since a human may squash-merge the PR without the loop's merge step) and before any merge, and refuse rather than push or merge one that carries a closing keyword for any issue, the backlog issue or another one a line cites (owner decision 2026-11-06, after spec review 4: a line fix closes nothing; its tick is its record). No step of this feature may close, relabel or retitle the backlog issue.
- **FR-018**: Board status and run reporting that today names the current issue MUST name the current line (backlog issue plus line identity) when a line is the work item.
- **FR-019**: Each new branch — selection, skip conditions, the read-modify-write conflict path, the stand-down path, the ambiguous-backlog path, the backlog-reference item resolution (FR-021), the switch-off path (FR-023: no new claim, a claimed line still worked, a line-born PR's merge still ticked), the closing-keyword check (FR-017), the shared backlog-edit helper (FR-024), and every line annotation — MUST be covered by a checked-in fixture a gate exercises.
- **FR-020**: With no line claimed and no line-born fix PR open, and with the backlog empty of candidate lines or the feature's lines unreachable, the loop's behaviour MUST be exactly today's. A claimed line (FR-006) is still handled when no candidate line remains, and the handling of a line-born PR's merge (FR-011's tick and FR-021's prove-after-merge entry, its stranded-proof recovery included) is never gated by the switch or by claim state: it runs on that PR's `pull_request: closed` event although the PR is by then no longer open, so "no line-born fix PR open" never switches it off.
- **FR-021**: Every path that today finds a fix PR's item from the PR body's `Fixes #N` (among them the `pull_request: closed` prove entry, the detection of a merge whose proof run never started, and resume's recovery of an open `board:owned` PR when the marker names none) MUST find a line-born PR's item from the non-closing backlog reference FR-017 requires (backlog issue plus line id) together with the loop's own board state for that line, so a human merge still reaches FR-011's tick and the prove-after-merge entry.
- **FR-022**: This feature MUST NOT be merged before a human-merged constitution amendment to Principle X that names Maintenance backlog lines as a board-loop entry and the line annotation as a line's hold, and updates the Development Workflow paragraph that restates the loop as working "one issue at a time" with "a closed issue" as an exit. The amendment moves its Sync Impact Report to the top of `.specify/memory/constitution-history.md` in the same commit (CLAUDE.md).
- **FR-023**: New line claims MUST be made only while the repository variable `WING_COMMANDER_BOARD_BACKLOG_LINES` is exactly `true`. It defaults to off. Turning it off stops new claims only: a line already claimed is finished or held as usual, and the merge of any line-born fix PR (including one a held line left open for a human) still ticks its line (FR-011, FR-021); once no line is claimed and no line-born fix PR is open, the loop's behaviour MUST be exactly today's (FR-020), apart from the handling of a line-born PR's merge, which FR-020 keeps on. `WING_COMMANDER_BOARD_LOOP_PAUSED` remains the hard stop (owner decision 2026-11-06, after spec review 2). Board status (#914) MUST show the switch beside the other board switches.
- **FR-024**: Every write to the backlog body, by the loop and by local sessions, MUST go through one shared helper that re-reads the body, applies only the caller's own change to the newest body, and reads the result back, re-applying the change if it was dropped, up to FR-015's bound. A CLAUDE.md "Working the issue board" rule MUST require sessions to edit the backlog only through this helper, and the helper MUST be the only home of that logic (CLAUDE.md "Shared logic has exactly one home"), enforced by a gate. FR-015 and FR-016 remain the loop's backstop for writers that bypass it.
- **FR-025**: Line selection MUST refuse, with a one-line reason in the run summary, while Principle X (the `### X.` section) of `.specify/memory/constitution.md` on the default branch, read fresh at selection time, does not contain the literal phrase `Maintenance backlog line` (singular; the phrase the FR-022 amendment PR, #1115, names as appearing exactly once in X — a check for the plural would never match it); a constitution that cannot be read refuses. This enforces FR-022's merge order deterministically, as spec 119 does for its hold gate (owner precedent 2026-10-30, option (b)). The check MUST be covered by fixtures for the amended text, the unamended text and an unreadable file.

### Key Entities

- **Maintenance backlog**: The single open `disposition:tracking` issue whose title begins with "Maintenance backlog" (#889 at the 2026-10-01 reset). Never closed or relabelled by this feature.
- **Backlog line**: One top-level checklist line in the backlog body. Attributes: identity, text, state (unchecked, in progress, held with reason, routed to a proposal, ticked with fix or evidence).
- **Line identity**: The short id the loop writes into a line when it claims it; names that line across edits to the rest of the body and to the line's own text (FR-003). Unclaimed lines carry none.
- **Line board state**: The board item marker and progress for a line, held in a loop-authored comment on the backlog issue keyed by the line's id (FR-009).
- **Line annotation**: The visible text the loop adds to a line to show in-progress, held (with reason), routed (with proposal link), or fixed (with PR or evidence).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the switch on (FR-023), no eligible issue waiting and at least one candidate line, every board-loop run that has capacity takes a line — the backlog moves without a local session.
- **SC-002**: 100% of lines the loop finishes end in exactly one visible terminal state on the line: ticked with "(fixed by #PR)", ticked with triage's close evidence (FR-012), pointing at a `spec-proposal`, or held with a reason (an already-fixed proposal included).
- **SC-003**: 0 concurrent edits by other writers that land before the loop's pre-write re-read are lost, demonstrated by a fixture that interleaves a concurrent write between the loop's first read and its re-read; a fixture where a later writer drops the loop's change shows the read-back re-applying it (FR-015).
- **SC-004**: 0 runs in which the loop claims a new line while an eligible issue was waiting. A line already claimed keeps the board until it finishes or is held (FR-006).
- **SC-005**: The backlog issue is never closed, relabelled or retitled by the loop, and no merged line fix closes it.
- **SC-006**: Over the first 30 days enabled, the count of open backlog lines falls, with no line selected again after reaching a terminal state.

## Assumptions

- Lines are taken only when the issue queue is empty (FR-001) — the proposal's own wording; interleaving is a later decision.
- A bundled or multi-file line is worked as one item bounded by the existing size-and-path backstop; it is not split by the loop.
- Authorization: lines come only from the body of a backlog issue a maintainer or the App authored; GitHub restricts editing an issue body to its author and collaborators with write access, so every body line was written by a maintainer, a collaborator, or the pipeline. Constitution Principle X is amended to name these lines and the line annotation explicitly (FR-022, owner decision 2026-11-06).
- Workflow-touching line fixes follow the existing `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` rule, and autonomous merge stays governed by `WING_COMMANDER_BOARD_AUTO_MERGE` (spec 115). Both are on since 2026-11-03 (#890, Owner decisions; the App holds Workflows: Read and write), so a workflow-touching line is pushed and, once ready, merged without a human; the FR-014 workflow-scope hold applies only while the switch is off. Neither switch is changed here.
- Existing triage evidence rules (API 429, upstream action bump; an already-fixed proposal is handed over, never closed on), route classification, the independent review, the readiness evaluation and the prove-after-merge entry (spec 096) are reused, except that a line-born PR's item is found from the backlog reference instead of `Fixes #N` (FR-021).
- The Roadmap issue's "Proposed" list is updated for a line-born `spec-proposal` the same way it is for an issue-born one.
- The feature has its own switch, `WING_COMMANDER_BOARD_BACKLOG_LINES`, default off (FR-023, owner decision 2026-11-06); the owner turns it on after merge.
