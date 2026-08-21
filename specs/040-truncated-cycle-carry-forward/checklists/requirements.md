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

- All three `[NEEDS CLARIFICATION]` markers are resolved. They were posted to the lifecycle issue rather than settled by assumption, because each was a scope decision the source request itself declined to make; the requester answered all three:
  - **FR-004 — what counts as "progress"** for the no-progress guard. Answered with the widest recognition of progress: *either* a task newly marked complete in the task list *or* a file changed outside the spec directory, compared against the branch as it stood at the start of the cycle, with the lifecycle-record advance excluded. The rationale given was that a wrong escalation costs a whole cycle redone cold at the escalation tier — the exact waste this feature exists to remove — so the guard should err toward carrying forward. The answer also confirmed the premise the marker raised: "the branch tip moved" can never fail, because the lifecycle-record advance is itself a commit. FR-004 now states both arms and FR-004a states the exclusion, so the guard cannot be inert; FR-018 requires each arm to be covered separately and FR-019 makes an inert guard fail a check.
  - **FR-010 — whether a truncated cycle consumes an iteration.** Answered: yes, identically to an unconverged cycle, so `max-iterations` stays a true bound on total cost and is safe to leave at its default. The requester noted the interaction with FR-004 explicitly — the "five cycles achieving nothing" case is caught by the no-progress guard, so runaway truncation is bounded by one mechanism rather than two. FR-010 now rules out both a separate allowance and a progress-conditional exemption.
  - **FR-011 — escalate-on-second-consecutive-truncation.** Answered by splitting the question: the *signal* is in scope, the *escalation* is not. The count of consecutive truncations is tracked and reported on the lifecycle issue (FR-011, FR-012, SC-007) so the follow-up arrives with data on how often the case occurs; no tier-switching decision is added (FR-011a), and the escalation is listed under Out of Scope to be filed separately against R3. User Story 5 was rewritten from "the pipeline escalates" to "the pipeline counts and reports", and FR-007 no longer carries an exception for it.
- The requester added two notes marked explicitly as being for the follow-up rather than for this spec: that the consecutive-truncation count should be written deterministically by the workflow rather than recorded by the agent, and that the escalation should be filed as its own issue once this lands. Neither is encoded as a requirement here. The first does bear on FR-011, which is in scope, so the Assumptions section records that the *mechanism* for writing the count is deliberately left unfixed by this spec.
- Validation ran twice — once at draft, once after the clarifications were folded in. No item failed on either pass other than the marker line, which now clears.
- **Content Quality**, first and third items: the spec names GitHub-native and pipeline-domain nouns (issues, runs, branches, commits, cycles, tiers) because the product *is* a GitHub-native spec-driven pipeline and those are its domain vocabulary, not implementation choices. It deliberately avoids naming the workflow file, the step ids, the result subtype string, the model identifiers, and the script directory — those appear only inside the verbatim `Input` quotation of the source request.
- **Success criteria**: the source request's dollar and turn figures are used as the *motivation* for SC-001/SC-002 rather than as targets, because they measure a sample of past runs rather than an outcome the delivered feature can be checked against. SC-003 through SC-010 are stated as counts and behavioural comparisons that can be observed without knowing how the change is built.
- **FR-005 / User Story 2** is the requirement the rest of the feature depends on. It is stated as its own P1 story rather than folded into the carry-forward story because the naive version of the carry-forward — the one that omits it — reports an unbuilt feature as finished, which is worse than shipping nothing at all.
