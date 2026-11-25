# Specification Quality Checklist: Workflow security — static-analysis gate, self-repository references, documented trigger requirements

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-25
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

- Both [NEEDS CLARIFICATION] markers were resolved by the clarify stage from the answer on lifecycle issue #1188 (2026-11-25):
  - FR-009 (Q1, option C): SHA-pin actions outside a trusted-publisher set; the trusted set keeps tags; one home for the list (FR-009a); update automation keeps pins current (FR-009b).
  - FR-016 (Q2, option B): keep `./`, disable the `self-repository` audit with a recorded reason, and add the untrusted-checkout gate (FR-016a).
- On "no implementation details": the subject of this feature is workflow tooling, so the spec has to name workflow files, trigger events, the analyser (zizmor, in Assumptions) and the existing gates. These are the subject, not a choice of how to build it. The analyser's invocation, register format, record key and gate wiring are left to the plan.
- The source issue says this design belongs to clarify and plan. The spec fixes scope and required outcomes, and leaves the build details (record key, configuration file, offline audit set) as plan-level choices.
