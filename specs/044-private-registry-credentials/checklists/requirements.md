# Specification Quality Checklist: Private-Image Credentials That Reach Every Stage Job

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-07
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

- All three `[NEEDS CLARIFICATION]` markers were resolved by the requester on the
  lifecycle issue (#283) and are now encoded in the requirements:
  - **FR-013 — the shape of the cloud-registry help.** Resolved: ship a supported,
    versioned, optional component the adopter calls from their own wrapper, mirroring
    the existing optional credentials component for the alternate model provider. The
    published contract surface widens deliberately (Constitution VII), bounded by a
    minimal contract — identity, region, optional registry override in; username and
    password out — and by the rule that no published stage may reference it. The
    component is now also subject to FR-022's composite-action description rules.
  - **FR-026 — what ships if the probe rules every candidate out.** Resolved as a
    preference order rather than a single answer: infer the private case from the
    supplied credentials if the probe shows that works (no new control); otherwise a
    single explicit opt-in control is acceptable; only if no single set of stage files
    can serve all three shapes does the feature reduce to evidence plus improved
    fallback documentation. A second set of stage files is excluded under every
    outcome.
  - **FR-027 — whether this repository dogfoods the private path.** Resolved as a
    narrow dogfood: one scheduled or on-demand check against a repository-scoped
    private image through the real stage-file shape, kept separate from the lifecycle
    stages, which stay on the no-image default. This repository takes on no cloud
    account or cloud-registry identity; the cloud path rests on probe evidence and
    documentation. SC-010 records the outcome.
- The request's own "measure before planning" instruction is specified as a delivery
  condition (User Story 5, FR-016 through FR-018) rather than left to the plan, because
  the previous attempt (#219 → #224 → #227) failed precisely by treating it as one.
- Two things the request states as facts are carried as measured constraints rather
  than re-derived: that a per-job credential mapping cannot be conditionally absent,
  and that minting inside a stage job is structurally too late. Both are recorded in
  #227 and its probe, and the specification requires any re-proposal to bring new
  evidence.
- The specification deliberately does not name the mechanism. Both candidates in the
  request are unverified, so naming one in the spec would re-commit the error the
  spec exists to prevent; FR-003 states the property all three shapes must satisfy and
  leaves the shape to a probe-informed plan.
- Terminology is kept implementation-neutral throughout (no workflow keyword, expression
  syntax, or gate number appears in the requirements) so the spec stays checkable by a
  reader who does not know the pipeline's internals. The constraints the request lists
  by gate number are covered as behavior in FR-019 through FR-022.
