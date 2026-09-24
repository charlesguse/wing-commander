# Specification Quality Checklist: Converged Means No Task Is Left — The Cycle Signal Reads tasks.md

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

- All three `[NEEDS CLARIFICATION]` markers are resolved. They were posted to
  lifecycle issue
  [#450](https://github.com/charlesguse/wing-commander/issues/450) rather than
  blocking, and the clarify stage encoded the owner's answers back into the
  spec:
  - **FR-010** — how an outstanding task a later cycle could complete is told
    apart, deterministically, from one no cycle can complete. **Resolved:
    option (a) — the checkbox delta.** A healthy cycle that checks no task its
    base left unchecked, leaves outstanding tasks, and lands no `converge:`
    commit is the loop's natural end: `converged=false`, hand off to
    finalization through the existing cap-reached terminal path. The marker
    alternative (option b) was set aside because it would need all 19 merged
    specs retroactively annotated and because marker placement is itself agent
    judgment at write time — a worse fit for Principle IX than a delta the code
    re-derives from the tree. FR-010a and FR-010b were added to pin the
    progress test's base, its checkbox forms, and its precedence behind the
    zero-outstanding case.
  - **FR-009** — the cap. **Resolved: unchanged.** `max-iterations` keeps its
    default of 5, the cap keeps counting every dispatched cycle, and today's
    behaviour at the cap stands. The six-cycle estimate came from spec 057's
    cycle 1, the cycle with the most setup overhead and the one that stopped
    early, while its cycle 2 landed 50 tasks; the defect under fix is the
    signal, not the cap.
  - **FR-011** — whether the implement agent's prompt is *additionally*
    tightened (the issue's option 2). **Resolved: option (b) — no prompt
    change.** With FR-001 and FR-010 shipped, a wrong early stop costs one
    extra cycle rather than a wrong finalize, so the prompt change buys a
    cheaper failure mode, not a correctness fix, at the price of pushing every
    cycle to its full turn budget and into spec 040's truncated carry-forward
    and the opus escalation tier. FR-015 still corrects how the prompts
    *describe* the signal; the spec states that the two do not conflict.
- Consistency edits the answers required, beyond swapping the marker text:
  - SC-002 and SC-005 were restated. The FR-010 hand-off means finalization
    *can* be reached from a healthy cycle with outstanding tasks, so SC-002 now
    measures "never reached with `converged=true` while tasks remain"; and a
    human-only spec now pays exactly one extra discovery cycle, so SC-005 is
    "at most one more cycle", not "no more". That cost is stated plainly in
    Context rather than left for plan to find.
  - New acceptance scenarios cover the two cases the rule's boundary creates:
    a zero-progress cycle whose converge pass *did* append (next cycle, not a
    hand-off) and a cycle that checks the last box (converges in place).
  - FR-019 and FR-020/SC-008 gained the progress-test fixtures and the
    progress-test mutation, so the new branch is gated like the rest.
  - Out of Scope now records what the answers closed: no `tasks.md` schema
    change, no cap change, no prompt behaviour change.
- Judgment calls made rather than marked, to stay inside the three-marker
  limit:
  - The remaining-work report on the new path (FR-012) is specified rather
    than asked about: today's text is extracted from the `converge:` commit's
    diff, so on a `converged=false` with no such commit it would render an
    empty fenced block. Reading the unchecked tasks from `tasks.md` is the
    only non-broken option.
  - One shared definition across the primary and retry arms (FR-007) follows
    CLAUDE.md's "shared logic has exactly one home" and the existing twin at
    `implement.yml:1824-1838`; it is not a trade-off.
  - Delivery as one spec, and no change to finalize's `converged=false`
    handling, are recorded in Out of Scope and Assumptions.
- Domain-vocabulary note: this repository's product *is* pipeline machinery,
  so "cycle", "stage", "tasks.md", "converged" and "iteration cap" are the
  stakeholder's own language. The requirements state outcomes — another cycle
  is dispatched, finalization is not reached, the comment names its reason —
  and never prescribe the workflow syntax that produces them. The
  `file:line` citations are evidence for the defect's location, not
  instructions for the implementation.
- Requirement completeness is met and no clarification remains open; the spec
  is ready for `/speckit-plan`.
