# Specification Quality Checklist: Gate 68 Derives Its Own Subjects

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-25
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- All three `[NEEDS CLARIFICATION]` markers are resolved, answered on
  the lifecycle issue and folded back into the spec (see
  **Clarifications / Session 2026-09-25**):
  - **FR-002** — the derivation rule: every job in every
    `.github/workflows/` file that contains an agent step, which brings
    `board-loop.yml`, `cleanup.yml`, `rebase.yml` and `watchdog.yml`
    into scope.
  - **FR-004** — the derived set is compared against a checked-in floor
    of known agent-bearing jobs, which derivation must cover and may
    exceed; a dropped subject fails, an un-updated floor fails safe.
  - **FR-014** — the four surfaced workflows are dispositioned per
    workflow: adopt the contract where the agent step has no wall-clock
    bound and a bot-acting step follows it, exclude the rest with a
    recorded reason (`watchdog.yml`'s `diagnose` on its
    `timeout-minutes: 10`).
- **Content Quality / "No implementation details"**: the spec names
  existing files, gate constants and mutation names in its Overview,
  Dependencies and Assumptions. These identify the *subject under
  change* — a deterministic gate is the feature — not a chosen
  implementation. The Requirements and Success Criteria sections state
  behaviour only.
- Items 2, 3 and 4 of the originating issue were verified as already
  landed on `main` (commit `2a1cf1b`) and are recorded in Out of Scope
  rather than dropped silently.
