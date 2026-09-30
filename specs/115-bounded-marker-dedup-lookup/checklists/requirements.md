# Specification Quality Checklist: A Bounded Read for the Marker Dedup Lookup

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-30
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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-09-30

- **"No implementation details" and "technology-agnostic"**: read against
  this repository's own domain, the way `specs/088-stop-check-closed-read`
  and `specs/109-watchdog-finding-fanout` already do. The product here *is*
  workflows, composite actions and gate scripts, so naming the
  `Look up, then report or close` step, the `found-by:*` labels and the
  fixture harness identifies the subject rather than prescribing an
  implementation. FR-002 does name a concrete bound (`--limit 200`) — that
  is deliberate and is not a new design decision: it adopts the value
  `watchdog.yml` already ships, which is the whole point of the fix, and
  the originating issue frames it as "applying that same settled
  convention". PASS.
- **Three [NEEDS CLARIFICATION] markers remain**, at the skill's limit.
  Each is a decision with no defensible default:
  - **FR-005 — behaviour at the bound.** A wider page moves the ceiling;
    it does not remove it. The three answers differ in what the pipeline
    does when the ceiling is reached again: accept the same silent
    duplicate further out, make it visible, or fail closed. The third
    trades a possible duplicate for a possible dropped finding, which is a
    trade-off only the owner should make (Principle X's "spec-shaped when
    it needs the owner to decide a trade-off").
  - **FR-006 — the no-marker path.** Leaving it alone is defensible
    (reading only the newest element of a newest-first list is correct at
    any page size) and so is bounding it (uniformity; a future edit that
    reads past `.[0]` inherits the bug). Bounding it also edits a live
    contract that quotes the line verbatim, which changes the change's
    blast radius. Two reasonable readings, different scope.
  - **FR-012 — coverage shape.** The originating issue asks for a fixture.
    A gate over the body-filtering lookup shape would catch the *next* such
    call site; CLAUDE.md's "a rule with no gate behind it lasts until the
    next session" pulls toward the gate, and its "extend the nearest
    existing gate" pulls toward keeping it small. That tension is the
    owner's to resolve.
- **FR-008 is the load-bearing requirement, not FR-001.** The existing `gh`
  stub in the fixture harness ignores `--limit` and prints its whole
  payload, so a 31-issue fixture written against today's stub would pass
  with or without the fix — a check that cannot fail its subject
  (Principle VIII). The spec states the stub's faithfulness as a
  requirement and SC-002/SC-003 as the demonstration. PASS.
- **SC-002 and SC-003 are verified by deliberately breaking the subject**
  (removing the bound, then narrowing it) rather than by asserting a
  passing run. That is the only form of evidence that distinguishes real
  coverage here, and it is checkable by the next reviewer from the fixture
  alone. PASS.
- **User Story 3 carries no behaviour** — it is the comment requirement.
  Kept as a story because this repository treats workflow comments as code
  and because the rationale's absence is what let the missing bound read as
  intentional through prior reviews. PASS.
