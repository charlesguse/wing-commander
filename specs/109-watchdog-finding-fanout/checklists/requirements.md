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
- **Three [NEEDS CLARIFICATION] markers remained** at the skill's limit;
  all three are now resolved — see "Clarification round 1" below.
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

### Clarification round 1 — 2026-09-29 (answers on #792 from @charlesguse)

- **FR-001 — mechanism.** Overlap matching *within a class*; cross-class
  grouping rejected. The class fan-out is answered instead by a filing
  condition (a converging implement cycle's red gate suite is not filed on),
  which the answer states would alone have suppressed #708–#713. FR-009 to
  FR-012 were rewritten from "findings split across classes" to that
  condition, and cross-class grouping moved to Out of Scope.
- **FR-007 — multi-match.** Lowest-numbered open match takes the
  occurrence; the record names the other matches so a maintainer can merge
  them. Explicitly *not* `data-integrity`, and nothing is closed, so spec
  024 FR-014's remediation surface is untouched.
- **FR-023 — retroactive consolidation.** Go-forward only. Added FR-025 to
  state that the existing duplicates are not touched and no follow-up issue
  is filed; Out of Scope now says so too.

Two readings the answer pins rather than states, recorded in the spec's
Clarifications section rather than carried as new markers, because the
answer's own text settles both:

- "Gate-suite finding" is scoped by cited evidence, not by the
  `gate-suite-failure` class label — #708–#713 carry six different classes
  and the answer says the condition alone accounts for all six.
- Overlap matching applies to open issues only (the answer says "open
  issue" in both Q1 and Q2), which also settles FR-006: a partial overlap
  does not reopen a closed issue.

Knock-on edits made for consistency: US2 rewritten around the filing
condition, US3 scenario 2 and US4 scenario 2 rewritten, SC-002/004/005/007
retargeted (SC-004 now scoped to same-class issues, since two issues of
different classes may legitimately share an id under a class-scoped rule),
FR-004 amended to name the one stated reduction, FR-019 amended to separate
a *decided* non-write from an undecidable one, and two grouping-specific
edge cases replaced by the undeterminable-cycle-state case.
