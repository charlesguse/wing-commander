# Specification Quality Checklist: Consumer-Chosen Runners and Container Images

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-17
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

**Validation run**: two passes over the draft. Two items failed on the first pass and
were fixed; the rest passed as written. A third pass after the clarification answers
re-checked the items the answers touch.

- **Failed then fixed — "All functional requirements have clear acceptance
  criteria"**: FR-010 (a named image with no credential fails with a message that
  identifies the missing credential) and FR-014/FR-015 (the parity check and its
  registered exceptions) had no scenarios behind them. Added as User Story 4
  scenario 2 and User Story 5 scenarios 1–3.

- **Failed then fixed — "Scope is clearly bounded"**: the draft was silent on runner
  *groups*, on the container settings other than the image (volumes, ports,
  environment, extra options, service containers), and on non-Linux runners. All
  three are now explicit non-goals in Edge Cases, Assumptions, and FR-017's
  documentation list.

- **All three [NEEDS CLARIFICATION] markers are resolved** by the requester's answers
  on issue #219 (`Q1: C, Q2: C, Q3: B`), folded into the spec:
  1. **FR-007 — granularity → one selection per stage, split deferred.** Both controls
     are set once per stage call and apply uniformly to every job; per-job targeting
     for agent-bearing versus bookkeeping jobs waits until an adopter asks and stays
     additive. Recorded in FR-007, the Assumptions entry on per-call granularity, and
     FR-017's documentation list.
  2. **FR-009 — private-registry credentials → in scope and generalized.** Credentials
     are stage secrets covering a static pair *and* token-based or cloud-registry
     (ECR/GCR/ACR) authentication, including credentials minted at run time. Split
     into FR-009 (secrets, inert, never logged) and FR-009a (the generalized
     mechanism), with User Story 4 scenario 4, SC-004, the Key Entities entry, and a
     new edge case for a credential that must exist *before* the job's container is
     created.
  3. **FR-011 — image prerequisites → documented *and* verified.** Every stage checks
     the prerequisites early and fails naming every missing one before agent cost is
     incurred (FR-011), and FR-011a machine-checks the list against what the stages
     and composites actually use so it cannot drift. Reflected in User Story 3
     scenario 2, User Story 5 scenario 4, and SC-005.

- **Open after clarification**: none. One design question is *flagged for planning
  rather than left unspecified*: how a short-lived registry token is minted before the
  job starts and refreshed for a long stage. The requirement is fixed (no adopter edits
  a published stage); only the mechanism is for the plan to choose.

- **Resolved with a documented default instead of a fourth marker**: the multi-label
  convention. The requester proposed a JSON array read from a string input, and it is
  the only shape a typed `workflow_call` input can carry, so it is recorded in
  Assumptions and constrained by FR-003 (the reading must be predictable from the
  documentation alone) rather than deferred.

- **Passed, with the judgement recorded** so a later reader does not re-litigate it:
  - *No implementation details*: `runs-on`, `container`, and `container.credentials`
    appear in the **Input** block, which quotes the request verbatim by template
    convention, and in the Overview's explanation of *why* the capability cannot live
    in a wrapper — which is a constraint of the platform, not a design choice. The
    requirements name roles ("the runner selection", "the container image
    reference"). References to specs/031 and issue #149 are this repository's own
    prior features.
  - *Written for non-technical stakeholders*: read as satisfied in context — the
    product is pipeline infrastructure and its stakeholders are adopters and
    maintainers, the same audience specs 031–037 are written for.
  - *Success criteria measurable and technology-agnostic*: each SC is a percentage, a
    before/after comparison, or a "can complete without X" statement. SC-002 names
    lifecycle stages, which are this product's own domain vocabulary, not technology.

- **Constitution check**: Principle VII is the reason this is a stage-interface
  change at all — `runs-on` and `container` are legal nowhere but inside the called
  workflow, the same narrow exception specs/031 established for the environment
  binding — and FR-012/FR-015 keep the rest of the principle intact (declared inputs
  only, registered exceptions only). Principle I is served by User Story 6. FR-013
  keeps the change additive, so no adopter is broken. No principle conflicts remain.
