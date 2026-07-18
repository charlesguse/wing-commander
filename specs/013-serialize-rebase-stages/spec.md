# Feature Specification: Keep Auto-Rebase From Force-Pushing a Spec Branch Out From Under an In-Flight Stage

**Feature Branch**: `spec-draft/013-serialize-rebase-stages`

**Created**: 2026-07-18

**Status**: Draft

**Input**: User description: "When a push to the default branch lands while a stage agent is mid-run on a spec branch, the auto-rebase workflow force-pushes that spec branch out from under the agent. The agent's eventual push is rejected (non-fast-forward), the stage's verify step fails the run, and the agent's work (and cost) is discarded. A manual re-dispatch recovers cleanly, but until then the lifecycle is stalled. Root cause: auto-rebase and the per-spec stages serialize on disjoint concurrency groups, so a rebase for a spec can run at the same time as a stage run for that same spec. Fix so that a rebase never disturbs an in-flight stage run for the same specification, while unrelated specifications still run concurrently and in-flight branches still get kept current."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stage run is never interrupted by an auto-rebase of the same specification's branch (Priority: P1)

While a stage is running against a specification's working branch — an agent has checked out the branch and is producing its artifacts — a change lands on the main line and would trigger an auto-rebase of that same branch. The rebase does not run concurrently with the stage: it is held until the stage finishes, so the branch is never force-updated underneath the running agent. When the stage completes and publishes its result, its push is accepted because the branch has not moved beneath it. The agent's work — and the cost of producing it — is preserved, and the lifecycle advances without a manual re-dispatch.

**Why this priority**: This is the entire point of the change. Today a rebase and a stage for the same specification serialize on unrelated groups, so a routine main-line push — including the pipeline's own fix and finalize merges, which is exactly when rebases fire — can force-push a branch out from under a working agent. The stage's push is then rejected as non-fast-forward, its verify step fails the run, the agent's work and spend are discarded, and someone has to notice and re-dispatch by hand. Preventing that collision is what makes the pipeline safe to run unattended on a busy repository.

**Independent Test**: Start a stage run against a specification's working branch and, while it is mid-run, advance the main line so an auto-rebase of that same branch would be triggered. Verify that the branch is not force-updated while the stage is running, that the stage's publish is accepted, and that the run succeeds without any human re-dispatch.

**Acceptance Scenarios**:

1. **Given** a stage running against a specification's working branch, **When** the main line advances such that an auto-rebase of that same branch would trigger, **Then** the rebase does not run concurrently with the stage and the working branch is not force-updated while the stage is in progress.
2. **Given** a stage that was running while a main-line advance occurred, **When** the stage finishes and publishes its result, **Then** the publish is accepted (the branch did not move beneath it) and the run succeeds.
3. **Given** a specification whose stage completed without interruption, **When** the lifecycle continues, **Then** no manual re-dispatch of that stage is required to recover from a force-push collision.

---

### User Story 2 - A stage dispatched while a rebase is in progress starts from the rebased branch (Priority: P2)

The collision also runs the other way: an auto-rebase of a specification's working branch is already in progress when a stage for that same specification is dispatched. The stage does not begin working against a branch that is being rewritten underneath it; it waits until the in-progress rebase has settled and then works from the branch as the rebase left it. Either the rebase completes before the stage starts, or — if the rebase is deferred instead — the stage proceeds against the un-rebased branch, but in no case do the two mutate the same branch at the same time.

**Why this priority**: The reported failure is a rebase interrupting a stage, but the same disjoint-group gap allows a stage to start against a branch a rebase is mid-rewrite. Ordering the two so only one touches a given specification's branch at a time closes the collision from both directions. It is second because the observed, repeatedly-hit instance is the rebase-interrupts-stage direction in User Story 1.

**Independent Test**: Begin an auto-rebase of a specification's working branch and, while it is in progress, dispatch a stage for that same specification. Verify that the stage and the rebase do not modify the branch concurrently, and that when the stage runs it operates on the branch as left by the settled rebase (or on the un-rebased branch if the rebase was deferred), never on a half-rewritten branch.

**Acceptance Scenarios**:

1. **Given** an in-progress auto-rebase of a specification's working branch, **When** a stage for that same specification is dispatched, **Then** the stage does not modify the branch while the rebase is still modifying it.
2. **Given** an auto-rebase that completes before the stage begins its work, **When** the stage runs, **Then** it operates on the branch as the completed rebase left it.
3. **Given** a rebase and a stage contending for the same specification's branch, **When** both have been requested, **Then** at most one of them is mutating that branch at any moment.

---

### User Story 3 - Unrelated specifications still run concurrently and in-flight branches still stay current (Priority: P2)

Preventing the collision must not serialize the whole pipeline or defeat the drift protection auto-rebase exists to provide. Rebases and stages for *different* specifications continue to run at the same time, so one specification's activity never blocks another's. And a rebase that is held or deferred because a stage for the same specification is running is not lost: the branch is still brought current — when the stage frees the branch, on the next main-line advance, or on the recurring nightly rebase — so in-flight branches keep landing on final review already based on current main.

**Why this priority**: The fix is only acceptable if it is surgical. Over-serializing would trade a rare collision for chronic pipeline-wide queuing, and dropping deferred rebases entirely would reintroduce the branch drift that auto-rebase (spec 008) was built to eliminate. Preserving cross-specification concurrency and eventual currency is what keeps the fix from regressing throughput or drift.

**Independent Test**: With work in flight for two different specifications, trigger a rebase for one and a stage for the other and confirm they run concurrently. Separately, cause a rebase to be held or deferred by an in-flight stage for the same specification and verify the branch is subsequently brought current (after the stage frees it, on a later main-line advance, or on the nightly rebase) rather than being permanently skipped.

**Acceptance Scenarios**:

1. **Given** a rebase for specification A and a stage for a different specification B, **When** both are triggered, **Then** they run concurrently and neither blocks the other.
2. **Given** a rebase for a specification that was held or deferred because a stage for that same specification was running, **When** the contention clears, **Then** the specification's working branch is brought current rather than left permanently un-rebased.
3. **Given** no stage is running for a specification, **When** a main-line advance triggers a rebase of its branch, **Then** the rebase proceeds exactly as it does today, with no added delay.

---

### Edge Cases

- **Main-line advance from the pipeline's own automation** (a fix or finalize merge) lands while a stage for the affected specification is mid-run: this is the common trigger in practice, and the rebase it would fire MUST NOT run concurrently with that stage — see FR-001, FR-002.
- **A stage and a rebase for the same specification are both requested at nearly the same instant**: the two MUST be ordered so only one mutates the branch at a time, regardless of arrival order — see FR-003.
- **The nightly scheduled rebase fires while a stage is running** for one of the in-flight specifications: the same non-interference applies to the scheduled rebase as to the push-triggered one — see FR-002.
- **Two different stages for the same specification would somehow overlap** (rather than the normal one-stage-at-a-time progression): per the resolved Question 1 (Option B, full per-specification serialization), this is now in scope — any two operations touching the same specification's working branch, including stage-vs-stage, MUST NOT overlap — see FR-001 and FR-008.
- **Intake (which has no specification slug yet) and the clarify stage (which is keyed to the lifecycle issue, not a branch)** neither rebase nor mutate a specification working branch in a way that collides with auto-rebase; these are excluded from the serialization and keep their current behavior — see FR-005.
- **A rebase is deferred while a stage runs and the stage then does not finish for a long time**: the deferred rebase MUST NOT be silently dropped forever; currency is restored by the next opportunity (stage completion, a later main-line advance, or the nightly rebase) — see FR-004.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: For any single specification, the system MUST NOT run an auto-rebase of that specification's working branch at the same time as a stage run operating on that same specification. The two MUST be mutually exclusive per specification so that neither modifies the branch while the other is modifying it.
- **FR-002**: When a stage is running against a specification's working branch, the system MUST NOT force-update (rebase-and-publish) that branch until the stage has finished — this applies equally to rebases triggered by a main-line advance (including advances originating from the pipeline's own automation) and by the nightly schedule.
- **FR-003**: The mutual exclusion in FR-001 MUST hold regardless of which operation was requested first — a stage dispatched while a rebase is in progress, and a rebase triggered while a stage is in progress, MUST both resolve to one-at-a-time access to the specification's branch rather than concurrent access.
- **FR-004**: A rebase that is held or deferred because a stage for the same specification is running MUST NOT be permanently lost; the system MUST still bring the branch current at the next opportunity — when the branch is freed, on a subsequent main-line advance, or on the recurring nightly rebase — so the branch-currency guarantee of the existing auto-rebase behavior is preserved.
- **FR-005**: The system MUST scope the mutual exclusion to a single specification and to operations that actually contend for that specification's working branch. Rebases and stages for *different* specifications MUST continue to run concurrently, and pipeline steps that do not mutate a specification's working branch in a way that collides with auto-rebase (for example, intake before a slug exists, and the clarify stage keyed to the lifecycle issue) MUST retain their current behavior and MUST NOT be blocked by this change.
- **FR-006**: The change MUST NOT alter what a rebase or a stage does when there is no contention — an uncontended rebase or stage MUST run exactly as it does today, with no added delay or behavioral difference.
- **FR-007**: The change MUST preserve the existing failure-safety and reporting behavior of the affected stages and of auto-rebase — it MUST NOT introduce silent branch corruption, MUST NOT cause a stage's work to be discarded due to a same-specification force-push, and MUST NOT suppress the existing loud, deterministic verification that guards each stage's publish.
- **FR-008**: Per the resolution of Question 1 (Option B, full per-specification serialization), the mutual exclusion MUST extend to all slug-bearing operations that mutate a single specification's working branch — the auto-rebase and every stage run — placing them under one ordering so that no two such operations for the same specification ever run concurrently, including two stage runs for the same specification. This subsumes the rebase-vs-stage exclusion of FR-001 as the specific reported case, and MUST remain scoped per specification so that FR-005's cross-specification concurrency is unaffected.

### Key Entities

- **Specification working branch**: A specification's long-lived working branch, the shared resource that both auto-rebase and the stage runs mutate and that this change protects from concurrent mutation.
- **Auto-rebase operation**: The existing behavior that rebases an in-flight specification's working branch onto current main and force-updates it, triggered by main-line advances and a nightly schedule.
- **Stage run**: A pipeline stage (for example, plan, tasks, implement, finalize) executing against a specification's working branch, checking it out, producing artifacts, and publishing its result.
- **Contention**: The condition where an auto-rebase and a stage run would both act on the same specification's working branch at overlapping times — the situation this change orders into one-at-a-time access.
- **Lifecycle issue**: The per-specification issue every stage and the rebase report to; unchanged by this feature except that fewer manual re-dispatch notices should be needed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A main-line advance (including one from the pipeline's own automation) that occurs while a stage is running for the affected specification never causes that stage's publish to be rejected as non-fast-forward, and never discards the agent's completed work.
- **SC-002**: The manual re-dispatch that today recovers an interrupted stage is no longer required for the rebase-vs-stage collision; the lifecycle advances without human intervention in that scenario.
- **SC-003**: Rebases and stages for different specifications continue to run concurrently, so this change adds no measurable end-to-end delay to the pipeline in the absence of same-specification contention.
- **SC-004**: Every in-flight specification working branch is still brought current — a rebase held or deferred by same-specification contention is subsequently applied — so branches continue to reach final review already based on current main, exactly as before this change.
- **SC-005**: No specification's stage work is lost and no branch is left corrupted as a result of a same-specification rebase/stage overlap under any triggering order.

## Assumptions

- "Specification working branch," "auto-rebase," "the main line," "the pipeline's own automation," "stage run," "nightly schedule," and "lifecycle issue" refer to the same concepts established by the earlier pipeline stages (notably the auto-rebase behavior specified in spec 008 and the reusable stages in spec 010); this change introduces no new such concepts and only orders existing operations so they do not collide on the same branch.
- The intended resolution of contention is that the two operations serialize (queue and run one after the other) rather than one cancelling the other, consistent with the existing convention that these operations are not cancelled in progress; whether a deferred rebase queues behind the stage or is skipped-and-retried on the next trigger is a design/implementation decision left to planning, provided FR-004's currency guarantee holds.
- Under normal operation the pipeline runs one stage at a time per specification, so same-specification stage-vs-stage overlap is not the reported problem; per the resolved Question 1 (Option B, full per-specification serialization), preventing same-specification stage-vs-stage overlap is now also required, so the chosen mechanism MUST place the rebase and all slug-bearing stages for one specification under a single ordering (see FR-008).
- The affected stages and auto-rebase keep their existing least-privilege tool allowlists, model tiering, and deterministic verification; this change adjusts only how same-specification operations are ordered, not what any stage or the rebase is permitted to do.
- The fix applies to the reusable pipeline stages, so external adopters of the pipeline inherit the corrected behavior identically, consistent with the portability principle.

## Clarifications

### Session 2026-07-18

- **Q1: Scope of the mutual exclusion — rebase-vs-stage only, or full per-specification serialization?** → **A: Option B — Full per-specification serialization.** The auto-rebase and all slug-bearing stages for a single specification share one ordering, guaranteeing that no two same-specification operations touching its working branch — including stage-vs-stage — ever run concurrently. This closes the reported rebase-vs-stage collision and, as a side effect, prevents any same-specification overlap; it matches the issue's preferred fix direction. Answered by @charlesguse on lifecycle issue #53. Encoded in FR-001, FR-008, the Edge Cases, and the Assumptions above.
