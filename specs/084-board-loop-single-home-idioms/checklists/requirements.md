# Specification Quality Checklist: Single-home the remaining board-loop idioms

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

- **3 [NEEDS CLARIFICATION] markers remain**, at the limit and deliberately
  left for the clarify stage. Each is a trade-off the owner decides, not a
  gap a reasonable default closes:
  - **FR-005** — the consolidation mechanism for the marker-write
    bootstrap. Gate 98 (`verify-board-loop-helper-provenance.py`) allows
    only three python spellings inside the fix, review and readiness
    jobs, all resolving under the pristine snapshot; a composite action
    resolves from a checkout those jobs' agents can write, so the obvious
    answer for a shell idiom is not obviously the right one here.
  - **FR-009** — published (`wing-commander-*`) versus internal
    (`_shared/`) placement for the PR-branch composite. Constitution VII
    makes a published composite's inputs and outputs an adopter-pinned
    compatibility surface; widening it is "a deliberate act rather than a
    convenience", which is precisely an owner's call.
  - **FR-015** — one home for the new checks versus one check per idiom's
    nearest existing gate. `CLAUDE.md` says "the nearest existing gate";
    the existing cross-workflow single-home gate says its remit is
    cross-workflow duplication. Both readings are defensible and they
    produce different file layouts.

- **Content Quality, "no implementation details"**: this specification names
  concrete files, gates and job names throughout. That is deliberate and
  not a violation here — in this repository the workflows, gates and
  composite actions *are* the product surface, and a requirement such as
  "the marker-write bootstrap has one home" is untestable without naming
  the 17 sites it must disappear from. What the spec deliberately does not
  fix is *how* each consolidation is built; that is the plan stage's work,
  and the three open questions above are exactly the points where the spec
  stops short.

- **Counts are baseline facts against `main` at commit `e170077`**: 17
  marker-write sites, 2 PR-branch sites, 6 kill-switch callers. The plan
  stage should re-verify them against the real tree rather than trusting
  this number, per the repository's usual T001 discipline.
