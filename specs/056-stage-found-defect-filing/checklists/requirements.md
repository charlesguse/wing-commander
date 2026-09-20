# Specification Quality Checklist: Stage-Found Defect Filing Through a Deterministic Filing Step

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

- **Three `[NEEDS CLARIFICATION]` markers remain open**, at the limit the
  specify skill allows. They are the three decisions on lifecycle issue
  #412 that carry a genuine trade-off rather than a defensible default:
  - **FR-001 (which stages)** — all seven agent stages at once, or implement
    and finalize first with the rest following. This is a scope decision:
    it sets how much of the published surface moves in this release and how
    many prompts, fixtures, and gate rows the feature carries.
  - **FR-006 (where the agent writes)** — a fenced block in the agent's
    final message, which every stage already captures and which the
    read-only stages can produce with no write tool, versus a
    `findings/*.json` file, which is easier to validate but which only the
    write-capable stages can produce. This one interacts with FR-001: the
    file channel cannot cover the read-only stages, so choosing it narrows
    the eligible stage set rather than merely changing the parsing.
  - **FR-016 (single home for the filing idiom)** — promote the existing
    internal composite to the published surface and repoint the current
    consumers, or introduce a new published composite and retire the
    internal one. Constitution Principle VII makes promotion a deliberate
    release act rather than a rename, so this is the owner's call, not the
    plan stage's.
  These are posted to #412 as the intake questionnaire; they are left in
  the spec rather than guessed, per the CI deviation in the intake prompt.
- The lifecycle issue's two remaining decision points are **not** markers,
  because each has a defensible default recorded in the spec instead:
  - **Dedup key** — already settled by the issue itself ("a fingerprint over
    deterministic fields, never over the model's prose"). FR-010 states it
    as a requirement, and the Assumptions section records the consequence of
    keeping the stage in the basis.
  - **Cap and cost** — FR-013 requires a code-enforced cap and FR-029 makes
    it a declared input; the Assumptions section takes the issue's proposed
    default of three. FR-020 and FR-021 require the run to report what it
    filed, which is the substance of the "does the cost line say so"
    question; where exactly that line appears is a plan-stage detail, not a
    spec decision.
- A fourth question the issue does not raise — **whether filing is on by
  default for adopters** — is answered in the spec rather than deferred. The
  Assumptions section takes "enabled by default, wrapper can disable"
  (FR-029) and pairs it with FR-033's documentation requirement, so an
  adopter learns before adoption that a stage may open labelled issues in
  their repository. It is reversible by one input and did not warrant
  spending one of the three markers.
- **Content Quality — "no implementation details"**: this repository's
  product is CI workflow behaviour, so the spec necessarily names stages,
  labels, lifecycle issues, and run summaries. It names no job, step, file,
  or language. The two artifacts it does name — the internal
  `durable-failure-issue` composite in FR-016 and stage 10's
  outstanding-task mechanism in FR-017 — are named because reusing them
  rather than re-typing them *is* the requirement (this repository's
  single-home rule), not as a chosen implementation.
- **Requirement Completeness — bounded scope**: FR-002 leaves every existing
  filing route untouched, FR-005 bounds the blast radius inside a stage
  (nothing about the stage's own work changes), and FR-022 through FR-024
  bound it at the job level (filing can never change a stage's outcome).
  FR-029 bounds what widens on the published surface.
- **Feature Readiness** — the open markers do not block the acceptance
  scenarios: every user story is testable under either answer to FR-001,
  FR-006 and FR-016, because each story asserts observable outcomes (an
  issue exists, a duplicate does not, the stage's outcome is unchanged)
  rather than the channel or the composite path. Planning, however, needs
  all three answered before it can name a contract.
