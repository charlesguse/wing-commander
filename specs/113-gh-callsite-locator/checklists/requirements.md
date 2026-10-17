# Specification Quality Checklist: Gate 12 — an authoring rule for `gh` call sites and one shared locator

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-10
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

- The subject of this feature is the repository's own gate suite, so the "users" are maintainers and the implement stage, and names of existing gates, scripts and modules (Gate 12, Gate 28, `wc_shell_harness.py`, `verify-*.py`) are the domain vocabulary rather than leaked implementation choices. Success criteria are stated as counts and outcomes, not mechanisms.
- All three clarifications were resolved by the owner on #993: FR-020 adopts the authoring rule and fail-closed locator, including in published stage workflows and composites (answer A); FR-012 moves Gate 28 onto the shared locator in this spec and leaves #954's script-call reader to its own lifecycle, waived in the single-home check with a tracking line on #889 (answer C); FR-019 adds no new dependency, so a real-parser fallback such as `shfmt` becomes its own evidence-backed proposal if needed.
