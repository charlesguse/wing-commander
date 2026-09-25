# Specification Quality Checklist: The Label Table Tells the Truth — `stage:clarify` Is Either Applied or Retired

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-24
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

- All three `[NEEDS CLARIFICATION]` markers were resolved on lifecycle issue
  [#483](https://github.com/charlesguse/wing-commander/issues/483) and folded
  into the spec's Clarifications section. None remain.
  - **FR-002 — the direction: (a) wire it up.** The pipeline applies and
    clears the label, so the lifecycle is readable from the issue and the
    end-to-end clarify gate becomes assertable. This was the trade-off the
    originating issue (#361) explicitly declined to decide locally ("Worth a
    maintainer call on whether to (a) actually wire up applying/removing the
    label ... or (b) drop it from the documented label taxonomy"), and it is
    what routed the request into the pipeline rather than a local fix PR.
    Direction B (FR-016..FR-020) is dropped; its numbers are left unreused so
    existing citations still resolve.
  - **FR-012 — flip.** `stage:clarify` replaces `stage:spec`: one current
    stage label at a time, as with every other transition
    (`plan.yml:1153-1155`). The coexistence reading was rejected, so a
    maintainer filter on `stage:spec` now means "awaiting spec review" only.
    The clarify wrapper's second disjunct — dead until now — becomes the one a
    pipeline-driven run matches, which is the load-bearing consequence
    planning must carry (FR-003, FR-004).
  - **FR-021 — (a) in scope here.** The conditional end-to-end assertion lands
    in this same change, gated on that run's intake having actually posted a
    questionnaire; an unconditional one would reproduce the impossible-pass
    bug `auto-release.yml:1143-1147` exists to record. SC-007 was added so the
    skip path is observable rather than silent.
- Judgment calls made rather than marked, to stay inside the three-marker
  limit:
  - The enforcement gate covers the whole documented lifecycle taxonomy
    rather than only `stage:clarify` (Assumptions). Every other documented
    label already has a writer, so the general check passes today except for
    the label under specification — it is strictly cheaper than adding a
    second gate later, and CLAUDE.md's "a rule with no gate behind it lasts
    until the next session" argues for the general form.
  - Create-before-add (FR-014), deterministic-not-agent derivation (FR-013),
    and flip-before-PR-mirror ordering (FR-023) each follow an existing,
    cited precedent in the repository, so they are specified rather than
    asked about.
  - Whether the `stage:clarify` disjunct in the clarify wrapper's trigger was
    removed under Direction B was specified as conditional on recorded
    evidence that no open issue carries the label (FR-018) rather than left
    open — the invariants FR-003 and FR-004 decided it either way. Moot now
    that Direction A is in force: the disjunct stays and starts doing work.
- Direction-conditional requirements were grouped under explicit "Direction A"
  / "Direction B" headings rather than interleaved, so the unselected branch
  could be dropped wholesale once the answer arrived. Direction B's heading is
  retained marked NOT TAKEN, carrying no planning or implementation work.
- Domain-vocabulary note: this repository's product is pipeline machinery, so
  "lifecycle issue", "stage label", "gate", and "adopter" are the
  stakeholder's own language. The requirements state outcomes — the label is
  applied, the trigger still fires, the gate fails on the pre-change tree —
  and the `file:line` citations are evidence for where the defect lives, not
  instructions for how to fix it.
- Requirement completeness is met and all clarifications are resolved; the
  spec is ready for `/speckit-plan`.
