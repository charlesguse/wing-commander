# Specification Quality Checklist: A Turn-Exhausted Implement Cycle Is Carried Forward, Not Redone from Cold

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-21
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

- Three `[NEEDS CLARIFICATION]` markers remain, posted to the lifecycle issue for the requester rather than resolved by assumption. Each is a scope decision the source request itself declined to settle:
  - **FR-004** — what counts as "progress" for the no-progress guard. The source request proposes "the branch tip moved", but FR-002 already requires the cycle to have advanced the feature's lifecycle record, and that advance is itself a commit — so the proposed test would always be true and the guard would never fire. Since the guard is what stops the change from consuming the whole iteration budget for nothing (story 3), an inert version of it makes the feature strictly worse than today. No default was assumed.
  - **FR-010** — whether a truncated cycle consumes one of `max-iterations`. The source request explicitly flags this (R2) as deserving "a deliberate answer rather than a default". The spec states the simplest answer (it does consume one) as a working assumption so the rest of the requirements are coherent, and marks it for confirmation.
  - **FR-011** — whether escalate-on-second-consecutive-truncation is in scope, and where the consecutive-truncation count is carried between separately-dispatched cycles. The request lists it in its suggested shape but frames the underlying risk (R3) conditionally. It is the difference between a self-contained change and one that adds cross-cycle state, so it materially changes scope. The Assumptions section names the feature's lifecycle record as the natural home if it is in scope.
- Validation ran once. No item other than the marker line failed; the remaining boxes are checked on that pass, and the marker box clears once the three questions are answered.
- **Content Quality**, first and third items: the spec names GitHub-native and pipeline-domain nouns (issues, runs, branches, commits, cycles, tiers) because the product *is* a GitHub-native spec-driven pipeline and those are its domain vocabulary, not implementation choices. It deliberately avoids naming the workflow file, the step ids, the result subtype string, the model identifiers, and the script directory — those appear only inside the verbatim `Input` quotation of the source request.
- **Success criteria**: the source request's dollar and turn figures are used as the *motivation* for SC-001/SC-002 rather than as targets, because they measure a sample of past runs rather than an outcome the delivered feature can be checked against. SC-003 through SC-010 are stated as counts and behavioural comparisons that can be observed without knowing how the change is built.
- **FR-005 / User Story 2** is the requirement the rest of the feature depends on. It is stated as its own P1 story rather than folded into the carry-forward story because the naive version of the carry-forward — the one that omits it — reports an unbuilt feature as finished, which is worse than shipping nothing at all.
