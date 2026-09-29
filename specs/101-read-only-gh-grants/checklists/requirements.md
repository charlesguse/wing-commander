# Specification Quality Checklist: Read-Only Agents Hold No Write-Capable `gh` Grant

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

- **"No implementation details" — satisfied with a stated caveat.** This
  feature's subject *is* an implementation artifact: the tool allow-lists
  of two agent steps, and the deterministic check that guards them. The
  spec therefore names the workflows, the grant strings, and the existing
  gate whose machinery it extends, because a requirement like "the agent
  must not hold a write-capable grant" is untestable without naming the
  grant. The same convention is used by this repository's sibling
  security-posture specs (`specs/051-read-only-inspection-policy/spec.md`
  quotes `Bash(gh:*)` and `Bash(gh auth status)` directly). What the spec
  deliberately does *not* decide is the mechanism: Question 1 leaves the
  replacement route open, and the "extend check 4b rather than add a new
  gate number" judgement is recorded in Assumptions as an assumption for
  the plan stage to confirm, not as a requirement.

- **"Written for non-technical stakeholders" — satisfied for this
  repository's stakeholders.** The requester is the maintainer of a
  CI pipeline; the Overview states the exposure in plain terms (remote
  writes, local file writes, arbitrary command execution) before any
  requirement names a file.

- **Three `[NEEDS CLARIFICATION]` markers remain, deliberately.** The
  intake stage runs headless in CI and does not wait for answers; the
  markers stay in `spec.md` and the questions are posted to lifecycle
  issue #759 for the clarify stage. All three are genuine trade-offs with
  no defensible default:
  - **Q1 (FR-002)** — what replaces `Bash(gh:*)` on diagnose. This is the
    trade-off the route agent named when it classified the issue as
    spec-shaped: a read-only subcommand allow-list cannot cover
    API-shaped reads, and removing `gh` entirely shifts cost onto the
    collectors. Scope-level impact.
  - **Q2 (FR-014)** — whether the rule binds consumer-supplied
    `extra-allowed-tools`/`allowed-tools-override`. Option B is a
    published-contract compatibility event under Principle VII; the owner
    decides that, not the spec.
  - **Q3 (FR-006)** — what diagnose does when staged evidence cannot
    adjudicate a signal. Bears on whether a narrowing is acceptable at
    all, since a watchdog that reaches no verdict is worse than none
    (Principle II).

- Items marked incomplete require spec updates before `/speckit-plan`.
