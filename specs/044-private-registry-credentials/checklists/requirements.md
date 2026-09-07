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

- Three `[NEEDS CLARIFICATION]` markers remain, at the specification's maximum. They
  are posted to the lifecycle issue for the requester rather than blocking the draft:
  - **FR-013 — the shape of the cloud-registry help.** A supported, versioned
    component adopters call is a permanent addition to the published contract
    (Constitution VII: widening that surface is a deliberate act); a documented
    snippet is free to change but leaves every adopter owning their own copy.
  - **FR-026 — what ships if the probe rules every candidate out.** The request
    names two candidate mechanisms and explicitly forbids assuming either. The
    fallback shape is a scope decision, not a planning detail, because one option
    adds a control to the stage interface and the other delivers evidence and
    documentation only.
  - **FR-027 — whether this repository dogfoods the private path.** Constitution I
    wants the repo to be its own first example; doing so here means this repository
    owning a private image and a registry identity, which is a real cost rather than
    a formality.
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
