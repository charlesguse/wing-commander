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
- **The three markers this round opened are now resolved too** (clarify
  round 2, 2026-09-21, answered on #408 — recorded in the spec's
  Clarifications section). No `[NEEDS CLARIFICATION]` marker remains:
  - **FR-012 — what code must re-derive before closing on "already fixed on
    `main`"**: the ground is dropped. Triage's autonomous closes are the two
    that name the fields a gate reads — the 429 record and the upstream
    action bump. The third is recorded as deferred, not rejected; an issue
    the loop believes is already fixed is handed to a human under the
    `board:stalled` marker so it is not re-proposed every run. FR-013 no
    longer quotes a commit, FR-011 reads `main`'s commits for the hand-over
    rather than for a close, US1 gained a scenario asserting the refusal, and
    the two edge cases that leaned on the ground ("two issues describe the
    same defect", "the issue cites no run at all") were rewritten.
  - **FR-008 — may eligibility read the `labeled` event's actor?**: yes.
    FR-006's maintainer-applied/pipeline-applied distinction is kept and made
    decidable by the actor; an allowlist read off the label set alone would
    let the bot's own `spec-request` spin-off admit an issue. FR-006 now says
    a bot-applied label does not admit on that ground, and a new edge case
    records it. Closes #431.
  - **FR-007 — does the read-only proposal path ship at all?**: dropped,
    deferred rather than rejected, its number retired. Selection reaches only
    eligible issues, so an ineligible one receives nothing at all; the edge
    case was rewritten to say so and SC-009 stands unchanged. Closes #433.
- **`board:stalled` is now the loop's single hand-to-human marker**, applied
  by FR-012 (suspected already-fixed), FR-021 (post-push backstop breach) and
  FR-030 (exhausted round budget), with removal the sole condition that
  re-admits the item. FR-010 excludes on it in all three cases, which keeps
  the exclusion a label check rather than three different pieces of state.
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
  FR-005 leaves every existing filing route untouched; FR-006/FR-008/FR-009
  bound the loop to issues it is authorized for and leave every other issue
  untouched (FR-007's answer); FR-048–FR-054 bound
  concurrency, budget and stopping; FR-068 bounds the loop out of merging at
  all. FR-062/FR-063 settle the published surface: nothing widens on it.
- **Requirement Completeness — testability**: every requirement that gates a
  durable action is paired with a fixture obligation in FR-064, which
  enumerates the failure branches for the four gates (triage close,
  eligibility, route backstop, readiness report) rather than leaving "has
  fixtures" as prose. The list is now complete: FR-012's answer replaced the
  branch it could not enumerate with a single fixture asserting that an
  already-fixed proposal closes nothing, and FR-008's answer added the
  bot-applied entry label beside the maintainer-applied one.
- **Feature Readiness** — the seven user stories are ordered as the loop runs
  and each asserts observable outcomes (an issue is closed with quoted
  evidence, a review object exists on the PR, a readiness claim is refused
  with a named reason) rather than naming the mechanism that produces them.
  All seven survived FR-003's answer: User Story 5 kept every refusal branch
  and every fixture and lost only the act of merging, and User Story 6 gained
  the resume path as a new entry.
