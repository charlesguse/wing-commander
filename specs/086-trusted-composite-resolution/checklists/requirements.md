# Specification Quality Checklist: The Loop's Own Code Comes From a Trusted Commit — Composite Resolution in board-loop's Item-Branch Jobs

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

- The three [NEEDS CLARIFICATION] markers intake left for the owner were
  answered on lifecycle issue #615 and folded in by the clarify stage; none
  remain:
  - **FR-011** (scope) — answered: **every board-loop job uniformly**, not
    a list of the three jobs exposed today, because a per-job list is the
    same shape as the gap being fixed. Propagated to the Scope section, User
    Story 3, SC-001, the Key Entities and the Assumptions.
  - **FR-012** (security) — answered: **trusted resolution alone**; the loop
    works such an item normally and does not stand it down or hold it for a
    human, since that would stop the loop fixing most of the board. The
    residual gap (the gate suite runs the item's tree while the App token is
    held) stays tracked on issue #590 and is now named in Assumptions and
    Out of Scope. FR-013 was rewritten to match: the rule is unconditional,
    so nothing branches on what the item's content touches.
  - **FR-003** (security/provenance) — answered: **the commit whose workflow
    definition is running**, the same provenance as the #583/#589 helper
    snapshot. Propagated to FR-004, the "two runs at different workflow
    versions" edge case, the Trusted copy entity and the Assumptions.
- Named job names, composite names and file paths appear in the Overview,
  Scope, Edge Cases and Key Entities as *evidence of the reported defect*
  and as the boundary of the change, not as prescribed implementation. The
  functional requirements themselves name behaviours — where the loop's own
  code comes from, what must fail closed, what a gate must catch — not
  mechanisms. The one exception the requirements do name, the gate suite
  running the item's tree, is named because it is the deliberate carve-out
  that the fix must preserve.
- Success criteria avoid naming any mechanism. SC-002's "byte-identical
  loop behaviour" is the observable property, measurable by comparing two
  demonstration runs.
- Counts are stated as "every reference in the affected jobs" rather than a
  literal number, so the requirements cannot go stale as call sites are
  added or removed.
- All items are complete; the spec is ready for `/speckit-plan`.
