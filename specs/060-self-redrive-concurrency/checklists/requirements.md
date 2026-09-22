# Specification Quality Checklist: The Proof Run Can Actually Start — Self Re-Drive vs. the Board Loop's Own Concurrency Group

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-22
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

- Three `[NEEDS CLARIFICATION]` markers remain open, at the three-marker limit.
  Per the intake stage's CI deviation they were not presented interactively;
  they are posted to lifecycle issue
  [#460](https://github.com/charlesguse/wing-commander/issues/460) and the
  clarify stage encodes the owner's answers back into the spec.
  - **FR-002** — the resolution shape for the concurrency conflict. The
    lifecycle issue states outright that this needs an owner decision, not a
    unilateral fix, and names three of the four options (separate group, async
    proof, accept-as-is); the fourth (per-trigger group scoping) is added
    because it is cheaper than the first and the issue does not consider it.
    No default exists: each option pays in a different currency — spec 057
    FR-048's simultaneity guarantee, FR-043's definition of proof, or a
    permanently non-functional re-drive branch.
  - **FR-010** — whether the issue may close on a dispatched-and-started run
    without a terminal conclusion. Separated from FR-002 deliberately: it is
    the evidence bar, and the owner may well want it answered the same way
    (terminal conclusion required) regardless of which concurrency shape wins.
    Guessing it would silently redefine what "proven" means on this board.
  - **FR-014** — whether `.github/scripts/**` joins the uses-graph, whether a
    board-helper-only merge instead closes on the merged PR's own checks, or
    whether the reachability gap leaves this feature's scope. The lifecycle
    issue asks for "the same owner look" on this one and does not propose an
    answer. It is also the one marker whose answer may *remove* scope
    (User Story 4, FR-013, FR-015), which is recorded in Assumptions.
- Findings the spec records that the lifecycle issue did not, established by
  reading the tree rather than assumed:
  - `board-loop.yml` is the **only** member of the dispatchable set —
    `release.yml` carries the run-name/attempt-token wiring but is rejected for
    its required `version` input — so `redrive_target()`'s case 2 can only ever
    return `board-loop.yml` too. The deadlock is the entire re-drive path, not
    case 1 alone. The issue frames it as the self-wrapper case; the spec widens
    it and says why.
  - Correlation *succeeds* against a queued run, because `run-name` is rendered
    at run creation. That is why the symptom is `conclusion=timeout` with a
    real-looking `run-url` rather than an empty `run-url`, and it is why FR-006
    has to separate "never started" from "started and ran out of budget".
  - GitHub keeps at most one pending run per concurrency group, so the hourly
    schedule tick can displace a queued proof dispatch outright. FR-007 and the
    edge-case list cover it; the issue does not mention it.
  - A proof re-drive of `board-loop.yml` runs the loop's own entry gates, so it
    can conclude `success` having stood down without exercising the fix at all.
    FR-003 forbids recording that as proof. This is a correctness hole in the
    *intended* behaviour, not only in today's broken one, and it would have
    shipped with any of the issue's three options.
- Judgment calls made rather than marked, to stay inside the three-marker
  limit:
  - FR-006 through FR-009 (legibility of every no-proof condition) are
    specified rather than asked about: they are required under every FR-002
    option, including "accept the current behaviour", so there is no trade-off
    to settle.
  - FR-011/FR-012 (the abandoned dispatch must not become an unattributable
    board iteration, and its cost must be visible) state the outcome and leave
    the mechanism to plan. Some FR-002 options remove the condition entirely;
    the requirement is written so that satisfying it by removal is valid.
  - FR-004 (the rule must work for a target outside the caller's group) follows
    from the dispatchable set being one workflow *today* and not permanently;
    it is not a trade-off.
  - FR-021's real-tree assertion follows the precedent
    `verify-board-prove.py` already set for exactly this class of silent
    failure, and CLAUDE.md's "a rule with no gate behind it lasts until the
    next session".
  - Out of Scope records what was deliberately excluded: `release.yml`'s
    dispatchability, the loop's budgets and schedule, the other `actions_only`
    path rules, the human-merge rule, and the composite's correlation
    mechanism.
- Domain-vocabulary note: this repository's product is pipeline machinery, so
  "concurrency group", "re-drive", "prove step", "dispatchable" and
  "attempt-token" are the stakeholder's own language. The requirements state
  outcomes — the run starts, the issue names its reason, the guarantee is
  checked — and never prescribe the workflow syntax that produces them. The
  `file:line` citations are evidence for where the defect lives, not
  instructions for the implementation.
- Every other checklist item passes. The spec is ready for `/speckit-clarify`.
