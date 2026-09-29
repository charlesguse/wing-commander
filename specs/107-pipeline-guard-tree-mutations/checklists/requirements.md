# Specification Quality Checklist: Guard the pipeline checkout against every tree-mutating step

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-29
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

### No [NEEDS CLARIFICATION] markers remain — FAILS, deliberately

Three markers remain, at the cap the specify skill allows:

1. **FR-002** — how wide the tree-mutating class is (the two named paths only,
   plus agent steps, or every in-shell tree-mutating git verb). This is a scope
   decision the owner makes: the narrow reading fixes today's two holes, the wide
   reading closes the class but enlarges the gate's static-analysis surface.
2. **FR-005** — where the guard goes when the mutation lives inside a shell block
   rather than as its own step (metrics-persist's eight-attempt retry loop). This
   determines what Gate 116 can pin byte for byte and how an in-shell call site
   coexists with the single-home rule, so it cannot be defaulted away.
3. **FR-009** — whether a guard refusal inside metrics-persist fails the metrics
   job (dropping the run's records) or degrades visibly. Fail-closed is the
   established stance everywhere else, but metrics-persist is the one site where
   fail-closed loses data that nothing else reproduces.

These are posted to lifecycle issue #789 as questions rather than resolved here,
per the intake stage's CI deviation from the skill.

### Content-quality items — passing, with the domain noted

The subject of this feature is CI machinery, so the "user" is the pipeline owner
and the named artefacts (the guard script, Gate 116, the two workflow files) are
the domain objects, not implementation choices. They appear in Dependencies and
in requirements that pin *where* behaviour must hold; the requirements themselves
state outcomes (a refusal happens, a gate fails) and leave the mechanism to
planning. Success criteria are stated as observable outcomes and counts, with no
reference to how the check is written.
