# Specification Quality Checklist: A Run That Spent Money Says So — Intake's Silent Outcome Paths Report Their Cost

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-24
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

- Both [NEEDS CLARIFICATION] markers were answered on lifecycle issue #495
  and are now folded into the spec; no markers remain.
  - **FR-002 (scope)** — answered: the uniform option. One cost report per
    cost-bearing stage, emitted from the cost line's existing single home;
    the outcome callouts stop carrying the cost line (FR-002a) and the
    clarify (#366) and plan/tasks (#377) bespoke copies retire in the same
    change. Recorded as FR-001a, FR-002, FR-002a, FR-004, FR-010a, User
    Story 3, SC-006 and SC-007. The single-home check joins the nearest
    existing gate, per CLAUDE.md's "shared logic has exactly one home".
  - **FR-012 (coverage of deliberately failed runs)** — answered: include
    them. Every run that invoked its agent reports its cost whatever its
    conclusion, both veto paths included, and the report must not be
    strandable by the failing step above it (FR-012a). Cancelled runs stay
    exempt, matching what the supervision layer already skips (FR-013).
    Recorded also as US2 scenarios 6 and 7 and a rewritten edge case.
- The requester's answer carries two implementation directions that the spec
  records as constraints rather than prescribed mechanisms (under
  Assumptions): gate the report so a failing step above it cannot strand it,
  and give that gating a `review-step-gating` pass before merge.
- Every other gap was closed with a documented default rather than a
  marker: the delivery shape (a short comment of its own, following the
  clarify precedent), the metrics-unavailable wording, the treatment of
  runs that never invoked an agent, and the requirement that a failed post
  never changes the run's conclusion are all recorded under Assumptions and
  as functional requirements.
- Issue numbers (#366, #377, #381, #495) and the named outcome paths appear
  as *evidence of the reported defect* and as the boundary of the change,
  not as prescribed implementation. The functional requirements themselves
  name behaviours, not mechanisms.
- No items remain incomplete; the spec is ready for `/speckit-plan`.
