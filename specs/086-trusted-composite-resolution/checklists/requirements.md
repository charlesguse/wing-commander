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

- Three [NEEDS CLARIFICATION] markers remain, deliberately, and they are the
  trade-offs the originating issue said an owner must decide rather than a
  local fix pick unilaterally:
  - **FR-011** (scope) — the three jobs exposed today, or every board-loop
    job uniformly.
  - **FR-012** (security) — whether trusted resolution alone is the answer
    for an item branch that edits the loop's own judging surface, or whether
    such an item is additionally stood down or held for a human.
  - **FR-003** (security/provenance) — which commit supplies the trusted
    copy: the commit whose workflow definition is running, or the default
    branch's tip at job start.
  This intake run does not wait for answers; they are posted to lifecycle
  issue #615 as a questionnaire and folded in by the clarify stage. Every
  other requirement carries a reasonable default with its assumption
  recorded, so the marker count is at the limit of 3 and not above it.
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
- Items marked incomplete require spec updates before `/speckit-clarify` or
  `/speckit-plan`.
