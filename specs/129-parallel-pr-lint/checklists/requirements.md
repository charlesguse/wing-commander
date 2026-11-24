# Specification Quality Checklist: Faster PR Lint — Parallelise the Gate Suite in CI

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-24
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

- All three clarifications were resolved from the reply on lifecycle issue #1198 (2026-11-24): Q1 wall-clock target ≤10 minutes (FR-002, SC-001); Q2 every gate stays its own step, via sharding into several jobs (FR-006, FR-002); Q3 slow-gate speed-ups deferred to the Maintenance backlog (FR-012).
- The subject is CI infrastructure, so the spec necessarily names the workflow file, the local runner script and the check name; these name the subject being changed, not an implementation choice. Shard assignment and mechanism are deliberately left to the plan.
- Issue open questions 3 (shape), 4 (required checks) and 5 (gates that read the workflow) are bounded by FR-003, FR-005–FR-008 as requirements; question 6 (cost) is settled as an assumption.
- Spec review round 1 on #1199 (at `31a530c`) applied: FR-003 keeps both stable names (workflow `lint · workflows` and check-run `lint`) and lists the verdict readers separately from metrics persistence and the board-status report; FR-004 and the edge cases forbid a skipped or neutral aggregate; FR-004a puts `harness tests` under the aggregate; FR-007 makes the job layout the single record of unit membership; FR-009 states the change from today (70 unguarded steps) and its one self-test exception; SC-001 is measured from Actions API timestamps with no tolerance beyond the owner's ≤10 minutes; SC-003 is scoped to verdict readers; SC-005 is deterministic.
