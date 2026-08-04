# Feature Specification: Auto-Update Spec Kit — Narrate Prepare Failures and Verify End-to-End for Real

**Feature Branch**: `030-auto-update-gaps`

**Created**: 2026-08-04

**Status**: Draft

**Input**: GitHub issue #157 — "Auto-update Spec Kit: a prepare failure narrates nothing, and the \"end-to-end\" tier verifies almost nothing". Two design-level gaps in the auto-update Spec Kit process (specified in specs/027) that do not crash but undercut guarantees the spec makes: (1) when the upgrade-preparation phase fails, nothing narrates the outcome on the lifecycle issue, so the issue stays silent while the cycle has actually died — undercutting SC-004 and FR-010; (2) the "end-to-end" verification tier for minor/major upgrades copies a template file and checks it is non-empty rather than exercising the candidate version's own behavior, and its fallback lets a *missing* template still pass — undercutting FR-004 and FR-014.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A preparation failure tells its story on the lifecycle issue (Priority: P1)

A maintainer relying on the auto-update process expects the lifecycle issue to be the single place that conveys what happened to an upgrade attempt. Today, if the phase that prepares the candidate upgrade fails, every downstream phase skips and no one touches the issue: it keeps saying the attempt is in progress while the attempt has, in fact, died. The maintainer only discovers this by noticing a red run in the Actions tab — exactly the log-reading that the process is meant to spare them. This story makes a preparation failure narrate itself on the issue the same way a verification failure already does: a comment explaining what failed and which version is still in effect, plus the visible failure flag, with the issue left open for a human.

**Why this priority**: A preparation failure is not hypothetical — the preparation step deliberately fails loudly rather than mis-applying an unverified upgrade command, and that command shape is a known open assumption. An outcome that the issue never reports is the exact gap SC-004 and FR-010 promise not to leave. Silence on the most likely early-failure path defeats the legibility the whole feature exists to provide.

**Independent Test**: Simulate an upgrade attempt whose preparation phase fails, let the process run to completion, and confirm the lifecycle issue ends open, carries the failure flag, and contains a comment stating that preparation failed and which version remains pinned — without the maintainer reading any run logs.

**Acceptance Scenarios**:

1. **Given** an upgrade attempt whose preparation phase fails, **When** the process completes, **Then** the lifecycle issue receives a comment describing that preparation failed and which version is still in effect, and the visible failure flag is applied.
2. **Given** a preparation failure that has been narrated, **When** the maintainer reads the lifecycle issue alone, **Then** they can tell that an upgrade was attempted, that it failed during preparation, and that no version was adopted, without opening the Actions tab.
3. **Given** a preparation failure, **When** the process completes, **Then** the pinned version is left unchanged and the lifecycle issue is not closed.

---

### User Story 2 - The end-to-end tier actually exercises the candidate version (Priority: P1)

For minor and major upgrades — the jumps most likely to change behavior — the maintainer expects a deeper check that runs something genuinely driven by the candidate Spec Kit version, not a check that any working repository would pass regardless of the candidate. Today the "end-to-end" tier copies a template file and asserts the copy is non-empty; no candidate-driven stage runs, and a *missing* template still passes through a fallback. As a result the extra tier buys almost nothing for the very case it exists to protect: a minor or major jump. This story makes the end-to-end tier run a real Spec-Kit-driven stage that depends on the candidate's own artifacts and assert the expected result, and makes an absent expected artifact fail rather than pass.

**Why this priority**: FR-004 and FR-014 promise that minor and major upgrades receive a check beyond the lightweight tier — "running at least one real spec-kit-driven stage and confirming it succeeds." A tier that exercises nothing candidate-specific violates that promise and gives false confidence precisely when the repository is taking its largest tooling jump (currently a minor/major gap between the pinned version and upstream). Equal in weight to Story 1: both are guarantees the parent spec already made and the implementation does not keep.

**Independent Test**: Point the end-to-end tier at a candidate whose artifacts would make a real stage fail (for example, an absent or malformed expected artifact) and confirm the tier reports failure; point it at a healthy candidate and confirm it runs a real candidate-driven stage and reports success. Confirm that a run where the expected template/artifact is missing no longer passes.

**Acceptance Scenarios**:

1. **Given** a minor or major upgrade under the end-to-end tier, **When** verification runs, **Then** it executes at least one real Spec-Kit-driven stage that depends on the candidate version's own artifacts and asserts the expected output before reporting a result.
2. **Given** the candidate's expected artifact for the end-to-end stage is missing, **When** verification runs, **Then** the tier reports failure rather than passing on a fallback.
3. **Given** a candidate whose real stage execution would fail with that candidate's artifacts, **When** the end-to-end tier runs, **Then** the candidate is judged not working and is not adopted, and the failure is narrated on the lifecycle issue.
4. **Given** a healthy candidate whose real stage runs and produces the expected output, **When** the end-to-end tier runs, **Then** the tier reports success and the attempt proceeds to its reviewable version-bump pull request.

---

### Edge Cases

- What happens when preparation fails *after* the lifecycle issue has already received in-progress narration? The failure comment and flag are added to that same issue; no second competing issue is opened.
- What happens when both a preparation failure and a verification failure could occur in one attempt? Only one failure path runs per attempt (preparation failure short-circuits before verification), and exactly one failure narration and flag result — no double-reporting and no silent skip.
- What happens when the end-to-end tier's expected artifact is missing because the candidate legitimately reorganized its templates/scripts rather than because it is broken? See [NEEDS CLARIFICATION: should a missing expected end-to-end artifact be reported as a verification *failure* (candidate broken, flagged), or routed to human attention as a "not a clean version bump" case per FR-018? The parent issue's suggested fix says a missing template should fail; FR-018 says a non-clean-bump upgrade should be routed to a human instead of failing.]
- What happens when the end-to-end stage is flaky (fails once, would pass on retry)? Consistent with the parent spec's conservative stance, a failure is treated as a real failure — the candidate is not adopted and the issue is flagged — rather than silently retried into a false pass.
- What happens for a patch upgrade, which only runs the lightweight tier? Nothing in this feature changes the patch path; the end-to-end changes apply only where the end-to-end tier already runs (minor/major).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the upgrade-preparation phase of an attempt fails, the system MUST narrate the failure on that attempt's lifecycle issue rather than leaving the issue silent — mirroring the existing verification-failure narration.
- **FR-002**: The preparation-failure narration MUST convey, from the issue content alone, that an upgrade was attempted, that it failed during preparation, and which Spec Kit version remains pinned — without the maintainer needing to read run logs. (Satisfies the parent spec's SC-004 for the preparation-failure path.)
- **FR-003**: On a preparation failure, the system MUST apply the same visible failure flag used for verification failures and MUST leave the lifecycle issue open. (Satisfies the parent spec's FR-010 for the preparation-failure path.)
- **FR-004**: On a preparation failure, the system MUST NOT adopt any candidate version and MUST leave the pinned version unchanged.
- **FR-005**: The system MUST NOT open a duplicate or competing lifecycle issue when narrating a preparation failure; the failure MUST be recorded on the attempt's existing lifecycle issue.
- **FR-006**: For minor and major upgrades, the end-to-end verification tier MUST run at least one real Spec-Kit-driven stage whose behavior depends on the candidate version's own artifacts, rather than only copying a file and checking it is non-empty.
- **FR-007**: The end-to-end tier MUST assert that the candidate-driven stage produced its expected result and MUST report failure when it does not.
- **FR-008**: The end-to-end tier MUST NOT pass on a fallback when the expected artifact the stage depends on is absent; an absent expected artifact MUST NOT be treated as success.
- **FR-009**: A candidate that fails the end-to-end tier MUST be judged not working, MUST NOT be adopted, and MUST have its failure narrated on the lifecycle issue (consistent with the existing verification-failure narration).
- **FR-010**: The end-to-end changes MUST NOT alter the patch-upgrade path, which continues to run only the lightweight tier, nor weaken the lightweight tier that always runs.
- **FR-011**: Both the preparation-failure narration and the strengthened end-to-end tier MUST be exercisable by the pipeline's own executable scenario checks (the parent effort's verification harness), so each gap's fix is asserted rather than desk-checked.

### Key Entities *(include if feature involves data)*

- **Upgrade attempt**: A single run of the auto-update process against a candidate version, tracked by one lifecycle issue. The unit whose preparation or verification may fail.
- **Preparation phase**: The phase that prepares the candidate upgrade before verification. Its failure is the outcome this feature makes visible.
- **Lifecycle issue**: The GitHub issue that tracks one attempt and is meant to convey the outcome on its own. The surface a preparation failure must now narrate to.
- **Failure flag**: The visible label applied to a lifecycle issue when an attempt is blocked or rolled back. Reused for the preparation-failure path.
- **End-to-end verification tier**: The deeper verification tier that runs for minor and major upgrades. The check this feature makes exercise the candidate version's own artifacts.
- **Expected artifact**: The candidate-provided template/script/output the end-to-end stage depends on; its absence must now fail rather than pass.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of upgrade attempts that fail during preparation end with a lifecycle issue that is open, carries the failure flag, and contains a comment describing the failure and the still-pinned version.
- **SC-002**: A maintainer can determine that a preparation-failed attempt was attempted, failed in preparation, and adopted no version, from the lifecycle issue alone, with zero run-log reads.
- **SC-003**: No upgrade attempt that fails during preparation leaves the lifecycle issue silent or in an "in progress" state.
- **SC-004**: For every minor and major upgrade, the end-to-end tier runs at least one real candidate-driven stage; 0% of minor/major end-to-end passes are produced without a candidate-driven stage having run.
- **SC-005**: A run in which the expected end-to-end artifact is missing results in a reported failure, not a pass, in 100% of cases.
- **SC-006**: A candidate that would fail a real candidate-driven stage is never adopted as a result of the end-to-end tier reporting a false pass.
- **SC-007**: Each of the two fixes is covered by an executable scenario check that fails when the corresponding gap is reintroduced.

## Assumptions

- This feature refines the auto-update Spec Kit process specified in specs/027; all of that spec's requirements (FR-001…FR-018, SC-001…SC-007) remain in force and are the source of the guarantees this feature closes gaps against. Where this spec cites SC-004, FR-004, FR-010, or FR-014, it means the parent spec's numbering.
- The failure flag/label and the verification-failure narration shape already exist in the process; this feature reuses them for the preparation-failure path rather than introducing a new label or a new comment style.
- Preparation runs before any version is adopted, so a preparation failure has nothing to roll back — the correct outcome is "left unadopted and flagged," matching the parent spec's block-rather-than-rollback branch.
- The information the preparation-failure narration needs (which lifecycle issue to comment on, which version is pinned) is already available to the process at the point of failure; no new discovery mechanism is introduced.
- "A real Spec-Kit-driven stage" means a stage whose execution and output depend on the candidate version's own scripts/templates (for example, creating a throwaway feature and running a candidate stage against it and asserting the documented output shape), consistent with the parent spec's FR-004 wording ("generating a throwaway spec" / "running at least one real spec-kit-driven stage"). The specific stage chosen is an implementation detail left to planning, provided it genuinely exercises candidate artifacts.
- The pipeline's existing executable scenario harness (the parent effort's verification gate) is the intended home for the assertions in FR-011/SC-007; this feature does not introduce a separate testing framework.
- These changes are scoped to the auto-update process's own workflow behavior; no change is made to the human-merges-to-main rule, the PR-review adoption gate, or any other parent-spec guarantee.
