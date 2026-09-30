# Specification Quality Checklist: Attributable Gate Output in the Local Gate Suite

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-30
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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
- **[NEEDS CLARIFICATION] markers: 3 remain, at the cap.** FR-004 (is the
  full passing-gate output a new opt-in mode or a change to the default
  run?), FR-007 (suppress the expected fixture message at its source, or
  keep it visible with an "expected" marker?), FR-010 (does the
  fixture-drift requirement cover only the two gates named in the report,
  or every gate that stages fixtures?). All three change the size or the
  shape of the delivered work, and none has a default the spec could pick
  without deciding for the owner — FR-010 in particular is the difference
  between fixing the reported instance and making the class
  unrepeatable. Per the intake stage's CI deviation these are left in
  place and posted to the lifecycle issue rather than blocking.
- **"No implementation details" — accepted deviation, recorded not
  waved through.** The users of this feature are this repository's
  maintainers, and the product surface *is* a command and its printed
  output. The spec therefore names the suite's entry point, its
  serial/parallel selector, and the distinction between a gate's own
  output and its children's, because a requirement about what a run
  displays is untestable without them. It names no language construct,
  library or file layout, and every FR and SC is stated as an observable
  property of a run rather than as a change to a particular file. The
  "non-technical stakeholders" item is read the same way: the audience is
  a maintainer running the suite before pushing.
- The originating report's stated cause (a cwd/relative-path race) is
  deliberately *not* adopted as a requirement. Two fix attempts have been
  closed unmerged for acting on an unconfirmed emitter, so FR-005 requires
  the emitter be captured before any disposition, and the spec's
  Assumptions record the hypothesis as a hypothesis.
- Scope bound worth re-reading at plan time: this feature changes what the
  suite *reports*, not which gates run or what any gate checks. FR-006,
  FR-010 and FR-012 are the only requirements that can change a verdict,
  and each does so by turning a silent pass into a loud failure — never
  the reverse.
