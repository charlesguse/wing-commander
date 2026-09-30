# Specification Quality Checklist: Denied Read-Only Commands — Widen the Grant, or Stop Filing the Recovery

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-30
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [ ] No [NEEDS CLARIFICATION] markers remain — **three remain (FR-001, FR-005, FR-007)**, at the skill's limit; they are posted to lifecycle issue #827
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

### Validation iteration 1 — 2026-09-30

- **"No implementation details" and "technology-agnostic"**: read against this
  repository's own domain, matching the house style of
  `specs/109-watchdog-finding-fanout` and `specs/090-stage-write-boundary`.
  The product here *is* GitHub Actions workflows, composite actions and gate
  scripts, so naming `watchdog.yml`'s collector and eligibility steps, the
  `default-allowed-tools` literals, the `pipeline-defect` label and
  `git_read.py` identifies the subject rather than prescribing an
  implementation. The spec deliberately does **not** choose where the
  recovery predicate is computed, which grants are added, how the
  suppression is reported, or where the fixtures live — those are
  plan-stage decisions. PASS.
- **Three [NEEDS CLARIFICATION] markers remain**, at the skill's limit. All
  three are decisions the issue itself frames as open, and none has a
  defensible default:
  - **FR-001 — which route.** The issue is explicitly a request for the owner
    to choose between (a) widening grants, (b) suppressing recovered
    denials, and (c) sharpening prompts. They are not equivalent: only (b)
    bounds the issue rate, only (a) and (c) reduce the turns the agents lose,
    and (b) puts a defect class behind a suppression that Principle VIII
    then has to keep honest. Choosing on the owner's behalf would decide the
    feature, which is exactly why CLAUDE.md routes this shape to a spec
    rather than a fix PR.
  - **FR-005 — what counts as "recovered".** Four candidates are offered,
    each strictly narrower than the last. The difference is not cosmetic: a
    run that went green after burning twelve turns on refused variants
    recovers under the loosest reading and does not under the count-bounded
    one, and that single choice decides whether the live #764 run (seven
    denials, run delivered) files or not.
  - **FR-007 — the reporting surface for a suppressed denial.** The existing
    analogue is `narrative-drift`'s issueless path, which reports to the
    lifecycle issue and files nothing. Inheriting it is a real choice with a
    real cost — a denial rate that climbs is then visible only to whoever
    reads a lifecycle issue on purpose — so a digest surface is a
    substantively different answer, not a variation on it.
- **Deliberately *not* raised as a fourth marker**: whether `git stash`
  should be granted. The spec answers it as a requirement (FR-012) rather
  than a question, because the issue's own framing calls it read-only and it
  is not — that is a factual correction, not a trade-off, and Principle V
  already settles it. Flagged in the Overview so the owner can overrule it
  in the clarify round if they disagree.
- **Testability of SC-003** ("zero issues across 20 consecutive runs, and
  every denial still accounted for"): measurable from the tracker plus the
  named-outcome record FR-008 requires, and only measurable *because* FR-008
  requires it. Recorded as a dependency between the two rather than a gap.
  PASS.
- **SC-001 is deliberately written as "the number the adopted answer
  predicts"** rather than a fixed count. Every candidate answer to FR-001
  and FR-005 implies a different count for the same three replayed runs, so
  naming one would smuggle an answer into the success criteria. The
  criterion still bites, because it also requires that a reviewer predict
  the count from the requirements before the replay. PASS.
- **SC-006 is verified by inspection, not by a gate.** One row per denied
  command shape, checked at review time. A gate would have to encode "what
  information did the agent actually need", which is a judgment, not a
  derivable fact — and per Principle IX a judgment that gates nothing
  durable does not need to be code. PASS.
- **User Story 2 carries no new capability** — it is the correctness bound on
  User Story 1. Kept as a story because it is independently testable (replay
  a failed run carrying a denial and count one issue) and because a silent
  regression there is the most likely way this feature does harm: it would
  trade visible noise for invisible blindness.
- **Requirement groups FR-004–FR-010, FR-011–FR-016 and FR-017–FR-020 are
  conditional on the FR-001 answer.** They are written as full requirements
  rather than sketches so that whichever combination the owner picks arrives
  at the plan stage already specified; the groups the answer does not adopt
  drop out in the clarify round. Noted here because a reader who expects
  every FR to bind unconditionally will otherwise read the spec as
  over-specified.
