# Specification Quality Checklist: The Board Loop — A Scheduled Run Takes One Open Issue From Triage To Proven

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

- **The intake stage's three markers are resolved** (clarify, 2026-09-21,
  answered on #408 — recorded in the spec's Clarifications section):
  - **FR-003 — how far autonomy goes**: stop at "ready to merge". FR-034,
    FR-035, FR-038, FR-039 and FR-040 left scope as one block for a follow-on
    feature; their numbers are retired rather than reused, FR-036 and FR-037
    stayed in scope, and the readiness report that replaces the merge gate is
    FR-066–FR-068. User Story 5 kept its refusal branches and lost its merge;
    User Story 6 gained the `pull_request: closed` resume path.
  - **FR-062 — published stage or repository-only workflow**: repository-only,
    in the `auto-release.yml` shape. FR-063's second branch applies and the
    feature moves no adopter-pinned surface.
  - **FR-040 — the second merge class**: deferred entirely with the merge
    block, as its own feature.
- **Three `[NEEDS CLARIFICATION]` markers are open, all opened in this
  round** rather than carried from intake, so the spec is not ready to merge
  and the questions go back to #408:
  - **FR-012 — what code must re-derive before closing on "already fixed on
    `main`".** Raised in the answer itself. The 429 ground names four fields a
    gate reads; this ground names no decidable rule, so FR-064 cannot
    enumerate its failure branches, and it sits exactly where Principle IX's
    "code decides" either holds or degrades into a rubber stamp on the
    agent's verdict. No defensible default — the same test the other three
    markers passed.
  - **FR-008 — may eligibility read the `labeled` event's actor?** FR-006
    turns on *who* applied a label; author association plus the label set
    cannot recover that, and the bot's own `spec-request` spin-off label would
    be read as "a maintainer labeled it". Widening FR-008 and replacing the
    distinction with an entry-label allowlist are both coherent and differ in
    what they admit, so this is the owner's call. Tracked as #431.
  - **FR-007 — does the read-only proposal path ship at all?** FR-009 selects
    only eligible issues, so FR-007 and its edge case are currently
    unreachable; making them reachable needs its own selection pass, its own
    SC-009 wording and an exclusion a posted proposal sets, while dropping
    them is permitted by X. Tracked as #433.
- **Findings from the same review that were folded in rather than asked
  about**, because each had one defensible resolution: the lifecycle-owned
  exclusion FR-010 was missing (#432, keyed on `stage:*` / `spec:*` — without
  it this feature's own lifecycle issue is selectable on the loop's first
  run); FR-021's post-push re-route, which the spec left undefined between
  "withdraws the fix" and "leaves the PR open" and which the existing
  "deleting work is the more surprising behaviour" assumption settles;
  FR-030's exhausted-budget marker, now named (`board:stalled`) with removal
  as its sole clearing condition, so FR-010's label-or-state check is
  decidable; and FR-029's review event, now `COMMENT`, because the loop's PR
  and its review carry the same App identity and GitHub rejects `APPROVE` and
  `REQUEST_CHANGES` on a self-authored PR.
- **Numbering**: requirements added in this round take fresh numbers
  (FR-066–FR-068) and sit in the Readiness section beside the deferred block
  they replace, so a deferred number never has two meanings.
- **Decision points the lifecycle issue raises that are *not* markers**,
  because each has a defensible default recorded in Assumptions instead:
  cadence; round budget; per-item turn ceiling; stand-down while an implement
  cycle runs (the issue's own Constraints already settle it); reviewer model
  tier; whether a settled disposition or a closed lifecycle stops the loop;
  whether closing the issue mid-loop closes its PR; and how non-maintainer
  comments are kept out of the fixer's instructions (FR-056 settles the
  mechanism — code decides from author association — leaving only a knob).
  Each is reversible by one constant or one input; spending a marker on any
  of them would have displaced one of the three above.
- **The findings format is deliberately not a marker.** The issue lists it
  under "Review tier and format", but X requires the merge gate to count open
  findings in code, so a schema-validated structure is a constitutional
  requirement (FR-029, FR-033), not a choice. Only the reviewer's model tier
  remained open there, and that has a default.
- **Content Quality — "no implementation details"**: this repository's
  product is CI workflow behaviour, so the spec necessarily names stages,
  labels, lifecycle issues, branches and run evidence. It names no job, step,
  language or file path except where reusing an existing artifact *is* the
  requirement (FR-059–FR-061, this repository's single-home rule) or where a
  named constant would otherwise go stale (the pr-conversation stage's ≤3
  files / ≤40 changed lines, quoted in Assumptions as the precedent the
  board's own thresholds deliberately do not inherit).
- **Requirement Completeness — bounded scope**: FR-001 bounds the feature to
  one loop over one issue per run; FR-004 keeps the feature lifecycle out;
  FR-005 leaves every existing filing route untouched; FR-007 bounds what the
  loop may do to an issue it is not authorized for; FR-048–FR-054 bound
  concurrency, budget and stopping; FR-068 bounds the loop out of merging at
  all. FR-062/FR-063 settle the published surface: nothing widens on it.
- **Requirement Completeness — testability**: every requirement that gates a
  durable action is paired with a fixture obligation in FR-064, which
  enumerates the failure branches for the three gates (triage close, route
  backstop, readiness report) rather than leaving "has fixtures" as prose.
  One entry there is knowingly incomplete: the already-fixed-on-`main`
  branches cannot be enumerated until FR-012 is answered, and FR-064 says so
  instead of implying coverage it cannot yet have.
- **Feature Readiness** — the seven user stories are ordered as the loop runs
  and each asserts observable outcomes (an issue is closed with quoted
  evidence, a review object exists on the PR, a readiness claim is refused
  with a named reason) rather than naming the mechanism that produces them.
  All seven survived FR-003's answer: User Story 5 kept every refusal branch
  and every fixture and lost only the act of merging, and User Story 6 gained
  the resume path as a new entry.
