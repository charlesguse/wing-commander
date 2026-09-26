# Specification Quality Checklist: One Fold Queue Per PR — Concurrent Stage-9 Runs Stop Cancelling Each Other's Legs and Cycles

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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
- **All three `[NEEDS CLARIFICATION]` markers are resolved** by the owner's
  reply on lifecycle issue #560, recorded in the spec's Clarifications section
  (session 2026-09-25): FR-009 takes one implement cycle for the whole
  overlapping set, so a follow-up comment is absorbed into the round in flight;
  FR-016 takes report plus a single automatic re-dispatch, bounded at
  most-once by FR-016a; FR-017 keeps the second round's acknowledgment prompt,
  and FR-017a records that a whole-run per-PR group is ruled out because its
  single pending slot reproduces the eviction. Downstream effects were folded
  into FR-011, US1 scenario 5, US2 scenario 5, US3 scenarios 4–6, SC-003,
  SC-004a, SC-005, the "second run arrives after the first has dispatched" edge
  case, and the Assumptions note on the originating issue's four options.
- **On "no implementation details"**: the Context section names specific
  workflow files, jobs, and line ranges, and Key Entities names the concurrency
  groups by their literal names. This is deliberate and matches the repository's
  house style for pipeline specs (see `specs/060-self-redrive-concurrency`): the
  product *is* the workflow layer, and the observed failure cannot be stated
  without naming the queue the jobs share. The Requirements and Success Criteria
  sections stay behaviour-level — they say what must not be lost or cancelled,
  not which grouping achieves it, so all four options sketched on the issue
  remain open to the plan stage.
- **Constitution alignment**: III (a lost fold and a lost cycle must be legible
  from the issue — US1, US3, SC-005), IV and X (FR-016/FR-016a — the lifecycle
  self-heals once, and the recovery path is bounded so it cannot loop), VII (FR-019 holds the published contract
  fixed), VIII (FR-021, FR-022, SC-007 — a fixture per failure branch, evaluated
  against both files' real expressions), IX (FR-015 — the replaced-vs-human
  cancel verdict is code, not prompt), and the Operational Constraint that
  concurrent specs run in parallel (FR-004, SC-006).
