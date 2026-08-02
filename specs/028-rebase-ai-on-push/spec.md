# Feature Specification: Auto-Rebase AI Conflict Resolution on Push-Triggered Rebases

**Feature Branch**: `028-rebase-ai-on-push`

**Created**: 2026-08-02

**Status**: Draft

**Input**: User description: "The auto-rebase stage's AI conflict-resolution step can never run on push-triggered rebases: the underlying AI action fails immediately with 'Unsupported event type: push' when the calling workflow was triggered by a push event. Since the rebase wrapper's primary trigger is push to the default branch, every conflicted rebase caused by a normal push goes straight to the abandon + escalate path without any resolution attempt. Make AI conflict resolution reachable on the push path, keep the existing graceful safety fallback, scope the fix to the rebase wrapper only (no third-party change required), validate it on a real conflict, and add a static lint gate that prevents any future wrapper from routing an AI-agent step through an event the agent does not support."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A conflicted rebase caused by a normal push gets an automatic resolution attempt (Priority: P1)

When a routine change lands on the default branch and causes an in-flight spec branch to conflict during the automated rebase, the maintainer expects the pipeline to *try* to resolve that conflict automatically — the whole point of the auto-rebase stage's AI conflict-resolution step. Today, because that rebase run was set in motion by an ordinary push, the resolution step never even runs: it fails instantly, and the branch is abandoned and escalated without a single resolution attempt. This story makes the resolution attempt actually happen on the trigger that fires most often.

**Why this priority**: This is the core defect. The auto-resolution feature exists but is unreachable on the dominant trigger, so in practice it almost never runs. Restoring the attempt on the push path is what turns a feature that "works in theory" into one that works in practice, and it delivers value on its own even without the other stories.

**Independent Test**: Deliberately induce a merge conflict on a spec branch, let a push to the default branch drive the rebase, and confirm the AI conflict-resolution step is reached and attempts a resolution — rather than failing immediately with an "unsupported event" error before it can act.

**Acceptance Scenarios**:

1. **Given** an in-flight spec branch that will conflict when rebased and a rebase run initiated by a push to the default branch, **When** the rebase reaches the conflict, **Then** the AI conflict-resolution step runs and attempts to resolve the conflict (it does not fail immediately as "unreachable").
2. **Given** the resolution attempt succeeds, **When** the rebase continues, **Then** the branch is rebased with the conflict resolved and no human intervention was required.
3. **Given** the same conflict occurs on a schedule-initiated rebase instead of a push-initiated one, **When** the rebase reaches the conflict, **Then** the resolution step runs identically — the behavior does not depend on which trigger started the rebase.

---

### User Story 2 - A future unsupported trigger is caught by CI before it can ship (Priority: P2)

A maintainer editing the pipeline's workflows should not be able to silently reintroduce this defect — for example by adding a new triggering event to a rebase-like wrapper whose stage contains an AI-agent step that cannot run under that event. Today nothing stops that; the breakage only surfaces later, at the moment a real conflict occurs in production. This story adds a static check that fails the pull request the moment such a mismatch is introduced, so the problem is caught in review instead of in a live run.

**Why this priority**: The fix in Story 1 restores the behavior, but nothing prevents the same class of mistake from recurring. A static gate converts a latent runtime failure — one that only appears on a genuine conflict, long after merge — into an immediate, legible CI failure. It is high value but secondary to actually restoring the resolution attempt.

**Independent Test**: On a branch, add an unsupported triggering event to a rebase-like wrapper whose stage contains an AI-agent step, and confirm the workflow-lint check fails with a clear message; then remove it and confirm the check passes.

**Acceptance Scenarios**:

1. **Given** a wrapper workflow whose resolved stage contains an AI-agent step, **When** that wrapper declares a triggering event the agent does not support, **Then** the workflow-lint gate fails the pull request and names the offending wrapper and event.
2. **Given** a wrapper whose resolved stage contains an AI-agent step and whose triggering events are all supported, **When** the gate runs, **Then** it passes.
3. **Given** a wrapper whose resolved stage contains **no** AI-agent step, **When** that wrapper declares any triggering event, **Then** the gate does not flag it (the event set only matters where an agent step is present).
4. **Given** a wrapper adds a *different* unsupported event in the future (not only push — for example a release or branch-creation event), **When** the gate runs, **Then** it is flagged just the same.

---

### User Story 3 - The graceful safety net is preserved when the AI genuinely cannot resolve (Priority: P2)

The maintainer must never be worse off than before. Today, when a rebase conflicts, the branch is safely aborted, left untouched, and the conflict is escalated on the lifecycle issue — that graceful behavior is correct and must survive the fix. After this change, that safety path becomes the *fallback* for conflicts the AI attempts but cannot resolve, rather than the *only* path.

**Why this priority**: Restoring the resolution attempt must not come at the cost of the existing safe failure mode. A resolution feature that leaves a branch in a broken or half-rebased state on failure would be worse than the current abandon-and-escalate behavior. This story guards the existing invariant.

**Independent Test**: Induce a conflict the AI cannot resolve on a push-triggered rebase and confirm the rebase is aborted, the branch is left exactly as it was, and the conflict is escalated on the lifecycle issue — identical to today's graceful outcome.

**Acceptance Scenarios**:

1. **Given** a push-triggered rebase whose conflict the AI attempts but cannot resolve, **When** the attempt ends unsuccessfully, **Then** the rebase is aborted, the branch is left untouched, and the conflict is escalated on the lifecycle issue.
2. **Given** the resolution step errors, stalls, or times out rather than returning a clean result, **When** the run completes, **Then** the branch is still left untouched and the outcome is escalated rather than silently swallowed.
3. **Given** the AI resolves only part of a multi-file conflict, **When** the rebase cannot complete cleanly, **Then** the run is treated as unresolved and takes the safety path rather than pushing a partially-rebased branch.

---

### Edge Cases

- **No conflict on the rebase**: the resolution step never fires (as today); the rebase completes normally and nothing about the fix changes that path.
- **Skipped rebase job**: when the rebase matrix has no eligible branch to act on (e.g. the branch's PR is already merged), no resolution is attempted — the fix does not cause work where there was none.
- **Both triggers present**: the rebase can be initiated by either a push or a scheduled run; the resolution step must be reachable under both, and the validated behavior must not silently regress on one while the other is exercised.
- **A wrapper triggered by several events, only some unsupported**: the static gate flags the wrapper if *any* of its triggering events is unsupported for its agent-bearing stage, not only when all are.
- **Validation coverage**: the schedule path is documented as supported but, historically, was inferred from source and never actually exercised on a real conflict; validation of this fix must run against a genuine induced conflict on the affected (push) path rather than being assumed from inspection.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a rebase initiated by a push to the default branch encounters a merge conflict, the system MUST reach and run the AI conflict-resolution step, rather than failing before it can act because the initiating event is unsupported.
- **FR-002**: The AI conflict-resolution behavior MUST be equivalent regardless of which event initiated the rebase (push or scheduled run) — one resolution path serving both triggers, with no trigger-dependent difference in whether the attempt is made.
- **FR-003**: When the AI conflict-resolution attempt succeeds, the rebase MUST continue to completion with the conflict resolved and the branch updated, requiring no human intervention.
- **FR-004**: When the AI conflict-resolution attempt does not fully resolve the conflict — including error, stall, timeout, or partial resolution — the system MUST fall back to the existing safety behavior: abort the rebase, leave the branch untouched, and escalate the conflict on the lifecycle issue.
- **FR-005**: The existing graceful safety behavior (abort, leave branch untouched, escalate on the lifecycle issue) MUST NOT regress; it MUST remain the outcome for any conflict the AI cannot resolve.
- **FR-006**: The change MUST be scoped to the auto-rebase wrapper only. Other agent-bearing stages and wrappers already reach their agent step under a supported event and MUST NOT be modified by this feature.
- **FR-007**: The solution MUST be self-contained within this repository. It MUST NOT require any change to a third-party/external component to make the resolution step reachable on the push path.
- **FR-008**: The system MUST add a static, pre-merge check (a new gate in the workflow-lint suite) that fails a pull request whenever a wrapper's resolved stage contains an AI-agent step and the wrapper declares a triggering event that the agent does not support.
- **FR-009**: The static check MUST first determine whether a wrapper's resolved stage actually contains an AI-agent step, and only apply the supported-event comparison to wrappers that do — wrappers without an agent step MUST NOT be flagged for their triggering events.
- **FR-010**: The static check MUST be forward-looking: it MUST flag *any* unsupported triggering event on an agent-bearing wrapper, not only the specific event that caused this defect.
- **FR-011**: When the static check fails, its output MUST identify the offending wrapper and the specific unsupported event(s) clearly enough for a maintainer to fix the workflow without reading run logs.
- **FR-012**: The fix MUST be validated against a real, deliberately induced merge conflict exercised on the affected (push-initiated) rebase path — its correctness MUST NOT rest solely on inspection of source or on the assumption that a never-exercised path works.

### Key Entities

- **Auto-rebase wrapper**: the repository-owned workflow that triggers the reusable rebase stage; its declared triggering events determine what event the stage's agent step observes.
- **AI conflict-resolution step**: the stage step that attempts to resolve a rebase merge conflict automatically; it is the capability rendered unreachable on the push path today.
- **Supported-event set**: the fixed set of events under which the AI-agent step can run; a triggering event outside this set makes the step unreachable.
- **Workflow-lint gate**: the static, pre-merge check suite that this feature extends with a new gate covering the event/agent-step mismatch.
- **Lifecycle issue**: the per-spec GitHub issue where a conflict that cannot be resolved is escalated, unchanged by this feature except that escalation now follows a resolution *attempt* on the push path.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a push-initiated rebase that hits a conflict, the AI conflict-resolution step is reached and attempts a resolution 100% of the time — down from the current 100% immediate "unreachable" failure rate before any attempt.
- **SC-002**: A deliberately induced conflict on the push-initiated rebase path is resolved automatically end-to-end in a real validation run, demonstrating the feature works in practice and not only in principle.
- **SC-003**: For any conflict the AI cannot resolve, the branch is left untouched and the conflict is escalated on the lifecycle issue 100% of the time — no partially-rebased or half-resolved branch is ever pushed.
- **SC-004**: Introducing an unsupported triggering event on an agent-bearing rebase-like wrapper is caught by CI before merge 100% of the time; a wrapper with only supported events, and a wrapper with no agent step, both pass.
- **SC-005**: No agent-bearing stage or wrapper other than the auto-rebase wrapper changes behavior as a result of this feature.

## Assumptions

- The two implementation directions named in the request — re-dispatching the push path through an event the agent already supports, or running the resolution step by a different mechanism for this one step — are both acceptable; this specification deliberately does not choose between them, as that is a planning decision. It requires only the outcome: the resolution attempt is reachable on the push path with one behavior across triggers.
- The existing abort-and-escalate safety path already works correctly on every trigger and is retained as the fallback; this feature adds a resolution attempt in front of it rather than replacing it.
- The set of events the AI-agent step supports is treated as a known, fixed list (the settled constraint stated in the request); the new static gate encodes that list and compares wrapper triggers against it.
- "Validated on a real conflict" means a deliberately induced conflict exercised on the affected trigger path, consistent with the repository's prior live-validation practice, rather than correctness inferred from reading source.
- The new static gate is an additional gate in the existing workflow-lint suite; it is numbered as the next available gate (the request notes an earlier draft's "Gate 4" label has since been reused and that this is a later-numbered gate), and its exact number is a naming detail resolved at implementation time.
- Only the auto-rebase wrapper carries an unsupported trigger today; the request's audit found every other agent-bearing workflow already reaches its agent step under a supported event, so no other wrapper needs changing and the gate is expected to pass for all of them at introduction.
- No change to any third-party/external component is required or in scope; the defect is resolved entirely within this repository.
