# Specification Quality Checklist: Composite Test Harness Gate Discovery

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

- All three [NEEDS CLARIFICATION] markers are resolved by the answer on
  lifecycle issue #591, recorded in the spec's **Clarifications** section:
  FR-001 takes option (b) — `.github/scripts/` stays the single discovery
  root and a new gate fails on any harness under `.github/actions/`; FR-011
  leaves the three existing harnesses in place, which option (b) makes moot;
  FR-012 bounds the enforcement check to `run-tests.sh` and standalone
  `verify-*.py|.sh` at any depth under `.github/actions/`, carving out
  `.github/actions/_shared/`. The questions were posted to the issue rather
  than asked interactively, per the intake stage's CI deviation.
- Option (b) reshaped Stories 1–3 rather than only the three requirements:
  Story 1's mechanism is now a gate asserting local/CI set equality, Story 2
  is placement enforcement rather than a second discovery root, and Story 3's
  reverse-direction gap is now grounded in the `.github/actions/_shared/*.sh`
  helpers that `run:` blocks already invoke directly.
- FR-007 was sharpened from a hypothetical to a live defect: all five
  `run-tests.sh` harnesses in the tree today share the single local-runner
  label `run-tests.sh`, so the timing cache cross-attributes them. SC-008 was
  added to make that measurable.
- "No implementation details": the spec names existing files
  (`wc_gate_registry.py`, `verify-gate-wiring.py`, `run-local-gates.py`) only
  in the **Input** quotation of the originating finding and in the framing of
  which existing behaviour changes. The requirements themselves are phrased
  as behaviours of "gate discovery", "the wiring gate" and "the local gate
  suite", so a plan is free to choose where the change lands.
- Items marked incomplete require spec updates before `/speckit-plan`.
