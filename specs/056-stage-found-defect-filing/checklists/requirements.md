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

- **All three `[NEEDS CLARIFICATION]` markers are resolved** by the owner's
  reply on lifecycle issue #412. The three decisions and their answers:
  - **FR-001 (which stages)** — *all seven agent stages, behind the enable
    input, switched on for implement and finalize first*. Scope covers
    intake, clarify, plan, tasks, implement, converge and finalize; the
    rollout risk sits in configuration rather than in scope, and the
    published surface moves once (FR-001a, FR-029). The accepted
    consequence — five stages shipping code that is off by default — is
    covered by extending FR-030's fixtures and FR-031's gate to all seven.
  - **FR-006 (where the agent writes)** — *a fenced block in the agent's
    final message, plus a `findings` array in the structured result of every
    stage that already returns a schema-validated one*. A bare fenced block
    alone would break intake, whose terminal result is a JSON object a
    schema validates; a `findings/*.json` file alone would exclude the
    read-only stages that FR-001's answer puts in scope. Each stage has one
    authoritative shape, fixed by what its terminal result already is, and
    FR-007 keeps the added array optional so existing validation is
    undisturbed.
  - **FR-016 (single home for the filing idiom)** — *promote the existing
    internal `durable-failure-issue` composite and repoint auto-release and
    auto-update at the promoted path in the same change*. Its interface is
    already a general find-or-create-under-a-dedup-label filer, so the
    promotion is a move rather than a reshaping, and no second copy of the
    idiom is ever created. FR-032 additionally fails CI on a caller left
    behind on the retired internal path.
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
  default for adopters** — is answered in the spec rather than deferred, and
  FR-001's answer sharpened it: filing is on by default for implement and
  finalize and off for the other five, with the wrapper able to set either
  way (FR-029). FR-033 pairs that with a documentation requirement naming
  which stages file by default, so an adopter learns before adoption that a
  stage may open labelled issues in their repository. It is reversible by
  one input and did not warrant spending one of the three markers.
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
- **Feature Readiness** — every user story asserts observable outcomes (an
  issue exists, a duplicate does not, the stage's outcome is unchanged)
  rather than the channel or the composite path, so the stories stood
  unchanged under either answer and stand unchanged now. With FR-001,
  FR-006 and FR-016 settled, planning can name the contract: seven stages,
  two channel shapes decided per stage by its existing terminal result, and
  one promoted composite.
