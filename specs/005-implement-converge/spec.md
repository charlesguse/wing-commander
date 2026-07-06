# Feature Specification: Implement/Converge Stage — Iterative Build to Convergence

**Feature Branch**: `spec-draft/005-implement-converge`

**Created**: 2026-07-06

**Input**: User description: "Please spec out stage 4 as per the architecture doc." (from docs/architecture.md: once a task list exists for a specification, the pipeline should build the task list on the specification's persistent working branch, then reassess for remaining gaps; while gaps remain it repeats the build-and-reassess cycle, bounded by a configurable maximum number of cycles; when the work converges it hands off to finalization, and when the cap is reached without converging it reports the remaining work and hands off to finalization flagged as not converged, keeping the lifecycle issue current each cycle.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A ready task list is built to completion automatically (Priority: P1)

A specification has a task list ready and has been handed off to this stage. Without anyone doing it by hand, the pipeline works through the task list on the specification's persistent working branch, then reassesses whether anything is still missing. If the reassessment finds remaining work, the build-and-reassess cycle repeats; once nothing remains, the specification is handed off to the finalization stage.

**Why this priority**: This is the pipeline's stage that actually turns a plan-derived task list into working code. It is the point where the feature is built; nothing downstream (finalization, cleanup) is meaningful until the work has been implemented and judged complete.

**Independent Test**: Hand a specification with a ready task list to this stage and verify that its task list is worked through on the persistent working branch, that a convergence reassessment runs afterward, that the cycle repeats while the reassessment reports remaining work, and that the specification is handed off to finalization once the reassessment reports no remaining work — all with no human performing the build, reassessment, or hand-off steps.

**Acceptance Scenarios**:

1. **Given** a specification has been handed to this stage with a ready task list, **When** the stage runs, **Then** the task list is worked through and progress is committed to the specification's persistent working branch.
2. **Given** an implementation pass has completed, **When** the convergence reassessment runs and finds remaining work, **Then** the remaining work is recorded and another build-and-reassess cycle begins for the specification at the next iteration.
3. **Given** the convergence reassessment reports that no remaining work exists, **When** the cycle completes, **Then** the specification is handed off to the finalization stage.

---

### User Story 2 - Convergence is bounded and always resolves to a hand-off (Priority: P2)

The build-and-reassess loop cannot run forever. A configurable maximum number of cycles bounds it. If the work converges within that bound, finalization proceeds normally. If the bound is reached while work still remains, the pipeline does not silently stall or loop endlessly: it reports the remaining work on the lifecycle issue and still hands off to finalization, flagged so that everyone downstream knows the feature was handed over without fully converging.

**Why this priority**: Without a hard bound and a defined outcome at that bound, a specification whose work never fully converges (or repeatedly regenerates the same gaps) could consume unbounded effort or get stuck with no visible result. Guaranteeing that every specification reaching this stage ends in exactly one finalization hand-off — converged or not — is what makes the stage safe to run automatically.

**Independent Test**: Configure a low cycle maximum and hand a specification to the stage such that its reassessment keeps finding remaining work; verify the number of cycles never exceeds the configured maximum, that the remaining work is reported on the lifecycle issue, and that finalization is still handed off exactly once, flagged as not converged.

**Acceptance Scenarios**:

1. **Given** a specification whose convergence reassessment keeps reporting remaining work, **When** the configured maximum number of cycles is reached, **Then** no further build-and-reassess cycle begins.
2. **Given** the configured maximum has been reached without convergence, **When** the stage stops cycling, **Then** the remaining work is reported on the lifecycle issue and the specification is handed off to finalization flagged as not converged.
3. **Given** the work converges before the maximum is reached, **When** the reassessment reports no remaining work, **Then** the specification is handed off to finalization without the not-converged flag.

---

### User Story 3 - Progress and model choice are visible and configurable (Priority: P3)

Anyone following the lifecycle issue can see the stage advancing: each build-and-reassess cycle posts a short progress update, so a maintainer knows how many cycles have run and whether the feature is converging — without inspecting the persistent working branch directly. A repository can also choose how much capability to spend on implementation: a default model applies, and a specification can opt in to a higher-capability model for its implementation via a designated label on its lifecycle issue.

**Why this priority**: The lifecycle issue is the single place people check on progress; per-cycle updates make an otherwise-opaque, potentially multi-cycle stage legible. The model choice matters for cost and quality but has a sensible default, so it is a lower-priority refinement on top of the core loop.

**Independent Test**: Run the stage for a specification and verify a progress update is posted to its lifecycle issue for each cycle; separately, apply the higher-capability opt-in label to a specification's lifecycle issue and verify its implementation uses the higher-capability model instead of the default.

**Acceptance Scenarios**:

1. **Given** the stage runs a build-and-reassess cycle for a specification, **When** the cycle completes, **Then** a progress update for that cycle is posted to the specification's lifecycle issue.
2. **Given** a specification's lifecycle issue does not carry the higher-capability opt-in, **When** implementation runs, **Then** it uses the default implementation model.
3. **Given** a specification's lifecycle issue carries the higher-capability opt-in, **When** implementation runs, **Then** it uses the higher-capability model.

---

### Edge Cases

- The convergence reassessment keeps reporting remaining work every cycle (for example, the same gaps regenerate without being resolved): the configured cycle maximum bounds the loop, and the specification is still handed off to finalization flagged as not converged rather than cycling forever.
- The same hand-off for a specification at the same iteration is observed more than once (for example, a retried or duplicated dispatch): the stage must not run a second build-and-reassess cycle, post a duplicate progress update, or trigger a duplicate finalization hand-off for that same iteration.
- An implementation or convergence pass cannot complete because of a resource or tooling failure (as distinct from completing but not yet converging): the stage automatically retries the same iteration once on the next-higher-capability model tier (for example, Haiku → Sonnet → Opus); if that retry also fails — or the failing pass was already running on the highest-capability tier, leaving no tier to escalate to — the specification is marked stalled for manual restart and the failure is surfaced on the lifecycle issue, rather than silently advancing or silently dropping the specification.
- The hand-off cannot be matched to a valid specification (its target working directory, lifecycle record, or task list is missing or inconsistent): the stage reports the failure rather than guessing which specification to build.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a specification is handed to this stage (identified by its target working directory, lifecycle issue, and current iteration), the system MUST work through the specification's task list on its persistent working branch, committing progress as work completes.
- **FR-002**: After each implementation pass, the system MUST run a convergence reassessment that either records remaining work by extending the task list, or reports that no remaining work exists.
- **FR-003**: When the convergence reassessment records remaining work, the system MUST begin another build-and-reassess cycle for the specification at the next iteration.
- **FR-004**: When the convergence reassessment reports that no remaining work exists, the system MUST hand off the specification to the finalization stage without the not-converged flag.
- **FR-005**: The system MUST enforce a configurable maximum number of build-and-reassess cycles per specification, with a sensible default, and MUST NOT begin a cycle beyond that maximum.
- **FR-006**: When the configured maximum number of cycles is reached without convergence, the system MUST report the remaining work on the specification's lifecycle issue AND hand off the specification to the finalization stage flagged as not converged.
- **FR-007**: The system MUST guarantee that every specification reaching this stage is handed off to finalization exactly once — either converged or flagged as not converged — and never left cycling indefinitely (the sole exception being a specification marked stalled under FR-013 after an outright pass failure, which awaits a manual restart rather than a hand-off).
- **FR-008**: The system MUST post a progress update to the specification's lifecycle issue for each build-and-reassess cycle.
- **FR-009**: The system MUST use a configurable default implementation model, and MUST use a higher-capability implementation model when the specification's lifecycle issue carries the designated higher-capability opt-in.
- **FR-010**: The system MUST update the specification's durable lifecycle record to reflect its progress through this stage, including which iteration it is on.
- **FR-011**: The system MUST treat a repeated or duplicate hand-off for the same specification at the same iteration idempotently, without running a second build-and-reassess cycle, posting a duplicate progress update, or triggering a duplicate finalization hand-off for that iteration.
- **FR-012**: When the hand-off cannot be matched to a valid specification, the system MUST report the failure rather than acting on an incorrect or nonexistent specification.
- **FR-013**: When an implementation or convergence pass cannot complete because of a resource or tooling failure (as distinct from completing but not yet converging), the system MUST automatically retry the same iteration once, escalating the implementation model to the next-higher-capability tier for the retry (for example, Haiku → Sonnet → Opus). If the retry also fails — or the failing pass was already running on the highest-capability model tier, leaving no tier to escalate to — the system MUST mark the specification stalled and require a manual restart, surfacing the failure on the specification's lifecycle issue rather than silently advancing or silently dropping the specification.
- **FR-014**: The system MUST record each build-and-reassess cycle as an independently auditable unit of work, so that any individual cycle's actions can be reviewed after the fact.
- **FR-015**: The system MUST NOT itself open, approve, or merge the feature's eventual pull request; this stage's outputs are committed progress on the persistent working branch and the hand-off to finalization.

### Key Entities

- **Build-and-reassess cycle (iteration)**: One numbered pass consisting of working through the task list followed by a convergence reassessment; iterations advance until convergence or the configured maximum.
- **Convergence reassessment**: The judgment, run after each implementation pass, that either extends the task list with remaining work or reports that nothing remains; its extend-vs-unchanged outcome is what drives the loop.
- **Cycle maximum (configuration)**: The repository-level upper bound on the number of build-and-reassess cycles per specification, with a sensible default; guarantees the loop terminates.
- **Implementation model (configuration)**: The model capability used to implement the task list — a default with an opt-in to a higher-capability model via a designated label on the lifecycle issue, plus an automatic one-tier escalation used only to retry a pass that failed outright (see FR-013).
- **Task list**: The dependency-ordered breakdown of work being implemented and, when gaps remain, extended by the convergence reassessment.
- **Lifecycle record (spec metadata)**: The durable association between a specification, its issue, its stage, its iteration, and its branches; updated to reflect progress through this stage.
- **Finalization hand-off**: The signal passed downstream when this stage completes, carrying whether the work converged or was handed over not converged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the common case, a specification with a ready task list is built to a converged state and handed to finalization with zero human performing the build, reassessment, or hand-off steps by hand.
- **SC-002**: Every specification that reaches this stage is handed off to finalization exactly once — either converged or flagged as not converged — so no specification is ever left cycling indefinitely or stuck with no downstream result.
- **SC-003**: The number of build-and-reassess cycles run for any specification never exceeds the configured maximum.
- **SC-004**: A maintainer can determine, from the lifecycle issue alone, how many cycles ran and whether the feature converged, without inspecting the persistent working branch directly.
- **SC-005**: When a specification is handed off without fully converging, its remaining work is visible on the lifecycle issue.
- **SC-006**: Repeated or duplicate hand-offs for the same specification at the same iteration never result in more than one build-and-reassess cycle or more than one finalization hand-off for that iteration.

## Assumptions

- "Persistent working branch," "lifecycle issue," and "durable lifecycle record" refer to the same per-specification branch, issue, and metadata established by the earlier pipeline stages; this stage does not introduce new such concepts.
- This specification concerns the orchestration of the implement-then-reassess loop — when it runs, how many times, what it reports, and how it hands off — not the internal behavior of the implementation or convergence tooling, which decides how code is written and how remaining work is judged.
- Convergence is inferred from the convergence reassessment's append-only contract: an extended task list means remaining work (keep cycling), an unchanged task list means converged (hand off); this stage relies on that contract rather than redefining how convergence is measured.
- The default cycle maximum is a small number (the pipeline's configured default of five) — chosen to allow multi-pass completion while bounding cost and runtime; it is a repository-level configuration, not per-specification.
- Each cycle is a distinct, separately triggered unit of work rather than one long-running loop, so each iteration is individually auditable and bounded — matching the pipeline's chaining-by-dispatch pattern between stages and iterations.
- The default implementation model and the higher-capability opt-in follow the pipeline's model-tiering conventions; the opt-in is expressed as a designated label on the lifecycle issue.
- Handing off to finalization means triggering the finalization stage for the specification, carrying the converged/not-converged outcome; the finalization stage's own behavior (such as opening the feature's pull request) is out of scope for this specification.
- Starting this stage is itself a hand-off from the tasks stage at the first iteration; the tasks stage's behavior is out of scope here.
