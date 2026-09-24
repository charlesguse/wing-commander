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

- **All three `[NEEDS CLARIFICATION]` markers are resolved.** Per the intake
  stage's CI deviation they were not presented interactively; they were posted
  to lifecycle issue
  [#460](https://github.com/charlesguse/wing-commander/issues/460) and answered
  there on 2026-09-23, and the clarify stage encoded the answers into the spec.
  On 2026-09-24 the owner withdrew the FR-002 and FR-010 answers — the review
  of the draft spec PR showed the premise both rested on does not hold on the
  current tree — confirmed the FR-014 answer, and then re-answered FR-002 and
  FR-010 against the four facts that now govern them (see "What the owner
  decided"). Nothing is outstanding.
  - **FR-002** — the resolution shape for the concurrency conflict. Answered
    **re-drive only the changed behaviour**: the prove step dispatches a
    *directed proof run* aimed at the changed stage, not a whole board
    iteration. Because a directed run selects no board item and opens no fix
    PR, spec 057 FR-048's "one board item in flight repository-wide" **holds
    unchanged** rather than being narrowed or revoked, FR-017's guard stays a
    within-run check on the directed run's shape, and there is no second
    concurrent iteration to pay for. The 2026-09-23 answer, (a) a separate
    concurrency group, is superseded: it failed facts 1, 3 and 4. The directed
    run must be able to exercise the prove step itself, which is what makes
    FR-022 satisfiable (FR-002a). No mechanism for directing a run at one stage
    exists in the tree today; building it is this feature's work, and the spec
    records that as an assumption rather than leaving it implicit.
  - **FR-010** — whether the issue may close on a dispatched-and-started run
    without a terminal conclusion. Answered **no — the bar is unchanged from
    spec 057 FR-043**, and this time the answer is consistent with FR-002
    rather than resting on the withdrawn premise: a directed proof run is
    bounded, so the dispatching prove step itself observes the conclusion, with
    no asynchronous observer introduced. For a change no directed run can be
    aimed at, the prove step records that fact and what changed, leaves the
    issue open, and a human closes it after reading the evidence (FR-010a); the
    loop never substitutes a whole board iteration for the directed run
    (FR-002b).
  - **FR-014** — whether `.github/scripts/**` joins the uses-graph. Answered
    **yes**: a board-helper-only merge re-drives its wrapper like any other
    Actions-only change, because the loop executes those helpers on every
    iteration and "nothing reaches this change" is false for them. Scope is
    therefore *not* removed — User Story 4, FR-013 and FR-015 stay — and the
    ordering caveat (FR-014 not before FR-002) is internal to this feature,
    which ships both. Assumptions records this.
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
  - GitHub keeps at most one pending run per concurrency group, so a queued
    proof dispatch can be displaced outright — by the hourly schedule tick
    today, and under any resolution that leaves proof dispatches sharing a
    group with each other, by a second proof dispatch. FR-007 and the
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
    the mechanism to plan. They stood under every FR-002 option; under the
    adopted one they hold by construction, since a directed proof run takes no
    board item even if it outlives the caller — which is why FR-011 now points
    at FR-017 for the check rather than leaving "by construction" as an
    argument.
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
- Every checklist item passes. With the resolution shape and the evidence bar
  both settled — a bounded directed proof run, observed to a terminal
  conclusion by the prove step that dispatched it — what the prove step waits
  for, what the concurrency blocks guarantee, and what FR-017's check has to
  hold are all determined, so the spec is ready for `/speckit-plan`. The open
  design work the plan inherits is the directed-run mechanism itself (FR-002a):
  nothing in the tree can aim a run at one stage today, and the path that
  reaches the prove step is the hardest part of building one, since `prove` is
  gated on the `pull_request` event.
