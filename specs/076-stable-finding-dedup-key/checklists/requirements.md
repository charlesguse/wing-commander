# Specification Quality Checklist: A Stage-Finding Dedup Key That Does Not Drift With Agent Wording

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

- The three `[NEEDS CLARIFICATION]` markers intake left open were answered
  by the repository owner on lifecycle issue #569 and resolved in place by
  the clarify stage on 2026-09-25. None remain:
  - **FR-004** — the keying strategy is the verbatim anchor (an exact
    heading, job name or gate name the agent copies, checked against the
    named file) over stage and normalised file path.
  - **FR-007** — an unanchorable finding falls back to the
    stage-plus-file-path key, with the later encounter appended in full
    text.
  - **FR-015** — this release changes stage findings only; the board loop
    keeps its per-issue key composition, shares the invariants, and a gate
    holds the difference in place.
- The answers introduced one consequence the original draft did not state:
  a run that anchors and a run that does not key apart, so one
  (stage, file) pair can hold two board items rather than one. FR-001,
  SC-001, SC-002, FR-010 and FR-011 were restated against that behaviour,
  Edge Cases gained the mixed-route case, and User Story 1 gained
  acceptance scenario 5 for it. SC-008 was added so FR-015's gate has a
  measurable outcome.
- This spec was drafted by the intake stage of the CI pipeline, so the
  questions were not presented interactively; they were posted to the
  lifecycle issue and answered there.
- Two content-quality items were re-checked after the first pass and
  tightened: Success Criteria originally named the hash function and the
  marker format (implementation detail) and now state the observable
  outcome instead; the User Story 2 independent test originally described
  a specific fixture file layout and now describes the property proven.
- `.specify/feature.json` was intentionally **not** written. The intake
  stage is constrained to create at most one spec directory and to edit no
  file outside it. Downstream stages in this pipeline locate the feature
  directory from `spec-meta.json`, not from `.specify/feature.json`.
