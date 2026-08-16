# Specification Quality Checklist: The Prompt's Tooling List States What the Run Actually Permits

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-16
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

**Validation run**: one pass over the draft. One item failed and was fixed; the rest passed as written.

- **Failed — "All functional requirements have clear acceptance criteria"**: FR-016 (the step-skip condition keeps meaning only "composition produced no allowed list", and must not become a proxy for an empty statement) appeared in Edge Cases but had no acceptance scenario behind it. Added as User Story 2, Acceptance Scenario 7, which separates the two configurations that were being conflated: no list composed at all (agent does not run) versus a list with no shell grant in it (agent runs, and is told no shell command is permitted).

- **Passed, with the judgement recorded** so a later reader does not re-litigate it:
  - *No implementation details*: file paths, the composite's name, and the output identifier appear only in the **Input** block, which quotes the request verbatim by template convention. The requirements name roles ("the composite action", "the tooling statement", "the enforced lists"). References to specs 026 and 036 are this repository's own prior features, not implementation detail.
  - *Written for non-technical stakeholders*: read as satisfied in context — the product is pipeline infrastructure and its stakeholders are adopters and maintainers, the same audience specs 033–036 are written for.
  - *Success criteria measurable and technology-agnostic*: every SC is a count, a percentage, or a before/after comparison over "legal configurations". None names a tool, file, or format.

- **Zero [NEEDS CLARIFICATION] markers.** Three candidates were resolved with documented defaults instead, each recorded in Assumptions rather than deferred: subtraction granularity for a partially-overlapping deny (per grant — a deny must cover everything its allow permits); how an exact-command grant is distinguished from a prefix grant (stated distinctly per FR-004, with the wording left to planning); and whether the prompt's existing exactness claim is kept or dropped (kept, and made true — FR-009).

- **Constitution check**: Principle VII (Two Interfaces) is why this feature exists — User Story 3 and FR-011/FR-012 close an undeclared widening of the published contract. Principle I is breached by the change that prompted this spec: the output shipped ahead of its specification, and this spec is the retrospective correction rather than the originating artifact. That is worth stating in the eventual PR description per Principle I's own bootstrap clause. No principle conflicts remain in the spec as written.
