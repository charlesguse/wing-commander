# Specification Quality Checklist: The Last Two Agent Stages Join the Credential Sweep

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

- Two `[NEEDS CLARIFICATION]` markers remain by design, both on genuine forks
  the owner has to decide and neither of which has a defensible default:
  - **FR-005** — `cleanup.yml`'s remedy: the full post-agent mechanism
    (uniform, no exemption needed, three extra steps in a job whose agent has
    never exceeded one minute) versus a wall-clock bound plus a recorded
    exemption (cheaper, but a second and weaker kind of coverage). The
    measured data supports either; the choice is about which cost the owner
    would rather carry.
  - **FR-009** — how the check's subject list is determined: derived by
    scanning for agent steps (pulling `board-loop.yml` and `watchdog.yml` into
    this feature, and resolving #410 item 1 here) versus hand-extended with
    these two files only. This materially changes the feature's size.
- Per the intake stage's CI deviation, these are not resolved by waiting in
  the spec run; they are posted to lifecycle issue #558 as clarification
  questions.
- Unrelated to the markers: FR-001–FR-004, FR-006–FR-008 and FR-010–FR-016
  are all written against observable workflow behaviour or a gate outcome, so
  each is testable without knowing the implementation.
- Content-quality note: the Overview cites specific file and line numbers.
  These are evidence for *why* the feature exists — the observed defect — not
  a prescription of how to fix it; the requirements themselves name jobs and
  behaviours, never steps to write.
