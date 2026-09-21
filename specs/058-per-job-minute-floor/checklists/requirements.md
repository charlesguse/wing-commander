# Specification Quality Checklist: The Per-Job Minute Floor — No-Op and Healthy Paths Cost What They Run

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-21
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

- All three `[NEEDS CLARIFICATION]` markers the intake stage carried are
  resolved by the owner's reply on issue #434, recorded in the spec's
  Clarifications section:
  - **FR-019** — the agent-skip condition keys on an empty signal set alone;
    a pass with failed collectors is recorded as a partial pass by the same
    deterministic step, with no agent call.
  - **FR-020** — folding the watchdog wrapper's run resolution into the stage
    is in scope; `run-name` becomes optional, additively, as a minor version
    recorded in the watchdog stage's contract.
  - **FR-030** — sub-problem C is per-record-bearing-completion plus a daily
    scheduled sweep: the nine promptly-read stage workflows keep the
    completion trigger, the watchdog leaves it, a sweep over a high-water
    mark picks up the rest, and there is no concurrency-based coalescing.
- **FR-031** was added by the same reply (a healthy inspection now emits no
  metrics record) and is numbered after the highest existing requirement
  rather than inserted into sub-problem B's run, so that every FR number
  already cited on the issue keeps pointing at the same requirement.
- Three corrections from the same reply are folded in: the Context cites PR
  #403 without the unrelated spec 057; SC-004 is restated as a per-stage job
  count a jobs listing can show, since "performed work" is not a field; and
  User Story 2's Independent Test says the diagnose job is listed as skipped
  rather than absent.
- The fourth open question the lifecycle issue raised — whether sub-problem
  A ships for all 13 stages or for `metrics-persist` first, and whether
  delivery is one PR or three — is resolved in Assumptions (all 13, A
  sequenced first) rather than marked, because the issue states a clear
  recommendation and the PR-splitting half is a planning decision.
- Domain vocabulary note: this repository's product *is* CI workflow
  machinery, so terms like "stage run", "job", "skipped" and "record" are
  the stakeholder's own language, not leaked implementation detail. The
  specification states outcomes (a job is not billed, an agent does not run)
  and never prescribes the workflow syntax that produces them.
- Every item is complete; the spec is ready for `/speckit-plan`.
