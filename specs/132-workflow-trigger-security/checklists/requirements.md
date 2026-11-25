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
  - FR-009 (Q1, option C): SHA-pin actions outside a trusted-publisher set; the trusted set keeps tags; one home for the list (FR-009a); new pin-update automation keeps pins current, its PRs human-merged (FR-009b).
  - Trusted-publisher set fixed by owner decision (2026-11-25, Roadmap #890): exactly `actions/*`, `github/*`, `anthropics/*`; changes to it are owner decisions.
  - FR-016 (Q2, option B): keep `./`, disable the `self-repository` audit with a recorded reason, and add the untrusted-checkout gate (FR-016a), defined by where a `./` reference resolves (trusted copy versus untrusted tree).
- Spec review round 1 (PR #1221) fixes: FR-016a/FR-014 redefined by resolution target; one home with Gate 104 and the lifecycle-review-gate provenance gate, Gate 151 unchanged, agent-writable workspace out of scope; FR-009b states the automation is new and human-merged, FR-017a keeps Gates 170 and 92 green on SHA refs; FR-018a and the Layer section cover per-release freezing; FR-006 covers every new gate's failure branches; SC-005a split into SC-008/SC-009, with SC-010/SC-011 added.
- Spec review round 2 (PR #1221) fixes: FR-016a defines a trusted copy by repository and ref (any path), and counts artifact-extracted trees as untrusted and judges a composite's `./` steps in each calling job; FR-016b classifies repo-only reusable workflows (`shared-pr-reviewer.yml`) as consuming instrument and makes stage-input additions an owner decision; FR-015 sends contract-widening fixes to the owner; SC-009 holds once FR-015's fixes (including the separate `pr-conversation.yml` fix) land, and the zero-exposure assumption is dropped; FR-009a defines a second copy and makes the `unpinned-uses` policy the home or derived from it; FR-017a has bump PRs carry Gate 170 register rows and notes Gate 92 is unaffected; the Q2 clarification carries a note that FR-016a sharpened it.
- On "no implementation details": the subject of this feature is workflow tooling, so the spec has to name workflow files, trigger events, the analyser (zizmor, in Assumptions) and the existing gates. These are the subject, not a choice of how to build it. The analyser's invocation, register format, record key and gate wiring are left to the plan.
- The source issue says this design belongs to clarify and plan. The spec fixes scope and required outcomes, and leaves the build details (record key, configuration file, offline audit set) as plan-level choices.
