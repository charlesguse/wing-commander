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
  the plan stage to confirm, not as a requirement. Question 1 is now
  answered (remove `gh`, stage the failed jobs' logs), so the replacement
  route is stated as FR-018–FR-020; the mechanism *inside* that route —
  which logs, which paths, which script — remains the plan stage's call.

- **"Written for non-technical stakeholders" — satisfied for this
  repository's stakeholders.** The requester is the maintainer of a
  CI pipeline; the Overview states the exposure in plain terms (remote
  writes, local file writes, arbitrary command execution) before any
  requirement names a file.

- **All three `[NEEDS CLARIFICATION]` markers are resolved.** They were
  raised by intake (which runs headless in CI and does not wait for
  answers), posted to lifecycle issue #759, and answered there on
  2026-09-29. The answers are folded into the requirements and recorded in
  `spec.md`'s Clarifications section:
  - **Q1 (FR-002)** — what replaces `Bash(gh:*)` on diagnose. **Answered:
    Option C** — remove `gh` outright and stage the failed jobs' logs
    beforehand, with the fetch failing loudly rather than silently under the
    App token. Because both named agents now end at zero `gh` grants, the
    fleet rule is the same total rule board-loop's check 4 applies, and no
    per-subcommand allow-list ships (FR-002, FR-007, FR-018, FR-019).
  - **Q2 (FR-014)** — whether the rule binds consumer-supplied
    `extra-allowed-tools`/`allowed-tools-override`. **Answered: Option A** —
    shipped defaults only, because the consuming repository owns its
    configuration (Principle VI). Option B's published-stage runtime refusal
    is out of scope, so this feature is not a compatibility event under
    Principle VII.
  - **Q3 (FR-006)** — what diagnose does when staged evidence cannot
    adjudicate a signal. **Answered: Option A** — reuse the
    untrusted-collectors mechanism so the verdict names the evidence it
    could not gather, which keeps a narrowed watchdog reaching a verdict
    (Principle II) (FR-020, SC-008).

- No items remain incomplete; the spec is ready for `/speckit-plan`.
