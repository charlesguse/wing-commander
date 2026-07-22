# Feature Specification: Parameterize Hardcoded Models

**Feature Branch**: `017-parameterize-hardcoded-models`

**Created**: 2026-07-22

**Status**: Draft

**Input**: User description: "Some locations have a model hard-coded in. These models don't work when using Bedrock. Any model that is hardcoded in should be passed in as a parameter with a default set. That way Bedrock consumers can properly change the model as needed, or if someone wants to use a different model than is set by default."

## Clarifications

### Session 2026-07-22

- Q: At what granularity should model selections be overridable? → A: Per tier — expose the small set of task tiers (e.g. triage, plan/tasks, spec/clarify, implement/escalation) as named overrides, and map every currently-hardcoded model location to a tier. Fewest knobs, cost tiering preserved cleanly; locations sharing a tier resolve to the same override.
- Q: Where should a consumer set the model overrides? → A: Repository variables in the consuming repository — the same mechanism already used for the implement-tier model. Set once per repo, no per-run editing, consuming repo owns the values.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bedrock consumer overrides every model the pipeline uses (Priority: P1)

An operator running the pipeline against a Bedrock-backed Claude deployment needs to replace every model identifier the pipeline selects with the identifier their Bedrock deployment expects. Today some stages read a model from a configurable input while other model selections are written directly into the pipeline's logic, so the operator can change the former but not the latter. When a stage reaches one of the hardcoded selections, it invokes a model identifier the Bedrock deployment does not recognize and the run fails. The operator needs a single, complete set of override points so that no model selection remains beyond their control.

**Why this priority**: This is the core problem in the request. Without full coverage, Bedrock consumers cannot run the affected stages at all — a partially-overridable pipeline is as broken for them as a fully hardcoded one, because it fails at the first unreachable selection.

**Independent Test**: Configure the pipeline with non-default model identifiers for every override point, run each stage (including retry/escalation paths), and confirm no stage ever invokes a model identifier the operator did not supply.

**Acceptance Scenarios**:

1. **Given** an operator has supplied a custom model identifier for every override point, **When** any stage runs — including retry, fallback, and escalation paths — **Then** every model invocation uses one of the operator-supplied identifiers and none uses a value baked into the pipeline.
2. **Given** an operator has supplied a custom identifier for one stage but not others, **When** that stage runs, **Then** it uses the custom identifier while the remaining stages fall back to their defaults.
3. **Given** an operator inspects the pipeline's configuration surface, **When** they look for the models a run will use, **Then** they can enumerate every model the pipeline may select from configuration alone, without reading pipeline internals.

---

### User Story 2 - Existing consumer keeps current behavior with no configuration (Priority: P2)

An operator already running the pipeline on the default (non-Bedrock) Claude models does not want their runs to change. When they provide no model overrides, the pipeline must select exactly the models it selects today, including for retry and escalation paths.

**Why this priority**: Backward compatibility protects every existing adopter. The change must be purely additive — introducing override points without shifting default behavior — or it risks silently altering cost, latency, or output quality for consumers who did nothing.

**Independent Test**: Run every stage with no overrides supplied and confirm each model invocation matches the model that stage invokes in the current pipeline, including on retry/escalation paths.

**Acceptance Scenarios**:

1. **Given** an operator supplies no model overrides, **When** any stage runs, **Then** it selects the same model it selects in the current pipeline.
2. **Given** an operator supplies no overrides, **When** a stage takes a retry or escalation path, **Then** the model selected on that path matches the model the current pipeline uses on that path.

---

### User Story 3 - Maintainer can confirm no model remains hardcoded (Priority: P3)

A maintainer reviewing the change wants to confirm that no executable model selection remains embedded in pipeline logic, so future Bedrock consumers are not tripped up by a missed location.

**Why this priority**: This is a completeness guarantee rather than a user-facing capability. It reduces the risk that the feature ships "mostly done," which for Bedrock consumers is equivalent to not done.

**Independent Test**: Audit the pipeline's executable logic and confirm every model selection resolves to a configurable override point with a default, with no model identifier embedded directly in the selection logic.

**Acceptance Scenarios**:

1. **Given** the change is complete, **When** a maintainer audits executable pipeline logic for model selections, **Then** each one resolves through a configurable override point rather than an embedded literal.

---

### Edge Cases

- **Partial override**: An operator overrides some but not all points. Each unoverridden point must independently fall back to its default; there must be no all-or-nothing coupling.
- **Retry / escalation paths**: A stage that escalates to a higher-capability model on retry must select that escalation model through an override point too, not a hardcoded identifier.
- **Cost-tiering integrity**: Because the project assigns models to stages by task weight, overrides must preserve the ability to keep distinct models for distinct tiers rather than collapsing everything to one value — unless the operator deliberately sets them equal.
- **Empty / blank override**: An operator supplies an empty value for an override. The pipeline must fall back to the default rather than invoking an empty or invalid model identifier.
- **Reusable-pipeline consumers**: A downstream repository consuming the pipeline must be able to set the overrides from its own configuration without editing pipeline-owned files.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every model identifier that an automated agent step selects MUST be resolved from a configurable override point rather than from a literal embedded in the pipeline's executable logic. Override points are exposed per task tier: every currently-hardcoded model location MUST map to one of the pipeline's task tiers (e.g. triage, plan/tasks, spec/clarify, implement/escalation), and locations sharing a tier resolve to that tier's override.
- **FR-002**: Each override point MUST define a default value that reproduces the pipeline's current model selection when no override is supplied.
- **FR-003**: Consumers MUST be able to set each override by defining repository variables in the consuming repository — the same mechanism already used for the implement-tier model — without modifying pipeline-owned source (consistent with the project's principle that the consuming repository owns its configuration).
- **FR-004**: Retry, fallback, and escalation model selections (e.g., escalating to a higher-capability model after a failed attempt) MUST be resolved through the override point of their assigned tier, not embedded identifiers.
- **FR-005**: When no overrides are supplied, the pipeline MUST select the same models — for every stage and every retry/escalation path — that it selects today.
- **FR-006**: Overrides MUST be independent: supplying an override for one tier MUST NOT require supplying overrides for any other tier.
- **FR-007**: The set of models a run may select MUST be discoverable from the pipeline's configuration surface alone, without reading pipeline internals.
- **FR-008**: The design MUST preserve the ability to assign different models to different task tiers, so that per-tier cost tiering is not lost when overrides are introduced.
- **FR-009**: When an override point receives an empty or blank value, the pipeline MUST fall back to that point's default rather than invoking an empty model identifier.
- **FR-010**: Every model selection MUST remain explicit after the change — no selection may become implicit or defaulted inside a downstream component in a way that hides which model is used. (The project already requires every automated invocation to declare an explicit model and a bounded turn budget; parameterization keeps the model visible at the configuration layer rather than delegating to a component default.)

### Key Entities *(include if feature involves data)*

- **Model override point**: A named, per-tier configurable setting (a repository variable in the consuming repository) that determines which model the code paths in a given task tier select. The pipeline exposes a small set of tier overrides (e.g. triage, plan/tasks, spec/clarify, implement/escalation); every currently-hardcoded model location maps to exactly one tier. Has a default value and may be set by a consumer.
- **Task tier**: A grouping of pipeline stages/code paths by task weight (cost tiering) to which one model override point applies. Distinct tiers may resolve to distinct models.
- **Default model value**: The value an override point resolves to when the consumer supplies nothing; reproduces current behavior.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of model selections in the pipeline's executable logic — including retry and escalation paths — resolve through a configurable override point; zero remain as embedded identifiers.
- **SC-002**: With no overrides supplied, every stage selects the identical model it selects before the change (verified across all stages and retry/escalation paths).
- **SC-003**: A Bedrock consumer can run every affected stage end-to-end using only their own model identifiers, with no stage invoking a model identifier they did not supply.
- **SC-004**: A consumer can override any single tier's model without being forced to configure any other tier.
- **SC-005**: A reviewer can enumerate every model a run may select by reading configuration alone, in under 5 minutes, without inspecting pipeline logic.

## Assumptions

- "Model that is hardcoded in" refers to executable model selections in pipeline logic (stage invocations, retry/escalation branches, and any script fallback that picks a model). Illustrative model names appearing only in comments, documentation, or prior spec artifacts are out of scope except where they document the new defaults.
- Defaults will reproduce today's model choices, so existing non-Bedrock consumers experience no behavioral change and only Bedrock (or otherwise custom) consumers need to override.
- The pipeline need only accept the operator-supplied model identifiers as-is; validating that a given identifier is a real Bedrock/Anthropic model is out of scope (invalid identifiers surface as ordinary run failures).
- Translating between Anthropic model IDs and Bedrock model/inference-profile identifiers is the consumer's responsibility; this feature provides the override points, not a translation table.
- This feature builds on the existing Bedrock-support work (spec 016) rather than replacing it; where that work already parameterized a model, this feature closes the remaining hardcoded gaps.

## Dependencies

- Relies on the pipeline's existing per-stage model configuration mechanism as the pattern to extend to the currently-hardcoded locations.
- Related to spec `016-bedrock-support`; this feature completes model overridability for locations that remained hardcoded.
