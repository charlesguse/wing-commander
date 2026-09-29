# Specification Quality Checklist: A Merged Fix Reaches Prove — The Prove Entry Survives a Displaced Queue Slot

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-29
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

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-09-29

**Three [NEEDS CLARIFICATION] markers remain, at the limit of three.** They
are carried deliberately, on FR-001, FR-004 and FR-011, and are posted to
lifecycle issue #723 rather than resolved by a guess:

1. **FR-001 (scope)** — spec 060's FR-010b already requires deterministic
   detection and recording of this exact displacement, and spec 060 is in
   flight and unimplemented. Whether #723 is the *recovery* delta beyond
   FR-010b, is already covered by it, or should be folded into spec 060 is
   not derivable from the issue; all three readings produce materially
   different work, and one of them means this feature should be declined.
2. **FR-004 (mechanism)** — issue #537 names two mechanisms and says
   explicitly "Needs a check against the FR-048 rationale before choosing".
   The check is performed and recorded in the Overview (both prove jobs run
   no agent, and FR-048's stated reason is the shared usage window), which
   makes mechanism (A) admissible — but whether the owner reads FR-048 as
   bounding agent concurrency alone or Actions concurrency generally is the
   owner's call, and it decides between (A), (B) and (C).
3. **FR-011 (breadth)** — a `prove` marker left by a failed re-drive is
   unreachable by every automated path today and waits for a maintainer.
   Whether recovery should also unstick it is adjacent to #723, not stated
   by it, and answering it either way changes the bound the feature needs.

**Content-quality note.** This spec names specific files, functions and
line numbers in its Overview, Edge Cases and Dependencies. That is a
deliberate deviation from "written for non-technical stakeholders": the
subject is this repository's own CI plumbing, its stakeholders are its
maintainers, and every shipped spec in `specs/` from 057 onward reads this
way. The Functional Requirements and Success Criteria themselves stay
behavioural — they state what must hold, not how — so the checklist item is
marked passing on the requirements, with the citation style recorded here.

**Success-criteria note.** SC-001/SC-002/SC-004/SC-006 are counted over the
checked-in coverage set rather than over production runs, because the
condition being fixed (a pending-slot eviction) is not observable after the
fact — a displaced run leaves no record at all. That is stated in the Key
Entities section as the reason detection must work from state the run
*failed* to change.

### Validation iteration 2 — 2026-09-29 (clarifications resolved)

**All three [NEEDS CLARIFICATION] markers are resolved** from the reply
@charlesguse posted on lifecycle issue #723, and the Clarifications section
now records the decisions rather than the questions:

1. **FR-001 (scope)** — actual recovery, specified in this spec and built on
   spec 060 as merged (PR #490, commit `fa656bc`, 2026-09-29). FR-010b's
   record remains as the backstop; spec 060 is not amended.
2. **FR-004 (mechanism)** — mechanism (A): the `pull_request: closed`
   `prove-gate`/`prove` path gets its own concurrency group, keyed per
   merged item. FR-048 is read as bounding agent concurrency, which settles
   the reading the previous iteration flagged as the owner's call.
3. **FR-011 (breadth)** — recovery reaches only the cases where the loop
   could not observe a proof: the displacement record itself and an
   `uncorrelated` re-drive. `failure` and `unfinished` wait for a
   maintainer. FR-011a adds the starvation bound the question asked for
   (one attempt per merged PR, durably recorded) and FR-011b keeps a second
   recoverable item recoverable.

**Spec 060 had landed between drafting and this reply**, which the reply
states and the repository confirms (`fa656bc`; this feature's branch was
cut before it). The consequences were folded in rather than left as prose
that contradicted `main`: the Overview now describes per-job concurrency
groups and spec 060's shipped displacement detection, the pre-060
re-triage harm is recorded as history with the present harm restated as
"recorded and then stranded", FR-002 names spec 060's directed dispatch as
the recovery's entry (one home), FR-005 and FR-021 name the live spec 060
contracts this feature must correct — including
`concurrency-groups.md`'s "What does not change" bullet, which mechanism
(A) makes false — and FR-014/FR-015/FR-018/FR-019 reuse spec 060's
recorded reason, taxonomy labels, group-expression reader and Gate 101
instead of adding second copies.

**One consequence was decided here rather than re-asked.** Mechanism (A) is
prevention, so it does not by itself reach merges already stranded with a
`prove` marker, nor Q3's `uncorrelated` case. Both would otherwise stay
unproven forever, so the spec keeps a bounded recovery for exactly those
two shapes and says so in "Consequences of Q2 (A) rather than (C),
recorded rather than re-asked". A fourth question was judged
disproportionate to that gap.
