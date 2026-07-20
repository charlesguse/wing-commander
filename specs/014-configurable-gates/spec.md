# Feature Specification: Configurable Human Review Gates

**Feature Branch**: `014-configurable-gates`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "After approving the spec, the code produced has generally worked very well. I don't find myself tweaking the plan merged in. I would like to skip that approval but I want it to be configurable. I want to make it so human gate 3 is disabled. After I merge in the spec PR (human gate 2), I want the plan to be generated and go into tasks and the implement / converge loop. I want to make the other human gates similarly configurable in case I find I want to do this with the other gates."

## User Scenarios & Testing *(mandatory)*

The pipeline advances a feature through stages, and today each stage waits at a
human review gate before the next stage begins. The four gates are:

- **Gate 1 — Pipeline entry**: a maintainer applies the entry label to an issue.
- **Gate 2 — Spec review**: a maintainer reviews and merges the spec PR into `main`.
- **Gate 3 — Plan review**: a maintainer reviews and merges the plan PR (onto the
  per-spec integration branch, not `main`).
- **Gate 4 — Final review**: a maintainer reviews and merges the final PR into `main`.

This feature lets a repository declare that a given gate should not require a
human to pause the pipeline, so the next stage proceeds automatically once the
preceding stage's work is produced.

### User Story 1 - Skip the plan review gate (Priority: P1)

As a maintainer who consistently finds the generated plan acceptable without edits,
I want to disable the plan review gate (Gate 3) so that after I merge the spec PR,
the plan is generated and the pipeline flows straight into task generation and the
implement/converge loop without me having to review and merge the plan PR.

**Why this priority**: This is the requester's concrete, stated need and the
motivating use case. It is the gate that can be bypassed with the least risk
because it does not merge into `main`, so it delivers immediate value on its own.

**Independent Test**: Configure the pipeline to disable Gate 3, merge a spec PR,
and confirm the plan is produced and the tasks stage starts without any human
action on the plan artifact — and that the lifecycle issue records that the plan
gate was bypassed.

**Acceptance Scenarios**:

1. **Given** a repository configured to disable the plan review gate, **When** a spec PR is merged, **Then** the plan is generated and the tasks stage begins automatically without waiting for a human to review or merge the plan.
2. **Given** the plan review gate is bypassed, **When** the plan stage completes, **Then** the lifecycle issue records that the plan advanced automatically because the gate was disabled.
3. **Given** a repository with default configuration (no gate disabled), **When** a spec PR is merged, **Then** the plan PR is still opened and the pipeline waits for a human to merge it, exactly as it does today.

---

### User Story 2 - Configure each configurable gate independently (Priority: P2)

As a maintainer, I want to enable or disable each configurable human review gate
independently, so that I can tune how much automation I want per gate as I gain
confidence in the pipeline's output for that stage.

**Why this priority**: The requester explicitly asked for the mechanism to apply
to "the other human gates" too, "in case I find I want to do this with the other
gates." Independent per-gate control is the general capability behind User Story 1.
The configurable set is limited to gates that never merge into `main` — the plan
review gate (Gate 3) and the already-automatic tasks step — because the constitution
keeps Gates 1, 2, and 4 as mandatory human gates (FR-011).

**Independent Test**: Set each configurable gate's setting independently and confirm
that each behaves as specified (bypassed or enforced) without affecting the others,
and that the mandatory gates (1, 2, 4) cannot be disabled.

**Acceptance Scenarios**:

1. **Given** configuration that disables one configurable gate and leaves the other(s) enabled, **When** the pipeline runs, **Then** only the disabled gate is bypassed and every other gate still pauses for human action.
2. **Given** configuration that names an unknown gate, a non-configurable gate (1, 2, or 4), or an invalid value, **When** the pipeline reads it, **Then** the configuration is rejected or ignored safely, the affected gate defaults to enabled, and the discrepancy is surfaced rather than silently changing gate behavior.

---

### User Story 3 - Safe, discoverable defaults (Priority: P3)

As a maintainer who has not configured anything, I want every gate enabled by
default so that adopting this feature never weakens review on a repository that did
not opt in.

**Why this priority**: Preserves the current, safe behavior for all existing users
and adopting repositories; important for trust but subordinate to delivering the
configurable capability itself.

**Independent Test**: With no gate configuration present, run the full pipeline and
confirm all four gates behave exactly as they do today.

**Acceptance Scenarios**:

1. **Given** no gate configuration is present, **When** the pipeline runs, **Then** all gates are enforced, matching current behavior.
2. **Given** a maintainer inspects the configuration, **When** they read it, **Then** the set of gates and each gate's current enabled/disabled state is discoverable.

---

### Edge Cases

- **Merge-to-main gates vs. the security constitution**: Gates 2 and 4 merge into `main`, and Gate 1 is the maintainer-applied entry approval. The project constitution marks "humans merge every PR into `main`" and "pipeline entry requires a maintainer-applied label" as NON-NEGOTIABLE. These gates are therefore NOT configurable (FR-011): only the plan review gate (Gate 3) and the already-automatic tasks step may be bypassed, so the constitution's Principle V holds without amendment.
- **Auto-advanced artifact is defective**: If a gate is bypassed and the auto-generated artifact (e.g., the plan) is empty, invalid, or the generating stage failed, the pipeline must not silently proceed on bad input; it should stop and report rather than cascade a failure into later stages.
- **Concurrent specs**: Multiple specs can be in flight at once. Gate configuration is repository-wide (FR-012), so every in-flight spec observes the same settings; there is no per-spec override that could make one spec's setting affect another unexpectedly.
- **Traceability when a gate is bypassed**: When a review gate is skipped, the produced artifact should still be recorded/committed so the lifecycle remains legible from the issue, even though no human paused to approve it.
- **Configuration changed mid-lifecycle**: If the repository-wide gate setting changes while a spec is between stages, the setting is read when the spec reaches a gate, so the behavior at the next gate the spec reaches is always the currently-configured value. A spec that has already passed a gate is unaffected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST allow a repository to configure, per human review gate, whether that gate pauses the pipeline for human action ("enabled") or is bypassed so the next stage proceeds automatically ("disabled").
- **FR-002**: The pipeline MUST support disabling the plan review gate (Gate 3) such that, after the spec PR is merged, the plan is generated and the pipeline advances into task generation and the implement/converge loop with no human review or merge of the plan required.
- **FR-003**: Each gate's configuration MUST be independent of the others: disabling or enabling one gate MUST NOT change the behavior of any other gate.
- **FR-004**: Every gate MUST default to enabled when not explicitly configured, so that repositories that do not opt in retain today's full-review behavior.
- **FR-005**: When a gate is bypassed, the pipeline MUST record on the lifecycle issue that the stage advanced automatically because the gate was disabled, so the automated transition is auditable.
- **FR-006**: When a gate is bypassed, the artifact that the gate would have gated (e.g., the plan) MUST still be produced and persisted so the feature's history remains legible from the issue.
- **FR-007**: When a gate is bypassed but the stage that produced the gated artifact failed or produced an invalid/empty artifact, the pipeline MUST stop and report rather than advance the next stage on bad input.
- **FR-008**: Invalid, unrecognized, or malformed gate configuration MUST NOT weaken a gate: the affected gate MUST fall back to enabled, and the problem MUST be surfaced rather than silently applied.
- **FR-009**: The current enabled/disabled state of each gate MUST be discoverable by a maintainer.
- **FR-010**: Gate configuration MUST be treated as trusted maintainer configuration; it MUST NOT be settable by, or inferred from, untrusted issue or comment content.
- **FR-011**: The set of gates the pipeline recognizes as configurable MUST be limited to gates that do NOT merge into `main` and do NOT gate pipeline entry — that is, the plan review gate (Gate 3) and the already-automatic tasks step. Gate 1 (entry label), Gate 2 (spec→`main`), and Gate 4 (final→`main`) MUST remain mandatory human gates and MUST NOT be configurable, preserving the constitution's NON-NEGOTIABLE Principle V without any amendment.
- **FR-012**: Gate configuration MUST be applied repository-wide: a single repository-level configuration governs every spec in the repository, and there is NO per-spec override. All in-flight and future specs observe the same gate settings.

### Key Entities *(include if data involved)*

- **Review Gate**: A named point between two pipeline stages where the pipeline currently pauses for maintainer action. Attributes: identity (which gate — entry, spec, plan, final), whether it merges into `main`, and its enabled/disabled state.
- **Gate Configuration**: The maintainer-owned, repository-wide declaration of each configurable gate's enabled/disabled state, and its default (enabled). Only the plan review gate (Gate 3) and the tasks step are configurable; Gates 1, 2, and 4 are not.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the plan review gate disabled, a maintainer merges a spec PR and the pipeline reaches the implement/converge loop with zero additional human actions on the plan artifact.
- **SC-002**: With no gate configuration present, 100% of gates behave exactly as they do today (no regression in review behavior for unconfigured repositories).
- **SC-003**: A maintainer can determine, without reading pipeline source or run logs, which gates are currently enabled or disabled for their repository.
- **SC-004**: Every automatic stage transition caused by a bypassed gate is recorded on the lifecycle issue, so 100% of bypassed-gate advances are auditable after the fact.
- **SC-005**: Enabling or disabling one gate leaves all other gates' behavior unchanged in 100% of runs.

## Assumptions

- "Configurable" means a maintainer-owned, trusted setting (consistent with how the pipeline already treats maintainer-applied labels and repository variables), not something derived from untrusted issue/comment content.
- The requester's immediate goal is Gate 3 (plan review); the broader "make the other gates configurable" request is for the same mechanism to be reusable across gates, even if only Gate 3 is exercised initially.
- "Bypassing" a gate means the pipeline no longer waits for a human at that transition; it does not mean the corresponding artifact is skipped. The artifact is still produced and recorded.
- Default configuration reproduces current behavior: all gates enabled.
- This feature governs only gate pause/advance behavior; it does not change what each stage produces or how artifacts are validated, beyond requiring that a bad artifact halts rather than cascades (FR-007).
