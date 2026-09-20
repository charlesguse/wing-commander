# Specification Quality Checklist: The Board Loop — A Scheduled Run Takes One Open Issue From Triage To Proven

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-20
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

- **Three `[NEEDS CLARIFICATION]` markers remain, by design.** This spec was
  authored by the intake stage in CI, which does not wait for answers; the
  questions are posted to lifecycle issue #408 and resolved by the clarify
  stage. The three:
  - **FR-003 — how far autonomy goes.** The full loop including the bounded
    merge (Principle X's step 5), or stop at "ready to merge" with a human
    merging and a `pull_request: closed` trigger resuming at prove. Both are
    constitution-legal. This is the single largest scope call in the feature:
    it decides whether FR-034–FR-040 ship at all, and it is the only
    irreversible-ish action the feature adds. The spec states the full loop
    and marks the merge requirements as one deferrable block so that either
    answer leaves steps 1–4 and 6 untouched.
  - **FR-062 — published stage or repository-only workflow.** A
    `workflow_call`-only stage plus a thin wrapper (VII), or an unnumbered
    repository-only workflow in the `auto-release.yml` shape. The lifecycle
    issue argues for repository-only, because the loop encodes conventions
    specific to this repository (429 triage evidence, the
    `Found by the code review of #N` line, this repository's gate-suite entry
    point) that would each have to become a typed input to publish. That is a
    defensible default but not an obvious one — Principle I's "the repo is
    its own first example" pulls the other way — and the answer decides
    whether this feature moves the adopter-pinned surface at all. FR-063
    states the consequences of each branch so planning can proceed on either.
  - **FR-040 — the second merge class.** Whether the Spec Kit upgrade PR the
    auto-update stage opened is merged by this loop, and whether a
    patch-level jump qualifies. X permits the class but conditions it on "the
    verification that stage assigns to the jump has passed"; a patch jump's
    assigned tier verifies without the end-to-end stage, and whether that is
    enough is a judgment only the owner can make. No default exists.
- **Decision points the lifecycle issue raises that are *not* markers**,
  because each has a defensible default recorded in Assumptions instead:
  cadence; round budget; per-item turn ceiling; stand-down while an implement
  cycle runs (the issue's own Constraints already settle it); reviewer model
  tier; whether a settled disposition or a closed lifecycle stops the loop;
  whether closing the issue mid-loop closes its PR; and how non-maintainer
  comments are kept out of the fixer's instructions (FR-056 settles the
  mechanism — code decides from author association — leaving only a knob).
  Each is reversible by one constant or one input; spending a marker on any
  of them would have displaced one of the three above.
- **The findings format is deliberately not a marker.** The issue lists it
  under "Review tier and format", but X requires the merge gate to count open
  findings in code, so a schema-validated structure is a constitutional
  requirement (FR-029, FR-033), not a choice. Only the reviewer's model tier
  remained open there, and that has a default.
- **Content Quality — "no implementation details"**: this repository's
  product is CI workflow behaviour, so the spec necessarily names stages,
  labels, lifecycle issues, branches and run evidence. It names no job, step,
  language or file path except where reusing an existing artifact *is* the
  requirement (FR-059–FR-061, this repository's single-home rule) or where a
  named constant would otherwise go stale (the pr-conversation stage's ≤3
  files / ≤40 changed lines, quoted in Assumptions as the precedent the
  board's own thresholds deliberately do not inherit).
- **Requirement Completeness — bounded scope**: FR-001 bounds the feature to
  one loop over one issue per run; FR-004 keeps the feature lifecycle out;
  FR-005 leaves every existing filing route untouched; FR-007 bounds what the
  loop may do to an issue it is not authorized for; FR-048–FR-054 bound
  concurrency, budget and stopping. FR-062/FR-063 bound what, if anything,
  widens on the published surface.
- **Requirement Completeness — testability**: every requirement that gates a
  durable action is paired with a fixture obligation in FR-064, which
  enumerates the failure branches for the three gates (triage close, route
  backstop, merge gate) rather than leaving "has fixtures" as prose.
- **Feature Readiness** — the seven user stories are ordered as the loop runs
  and each asserts observable outcomes (an issue is closed with quoted
  evidence, a review object exists on the PR, a merge is refused with a named
  reason) rather than naming the mechanism that produces them, so all seven
  stand unchanged under either answer to FR-003 and FR-062. Under the
  narrower answer to FR-003, User Story 5 becomes a "ready to merge" gate
  with the same refusal branches and the same fixtures.
