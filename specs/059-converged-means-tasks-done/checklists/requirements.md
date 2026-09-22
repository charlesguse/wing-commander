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

- Three `[NEEDS CLARIFICATION]` markers remain, at the intake stage's ceiling
  of three. They are posted to lifecycle issue
  [#450](https://github.com/charlesguse/wing-commander/issues/450) rather than
  blocking, and the clarify stage encodes the answers back:
  - **FR-010** — how an outstanding task a later cycle could complete is told
    apart, deterministically, from one no cycle can complete. Marked rather
    than defaulted because it decides whether this feature improves or
    degrades the common case: **19 specs on `main` carry unchecked `- [ ]`
    tasks** (59 items), overwhelmingly human-only work such as spec 054's
    `T007 … dispatch auto-release.yml … record the run URL as evidence`. A
    bare "no unchecked task ⇒ converged" rule sends every such spec to the
    iteration cap. The three candidate rules differ in scope (one touches only
    the read-back step; one reaches into the tasks stage and its template),
    which is why no default is safe to assume.
  - **FR-009** — the cap. The lifecycle issue names it as the trade-off to
    settle first, and it only becomes reachable once FR-001 lands: at cycle
    1's observed 11 tasks per 79 turns, a 65-task spec needs roughly six
    cycles against a default of 5. Today's behaviour at the cap is recorded in
    Assumptions as the observed baseline (report remaining work, dispatch
    finalize `converged=false`, finalize banners the PR), so the owner is
    confirming or changing a stated behaviour rather than answering in the
    dark.
  - **FR-011** — whether the implement agent's prompt is *additionally*
    tightened (the issue's option 2). Marked because it carries a real cost
    trade-off in the opposite direction from the obvious one: instructing the
    agent not to stop while turns remain pushes every cycle to consume its
    full budget, routing more cycles into spec 040's truncated carry-forward
    and the opus escalation tier. The deterministic signal is **not** left
    open — Principle IX makes it the gate either way, and the spec says so in
    Assumptions.
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
- Requirement completeness is otherwise met; the spec is ready for
  `/speckit-clarify`, which should resolve FR-009, FR-010 and FR-011 before
  `/speckit-plan`.
