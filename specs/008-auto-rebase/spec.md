# Feature Specification: Auto-Rebase — Keep In-Flight Spec Branches Current With the Main Line

**Feature Branch**: `spec-draft/008-auto-rebase`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "Spec out the auto-rebase stage as described in the architecture doc. It triggers whenever the main line advances (skipping changes pushed by the pipeline's own automation) and on a nightly schedule. For each in-flight specification's persistent working branch, it rebases that branch onto the latest main line. When the rebase is clean, it updates the working branch to the rebased result. When the rebase hits conflicts, an AI assistant attempts to resolve only the in-progress rebase without making unrelated edits, and if it succeeds the working branch is updated. When the rebase still cannot be resolved, the attempt is abandoned so the working branch is left untouched, and a note is posted to the specification's lifecycle issue asking a human for help. Until now spec branches have drifted from the main line and had to be rebased by hand before their final review; this stage keeps them current automatically so merges stay clean."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - In-flight spec branches stay current with the main line automatically (Priority: P1)

Whenever the main line advances, every in-flight specification's persistent working branch is rebased onto the new main line without anyone doing it by hand. When the rebase applies cleanly, the working branch is updated to the rebased result. A maintainer who later opens a specification's review pull request sees it already sitting on top of current main, with a clean, mergeable diff, instead of a working branch that has silently drifted weeks behind and needs a manual rebase before it can merge.

**Why this priority**: Drift is the problem this stage exists to solve. Long-lived per-specification working branches fall behind main as other work merges, and by the time a specification reaches final review its diff is tangled with unrelated history and often no longer merges cleanly. Keeping every in-flight branch continuously rebased is the entire value of the stage — it removes the manual pre-merge rebase step and keeps final review honest about what a specification actually changes.

**Independent Test**: With one or more in-flight specification working branches present, advance the main line and verify that each in-flight working branch is rebased onto the new main line and updated to the rebased result, with no human performing the rebase.

**Acceptance Scenarios**:

1. **Given** an in-flight specification working branch that is behind the main line, **When** the main line advances, **Then** the working branch is rebased onto the latest main line.
2. **Given** a rebase that applies with no conflicts, **When** the stage runs, **Then** the working branch is updated to the rebased result.
3. **Given** an in-flight specification working branch that is already current with the main line, **When** the stage runs, **Then** the branch is left as-is and no spurious update is made.

---

### User Story 2 - Conflicting rebases are resolved by an AI assistant, scoped to the rebase alone (Priority: P2)

When a specification's working branch cannot be rebased cleanly because its changes conflict with what merged into the main line, an AI assistant attempts to resolve the conflicts of the in-progress rebase — and only those conflicts, making no unrelated edits. When it resolves them, the working branch is updated to the rebased, conflict-resolved result, so a mergeable conflict does not require a human just to reconcile the branch with main.

**Why this priority**: Conflicts are common for long-lived branches and are exactly where a purely mechanical rebase gives up. Automatically resolving the tractable ones keeps branches current without human involvement, while the scoping guarantee — resolve the rebase, change nothing else — is what makes the automated resolution trustworthy enough to run unattended. It is second to the clean-rebase path because it applies only when the mechanical rebase fails.

**Independent Test**: Create an in-flight working branch whose changes conflict with the main line, advance the main line, and verify that the AI-assisted resolution reconciles only the in-progress rebase (introducing no edits unrelated to the conflicts) and that the working branch is updated to the resolved result.

**Acceptance Scenarios**:

1. **Given** a rebase that stops on conflicts, **When** the stage runs, **Then** an AI assistant attempts to resolve the conflicts of the in-progress rebase.
2. **Given** the AI assistant is resolving conflicts, **When** it makes changes, **Then** those changes are confined to resolving the in-progress rebase and introduce no edits unrelated to the conflicts.
3. **Given** the AI assistant resolves all conflicts, **When** the rebase completes, **Then** the working branch is updated to the resolved, rebased result.

---

### User Story 3 - Unresolvable rebases escalate to a human without corrupting the branch (Priority: P3)

When a rebase cannot be completed even with AI assistance, the attempt is abandoned so the specification's working branch is left exactly as it was before the attempt, and a note is posted to the specification's lifecycle issue asking a human to rebase it by hand. The maintainer following the lifecycle issue learns the branch needs manual attention, and the branch itself is never left in a half-rebased or broken state.

**Why this priority**: The stage must fail safe. An abandoned, half-finished rebase that corrupted a working branch or silently discarded a specification's work would be far worse than the drift it set out to fix. Preserving the branch untouched on failure and surfacing the stall on the lifecycle issue is what makes the stage safe to run automatically, but it is a fallback that applies only when both the clean and AI-assisted paths fail.

**Independent Test**: Create an in-flight working branch whose conflicts the AI assistant cannot resolve, advance the main line, and verify that the rebase attempt is abandoned, the working branch is left identical to its pre-attempt state, and a comment requesting human help is posted to the specification's lifecycle issue.

**Acceptance Scenarios**:

1. **Given** a rebase that cannot be resolved even with AI assistance, **When** the stage gives up, **Then** the rebase attempt is abandoned and the working branch is left in its original, pre-attempt state.
2. **Given** an abandoned rebase attempt, **When** the stage finishes handling that branch, **Then** a comment asking a human to rebase the branch is posted to the specification's lifecycle issue.
3. **Given** one specification's rebase is abandoned, **When** the stage continues, **Then** the outcome for other in-flight specifications is unaffected.

---

### User Story 4 - The stage runs safely across many branches and its own triggers (Priority: P3)

The stage considers every in-flight specification's working branch on each run, does not loop on the changes its own automation pushes, and also runs on a nightly schedule so branches stay current even without a triggering main-line advance. When there is nothing to rebase, it completes quietly. One branch's outcome — clean, resolved, or abandoned — never blocks or corrupts the handling of the others.

**Why this priority**: Correct triggering and isolation are what let the stage run unattended on a busy repository with several specifications in flight. Without loop protection it could re-trigger on its own updates; without per-branch isolation one hard conflict could stall every other branch. These are robustness guarantees layered on top of the three core rebase behaviors.

**Independent Test**: With several in-flight specification working branches present, advance the main line (including a main-line advance that originates from the pipeline's own automation) and separately let the nightly run fire, and verify that all in-flight branches are considered, an automation-originated advance does not cause the stage to loop, branches with nothing to rebase are left unchanged, and each branch's outcome is independent of the others.

**Acceptance Scenarios**:

1. **Given** several in-flight specification working branches, **When** the stage runs, **Then** each in-flight working branch is considered independently.
2. **Given** a main-line advance that originates from the pipeline's own automation, **When** the stage would trigger, **Then** it does not act on that advance, so the stage does not loop on its own updates.
3. **Given** no triggering main-line advance has occurred, **When** the nightly schedule fires, **Then** the stage still runs and brings in-flight branches current.
4. **Given** there is nothing to rebase for a branch, **When** the stage runs, **Then** it completes without changing that branch and without posting a comment.

---

### Edge Cases

- A specification's working branch was updated by an in-flight pipeline stage between the moment the stage read it and the moment it tries to publish the rebased result: the update is rejected because the branch moved, and the stage must not overwrite the concurrent change — see FR-011.
- The same specification remains in conflict across several consecutive runs: the stage's behavior on repeated unresolved conflicts (whether it re-attempts AI resolution and re-comments every run, or backs off after asking for help once) governs its cost and comment noise — see FR-012.
- A specification is no longer actively progressing (for example, it has been marked stalled, or it has already completed): whether its working branch is still kept current determines the branch set the stage acts on — see FR-002.
- No in-flight specification working branches exist at all: the stage runs and completes without acting on any branch and without error.
- A working branch is already current with the main line: the rebase is a no-op and the branch is left untouched, with no spurious update or comment.
- A specification's working branch exists but its lifecycle issue cannot be identified: the stage cannot escalate an abandoned rebase to a human, and must record why rather than acting blindly on an unidentified specification.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST run both when the main line advances and on a recurring nightly schedule, so in-flight specification working branches are brought current by main-line activity and also periodically regardless of activity.
- **FR-002**: The system MUST identify the set of in-flight specification persistent working branches to keep current, and act on each of them. [NEEDS CLARIFICATION: does "in-flight" include every existing persistent working branch, or should specifications that are no longer progressing — e.g. marked stalled, or already completed/merged — be excluded from rebasing?]
- **FR-003**: For each in-flight working branch, the system MUST rebase the branch onto the latest main line.
- **FR-004**: When a rebase applies with no conflicts, the system MUST update the working branch to the rebased result.
- **FR-005**: When a rebase stops on conflicts, the system MUST have an AI assistant attempt to resolve the conflicts of the in-progress rebase, and that resolution MUST be confined to completing the rebase — it MUST NOT introduce edits unrelated to resolving the conflicts.
- **FR-006**: When the AI-assisted resolution completes the rebase, the system MUST update the working branch to the resolved, rebased result.
- **FR-007**: When a rebase cannot be completed even with AI assistance, the system MUST abandon the rebase attempt and leave the working branch in its original, pre-attempt state — never in a half-rebased or otherwise broken state.
- **FR-008**: When it abandons a rebase attempt, the system MUST post a comment to the affected specification's lifecycle issue asking a human to rebase the branch by hand.
- **FR-009**: The system MUST NOT act on main-line advances that originate from the pipeline's own automation, so it does not loop on the updates it itself publishes.
- **FR-010**: The system MUST handle each in-flight specification's working branch independently, so that one branch's outcome — clean rebase, AI-assisted resolution, or abandoned attempt — does not block or corrupt the handling of the others, and MUST complete without error when there are no in-flight working branches to rebase.
- **FR-011**: When publishing a rebased working branch, the system MUST NOT overwrite changes made to that branch concurrently by another actor (for example, an in-flight pipeline stage that pushed to the branch after the stage read it); if the branch has moved, the system MUST decline to overwrite it and leave the concurrent change intact. [NEEDS CLARIFICATION: when a concurrent update blocks the publish, should the stage simply skip that branch and rely on the next run, or notify the lifecycle issue that the branch could not be updated this cycle?]
- **FR-012**: The system MUST behave sensibly when the same specification remains unresolvable across consecutive runs, avoiding runaway cost and comment noise. [NEEDS CLARIFICATION: on a specification that stays in conflict across runs, should the stage re-attempt AI resolution and post a help request every run, or ask for human help once and then skip that branch until it changes?]
- **FR-013**: The system MUST identify each specification's lifecycle issue from its working branch so it can escalate an abandoned rebase to the correct issue; when it cannot make that match, it MUST record why rather than acting on an unidentified specification.

### Key Entities

- **Main-line advance**: A change landing on the main line; together with the nightly schedule it is what causes this stage to run. An advance originating from the pipeline's own automation is deliberately ignored.
- **In-flight specification working branch**: A specification's long-lived persistent working branch that is still progressing through the pipeline; the set of these is what the stage keeps current.
- **Rebase attempt**: The act of replaying a working branch's changes onto the latest main line, whose outcome is one of clean, AI-resolved, or abandoned.
- **AI-assisted conflict resolution**: The scoped attempt to reconcile an in-progress rebase's conflicts and nothing else, invoked only when a mechanical rebase stops on conflicts.
- **Lifecycle issue**: The per-specification issue every stage reports to; this stage comments on it only to ask a human for help when a rebase is abandoned.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a specification reaches final review, its working branch is already based on the current main line without any human having rebased it, so the review pull request presents a clean diff of only the specification's own changes.
- **SC-002**: Every in-flight specification working branch that can be rebased onto the latest main line — cleanly or with resolvable conflicts — is brought current automatically, with no human intervention.
- **SC-003**: When a rebase is abandoned, the working branch is left byte-for-byte as it was before the attempt, and the specification's lifecycle issue carries a request for human help; no specification work is ever lost or left in a broken state.
- **SC-004**: The stage never loops on its own updates, and one specification's unresolvable conflict never prevents the other in-flight specifications from being brought current in the same run.
- **SC-005**: A maintainer can rely on in-flight branches being kept current without watching them: branches are rebased on main-line activity and, absent activity, at least once per night.

## Assumptions

- "Persistent working branch," "the main line," "lifecycle issue," "in-flight specification," and "the pipeline's own automation" refer to the same per-specification integration branches, primary branch, issues, and automation identity established by the earlier pipeline stages; this stage introduces no new such concepts and only keeps existing working branches current.
- The AI-assisted conflict resolution uses a model consistent with the pipeline's model-tiering conventions and runs with the least-privilege tool set it needs; the specific model and tool set are design concerns, not requirements of this specification.
- Updating a working branch to a rebased result necessarily rewrites that branch's recent history (a force update); this is expected for the pipeline's own working branches and is acceptable because those branches are owned by the pipeline, not shared human development branches — the concurrent-change protection in FR-011 guards against clobbering another actor's legitimate update.
- The stage neither merges nor approves anything and never touches the main line itself; it only updates specification working branches and, on failure, comments on lifecycle issues.
- Specifications already in flight when this stage lands are kept current from the stage's first run onward; no backfill of historical drift beyond a normal rebase onto current main is implied.
