# Specification Quality Checklist: A Not-Ready PR Releases the Board

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-28
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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-09-28

- **"No [NEEDS CLARIFICATION] markers remain" — intentionally unchecked.**
  Three remain: FR-004 (which release mechanism), FR-005 (how a
  self-clearing unmet condition is treated), FR-007 (which step a
  re-admitted item resumes at). The originating issue frames the first as
  an owner trade-off between two competing designs; the other two follow
  from it and carry the same character. Intake runs headless, so the
  questions are posted on lifecycle issue #717 for the clarify stage rather
  than asked in-session. Each has a recorded default in **Assumptions**, so
  every requirement is testable as written and this is the only unchecked
  item.

- **"No implementation details" and "Success criteria are
  technology-agnostic" — read against this repository's own domain.** The
  product here *is* GitHub Actions workflows, gate scripts and the board
  loop's selection code, so naming `board:stalled`, a scheduled run, a
  fixture or a metrics `run-label` is naming the subject, not leaking an
  implementation. The distinction held to: **what** must be decided and
  **where that decision has its single home** are specified; **how** it is
  encoded is not. Specifically, FR-002 requires the not-ready outcome to be
  recorded durably and machine-readably without saying whether that is a
  new marker field, a new step name, or both — Assumptions defers that to
  the plan stage. FR-004's three options are stated as behaviours (release
  timing, hold condition, handover guarantee), not as code shapes.

- **"All functional requirements have clear acceptance criteria" — checked,
  with the reasoning.** FR-004, FR-005 and FR-007 each name their open
  decision *and* the default the specification is written against, and the
  User Story acceptance scenarios and SC-001…SC-008 are written against
  those defaults. An owner's answer narrows a requirement; it does not
  supply criteria that are missing today. FR-013 additionally makes each
  added rule's acceptance criterion concrete: the rule must have a
  checked-in fixture that fails when the rule is deleted.

- **Cross-artifact consistency.** The spec's "Observed facts" were each
  verified against `main` at `c27d0cb`, with file and line references, so a
  reviewer can re-check the premise without re-deriving it. FR-014 requires
  the superseded prose in specs 057 and 061 to be corrected in the same
  change, since this feature's rule contradicts three shipped statements
  (spec 057 FR-067, `contracts/readiness-report.md`'s "A not-ready outcome
  leaves the marker as it was", and spec 061's enumerations of which steps
  make an item in-flight). CLAUDE.md's single-home rule makes the
  correction canonical in one place with pointers elsewhere.

- **Scope boundary checked against the reported defect.** The issue's own
  two options are FR-004's (a) and (b); (c) is the union, offered because
  each alone leaves one of the two failure modes (an hourly comment, or a
  silently abandoned issue). Nothing about merging, the five readiness
  conditions, or the review round budget is touched — all are in **Out of
  Scope**, and FR-015 plus SC-008 make "unchanged" a checkable claim rather
  than an assurance.
