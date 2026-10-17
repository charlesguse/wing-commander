# Feature Specification: Board Loop Merges Its Own Fix-Class and Dependency-Bump PRs

**Feature Branch**: `spec-draft/115-board-loop-self-merge`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "Board loop merges its own fix-class PRs (#903). Roadmap goal (#890): auto-fix that finishes without the owner. Today the board loop opens a fix PR and stops at readiness ('Awaiting a human merge -- this loop never merges, approves, or enables auto-merge'). Constitution Principle X already authorizes the fix-PR merge class under conditions the loop checks fully or in part: green checks on the exact head SHA with the gate suite run on that SHA (a head with no checks is not green); an independent review with zero open findings; the size-and-path backstop holding on the final diff; a clear kill switch; a squash commit one human action reverts, proven after merge by re-driving one run when the fix only runs in Actions. Owner decision (2026-10-17): widen the scope to both bot merge classes constitution X authorizes — the bounded fix-PR merge and the verified dependency-bump merge (a Spec Kit upgrade the auto-update stage opened, merged after its assigned verification passed, with the gate suite green on the exact head and the kill switch clear). Settled by precedent: the merge re-derives every condition from a freshly fetched snapshot of the exact head SHA (where it runs is a plan detail); a workflow-touching PR GitHub refuses is handed to a maintainer with the reason stated, never routed around; the post-merge prove re-drive records its evidence on the PR. Open: the merge's own switch (resolved in Clarifications). Out of scope: spec, plan and lifecycle PRs, and constitution amendments."

## Clarifications

### Session 2026-10-17

- Q: The merge switch's shape, name, and kill switch? → A: One switch, `WING_COMMANDER_BOARD_AUTO_MERGE` (default off), covering both the fix-PR and dependency-bump classes, with the existing `WING_COMMANDER_BOARD_LOOP_PAUSED` as its kill switch. Mirrors `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` (constitution X). (Owner, #903.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A ready fix PR is merged without the owner (Priority: P1)

The board loop fixes a maintenance defect, opens a fix PR, gets it independently reviewed to zero open findings, and reaches readiness. Today it posts "Awaiting a human merge" and the item waits — sometimes for days — for the owner to press merge. With this feature, when the merge switch is on and every condition holds on a freshly fetched snapshot of the exact head SHA, the loop squash-merges the PR itself and announces the merge, with the head SHA and every condition that authorized it, on both the PR and the issue.

**Why this priority**: This is the roadmap goal — auto-fix that finishes without the owner. The fix class is the volume case and the one whose conditions the loop already largely derives.

**Independent Test**: With the switch on, drive one fix-shaped issue through the board loop to readiness; observe a squash commit on `main` for that PR whose merged SHA equals the head SHA named in the readiness decision, and an announcement on the PR and the issue naming each condition's result.

**Acceptance Scenarios**:

1. **Given** the switch is on, the kill switch is clear, checks are green on head SHA H with the gate suite run on H, the independent review left zero open findings, and the backstop holds on the final diff, **When** the loop evaluates readiness, **Then** it squash-merges the PR at exactly H and announces the merge on the PR and the issue with H and every condition's result.
2. **Given** all conditions held at evaluation but a new commit lands on the PR before the merge call, **When** the loop merges, **Then** the merge is refused because the head is no longer H, nothing reaches `main`, and the item is reported as not merged with that reason.
3. **Given** the switch is off, **When** a fix PR reaches readiness, **Then** behaviour is exactly today's: the readiness report is posted, a human merge is awaited, and the loop never merges, approves, or enables auto-merge.
4. **Given** any one condition fails (a check red or pending, no checks at all on H, gate suite not run on H, an open review finding, a backstop breach, the kill switch set), **When** the loop evaluates, **Then** it does not merge and names the failed condition on the issue.

---

### User Story 2 - A verified Spec Kit upgrade is merged without the owner (Priority: P2)

The auto-update stage opens a Spec Kit upgrade PR and runs the verification it assigns to that version jump. Today the PR waits for a human merge (one waited 7 days). With this feature, once that assigned verification has passed, the gate suite ran green on the exact head SHA, and the kill switch is clear, the board loop merges it — the upgrade stage itself still never merges its own PR.

**Why this priority**: The owner widened the scope to include it; it is the second class constitution X authorizes and nothing performs it yet. It is lower volume than fix PRs.

**Independent Test**: With the switch on, let the auto-update stage open an upgrade PR whose assigned verification passes; observe the board loop squash-merge it at the verified head SHA and announce it with the verification evidence it relied on.

**Acceptance Scenarios**:

1. **Given** an open upgrade PR opened by the auto-update stage whose assigned verification passed on head SHA H, the gate suite ran green on H, and the kill switch is clear, **When** the loop evaluates it, **Then** it squash-merges at exactly H and announces the merge with H, the verification that passed, and every condition's result.
2. **Given** the assigned verification failed, is still running, or ran on a SHA other than the current head, **When** the loop evaluates, **Then** it does not merge and names the reason.
3. **Given** an upgrade PR whose diff exceeds the fix-class size-and-path backstop, **When** every bump-class condition holds, **Then** the loop still merges it, because the backstop does not apply to this class.
4. **Given** a PR that resembles an upgrade but was not opened by the auto-update stage (another author, or a human-pushed commit on top), **When** the loop evaluates, **Then** it does not treat it as the dependency-bump class and does not merge it.

---

### User Story 3 - A merge GitHub refuses is handed to a maintainer (Priority: P2)

The pipeline's credential has no Workflows permission, so GitHub refuses to merge a PR that touches workflow files. When any autonomous merge is refused — for that reason or another (branch protection, a merge conflict) — the loop hands the PR to a maintainer with the refusal reason stated on the PR and the issue, and never reaches `main` another way.

**Why this priority**: Without it, a refused merge would either fail silently or tempt a workaround; both violate X.

**Independent Test**: With the switch on, bring a ready PR that touches a workflow file to the merge step; observe that nothing reaches `main`, and a handover naming the scope refusal appears on the PR and the issue.

**Acceptance Scenarios**:

1. **Given** a ready PR that touches a workflow file, **When** GitHub refuses the merge for lack of the workflow scope, **Then** the loop posts a handover stating that reason, leaves the PR open, and the item is released to a maintainer rather than retried every run.
2. **Given** any other refusal, **When** the merge call fails, **Then** the handover quotes the refusal reason and nothing is pushed to `main` by any other path.

---

### User Story 4 - The merge is proven and recorded on the PR (Priority: P3)

When the merged change alters behaviour that only runs in Actions, the post-merge prove re-drives one run and records the evidence — which run, on which merged commit, and that it took the changed path — on the merged PR.

**Why this priority**: X requires it for every such fix; the durable prove entry (spec 096) already exists, so this story wires the autonomous merge into it rather than inventing new proof machinery.

**Independent Test**: Auto-merge a fix that changes a workflow-only behaviour; observe a prove record on the PR naming the re-driven run and the merged SHA.

**Acceptance Scenarios**:

1. **Given** an autonomous merge of an Actions-only behaviour change, **When** the merge completes, **Then** a prove entry is created and its evidence, once the re-driven run finishes, is recorded on the PR.
2. **Given** an autonomous merge of a change that does not run in Actions (a gate script exercised by the gate suite, a doc correction), **When** the merge completes, **Then** no re-drive is required, and the announcement says why.

---

### Edge Cases

- The kill switch is set between the condition evaluation and the merge call: the merge does not happen (the kill switch is re-read immediately before the merge).
- The merge switch (`WING_COMMANDER_BOARD_AUTO_MERGE`) is turned off between evaluation and merge: no merge.
- A human pushes a commit, requests changes, or merges the PR themselves after readiness: the loop does not merge over a new head; if the PR is already merged or closed it records that and stands down.
- A head SHA with no checks reported at all: not green, no merge.
- Required checks still pending: not green; the item is left for a later run, not merged and not failed.
- A fix PR whose final diff breaches the backstop after a review fix-up: no merge (existing breach routing applies).
- An upgrade PR that touches workflow files: same refusal handover as User Story 3.
- Two candidates ready in the same run: the loop still works one item at a time under its global concurrency group.
- A merge succeeds but the announcement fails to post: the merge is not undone; the failure is surfaced loudly and the announcement is retried or left for a maintainer, never silently dropped.
- Spec, plan, lifecycle, or constitution-amending PRs are never candidates, even if they otherwise satisfy every condition.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The board loop MUST be able to merge a fix-class PR it opened only when, on a freshly fetched snapshot of the exact head SHA being merged, all of these hold: checks green on that SHA (a head with no checks is not green); the gate suite ran on that SHA; the independent review has zero open findings; the size-and-path backstop holds on the final diff; the kill switch is clear; and the merge switch (FR-006) is on.
- **FR-002**: The board loop MUST be able to merge a dependency-bump PR only when it was opened by the auto-update stage, the verification that stage assigned to the version jump passed on the exact head SHA, the gate suite ran green on that SHA, the kill switch is clear, and the merge switch is on. The size-and-path backstop MUST NOT be applied to this class.
- **FR-003**: Every merge decision MUST be made by deterministic code re-deriving every condition from a fresh snapshot, never from an agent's judgment and never from state cached by an earlier run or job.
- **FR-004**: The merge MUST be pinned to the evaluated head SHA, so that a PR whose head moved after evaluation is not merged.
- **FR-005**: Every autonomous merge MUST be a squash commit on `main` that one human action reverts.
- **FR-006**: The autonomous merge MUST be governed by one repository variable, `WING_COMMANDER_BOARD_AUTO_MERGE`, defaulting to off, covering both merge classes (fix PR and dependency bump) — mirroring `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` (constitution X). Its kill switch is the board loop's existing `WING_COMMANDER_BOARD_LOOP_PAUSED`, for both classes; no separate `*_PAUSED` variable is added. While the switch is off, the loop MUST behave exactly as today (readiness report, human merge awaited, never merges, approves, or enables auto-merge).
- **FR-007**: The kill switch (`WING_COMMANDER_BOARD_LOOP_PAUSED`) MUST be re-read immediately before the merge call; a set kill switch MUST prevent the merge.
- **FR-008**: Every autonomous merge MUST be announced on the PR and on the issue it resolves (for a fix PR) or the auto-update tracking issue (for a bump) with the merged head SHA, the merge class, and each condition's result.
- **FR-009**: Any failed condition MUST be named on the issue, and the PR MUST NOT be merged past it.
- **FR-010**: When GitHub refuses a merge — including for lack of the workflow scope a workflow-touching PR requires — the loop MUST hand the PR to a maintainer with the refusal reason stated on the PR and the issue, MUST NOT reach `main` by any other route, and MUST release the item so it is not re-attempted every run.
- **FR-011**: After an autonomous merge of a change to behaviour that only runs in Actions, the loop MUST create the post-merge prove entry so one run is re-driven, and the evidence MUST be recorded on the merged PR.
- **FR-012**: The merge MUST never reach a spec PR, a plan PR, a lifecycle (final implementation) PR, or a PR amending the constitution.
- **FR-013**: The auto-update stage MUST continue never to merge its own PR; only the board loop merges a dependency bump.
- **FR-014**: The loop MUST NOT approve PRs or enable GitHub's auto-merge as a substitute for performing the gated merge itself.
- **FR-015**: Each merge-blocking condition and each refusal branch MUST be covered by a checked-in fixture that a gate exercises, so the merge gate cannot pass a condition it did not check.

### Key Entities

- **Merge candidate**: An open PR the board loop may merge — a fix PR it opened for a board item, or an upgrade PR the auto-update stage opened. Attributes: class (fix or dependency-bump), head SHA, originating issue.
- **Merge snapshot**: The freshly fetched state of the candidate at one head SHA — check rollup, gate-suite result, review findings state, backstop result, verification result (bump class), kill switch and merge switch values.
- **Merge decision**: Deterministic result over a snapshot — merge or not, the head SHA, and each condition's pass/fail with reason.
- **Merge announcement / handover**: The durable record on the PR and issue of a merge (with its decision) or of a refusal handed to a maintainer (with GitHub's reason).
- **Prove entry**: The existing post-merge record (spec 096) that drives one re-run and holds its evidence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the switch on, a fix PR whose conditions all hold is merged within the same board-loop run (or the next scheduled run) that finds it ready — no owner action between readiness and merge.
- **SC-002**: With the switch on, a verified Spec Kit upgrade PR is merged within one board-loop cycle of its verification passing, instead of waiting for a human (one previously waited 7 days).
- **SC-003**: 0 autonomous merges occur with any authorizing condition unmet, at a head SHA other than the evaluated one, or while the kill switch or merge switch says no — demonstrated by a fixture per condition.
- **SC-004**: 100% of autonomous merges carry an announcement naming the head SHA and every condition's result, and 100% of refused merges carry a handover naming the refusal reason.
- **SC-005**: 100% of autonomous merges of Actions-only behaviour changes end with re-drive evidence recorded on the merged PR.
- **SC-006**: With the switch off, the board loop's observable behaviour at readiness is unchanged from today.

## Assumptions

- Where the merge runs (in the readiness job or a separate job modelled on the lifecycle review gate's snapshot) is a plan detail; the requirement is only that it re-derives every condition from a fresh snapshot of the exact head SHA (settled by constitution X's precedent for the lifecycle merge).
- The existing readiness evaluation, final-diff backstop, independent review convergence, and kill-switch recheck are reused as the fix-class condition sources rather than re-implemented.
- The auto-update stage already records, or can be made to record, which verification it assigned to a jump and whether it passed on which SHA, in a form deterministic code can read; how is a plan detail.
- A PR is attributable to the auto-update stage by deterministic signals (its author credential, branch, and markers), not by its title.
- The App's lack of Workflows permission is expected to persist; workflow-touching PRs will therefore routinely end in a maintainer handover, which is the intended outcome.
- No constitution amendment is required: both merge classes are already authorized by Principle X as worded at version 2.5.0.
- Spec 096 (durable prove entry) has merged and is the mechanism for FR-011; spec 097's recorded stop point is reused where it applies.
