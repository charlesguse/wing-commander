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

- The three [NEEDS CLARIFICATION] markers that intake left on FR-003, FR-006
  and FR-009 were answered by the owner on #338 and are now folded in; none
  remain:
  - **FR-003/FR-004 (option C)** — standardise the inspection primitive set
    across every read-capable stage (the `plan`/`tasks` set, named in the
    Gate 27 table) *and* have the rendered tooling statement state the
    chaining/redirect rule and the Read/Grep/Glob preference. Both halves
    ship together, because no list closes the compound/piped/redirected
    family.
  - **FR-006/FR-007/FR-008 (option A)** — no stage gains `gh api`. Clarify's
    comment bodies are staged deterministically by the workflow (the
    specs/029 pattern) and plan's PR read uses its existing
    `gh pr view --json` grant; `watchdog.diagnose`'s pre-existing
    `Bash(gh:*)` is recorded as untouched rather than re-granted.
  - **FR-009 (option A, with a preflight)** — implement only, under an
    explicit timeout, with `CLAUDE.md`'s "Before pushing" section scoped by
    audience. The owner added a requirement the options did not carry: a
    preflight for pyyaml/jq/actionlint in the implement container that
    degrades to a summary note rather than a denial or a stage failure. That
    is recorded as FR-009a, with the `CLAUDE.md` scoping as FR-009b and a new
    SC-008 covering both outcomes.
- The answers changed scope in three places beyond the markers themselves:
  User Story 2's third acceptance scenario now asserts the *absence* of a
  `gh api` grant rather than describing one, User Story 3's second scenario
  now names the timeout and the degradation, and the Out of Scope carve-out
  for turn-ceiling behaviour now names the timeout as the one exception that
  is in scope.
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
