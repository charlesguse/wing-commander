# Feature Specification: Implement Stall Hand-off and Honest Remaining-Work Reporting

**Feature Branch**: `spec-draft/117-implement-stall-handoff`

**Created**: 2026-10-17

**Status**: Draft

**Input**: Lifecycle issue #992 — "Implement stops a lifecycle after one zero-progress cycle and finalize calls unfinished code 'manual work'", with the precedent check and owner decision comments of 2026-10-17 folded in (owner: promote as filed — stop rule, task routing, finalize labelling, re-entry).

## Background

On 2026-10-09 three lifecycles left implement half-built: #972 (spec 110, PR #982), #759 (spec 101, PR #991) and #737 (spec 095, PR #990). Each did real work in its early cycles, then ran one cycle that checked no new task. Under spec 059 FR-010 that single zero-progress cycle ended the loop, and finalize opened the final PR with 13 to 25 tasks still open. The cycles that did work also stopped well under their turn budget (#759 used 61, 16 and 10 of 180 turns; #737 used 34, 14 and 14; #972's last cycle used 12).

The immediate cause was a defect since fixed (#989, fixed by #996): the pinned container image lacked PyYAML, so the implement agent could never run the gate suite and every gate-run task was impossible to check off. After #996, #982, #991 and #990 finished with zero unchecked tasks after re-entry through maintainer comments on their PRs, so part of the early-stop evidence was that defect. Three design choices, however, turned one defect into a half-built PR with no clear signal, and at least one of them is still live:

1. **One zero-progress cycle ends the loop** (spec 059 FR-010). FR-011 deliberately left out a "keep working while tasks remain" instruction, "revisited only if the corrected signal shows early stops remain common."
2. **The tasks stage places tasks only a maintainer can do in blocking phases** — driving a real run (#972 T001, which gated every model-ID change), reading Actions variables (T003), opening a separate human-merged PR (T004). With these open in Setup and Foundational phases, the implement skill's "complete each phase before the next" rule can stop a cycle before it reaches ordinary code tasks.
3. **Finalize calls every unchecked task "manual work."** The "Complete the remaining manual work" callout copies every unchecked line in tasks.md, even when the out-of-boundary classifier found nothing out of bounds. Still live after #996: spec 114's final PR #1022 (merged 2026-10-15) listed 17 "remaining manual work" lines — mostly standing "run the gate suite" instructions, one stale `M001 Complete every remaining unchecked task`, and one constitution amendment that had already merged as #1032.

Re-entering implement from review is also awkward. A manual implement dispatch on a review-stage lifecycle is a silent no-op: the idempotency guard skips because spec-meta says `review` (run 38004803493, `stage: review, iteration: 4`). The working route is a maintainer comment on the implementation PR, which the PR-conversation stage folds into a Maintainer Feedback cycle — but with the iteration cap at 5, a lifecycle that stopped at iteration 3 or 4 has only one or two cycles left.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The final PR tells the owner what is theirs and what is unfinished (Priority: P1)

When a lifecycle reaches finalize with unchecked tasks, the owner reads the lifecycle issue and the final PR and can tell, without opening tasks.md, which items are genuinely theirs to do (maintainer steps) and which are implementation the pipeline did not finish. When unfinished implementation remains, the report says the lifecycle stalled rather than inviting a normal review. Standing instructions that are not discrete work items are not presented as work at all.

**Why this priority**: This is the defect still live after #996 (#1022's 17 lines). It is the owner's only signal at the end of a lifecycle; a list that mislabels unfinished code as owner work either costs the owner a manual implementation or hides a stall behind a "review the PR" invitation.

**Independent Test**: Run finalize against a fixture tasks.md containing a mix of checked tasks, unchecked maintainer-tagged tasks, unchecked ordinary code tasks and standing instructions, and confirm the announcement lists exactly the maintainer tasks under maintainer steps, exactly the code tasks under unfinished implementation with a stall statement, and omits the standing instructions.

**Acceptance Scenarios**:

1. **Given** a tasks.md whose only unchecked items are maintainer-tagged tasks, **When** finalize announces remaining work, **Then** it lists them as maintainer steps and makes no stall statement.
2. **Given** a tasks.md with at least one unchecked untagged implementation task, **When** finalize announces remaining work, **Then** it lists those tasks under a separate "unfinished implementation" heading and states that the lifecycle stalled with implementation outstanding, instead of the ordinary "review the PR" framing.
3. **Given** a tasks.md whose unchecked lines include standing instructions (e.g. "keep the gates green after each cycle", "run the suite and fix the fallout" with no discrete deliverable), **When** finalize announces remaining work, **Then** those lines appear in neither list.
4. **Given** a tasks.md with no unchecked work items after standing instructions are excluded, **When** finalize runs, **Then** it announces that no manual work remains.

---

### User Story 2 - Maintainer-only tasks never block the implementation (Priority: P1)

When the tasks stage generates a task that only a maintainer can perform — dispatching a real run, reading or setting repository variables, opening or merging a separate human-merged PR, a post-merge proof — it marks the task as a maintainer task and places it outside the phases implement must complete in order. Implement skips such tasks and continues with ordinary code tasks instead of halting at them.

**Why this priority**: A maintainer task in a blocking phase can stop every cycle before it reaches code (#972 T001–T004). It also feeds Story 1: without a marker, finalize cannot tell maintainer steps from unfinished code deterministically.

**Independent Test**: Generate tasks for a fixture spec that requires a real dispatch and a variable change; confirm those tasks carry the maintainer marker and sit outside Setup/Foundational; run an implement cycle and confirm it completes later code tasks while the maintainer tasks stay unchecked.

**Acceptance Scenarios**:

1. **Given** a spec whose plan requires a real workflow dispatch to prove a change, **When** the tasks stage generates tasks.md, **Then** the proof task carries the maintainer marker and is not in a phase that precedes code tasks.
2. **Given** a tasks.md with an unchecked maintainer-tagged task in an early phase, **When** an implement cycle runs, **Then** the cycle proceeds to the next ordinary task rather than stopping at the maintainer task.
3. **Given** a cycle that leaves only maintainer-tagged tasks unchecked, **When** the read-back computes the loop outcome, **Then** the implementation is treated as complete for loop purposes and the lifecycle proceeds to finalize, with the maintainer tasks reported per Story 1.

---

### User Story 3 - The loop hands off only when continuing cannot help (Priority: P2)

A lifecycle with ordinary implementation tasks still open is not handed to finalize merely because one cycle checked no new task. The stop rule chosen in clarify decides when a zero-progress cycle ends the loop, and every hand-off with implementation outstanding is reported as a stall on the lifecycle issue.

**Why this priority**: The original trigger. After #996 the early-stop evidence is weaker, so it ranks below the still-live reporting defect, but the revisit condition spec 059 FR-011 named has been met.

**Independent Test**: Feed the read-back fixtures for (a) a zero-progress cycle with outstanding code tasks and no stated blocker, (b) a zero-progress cycle naming a concrete blocker, and (c) a cycle that made progress, and confirm each yields the dispatch-or-hand-off outcome the chosen stop rule specifies.

**Acceptance Scenarios**:

1. **Given** a healthy zero-progress cycle that leaves outstanding implementation tasks and is below the iteration cap, **When** the read-back decides the outcome, **Then** it applies the stop rule fixed by FR-005, deterministically from inputs a reviewer can re-derive.
2. **Given** a cycle that made progress and leaves outstanding tasks below the cap, **When** the read-back decides, **Then** another cycle is dispatched (unchanged from spec 059 FR-008).
3. **Given** a cycle that checks the last outstanding implementation task, **When** the read-back decides, **Then** the loop converges in that same cycle (unchanged from spec 059 FR-010b).

---

### User Story 4 - Re-entering implement from review is explicit (Priority: P3)

A maintainer who wants more implement cycles on a lifecycle already in review gets a visible outcome: either the re-entry route works and is documented, or a dispatch that does nothing says why on the lifecycle issue. The maintainer knows how many cycles the re-entry has left.

**Why this priority**: The PR-comment route already works (#982, #991, #990 finished that way). What is missing is legibility: a silent no-op and an undocumented cap interaction.

**Independent Test**: Dispatch implement manually against a fixture lifecycle in review stage and confirm the lifecycle issue receives the outcome required by FR-010, and that the remaining-cycle count reported matches FR-011.

**Acceptance Scenarios**:

1. **Given** a lifecycle whose spec-meta stage is `review`, **When** a maintainer dispatches implement manually, **Then** the lifecycle issue receives a comment stating what happened and why, never silence.
2. **Given** a re-entry into implement from review, **When** a cycle starts, **Then** the iteration cap that applies is the one FR-011 fixes, and the lifecycle issue states how many cycles remain.

---

### Edge Cases

- A task line carries the maintainer marker but also contains code work (e.g. "open the PR and edit X"): the tasks stage MUST split it so the code part is an ordinary task; an unsplit line is treated as a maintainer task for loop purposes and reported as such.
- An existing tasks.md predating this feature has no maintainer markers: every unchecked line is treated as ordinary implementation (today's behaviour), and finalize reports it as unfinished implementation rather than maintainer work, which errs toward the stall signal.
- A stale catch-all line such as `M001 Complete every remaining unchecked task`: treated as a standing instruction, never listed as work.
- A maintainer task that was already done elsewhere (the #1032 constitution amendment): it stays listed as a maintainer step; finalize does not try to detect off-branch completion.
- Every outstanding task is maintainer-tagged and the cycle made zero progress: this is completion for loop purposes, not a stall.
- A cycle that checks one task and unchecks another still counts as no progress (spec 059 FR-010a).
- A cycle that fails (unhealthy) keeps its existing retry/failure handling; the stop rule applies only to healthy cycles.
- A re-entry dispatch arrives while a cycle for the same lifecycle is already running: the per-spec concurrency group serializes it; the no-op explanation (if any) states the actual reason.

## Requirements *(mandatory)*

### Functional Requirements

**Task routing (tasks stage → implement)**

- **FR-001**: The tasks stage MUST mark every task that only a maintainer can perform — a real workflow dispatch or run re-drive, reading or changing repository variables or settings, opening or merging a separate human-merged PR, a post-merge proof, a constitution amendment merge — with a single, machine-readable maintainer marker on the task line, and MUST NOT place such tasks in any phase that precedes ordinary implementation tasks.
- **FR-002**: Implement MUST NOT halt a cycle on an unchecked maintainer-marked task; it continues to the next ordinary task. The marker's presence MUST be detected deterministically from the tasks.md line, never from the agent's judgment at implement time (Principle IX).
- **FR-003**: The loop's outstanding-task count, progress test and convergence decision MUST exclude maintainer-marked tasks and standing instructions, so a cycle that leaves only those unchecked converges.
- **FR-004**: The tasks stage MUST NOT emit standing instructions ("run the gate suite after each cycle", "complete every remaining unchecked task") as checkbox tasks; where such guidance is needed it goes in prose outside the task list. A recognisable standing-instruction form that still appears as a checkbox (including in tasks.md files written before this feature) MUST be identified by a deterministic rule and excluded per FR-003 and FR-007.

**Stop rule (implement read-back)**

- **FR-005**: For a healthy cycle below the iteration cap that checks no new implementation task and leaves implementation tasks outstanding, the read-back MUST [NEEDS CLARIFICATION: which stop rule replaces "one zero-progress cycle ends the loop"? (a) allow N consecutive zero-progress cycles before hand-off; (b) add spec 059 FR-011's deferred "keep working while tasks remain" prompt line, keeping the one-cycle rule; (c) hand off only when the cycle names a concrete blocker, otherwise dispatch another cycle. Precedent check recommends (c).] The decision MUST be computed by deterministic code from inputs a reviewer can re-derive (Principle IX); any agent-supplied input it consumes (e.g. a named blocker under option c) MUST be validated for shape before it can change the outcome.
- **FR-006**: Every hand-off to finalize with implementation tasks still outstanding MUST be reported on the lifecycle issue as a stall, naming the count of outstanding implementation tasks and the reason the loop stopped (zero-progress rule, named blocker, or iteration cap).

**Finalize labelling**

- **FR-007**: Finalize's remaining-work report (the lifecycle-issue announcement and the final PR's remaining-work section) MUST split unchecked items into two lists — "Maintainer steps" (maintainer-marked tasks) and "Unfinished implementation" (every other unchecked task) — and MUST omit standing instructions identified per FR-004. The split MUST be computed deterministically from tasks.md, never by the summarising agent.
- **FR-008**: When "Unfinished implementation" is non-empty, finalize MUST state that the lifecycle stalled with implementation outstanding, and MUST NOT frame the PR as ready for ordinary review. When only "Maintainer steps" remain, it MUST frame them as the owner's follow-up. When both are empty it MUST announce that no manual work remains.
- **FR-009**: The out-of-boundary classification result MUST remain reported as it is today and MUST NOT by itself move a task into "Maintainer steps".

**Re-entry**

- **FR-010**: A manual implement dispatch on a lifecycle whose spec-meta stage is `review` MUST [NEEDS CLARIFICATION: should a review-stage manual dispatch (a) be supported as a documented re-entry that runs a cycle, or (b) stay a no-op that posts on the lifecycle issue why it did nothing and points at the maintainer-comment route? Precedent check recommends (b).] and in either case MUST NOT be silent on the lifecycle issue.
- **FR-011**: A re-entry into implement from review (by whichever route FR-010 supports, including the existing maintainer-comment route) MUST [NEEDS CLARIFICATION: does a re-entry reset the iteration cap (a) no — it uses the remaining iterations under the existing cap; (b) yes — it starts a fresh cap; (c) it grants a fixed small allowance beyond the cap? Precedent check recommends (a).] and the lifecycle issue MUST be told how many cycles remain when the re-entry starts.

**Proof and gates**

- **FR-012**: Each deterministic rule this feature adds (maintainer-marker detection, standing-instruction detection, the stop rule, the finalize split, the re-entry outcome) MUST be covered by a checked-in fixture exercising every failure branch, and by a gate reachable through the gate registry (Principle VIII).
- **FR-013**: The live documentation describing the implement loop's stop rule and finalize's remaining-work report MUST be updated to the new behaviour; spec 059's merged documents are not edited.

### Key Entities

- **Maintainer task**: a tasks.md checkbox line carrying the maintainer marker; work only the owner can do. Excluded from loop progress; reported as a maintainer step.
- **Implementation task**: any unmarked, non-standing checkbox line. Drives the loop's progress and convergence; reported as unfinished implementation if unchecked at finalize.
- **Standing instruction**: guidance phrased as a task but with no discrete deliverable. Not a work item; never counted or listed.
- **Cycle outcome**: the read-back's deterministic decision (converge, dispatch another cycle, hand off as stall) with its reason.
- **Re-entry**: a return to implement after the lifecycle reached review, carrying its remaining-iteration count.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Replaying the #1022 tasks.md through the new finalize split lists zero standing instructions, lists the constitution amendment under maintainer steps, and lists no line under "remaining manual work" that is not a discrete owner action.
- **SC-002**: Replaying #737's tasks.md at its 2026-10-09 finalize, unfinished code tasks such as T011 appear under "Unfinished implementation" with a stall statement — 0 of them under maintainer steps.
- **SC-003**: In a fixture lifecycle whose first phase contains a maintainer task, an implement cycle checks at least one later code task in the same cycle.
- **SC-004**: 100% of hand-offs with outstanding implementation tasks produce a stall comment on the lifecycle issue naming the outstanding count and stop reason.
- **SC-005**: 0 manual implement dispatches on a review-stage lifecycle finish without a lifecycle-issue comment.
- **SC-006**: Every new deterministic rule has a fixture per failure branch, and the local gate suite and CI run the same gates over them.

## Assumptions

- The maintainer marker is a fixed literal token on the task line chosen during planning; spec 059 rejected an implement-time `**BLOCKED**` marker because it was authored judgment at the gate. This marker differs: it is assigned by the tasks stage from a closed list of action kinds (FR-001), it is visible in the tasks PR / auto-commit for review, and the gate that acts on it only checks for its presence. Spec 059's checkbox-delta discriminator stays the progress test; this feature narrows which lines it counts.
- Lifecycles already on `main` or in flight keep their tasks.md as-is; the edge-case defaults above (unmarked = implementation) apply to them.
- The iteration cap default (5) and the per-spec concurrency group are unchanged unless FR-011's answer changes cap behaviour on re-entry.
- The maintainer-comment re-entry route through the PR-conversation stage remains supported whichever FR-010 option is chosen.
- The changes touch the tasks, implement and finalize stage workflows and their shared composites; any new input or output on a published stage workflow is a deliberate widening of the published contract (Principle VII) to be identified in planning.
- #989/#996 (PyYAML in the pinned image) is fixed and out of scope.
