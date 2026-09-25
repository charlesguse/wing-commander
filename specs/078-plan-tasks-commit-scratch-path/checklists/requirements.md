# Specification Quality Checklist: A Plan or Tasks Agent Can Write a Multi-Line Commit Message

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

- The three clarification markers that were posted to the lifecycle issue
  (FR-010 scope, FR-011 single home, FR-012 gate backing) were answered on
  [#585](https://github.com/charlesguse/wing-commander/issues/585) and are now
  resolved in the spec: scope is every agent prompt that instructs a commit
  (nine sites across five workflows); the guidance text lives in one canonical
  source rendered into each prompt, shaped so `implement.yml`'s two sites can
  draw from it later (#605); and a new `verify-*.py` gate covers the in-scope
  sites with a visible exemption list for deterministic one-line committers.
  SC-006 and SC-007 no longer carry a dependency caveat, and SC-008 was added
  for the exemption list's completeness.
- "No implementation details" is read here as this repository reads it: the
  subject of the feature *is* workflow prompt text, so naming the affected
  workflows and prompt sites is the feature's domain vocabulary, not a leaked
  implementation choice. The requirements state what an agent must be told and
  what must hold afterwards; they do not dictate the sentence's wording, the
  filenames, or the mechanism by which the text is kept consistent.
- With all three resolved, the change now has three deliverables rather than
  one: the canonical guidance source, its rendering into seven prompt sites
  across four workflows (`plan.yml`, `tasks.yml`, `board-loop.yml`,
  `pr-conversation.yml`), and the new gate with its exemption list.
  `implement.yml`'s two sites stay as they are (FR-013).
- No items remain incomplete; the spec is ready for `/speckit-plan`.
