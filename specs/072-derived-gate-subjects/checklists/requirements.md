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

- [ ] No [NEEDS CLARIFICATION] markers remain
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

- Three `[NEEDS CLARIFICATION]` markers remain, by design — each is a
  scope decision the owner must make, not a gap a reasonable default
  covers:
  - **FR-002** — the derivation rule, which decides whether
    `board-loop.yml`, `cleanup.yml`, `rebase.yml` and `watchdog.yml`
    come into scope at all.
  - **FR-004** — what the derived set is compared against so a dropped
    subject fails, given that derivation destroys the evidence a job was
    ever a subject.
  - **FR-014** — the disposition of the four workflows derivation
    surfaces: adopt the contract, exclude with a reason, or per-workflow.
- The markers are posted to the lifecycle issue by the intake stage
  rather than resolved in-session; `/speckit-clarify` folds the answers
  back into the spec.
- **Content Quality / "No implementation details"**: the spec names
  existing files, gate constants and mutation names in its Overview,
  Dependencies and Assumptions. These identify the *subject under
  change* — a deterministic gate is the feature — not a chosen
  implementation. The Requirements and Success Criteria sections state
  behaviour only.
- Items 2, 3 and 4 of the originating issue were verified as already
  landed on `main` (commit `2a1cf1b`) and are recorded in Out of Scope
  rather than dropped silently.
