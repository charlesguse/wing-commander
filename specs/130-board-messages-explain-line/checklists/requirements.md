# Specification Quality Checklist: Board loop messages explain the line

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-25
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

- The three [NEEDS CLARIFICATION] markers (FR-008 review output form, FR-013 where the one-decision question goes and how the answer is picked up, FR-016 scope of surfaces) were resolved from the reply on #1215: Q1 A (named parts plus a gate), Q2 A (comment on #889 keyed by the `bl-` identifier), Q3 A (board-loop fix PRs only, for now). See the spec's Clarifications section. Q2's FR-013 has since moved to the follow-up spec-proposal #NNN (see below).
- The issue's open questions 1, 4 and 5 were given defaults recorded under Assumptions (FR-004, FR-017, FR-018); clarify may revisit them.
- The spec names existing repository artefacts (the auto-merge switch, the kill switch, `spec-proposal`, the Maintenance backlog) because they are the subject of the feature, not implementation choices.
- Spec review round 1 (2026-11-25): one canonical list of named parts (Background), constitution X settled by argument rather than amendment (FR-019, owner decision), maintainer-only answers read as data (FR-020), a distinct awaiting-decision state (FR-021), issue items keep today's routing (FR-022), the review parts mapped onto spec 127 as a rendering layer (FR-008a), and the posting-time refusal separated from the fixture gate (FR-007, FR-008).
- Spec split (owner decision 2026-11-25, recorded on #890, following spec review round 2 finding 3): Story 4 ("fix, but needs one decision"), FR-012–FR-015, FR-019–FR-022, SC-004, the constitution X argument, the awaiting-decision state, its edge cases and Key Entities moved to the follow-up spec-proposal #NNN. FR numbers are not renumbered. FR-016 now covers the fix PRs and the ticked-line records only. Q2's text stays in Clarifications with a pointer to #NNN.
- Spec review round 2 (2026-11-25): FR-004's PR-body summary is fenced as FR-003a and subject to spec 121's closing-keyword refusal (finding 6); Story 3 scenario 1 says the loop merges once the merge gate holds (finding 7). Findings 1, 2, 4 and 5 concern only the split-out route and are carried as requirements to settle on #NNN.
