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

- **One of the three `[NEEDS CLARIFICATION]` markers is resolved; two are open
  again.** Per the intake stage's CI deviation they were not presented
  interactively; they were posted to lifecycle issue
  [#460](https://github.com/charlesguse/wing-commander/issues/460) and answered
  there on 2026-09-23, and the clarify stage encoded the answers into the spec.
  On 2026-09-24 the owner withdrew the FR-002 and FR-010 answers — the review
  of the draft spec PR showed the premise both rested on does not hold on the
  current tree — and confirmed the FR-014 answer. Those two markers are
  therefore restored, re-asked with the four facts that now govern them (see
  "What the owner decided, and what is open again"). This checklist item stays
  unchecked until they are answered.
  - **FR-002** — the resolution shape for the concurrency conflict. **Open
    again.** The 2026-09-23 answer was **(a) re-drive dispatches get their own
    concurrency group**, on the premise that the proof run then completes
    inside the prove step's ~11-minute synchronous wait. It does not: a
    dispatched `board-loop.yml` run is a *complete board iteration* that runs
    the triage/route/fix/review agents well past the 600s budget, so (a)
    revokes spec 057 FR-048 rather than narrowing it, doubles concurrent agent
    spend, and makes "the abandoned dispatch carried on as an unrelated
    iteration" — the thing FR-011 forbids — the usual outcome. The marker now
    offers (a), per-trigger scoping, the asynchronous shape, accept-as-is, and
    a fifth shape that re-drives only the changed behaviour, with those costs
    stated in the options rather than left to be rediscovered.
  - **FR-010** — whether the issue may close on a dispatched-and-started run
    without a terminal conclusion. **Open again.** The 2026-09-23 answer was
    **no — the bar is unchanged from spec 057 FR-043**, on the same withdrawn
    premise. Under an unchanged bar plus a synchronous wait, every proof run
    that exercises anything ends as started-but-unfinished under FR-006 and no
    Actions-only issue ever closes on proof evidence, so the bar and the wait
    shape can no longer be chosen independently. The marker now offers keeping
    the bar with a bounded-wait resolution, keeping it with a named
    non-prove-step observer, lowering it to observed-to-start, or keeping it
    and accepting a human close.
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
    the mechanism to plan. They stand under every FR-002 option: a separate
    group removes the commonest cause today — a dispatch queued behind its own
    caller — but not a proof run that outlives the wait budget (which, per
    fact 1, becomes the usual case) or a dispatch displaced from its group's
    pending slot.
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
- Every checklist item except "No [NEEDS CLARIFICATION] markers remain" passes.
  The spec is not ready for `/speckit-plan` until FR-002 and FR-010 are
  answered: the resolution shape and the evidence bar together determine what
  the prove step waits for, what the concurrency blocks guarantee, and what
  FR-017's check has to hold across, so planning ahead of them would plan the
  wrong mechanism.
