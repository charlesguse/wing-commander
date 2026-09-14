# Specification Quality Checklist: One read-only inspection policy for stage tool allowlists

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-14
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

- Three [NEEDS CLARIFICATION] markers remain, on FR-003, FR-006 and FR-009.
  They are the three decisions the lifecycle issue itself names as the owner's
  to make, and each is genuinely open — no default is obviously right, and the
  answers change scope (FR-003 decides whether the tool lists are standardised
  or the prompts redirect to the built-in tools; FR-006 decides whether a
  writable-token stage gains a grant that cannot be restricted to reads;
  FR-009 decides whether a three-and-a-half-minute gate suite enters a stage
  agent's budget). The intake run does not block on them: they are posted to
  the lifecycle issue for the owner and are the clarify stage's subject.
- Every other gap the issue raised was resolved with an informed default and
  recorded as a requirement rather than a question: the deterministic leftovers
  (FR-011..FR-013) and the keep-it-true requirements (FR-014..FR-017).
- "No implementation details" is read as this repository reads it elsewhere:
  the spec names existing artifacts it must interoperate with (the per-stage
  table, the tooling-statement render, the gates that check them) because
  those artifacts are the subject of the feature, but it prescribes no
  mechanism — which list changes, which prose moves, and which gate grows the
  check are the plan's to decide once the three questions are answered.
- Two edge cases were found while specifying and are recorded rather than
  fixed here, because each is a small fact the plan must verify against the
  tree: `intake.yml` sets no `SPECIFY_FEATURE_DIRECTORY` for its agent step
  even though the prompt says it is exported (FR-012), and `plan`/`tasks`
  grant `Bash(gh auth status)` while all four shell-constraint prompt blocks
  tell the agent not to use it (FR-013).
- FR-004 and the assumptions place new agent-facing guidance in the rendered
  tooling statement rather than in four workflow prompts. Planning should
  expect to touch `wing-commander-tool-args` and Gate 21's cases, not just the
  call-site literals and Gate 27's table.
