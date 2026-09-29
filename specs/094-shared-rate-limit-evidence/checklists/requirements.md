# Specification Quality Checklist: One home for rate-limit evidence

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-29
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
- **3 `[NEEDS CLARIFICATION]` markers remain, deliberately** (FR-004, FR-020, FR-025), at the
  maximum the specify skill permits. Each is a decision the owner has to make, not a gap
  a reasonable default could fill:
  - FR-004 — which rule the unified evidence predicate adopts. Either resolution changes
    an existing behaviour at one of the two call sites (a narrowed close path, or a widened
    retry path #544 deliberately narrowed), so there is no status-quo answer.
  - FR-020 — what to do about statusless `rate_limit_event` records if the real artifact
    of run 32675877971 cannot be retrieved or contradicts the reduced fixture. Safety
    argues both ways (never demote a real refusal / never close on an unproven signal).
  - FR-025 — the shape of the single home. The two subjects are a shell/jq composite and
    a Python gate, so a literal single home imposes a cross-language dependency on one of
    them; the third option (conformance corpus only) satisfies the risk but not
    `CLAUDE.md`'s rule. This is the load-bearing design decision of the feature.
- Content-quality note: this specification names specific files, functions and field
  names throughout. That is deliberate and not an implementation leak — the subjects of
  this feature *are* two named existing implementations of one rule, and a requirement
  that did not name them would not be testable. The stakeholder for this specification is
  the repository maintainer.
- Validation was run once against the checklist above; the only failing item is the
  `[NEEDS CLARIFICATION]` count, which the CI intake deviation requires to be left in
  place for the clarify stage rather than resolved by asking the user inline.
