# Feature Specification: Implement Finishes Its Tasks

**Feature Branch**: `spec-draft/123-implement-task-completion`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "Implement finishes its tasks: cycles stop after one slice, unbuildable tasks block convergence, review folds count as tasks" (issue #1111; companion proposal #1110, the lifecycle review gate convergence proposal)

## Clarifications

### Session 2026-11-06

- Q: Which levers are in scope for the first cut? → A: Levers (a) prompt "keep building" change, (c) unbuildable-task classification, (d) buildable-only counting excluding review folds, (e) finalize waits / review gate does not review a final PR with unchecked buildable tasks, and (f) gate-suite prerequisite check. Lever (b) low-progress escalation is deferred to a follow-up until there is evidence whether (a) alone fixes the one-slice-and-stop pattern. Lever (e) lives in this spec; #1110 drops that part.
- Q: What is the low-progress response? → A: Re-prompt on the default tier (Sonnet) with a corrective "keep building" instruction; no automatic Opus escalation (that would need a constitution II amendment and is not wanted). Because lever (b) is deferred, this records the intended direction for the follow-up, not first-cut scope.
- Q: What happens at the iteration cap with buildable tasks unchecked? → A: The lifecycle is handed to a person: held or parked, with the remaining buildable and maintainer-only tasks listed on the lifecycle issue. No final PR is opened (pairs with lever (e)). A lifecycle whose only remaining tasks are maintainer-only counts as converged.

## Background

About half the lifecycles completed since 2026-09-01 posted "Iteration cap reached" (`WING_COMMANDER_MAX_ITERATIONS`, default 5). The issue's investigation of 75 implement-cycle job logs (#1066, #1055, #1074, #1020, #994, #992, #903, #993) found that cycles are neither out of turns (most used 9–39 of 180 turns; the highest raw count was 301 of 450) nor failing (every agent step ended `success`, no 429s). Cycles **stop on their own**. The ranked causes are:

1. A default-tier (Sonnet) cycle often builds one slice of 2–4 adjacent tasks and stops well inside its budget, while a cycle that keeps going builds the whole spec. The likely trigger is the phase-by-phase checkpoints in the implement skill and the prompt's "push after every phase" (inferred: the transcripts could not be downloaded).
2. Tasks no cycle can finish block convergence and cause zero-progress cycles: post-merge proofs not tagged `[maintainer]` (#903 T033), "run the gate suite" tasks while the cycle reports it cannot run the suite (#1020, #992), writes under `.claude/` that are denied (#994 T005), work waiting on a maintainer drill (#1055 T017).
3. After the cap, folded review findings take every cycle and are counted as implementation tasks; no task was built after the cap on #1066 or #1055.
4. Minor: converge sometimes adds tasks, and cycles spend 10–29 minutes running the gate suite themselves.

A higher iteration cap or turn budget would not have finished these lifecycles: #1066 averaged 2.6 tasks a cycle, several lifecycles were stuck on tasks no cycle can finish, and #1020 already ran with a cap of 12.

This spec builds on spec 117 (implement stall handoff), which introduced the `[maintainer]` task tag and the "standing instruction" line class in the one shared tasks.md checkbox counter, and complements #1110, which addresses the lifecycle review gate's own convergence.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A cycle keeps building until the buildable work is done (Priority: P1)

As the maintainer who labelled a spec, I want each implement cycle to keep building every buildable unchecked task, across phase boundaries, until the list is done or the cycle's budget runs out, so a spec that one cycle could finish is not spread over five.

**Why this priority**: This is the top-ranked cause. Lifecycles where one cycle kept going (#992, #903, #993, #1074) built nearly the whole spec in cycle 1; lifecycles where cycles stopped after a slice (#1066, #994, #1020) hit the cap with most tasks open.

**Independent Test**: Run implement on a spec with several phases of buildable tasks and enough budget; confirm one cycle ticks tasks in more than one phase, still pushes at each phase boundary, and ends only when no buildable task is left or the budget is spent.

**Acceptance Scenarios**:

1. **Given** a tasks.md with three phases of buildable unchecked tasks and a cycle with ample turn budget, **When** the cycle completes phase 1, **Then** it pushes its work and continues into phase 2 rather than ending the run.
2. **Given** a cycle that has ticked every buildable task, **When** only `[maintainer]` or otherwise unbuildable tasks remain, **Then** the cycle ends and reports that no buildable work remains.
3. **Given** a cycle that ticks 2 or fewer buildable tasks while buildable tasks remain and budget was left over, **When** the cycle ends, **Then** its cycle outcome records the tasks ticked, buildable tasks remaining and turns used (FR-003), so the evidence for the deferred low-progress follow-up (Story 4) is collected; the first cut does not change the next cycle's dispatch.

---

### User Story 2 - Tasks no cycle can finish never block convergence (Priority: P1)

As the maintainer, I want tasks that an automated cycle cannot complete — post-merge proofs, maintainer drills, "run the gate suite" checks the job cannot run, and writes under `.claude/` — to be recognised as such before cycles are spent on them, so they are handed to a person instead of holding the loop open until the cap.

**Why this priority**: Four of the investigated lifecycles (#1055, #903, #992, #1020) were stuck on exactly these tasks; no number of further cycles could have finished them.

**Independent Test**: Generate or converge a tasks.md containing a post-merge proof, a drill, an agent-run gate-suite task and a `.claude/` write; confirm each is classified as maintainer-only (or routed out), excluded from the buildable count, listed on the lifecycle issue as remaining human work, and that a cycle with only those left converges.

**Acceptance Scenarios**:

1. **Given** a task whose deliverable is a post-merge proof (re-driving a run after merge), **When** tasks are generated or converged, **Then** the task is classified maintainer-only and never counted as outstanding buildable work.
2. **Given** a task that requires writing under any `.claude/` directory, **When** it is classified, **Then** it is maintainer-only, because automated agents are denied those writes (constitution V).
3. **Given** a task that only says to run the gate suite, **When** the implement job is one where the suite cannot run, **Then** the task neither blocks convergence nor causes a zero-progress cycle.
4. **Given** a lifecycle whose only unchecked tasks are maintainer-only, **When** the cycle ends, **Then** the lifecycle converges and the remaining tasks are reported on the lifecycle issue as human work (reusing spec 117's remaining-work report).
5. **Given** a task that is ambiguous between buildable and maintainer-only, **When** it is classified, **Then** it is treated as buildable (ambiguity counts as implementation, matching spec 117's rule).

---

### User Story 3 - Review fixes do not consume the implementation budget (Priority: P2)

As the maintainer, I want folded review findings tracked separately from the spec's own implementation tasks, so the iteration cap measures progress on the spec, and review-fix cycles do not crowd out the tasks the spec still needs.

**Why this priority**: On #1066 and #1055 every post-cap cycle was spent on review fixes and no spec task was built. It matters only once Stories 1–2 let cycles reach the review gate with work left.

**Independent Test**: Fold review findings into a lifecycle with buildable tasks outstanding; confirm the findings are not counted toward the convergence count or the cap, that finalize does not open the final PR, and that the review gate does not review a final PR, while buildable tasks remain (FR-010).

**Acceptance Scenarios**:

1. **Given** a lifecycle with in-scope review findings folded into tasks.md, **When** buildable-task progress is computed for convergence and the cap, **Then** folded findings are excluded from that count.
2. **Given** a review-fix cycle on a lifecycle that still has buildable spec tasks, **When** the cycle runs, **Then** it also works on those outstanding tasks rather than ending after the fixes.
3. **Given** buildable spec tasks remain unchecked, **When** finalize would open the final PR, **Then** it does not open it until those tasks are done or handed off.
4. **Given** a final PR whose lifecycle still has unchecked buildable tasks, **When** the lifecycle review gate would review it, **Then** the review gate does not review it.

---

### User Story 4 - A low-progress cycle gets a different next step (Priority: P2, deferred follow-up)

> **Deferred (clarify 2026-11-06)**: lever (b) is out of the first cut and recorded as a follow-up on the Roadmap, pending evidence on whether Story 1's prompt change alone fixes the one-slice-and-stop pattern. This story records the intended direction for that follow-up; FR-011–FR-013 are not implemented in the first cut.

As the maintainer, I want a cycle that made little progress while buildable work remained to trigger a corrective re-prompt on the default tier rather than an identical next cycle that is likely to stop the same way.

**Why this priority**: It is the backstop for Story 1: if the prompt change alone does not keep a cycle going, the pipeline should notice and respond deterministically rather than burn the cap.

**Independent Test**: Simulate a cycle that ticks 1 task with buildable tasks remaining and turns left; confirm the next cycle is dispatched with the chosen low-progress response and that the response is recorded on the lifecycle issue.

**Acceptance Scenarios**:

1. **Given** a cycle that ticked 2 or fewer buildable tasks, ended `success`, left buildable tasks unchecked and used less than its turn budget, **When** the next cycle is decided, **Then** the next cycle is dispatched on the default tier (Sonnet) with a corrective "keep building" instruction; the model is not escalated to Opus automatically (constitution II allows Opus for implement only by explicit opt-in).
2. **Given** a cycle that ticked 2 or fewer tasks because it ran out of turns or failed, **When** the next cycle is decided, **Then** the low-progress response is not applied (existing truncation and failure handling apply).
3. **Given** a low-progress response was applied, **When** the lifecycle issue is read, **Then** it states which cycle triggered it, the tasks-ticked count, and the response taken.

---

### User Story 5 - A lifecycle at the cap with buildable work has a defined outcome (Priority: P3)

As the maintainer, I want a lifecycle that reaches the iteration cap with buildable tasks still open to end in one defined, announced state, so I know whether it will continue, needs me, or was extended.

**Why this priority**: With Stories 1–4 in place this should be rare; it must still be unambiguous when it happens.

**Independent Test**: Drive a lifecycle to the cap with buildable tasks remaining; confirm the defined outcome occurs and is reported on the lifecycle issue with the remaining buildable and maintainer-only tasks listed.

**Acceptance Scenarios**:

1. **Given** a lifecycle at the iteration cap with buildable tasks unchecked, **When** the cap is evaluated, **Then** the lifecycle is handed to a person: it is held or parked, the remaining buildable and maintainer-only tasks are listed on the lifecycle issue, and no final PR is opened (FR-010).
2. **Given** a lifecycle at the cap with only maintainer-only tasks unchecked, **When** the cap is evaluated, **Then** it is treated as converged (Story 2), not as cap-reached.

---

### Edge Cases

- A cycle ticks tasks in a later phase while an earlier-phase task stays unchecked because it is blocked on another task: progress still counts; the blocked task stays buildable unless it is classified maintainer-only.
- A task is re-tagged `[maintainer]` mid-lifecycle by converge: it leaves the buildable total; the change must not read as implementation progress (spec 117's tag-agnostic counting by task id applies).
- Converge adds new buildable tasks: they join the buildable count; the cycle that added them is not judged low-progress solely because the total grew.
- The gate suite becomes runnable in implement jobs (the issue asks to check whether `job_workflow_sha` is still empty after #1077): a "run the gate suite" task is then buildable, and classification must follow the job's actual capability, not a fixed assumption.
- A folded review finding duplicates an existing spec task: it is counted once, as the spec task.
- A spec whose every task is maintainer-only: implement converges immediately and reports all tasks as human work.
- (Deferred follow-up) Low-progress response on a lifecycle already running on Opus (`model:opus` or repo opt-in): the re-prompt applies on the lifecycle's existing tier; the response never changes the model.
- (Deferred follow-up) `model:haiku` trial lifecycles: the low-progress re-prompt stays on the trial's tier and respects its existing one-tier-up rule; it never skips to Opus.

## Requirements *(mandatory)*

### Functional Requirements

**Cycle behaviour (Story 1)**

- **FR-001**: The implement cycle's instructions MUST direct the agent to keep building every buildable unchecked task across phases until none remain or the budget is exhausted, and MUST state that a phase checkpoint is not a stopping point.
- **FR-002**: The implement cycle MUST continue to push its work at each phase boundary, so a cycle interrupted mid-run loses at most one phase of work.
- **FR-003**: Each cycle's outcome MUST record the number of buildable tasks ticked in that cycle, the buildable tasks remaining, and the turns used against the budget, derived by deterministic code from tasks.md at the cycle's base and tip (not from the agent's own report).

**Unbuildable tasks (Story 2)**

- **FR-004**: The pipeline MUST classify tasks as buildable or maintainer-only. At minimum these classes are maintainer-only: post-merge proofs (re-driving a run after merge), maintainer drills, writes under any `.claude/` directory, and gate-suite runs in a job where the suite cannot run.
- **FR-005**: The classification that decides convergence MUST be made by deterministic code (constitution IX); an agent (tasks or converge) MAY propose a `[maintainer]` tag, but a deterministic pattern check MUST also classify the listed classes so an untagged instance cannot block convergence.
- **FR-006**: Maintainer-only tasks MUST be excluded from the buildable count used for convergence, the iteration cap and the low-progress check, and MUST be listed on the lifecycle issue as remaining human work.
- **FR-007**: A task that matches no maintainer-only class, or matches ambiguously, MUST be treated as buildable.
- **FR-008**: The pipeline MUST determine whether the gate suite can run in implement jobs on current `main` (after #1077), and the classification of gate-suite tasks MUST follow that actual capability.

**Review folds (Story 3)**

- **FR-009**: Folded review findings MUST be distinguishable from spec tasks in tasks.md by deterministic code and MUST NOT count toward the buildable count used for convergence or the iteration cap.
- **FR-010**: While buildable spec tasks remain unchecked, finalize MUST NOT open the final PR, and the lifecycle review gate MUST NOT review a final PR whose lifecycle still has unchecked buildable tasks. This behaviour lives in this spec only; companion proposal #1110 does not implement it.

**Low progress (Story 4) — deferred follow-up, not in the first cut (FR-016)**

- **FR-011**: A cycle MUST be classified as low-progress when it ended successfully, ticked 2 or fewer buildable tasks, left buildable tasks unchecked, and did not exhaust its turn budget.
- **FR-012**: After a low-progress cycle, the next cycle MUST be dispatched on the default tier (Sonnet), or the lifecycle's existing tier if it already differs, with a corrective "keep building" instruction, decided by deterministic code; the response MUST NOT escalate the model (automatic Opus escalation would need a constitution II amendment), and every agent step MUST still declare an explicit model and turn budget (constitution II).
- **FR-013**: Every low-progress response MUST be announced on the lifecycle issue with the triggering cycle, its tasks-ticked count and the response taken.

**Cap outcome (Story 5)**

- **FR-014**: A lifecycle at the iteration cap with only maintainer-only tasks unchecked MUST be reported as converged, not as cap-reached.
- **FR-015**: A lifecycle at the iteration cap with buildable tasks unchecked MUST be handed to a person: held or parked, with no final PR opened, and announced on the lifecycle issue with the remaining buildable and maintainer-only tasks listed.

**Scope (all stories)**

- **FR-016**: The first cut MUST implement levers (a) prompt "keep building" change (FR-001–FR-003), (c) unbuildable-task classification (FR-004–FR-007), (d) buildable-only counting excluding review folds (FR-009), (e) finalize waits and the review gate skips a final PR with unchecked buildable tasks (FR-010), and (f) gate-suite prerequisite check (FR-008), plus the cap outcome (FR-014–FR-015). Lever (b) low-progress handling (FR-011–FR-013) is out of the first cut and MUST be recorded on the Roadmap as a follow-up, not dropped.
- **FR-017**: Every new deterministic check this feature adds (classification, buildable counting, finalize/review-gate wait) MUST be exercised by checked-in fixtures covering each failure branch (constitution VIII), and MUST extend the existing single home for tasks.md counting rather than add a second counter.

### Key Entities

- **Buildable task**: an unchecked tasks.md line that an automated implement cycle can complete; the only line class that counts toward convergence, the cap and low-progress.
- **Maintainer-only task**: a line tagged `[maintainer]` or matching a deterministic unbuildable class; listed as human work, never counted as outstanding.
- **Standing instruction**: an existing (spec 117) line class such as "run the gate suite before pushing"; counted in neither total.
- **Folded review finding**: a tasks.md line added by the lifecycle review gate from an in-scope finding; tracked separately from spec tasks.
- **Cycle outcome**: per-cycle record of buildable tasks ticked, buildable remaining and turns used (the low-progress flag arrives with the deferred lever (b) follow-up).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across the first 10 lifecycles completed after this feature merges, fewer than 20% post "Iteration cap reached" with buildable tasks remaining (baseline: about 50% since 2026-09-01).
- **SC-002**: The median number of buildable tasks ticked per default-tier cycle that has buildable work and budget left is at least twice the investigated baseline of about 2.6 tasks per cycle.
- **SC-003**: Zero cycles end with zero buildable progress solely because the only remaining tasks are maintainer-only.
- **SC-004**: In 100% of lifecycles that reach a review gate, folded review findings do not appear in the convergence or cap count.
- **SC-005**: Every cap outcome (and, once the lever (b) follow-up lands, every low-progress response) is visible on the lifecycle issue alone, without opening job logs.

## Assumptions

- The default iteration cap (5) and the per-cycle turn budget stay as they are; the issue's evidence is that neither was the binding constraint.
- Spec 117's `[maintainer]` tag, standing-instruction class and the shared checkbox counter (`count-tasks-checkboxes.sh`) are the base this feature extends; there is one home for task classification.
- Who classifies: the tasks stage and converge propose `[maintainer]` tags, and a deterministic pattern list is the backstop that decides (constitution IX precedent; spec 117's tag is already applied by agents and read by code). Clarify may revisit this.
- "Low progress" uses the issue's threshold of 2 or fewer buildable tasks ticked; it is a tunable default, not a contract.
- Cycles running the gate suite themselves (cause 4) is addressed only through FR-008's classification; reducing suite run time is out of scope.
- #1110 (lifecycle review gate convergence) proceeds in parallel; finalize's wait condition and the review gate's skip of a final PR with unchecked buildable tasks live in this spec only (FR-010), and #1110 drops that part.
- The causal claim about phase checkpoints is inferred, not proven; SC-002 is how the prompt change is judged, and its result decides whether the deferred lever (b) follow-up is needed.
