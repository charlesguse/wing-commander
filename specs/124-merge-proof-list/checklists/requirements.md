# Specification Quality Checklist: The Proof List

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-19
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

- All three clarification markers (FR-007 App comments, FR-012 leaving the report, FR-021 report location) are resolved from the answer on lifecycle issue #1144, which carries the owner's decision recorded on the Roadmap issue (#890). The issue's other open questions (record rule, window, per-workflow granularity, nightly end-to-end reach, name) were confirmed in the same decision and stand in Assumptions as written. See the spec's Clarifications section.
- The two questions raised in round 1 of the spec PR's review (#1148) are answered from the owner's reply on #1144 (2026-11-19): an App comment counts only under the board item marker at step `proven`, so unmarked App notices never count (FR-007, FR-009); and on an issue that more than one merge in the window names, a comment counts for a merge only when it also names that merge's pull request (FR-006, FR-009, Assumptions, SC-001).
- The question raised in round 2 of the spec PR's review (#1148) is answered from the owner's reply on #1144 (2026-11-19, option B): comments posted through `github-actions[bot]` fall under the same bot-account rule as the App's, so they count only under the board item marker at step `proven` (FR-007, FR-009, Edge Cases). No questions remain open.
- "No implementation details": the spec names existing repository artifacts (`board_prove.actions_only()`, the `prove-after-merge` reach scan, the board item marker, `WING_COMMANDER_*_PAUSED`) because the requirement is to reuse them rather than copy them, which is a behavioural constraint of this repository (CLAUDE.md "Shared logic has exactly one home"), not a design choice. File layout, languages and step shapes are left to the plan.
- Success criteria reference the repository's own merges and comments, which are this feature's user-visible outcomes. SC-001 runs against a checked-in record of what the lookup recorded on #1144 read, with that window supplied for the test only (FR-011), and fails on any difference not on its checked-in list of expected differences.
- The 12 spec findings from round 1 of the spec PR's review (#1148) are applied (2026-11-19). That review's notes for the plan stage are left for the plan stage. The two ticks it questioned were re-checked after the fixes:
  - "Requirements are testable and unambiguous": the aged-out count now has a basis in the build's own inputs (FR-012), the window is anchored to the build's time with a test-only override (FR-011), a run that cannot be resolved is told apart from an incomplete read (FR-013), and SC-001 is pass/fail.
  - "All functional requirements have clear acceptance criteria": FR-001 to FR-004 (Stories 2 and 3, SC-002), FR-005 (Story 1 AS4), FR-006 and FR-009 (Story 1 AS1 and AS3, Edge Cases), FR-007 (Edge Cases), FR-008 (Story 2), FR-010 (Story 1 AS3, Edge Cases), FR-011 (Story 2 AS5), FR-012 (Story 1 AS6), FR-013 (Story 3 AS3, Edge Cases, SC-007), FR-014 to FR-016 (Story 4, SC-004), FR-017 and FR-018 (Story 4 AS1 and AS2), FR-020 (Story 1 AS1, AS2 and AS5), FR-021 (Story 4 AS4 and AS5, SC-005). FR-019 (where the workflow lives) and FR-022 (what `docs/reference.md` says) have no scenario because they describe no runtime behaviour; they are checked by the review of the final PR.
