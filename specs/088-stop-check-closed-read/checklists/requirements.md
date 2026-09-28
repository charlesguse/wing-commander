# Specification Quality Checklist: An Honest Read-Failure Policy for board-stop-check's Closed Check

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-25
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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-09-25

- **"No implementation details" and "technology-agnostic"**: read against
  this repository's own domain, not a product domain. The product here *is*
  GitHub Actions workflows, composite actions and gate scripts, so naming
  `wing-commander-board-stop-check`, `continue-on-error:` and
  `verify-board-stop-check.py` identifies the subject rather than
  prescribing an implementation. The specification deliberately does **not**
  choose *how* FR-005's remedy is wired, *how* FR-009's gate detects the
  claim, or *what* the corrected comment's wording is — those are plan-stage
  decisions. Matches the house style of `specs/061-marker-owned-in-flight`
  and `specs/057-autonomous-board-loop`. PASS.
- **Three [NEEDS CLARIFICATION] markers remain**, at the skill's limit, all
  scope-or-behaviour decisions with no defensible default:
  - FR-002 — fail-open vs fail-loud for the `closed-check` read. This is the
    trade-off the route agent judged spec-shaped; both directions are
    defensible and they produce opposite `prove` behaviour on an
    undetermined read.
  - FR-005 — where the annotation-noise remedy lives. Three candidate homes
    with materially different blast radius (one call site, seven call sites,
    or the whole fleet's classification). Moot if FR-002 resolves fail-loud,
    which is itself a reason not to guess.
  - FR-012 — whether Gate 24 is widened to `.github/actions/**` in this
    feature or the boundary is only recorded. Widening pulls the composite
    fleet into scope and any finding would have to be fixed in this PR.
  All other gaps were resolved with informed defaults and recorded under
  Assumptions.
- **Testability**: every FR names an observable outcome. FR-001/FR-007/FR-008
  are verified by reading the shipped files; FR-002/FR-003/FR-004/FR-011 by
  driving the composite's extracted step (FR-013); FR-005/FR-006 by driving
  a `prove` run and inspecting the watchdog's signal set; FR-009/FR-012 by
  the gate suite and its mutation self-test.
- **Conditional requirements**: FR-005 and User Story 2 are explicitly
  no-ops if FR-002 resolves to fail-loud, and say so, so neither is
  ambiguous once the clarification lands.
- No spec updates required beyond the open clarifications. The three
  markers are posted to lifecycle issue #623 for the maintainer rather than
  guessed; per the intake stage's CI deviation they stay in `spec.md`.

### Clarification iteration 2 — 2026-09-28

All three markers are answered on lifecycle issue #623 and folded into
`spec.md`'s new `## Clarifications` section. Zero remain.

- **FR-002 — fail-loud.** `continue-on-error: true` comes off the
  `closed-check` step. Recorded with the trade-off it resolves (one deferred
  `prove` retried by the next schedule, against closing or re-driving an
  issue a maintainer already closed) and reflected in User Story 1's
  scenarios 3–4, which were written as a fail-open/fail-loud pair and are
  now both fail-loud.
- **FR-003 tightened while folding FR-002 in.** As shipped, `closed-check`
  runs *before* the step that re-checks the kill switch and scans for stop
  requests, so a fail-loud failure of `closed-check` would abort the
  composite before either. FR-003 previously only forbade *weakening* those
  checks; it now forbids preempting them too, and names the ordering as the
  constraint the plan stage has to satisfy. Edge case "kill switch already
  on and the read fails" updated to match.
- **FR-005 — moot, resolved by FR-002.** No remedy in `lifecycle-gate` or
  the watchdog; a green `prove` can no longer carry a `closed-check`
  total-failure error at all. FR-006 was a constraint *on* the remedy and is
  now the stronger "this feature introduces no annotation filtering
  anywhere". User Story 2 is retitled "satisfied by construction", and its
  third scenario now covers what the fail-loud choice does *not* change —
  the retry `::warning::`s on a read that fails twice and then succeeds,
  which are `lifecycle-gate`'s existing behaviour at all seven call sites
  and stay out of scope. SC-004 and SC-005 were written to be measured by
  driving runs against a remedy that no longer exists; both are now measured
  against the diff and the mutual exclusion.
- **FR-012 — record Gate 24's boundary only.** The widening to
  `.github/actions/**` becomes its own issue, per CLAUDE.md's rule about
  out-of-scope work, and the recorded boundary points at it. Added to Out of
  Scope.
- **FR-011 — deferred, not answered.** The reply volunteered a sequencing
  decision: sanitizing `$cancel_error` edits the same line spec 087 (#621)
  replaces, so it ships there rather than being rewritten twice. FR-011 and
  SC-006 are marked deferred rather than renumbered, so existing references
  to them keep resolving. User Story 4 loses its sanitize half and is
  retitled around what remains — Gate 24's recorded scope — with the
  deferral noted on the story.
- **Still testable after the folding**: FR-002/FR-003 by driving the
  extracted step under `verify-board-stop-check.py` (FR-013); FR-005/FR-006
  by inspecting the diff for absence of filtering; FR-012 by reading the
  gate. No requirement now depends on an unmade decision.
