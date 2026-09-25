# Specification Quality Checklist: Commit-Message-Policy Prompt Text Has One Home

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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
- Three `[NEEDS CLARIFICATION]` markers remain, by design, on FR-012, FR-013
  and FR-014. Each is an owner trade-off the originating issue explicitly
  asked to be decided rather than guessed: which mechanism holds the single
  home, whether `clarify.yml`'s partial overlap joins it, and whether the
  change covers one paragraph or the wider cycle/retry prompt duplication.
  They are posted to the lifecycle issue for the clarify stage; the
  specification is otherwise complete.
- "No implementation details" is read here as this repository reads it:
  the subject of the feature *is* the repository's own workflow
  instruments, so naming `implement.yml`, `clarify.yml` and the existing
  gates is description of the problem domain, not a prescription of how to
  build the fix. Requirements state outcomes (one home, a gate that can
  fail, equivalent text at both sites) and leave the mechanism to FR-013.
- Scope bounding depends on FR-014's answer; until it is resolved, the
  narrow reading (this paragraph only) is the working assumption.
