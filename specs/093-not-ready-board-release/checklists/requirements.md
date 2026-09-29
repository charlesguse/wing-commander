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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-09-28

- **"No [NEEDS CLARIFICATION] markers remain" — was intentionally
  unchecked; see the clarify iteration below for why it is now checked.**
  Three remained at intake: FR-004 (which release mechanism), FR-005 (how a
  self-clearing unmet condition is treated), FR-007 (which step a
  re-admitted item resumes at). The originating issue frames the first as
  an owner trade-off between two competing designs; the other two follow
  from it and carry the same character. Intake runs headless, so the
  questions were posted on lifecycle issue #717 for the clarify stage rather
  than asked in-session. Each had a recorded default in **Assumptions**, so
  every requirement was testable as written and this was the only unchecked
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

### Clarify iteration 1 — 2026-09-29

- **All three questions answered on lifecycle issue #717; every item now
  checked.** The answers are recorded verbatim-in-substance in the spec's
  **Clarifications** section. Q1 → both mechanisms (threshold 3), Q3 →
  self-clearing exempt from the hold but still counted. Both match the
  defaults the draft was written against, so no requirement changed shape.
  Q2 → resume at **`review`**, not `readiness`, which **replaced** the
  draft's default and is the only answer that moved the specification.

- **The owner's reply numbered its answers out of order.** Its "Q2" answers
  this document's Q3 and its "Q3" answers this document's Q2, and its option
  letters are its own rather than the questionnaire's. Each answer names its
  own subject in full, so the mapping was made by content and is recorded in
  the spec's **Clarifications** section for a later reader who compares the
  two.

- **What Q2's answer propagated to, since it changed a default.** FR-007
  (resume at `review`, and the general invariant that nothing is reported
  ready on a head no review has covered); FR-013 (fixtures for the resumed
  step and for budget continuation); FR-014 (spec 061's
  `contracts/resume-recovery.md` gains a step-resolution clause and a
  scenario row); User Story 3's narrative, Independent Test and scenarios 1,
  5 and 6; User Story 2's scenario 3 and the `board:stalled`-removal edge
  case, which now distinguish a head a review has covered from one it has
  not; the two head-movement edge cases; **Assumptions** (the two
  independent bounds, the accepted per-push review cost, and the fact that
  the recorded head SHA *is* the reviewed head so no new lookup is needed);
  **Out of Scope** (the round budget's *value* stays out, its accounting
  across a re-admission comes in); and **Dependencies** (spec 057 FR-031,
  spec 061 FR-014).

- **Two success criteria added rather than one amended.** SC-009 bounds the
  review invocations a repeatedly-pushing human can buy, and SC-010 states
  the invariant Q2's answer was chosen for. SC-004 gained the resumed step.
  Both new criteria are measurable and both are covered by FR-013's fixture
  list, so "All functional requirements have clear acceptance criteria"
  stays honest after the change.

- **One consistency defect in the draft, fixed here.** FR-001 said a
  not-ready outcome releases the board in the same run, unqualified, which
  contradicts FR-005's self-clearing exemption — the case the draft's own
  Q3 default already chose. FR-001 is now scoped to durable conditions and
  names the exemption; User Story 1 scenario 1 says "durable", and a new
  scenario 5 covers the self-clearing contrast. FR-007's citation of "spec
  057 FR-014" was also corrected to spec **061** FR-014 — 057's FR-014 is a
  triage evidence-unavailable rule, not a resume provenance rule.
