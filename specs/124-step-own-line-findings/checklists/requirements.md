# Specification Quality Checklist: A Gate 60 Finding Names Its Own Step's Line

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-30
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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

- **Three [NEEDS CLARIFICATION] markers remain, deliberately** (FR-003,
  FR-010, FR-012). Each is a scope or single-home trade-off the owner
  decides, not a detail a reasonable default covers:
  - FR-010 (scope) — fix the two checks the issue names, or all eight sites
    carrying the identical defective expression. This changes the diff size
    and whether six live copies of the defect survive.
  - FR-012 (single home) — keep the line resolution private to Gate 60, or
    consolidate the three different answers `verify-gate-24.py`,
    `verify-board-label-creation.py` and this gate currently give. The
    CLAUDE.md single-home rule points at consolidation; the issue's scope
    does not.
  - FR-003 (anchor granularity) — the step mapping's own line, as the issue
    asks, or the matched fragment's line, as the sibling gate that already
    fixed this defect class reports.
  Under the intake stage's CI deviation these are left in place and posted
  to the lifecycle issue as questions rather than blocking the spec.

- **Content Quality, "no implementation details"**: this feature's subject
  is a gate script, so the spec names the gate, its checks, and the sibling
  gates by file — those are the user-facing nouns of this repository, not
  implementation leakage. The spec states no parsing technique, data
  structure, or library: FR-006 states the property the line-carrying
  mechanism must have (invisible to step enumeration, uncollidable) rather
  than the mechanism the issue proposed.

- **Deliberately not stated**: how the line is recorded during parsing. The
  originating issue proposes a specific technique; FR-006 captures the
  property that technique was chosen for, leaving the technique to the plan.
