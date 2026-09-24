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

- Three `[NEEDS CLARIFICATION]` markers remain open, by design for this
  stage. Intake does not block on them; they are posted to lifecycle issue
  [#483](https://github.com/charlesguse/wing-commander/issues/483) and the
  clarify stage encodes the answers back into the spec.
  - **FR-002 — the direction.** Apply the label, retire it, or restate it as
    maintainer-applied. This is the trade-off the originating issue (#361)
    explicitly declined to decide locally ("Worth a maintainer call on
    whether to (a) actually wire up applying/removing the label ... or (b)
    drop it from the documented label taxonomy"), and it is what routed the
    request into the pipeline rather than a local fix PR. No reasonable
    default exists: both directions close the defect, and they close it in
    opposite directions.
  - **FR-012 — flip or coexist**, under Direction A only. Every other stage
    transition in the pipeline removes its predecessor label
    (`plan.yml:1153-1155`), which argues for a flip; but `stage:spec` is the
    label the clarify wrapper's working disjunct matches today and the one
    the end-to-end run's timeline assertion reads, which argues for
    coexistence. The two readings leave different label sets on every
    clarification-needed issue, so a maintainer filter written against
    either one behaves differently. Asked rather than assumed.
  - **FR-021 — the end-to-end assertion.** Closing
    `specs/055-unattended-e2e-gates/`'s recorded gap is only possible under
    Direction A, and only as a conditional assertion; an unconditional one
    reproduces the impossible-pass bug `auto-release.yml:1143-1147` exists to
    record. Whether that work belongs in this feature or its own is a scope
    call with real cost on either side.
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
  - Whether the `stage:clarify` disjunct in the clarify wrapper's trigger is
    removed under Direction B is specified as conditional on recorded
    evidence that no open issue carries the label (FR-018) rather than left
    open — the invariants FR-003 and FR-004 decide it either way.
- Direction-conditional requirements are grouped under explicit "Direction A"
  / "Direction B" headings rather than interleaved, so whichever branch the
  answer selects, the other is dropped wholesale at planning time and no
  requirement silently applies to both.
- Domain-vocabulary note: this repository's product is pipeline machinery, so
  "lifecycle issue", "stage label", "gate", and "adopter" are the
  stakeholder's own language. The requirements state outcomes — the label is
  applied, the trigger still fires, the gate fails on the pre-change tree —
  and the `file:line` citations are evidence for where the defect lives, not
  instructions for how to fix it.
- Requirement completeness is otherwise met; the spec is ready for
  `/speckit-clarify`, and ready for `/speckit-plan` once FR-002 is answered.
