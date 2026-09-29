# Specification Quality Checklist: Watchdog Dedup That Survives Partial Signal Overlap and Class Fan-Out

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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-09-29

- **"No implementation details" and "technology-agnostic"**: read against
  this repository's own domain. The product here *is* GitHub Actions
  workflows, composite actions and gate scripts, so naming
  `watchdog.yml`'s "Compute fingerprint" and "Dedup search" steps, the
  `🐕 · ` class labels and the `pipeline-defect` label identifies the
  subject rather than prescribing an implementation. The spec deliberately
  does **not** choose the marker format for FR-003, the lookup mechanics
  for FR-016, the bound's value for FR-008, or where the new fixtures live
  — those are plan-stage decisions. Matches the house style of
  `specs/088-stop-check-closed-read` and `specs/076-stable-finding-dedup-key`.
  PASS.
- **Three [NEEDS CLARIFICATION] markers remain**, at the skill's limit.
  All three are scope-or-behaviour decisions the issue itself frames as
  open, and none has a defensible default:
  - **FR-001 — which dedup mechanism.** The issue offers three (overlap
    matching, signal-first dedup, per-run grouping for gate-suite
    failures) and they are not equivalent: they differ in false-merge
    risk, in whether the class stays part of the identity, and in whether
    the dedup lookup has to widen past its class-label filter. Choosing
    one on the agent's behalf would decide the feature.
  - **FR-007 — multi-match resolution.** The exact-match analogue today is
    `data-integrity`: report, write nothing, leave it for a human. Under
    any overlap rule multi-match stops being a should-not-happen and
    becomes routine, so inheriting the existing suppression is a real
    choice with a real cost (findings that never reach the board), not a
    safe default.
  - **FR-023 — retroactive consolidation.** Whether this feature closes
    the six-plus-three duplicates it was filed over, or only changes
    go-forward behaviour, changes the size and blast radius of the work.
    CLAUDE.md's rule that out-of-scope work becomes its own issue cuts
    both ways here, so it is the owner's call.
- **Testability of SC-004** ("no two open issues cite a common signal id
  across 20 consecutive runs"): measurable from the tracker plus the
  per-issue signal record FR-003 requires, and only measurable *because*
  FR-003 requires it. Noted as a dependency between the two rather than a
  gap. PASS.
- **SC-002 is deliberately weaker than "exactly one issue"**: run
  36484099706's six findings have not been shown to be one underlying
  failure — the issue says "several of these are probably one red gate
  suite". Asserting a specific count would encode a conclusion nobody has
  verified, so the criterion asserts a reduction plus pairwise-disjoint
  evidence, both of which are checkable without that conclusion. PASS.
- **User Story 3 carries no new capability** — it is a correctness bound on
  Stories 1 and 2. It is kept as a story rather than folded into
  requirements because it is independently testable (replay #761/#764/#780
  and count three issues) and because a silent regression there is the
  most likely way this feature does harm. PASS.
