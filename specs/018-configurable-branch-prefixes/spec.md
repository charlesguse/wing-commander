# Feature Specification: Configurable Branch Prefixes & Consumer-Modifiable Naming

**Feature Branch**: `018-configurable-branch-prefixes`

**Created**: 2026-07-24

**Status**: Draft

**Input**: User description: "Parameterize branch names and other parts that should be modifiable by consumers. Consumers of this repository can't have custom naming schemes for their branches. Consumers may choose different branch prefixes, while providing sensible defaults."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Customize branch prefixes for the pipeline (Priority: P1)

A team adopts the reusable spec-driven pipeline in their own repository. Their organization already enforces a branch-naming convention (for example, branch protection rules or CI that expects branches to start with `feature/` or a team abbreviation). They want the pipeline's automatically created branches to follow their scheme instead of the built-in defaults (such as `spec-draft/`), without editing the pipeline's internal logic.

**Why this priority**: This is the core problem stated in the request. Without it, adopters whose repositories enforce naming conventions cannot use the pipeline at all, because the branches it creates would be rejected or would violate policy. It delivers the primary value on its own.

**Independent Test**: Configure a custom prefix for at least one pipeline-created branch type, run the corresponding stage, and confirm the branch is created with the configured prefix while every downstream stage still finds and operates on that branch.

**Acceptance Scenarios**:

1. **Given** a consumer has set a custom prefix for the spec-draft branch type, **When** the intake stage runs on a feature request, **Then** the created branch and its pull request use the custom prefix instead of the default.
2. **Given** a consumer has configured custom prefixes, **When** a later stage needs to locate a branch created by an earlier stage, **Then** the later stage resolves the branch using the same configured prefix and does not fail to find it.
3. **Given** a consumer has configured custom prefixes for some branch types but not others, **When** any stage runs, **Then** the unconfigured branch types fall back to their documented default prefixes.

### User Story 2 - Sensible defaults require zero configuration (Priority: P1)

A team adopts the pipeline and does not care about branch naming. They expect everything to work out of the box exactly as it does today, with no new required configuration.

**Why this priority**: The request explicitly asks for "sensible defaults." Introducing configurability must not break existing adopters or the pipeline's own self-hosted use. Equal priority to P1 because a customization feature that regresses the default experience is not shippable.

**Independent Test**: Run the full pipeline in a repository with no naming configuration present and confirm behavior is identical to the current pipeline (same prefixes, same branches, same labels).

**Acceptance Scenarios**:

1. **Given** no naming configuration is provided, **When** any pipeline stage runs, **Then** it uses the same branch prefixes and naming it uses today.
2. **Given** a consumer removes or omits the configuration file entirely, **When** the pipeline runs, **Then** no stage errors due to missing configuration and defaults apply.

### User Story 3 - Discover and configure all customizable naming in one place (Priority: P2)

An adopter setting up the pipeline wants to know which naming values are customizable and how to change them, from a single documented location, rather than discovering hardcoded strings scattered across stage definitions.

**Why this priority**: Even with the customizable surface scoped to branch prefixes for this feature (see FR-009), an adopter still benefits from discovering every configurable prefix, its default, and its effect in one place. Centralized discovery reduces adoption friction, but the pipeline still functions without it, so it is P2.

**Independent Test**: From the documentation and a single configuration location, an adopter can identify every consumer-modifiable naming value and its default, and change any of them without reading stage internals.

**Acceptance Scenarios**:

1. **Given** the adoption documentation, **When** an adopter looks for customizable naming, **Then** they find a complete list of configurable values, each with its default and effect.
2. **Given** an adopter sets a value in the single configuration location, **When** the pipeline runs, **Then** the change takes effect across every stage that uses that value.

### Edge Cases

- What happens when a configured prefix is empty, contains characters that are invalid in git branch names, or would collide with an existing branch type's namespace? (Resolved by FR-010: the run fails with a clear, actionable error before any branch is created.)
- How does the system behave when a consumer changes a prefix while lifecycle items are already in flight on branches created with the old prefix?
- How does the system handle a configuration file that exists but is malformed or contains unknown keys?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST allow consumers to override the prefix used for each type of branch the pipeline creates, without modifying the pipeline's internal stage logic.
- **FR-002**: The pipeline MUST provide a documented default value for every configurable naming value, and MUST use that default when no override is supplied.
- **FR-003**: Every stage that creates a branch MUST use the configured (or default) prefix, and every stage that later locates or acts on that branch MUST resolve it using the same configured (or default) prefix, so that a custom prefix does not break cross-stage handoff.
- **FR-004**: Consumers MUST be able to override some naming values while leaving others at their defaults; unset values MUST independently fall back to defaults.
- **FR-005**: The pipeline MUST behave identically to its current behavior when no naming configuration is provided (defaults preserve backward compatibility).
- **FR-006**: The set of consumer-modifiable naming values MUST be defined in a single, discoverable configuration location rather than duplicated across stage definitions.
- **FR-007**: Adoption documentation MUST enumerate every consumer-modifiable naming value, its default, and the effect of changing it.
- **FR-008**: The pipeline MUST NOT require any new configuration for existing adopters or for the repository's own self-hosted use to keep working.
- **FR-009**: For this feature, the set of consumer-modifiable naming values is limited to branch prefixes. Other naming elements — stage/lifecycle labels, the approval/gate label that triggers intake, pull request title formats, and the spec directory name pattern — remain fixed and are explicitly out of scope; they may be addressed by a future feature.
- **FR-010**: When a consumer supplies a naming value that is invalid or unusable — empty, containing characters that are illegal in git branch refs, or colliding with another branch type's namespace — the pipeline MUST fail the run with a clear, actionable error before creating any branch, rather than silently falling back to the default.

### Key Entities *(include if feature involves data)*

- **Naming configuration**: The single source that maps each consumer-modifiable naming value to an override, with any omitted value falling back to its default. Consumed by every stage that reads or writes the corresponding names.
- **Branch type**: A distinct category of branch the pipeline creates during the lifecycle (for example, the draft branch produced at intake and any per-stage working branches), each with its own configurable prefix and default.
- **Naming value**: An individual customizable string — for this feature, a branch prefix — with a default and an optional override.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An adopter can change the prefix of any pipeline-created branch by editing a single configuration location, with no edits to stage internals.
- **SC-002**: With a custom prefix configured, the pipeline runs end to end (from feature request through the final stage) with zero cross-stage handoff failures attributable to branch naming.
- **SC-003**: With no configuration present, 100% of pipeline behavior — branch names, pull requests, and labels — is identical to the pre-feature behavior.
- **SC-004**: Every consumer-modifiable naming value is listed with its default in one documentation location, so an adopter can enumerate the full customizable surface without reading stage definitions.
- **SC-005**: A consumer can override a subset of naming values and the remaining values still use their defaults, verified across a full run.

## Assumptions

- "Consumers" refers to other repositories that adopt this project's reusable spec-driven pipeline, not end users of any downstream product.
- The current hardcoded prefixes (such as the intake draft-branch prefix) remain the default values, so existing behavior is preserved when no configuration is present.
- Configuration is supplied through a mechanism already idiomatic to the pipeline (a checked-in configuration file and/or workflow inputs); the exact mechanism is an implementation detail to be settled during planning.
- Changing a prefix affects only branches created after the change; lifecycle items already in flight on old-prefix branches are outside the guaranteed scope of this feature and may need to complete under their original prefix.
- The pipeline retains sole ownership of creating and resolving these branches; consumers customize naming but do not change the pipeline's control flow.
