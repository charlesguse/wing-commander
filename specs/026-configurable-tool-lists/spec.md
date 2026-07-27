# Feature Specification: Configurable Allowed/Disallowed Tool Lists Across Pipeline Stages

**Feature Branch**: `026-configurable-tool-lists`

**Created**: 2026-07-27

**Status**: Draft

**Input**: User description: "Let downstream consumers append and/or replace the allowedTools/disallowedTools arguments across the different workflows. The implement stage is highly customizable depending on the application being built. Consumers need to be able to append their own allowed tools (or replace the list if they want a whole different subset of tools). This holds true for disallowed tools as well. And while the focus is on the implement stage, this is relevant on all of the stages. Consumers should be able to include a few tools and still expect the normal tools to work. Alternatively, someone should be able to replace the whole set of tools if they for some reason want to. Again, same with disallowed tools."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Append extra allowed tools to a stage (Priority: P1)

A downstream consumer building an application with unusual needs (for example, a stage that must run a domain-specific CLI) wants the agent in a pipeline stage to have access to one or two tools beyond the pipeline's built-in defaults, while keeping every default tool the stage normally relies on.

**Why this priority**: This is the core motivating request. Without it, the only way to add a single tool today is to fork and re-maintain the entire hard-coded tool list, which drifts out of sync with upstream. It delivers the most value for the least consumer effort.

**Independent Test**: Configure a stage with one additional allowed tool, run the stage, and confirm the agent can use both the additional tool and the pipeline's normal default tools without the consumer having to restate the defaults.

**Acceptance Scenarios**:

1. **Given** a consumer supplies one additional allowed tool for a stage, **When** that stage runs, **Then** the agent has access to the pipeline's default allowed tools plus the additional tool.
2. **Given** a consumer supplies no additional allowed tools, **When** a stage runs, **Then** the stage behaves exactly as it does today (defaults unchanged, fully backward compatible).

---

### User Story 2 - Append extra disallowed tools to a stage (Priority: P1)

A consumer wants to further restrict a stage — for example, forbidding a tool that is allowed by default because it is inappropriate for their environment — while keeping the pipeline's existing default restrictions in place.

**Why this priority**: Restricting tools is a safety/compliance need that carries equal weight to expanding them; the issue explicitly calls out that appending applies to disallowed tools as well.

**Independent Test**: Configure a stage with one additional disallowed tool, run the stage, and confirm that tool is denied while the pipeline's normal defaults (both allowed and disallowed) still apply.

**Acceptance Scenarios**:

1. **Given** a consumer supplies one additional disallowed tool for a stage, **When** that stage runs, **Then** the agent is denied that tool in addition to the pipeline's default disallowed tools.
2. **Given** a tool is both allowed by default and named in the consumer's additional disallowed list, **When** the stage runs, **Then** the tool is treated as denied for that stage.

---

### User Story 3 - Replace the entire allowed or disallowed list for a stage (Priority: P2)

A consumer with a substantially different use case wants to provide a completely different set of allowed (or disallowed) tools rather than layering on top of the defaults.

**Why this priority**: A less common but explicitly requested capability ("replace the whole set of tools if they for some reason want to"). It is secondary to appending because most consumers need small additions, not wholesale replacement.

**Independent Test**: Configure a stage with a full replacement allowed list, run the stage, and confirm the agent has exactly the replacement tools and none of the discarded defaults.

**Acceptance Scenarios**:

1. **Given** a consumer supplies a replacement allowed list for a stage, **When** that stage runs, **Then** the agent's allowed tools are exactly the replacement list (the defaults not present in it are no longer available).
2. **Given** a consumer supplies a replacement disallowed list for a stage, **When** that stage runs, **Then** the agent's disallowed tools are exactly the replacement list.

---

### User Story 4 - Configure tool lists consistently across every stage (Priority: P2)

A consumer needs the same append/replace capability to be available on every pipeline stage (intake, plan, tasks, clarify, implement, converge, finalize, cleanup, rebase, watchdog, and any other stage that runs an agent), not just the implement stage.

**Why this priority**: The issue states the focus is the implement stage but the need "holds true on all of the stages." Uniform availability prevents consumers from hitting a wall on a stage that lacks the capability, but the primary value is already delivered by Stories 1–3 on any single stage.

**Independent Test**: Apply an append configuration to each stage that runs an agent and confirm each stage honors it identically.

**Acceptance Scenarios**:

1. **Given** every agent-running stage exposes the same configuration capability, **When** a consumer appends a tool on any one of those stages, **Then** the behavior matches the append behavior described in Story 1.
2. **Given** a consumer configures nothing on a stage, **When** that stage runs, **Then** it uses its existing defaults unchanged.

---

### Edge Cases

- What happens when a consumer provides both an append value and a replacement value for the same list on the same stage? The configuration is rejected and the stage fails with a clear message; the consumer must choose one or the other (see FR-010).
- What happens when a consumer's appended allowed tool is a tool the pipeline disallows by default? The explicit append (allow) wins and re-enables the tool for that stage (see FR-011).
- What happens when a consumer fully replaces the allowed list and omits a tool the stage itself needs to complete its own bookkeeping (e.g. committing and pushing its results)? "Replace" means literally the consumer's list only; the pipeline does not silently re-add core tools, so an omission is the consumer's responsibility and may cause the stage to fail (see FR-012).
- What happens when the same tool name appears twice (once in defaults, once in an append list)? Duplicates should be harmless and collapse to a single grant/denial.
- What happens when a consumer provides an empty replacement value (empty string / empty list)? This should be distinguishable from "no value provided" so it does not accidentally strip all tools — an unset input keeps defaults; an explicit empty replacement is treated as an explicit choice.
- What happens on stages that do not run an agent (purely deterministic steps)? They have no tool list to configure and the configuration is simply inert for them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each pipeline stage that runs an agent MUST expose a way for a downstream consumer to supply additional allowed tools that are added to the stage's default allowed tools.
- **FR-002**: Each pipeline stage that runs an agent MUST expose a way for a downstream consumer to supply additional disallowed tools that are added to the stage's default disallowed tools.
- **FR-003**: Each pipeline stage that runs an agent MUST expose a way for a downstream consumer to supply a replacement allowed-tools list that is used instead of the stage's default allowed tools.
- **FR-004**: Each pipeline stage that runs an agent MUST expose a way for a downstream consumer to supply a replacement disallowed-tools list that is used instead of the stage's default disallowed tools.
- **FR-005**: When a consumer supplies no tool configuration for a stage, the stage MUST behave identically to its current behavior (full backward compatibility — existing consumers require no changes).
- **FR-006**: The capability described in FR-001 through FR-004 MUST be available uniformly on every pipeline stage that runs an agent, not only the implement stage.
- **FR-007**: When appending, the pipeline MUST preserve the stage's default tools so the consumer does not have to restate them; the effective list is the union of defaults and the appended tools.
- **FR-008**: When replacing, the pipeline MUST use only the consumer-provided list as the effective list for that stage, discarding the corresponding defaults.
- **FR-009**: The system MUST distinguish "no value provided" (keep defaults) from an explicitly empty value (an intentional choice), so that omitting configuration never unintentionally removes tools.
- **FR-010**: When a consumer supplies both an append value and a replacement value for the same list on the same stage, the system MUST reject the configuration as an error and fail the stage with a clear message that identifies the conflicting inputs, rather than silently choosing one. The consumer must pick either append or replace for a given list.
- **FR-011**: An appended allowed tool MUST take precedence over a default disallowed entry naming the same tool: the consumer's explicit allow re-enables the tool (allow wins). There is no "protected" subset of default denials that append cannot override; a consumer who appends an allowed tool that the pipeline denies by default re-enables it for that stage.
- **FR-012**: On a full replacement of the allowed list, the effective allowed list MUST be exactly the consumer's replacement list; the pipeline MUST NOT silently re-add its own core tools. The consumer is responsible for including every tool the stage needs to complete its own lifecycle bookkeeping (e.g. committing and pushing stage results, updating lifecycle metadata). If a replacement omits a tool the stage needs, that stage may fail to complete — this is the consumer's responsibility, consistent with the meaning of "replace."
- **FR-013**: The configuration MUST be documented for consumers, including the append-vs-replace semantics and the default tool lists each stage uses, so a consumer can make an informed choice.
- **FR-014**: Invalid or malformed configuration values MUST fail visibly (surface a clear signal) rather than silently discarding a consumer's intent or silently reverting to defaults.

### Key Entities *(include if feature involves data)*

- **Allowed-tools configuration**: The consumer-provided intent for which tools an agent may use in a stage, expressed as either an append (added to defaults) or a replacement (used instead of defaults).
- **Disallowed-tools configuration**: The consumer-provided intent for which tools an agent must not use in a stage, expressed as either an append or a replacement.
- **Stage default tool lists**: The built-in allowed and disallowed tool sets each stage ships with today; the baseline that append builds on and replace overrides.
- **Effective tool list**: The final allowed/disallowed sets an agent runs with for a given stage, derived from the defaults and the consumer's configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A consumer can add a single allowed tool to a stage by supplying exactly one configuration value, without restating any default tool.
- **SC-002**: A consumer can add a single disallowed tool to a stage by supplying exactly one configuration value, without restating any default.
- **SC-003**: A consumer can fully replace a stage's allowed or disallowed list by supplying one configuration value.
- **SC-004**: Every pipeline stage that runs an agent supports the same append and replace capability (100% coverage of agent-running stages).
- **SC-005**: Existing consumers who supply no tool configuration observe zero change in stage behavior (0 breaking changes).
- **SC-006**: A consumer can determine, from documentation alone, what each stage's default tool lists are and how append and replace interact, without reading pipeline source.

## Assumptions

- Configuration is applied per stage (each stage is invoked independently as a reusable workflow today), so a consumer sets tool lists on the specific stage(s) they want to customize; there is no separate pipeline-wide global setting in this feature's scope. A consumer wanting the same customization everywhere applies it on each stage.
- "Stages that run an agent" are the ones in scope; purely deterministic stages with no agent tool list are unaffected and require no configuration surface.
- Removing an individual default allowed tool while keeping the rest (a "subtract" operation) is out of scope; the requested operations are append and replace only. A consumer needing removal uses replacement.
- The existing default tool lists per stage remain the shipped defaults; this feature adds configurability around them but does not redefine what the defaults are.
- Configuration values name tools in the same form the pipeline already uses for its tool lists; validating the internal correctness of an individual tool name/pattern is the underlying agent runtime's responsibility, not this feature's.
