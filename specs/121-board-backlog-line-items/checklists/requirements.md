# Specification Quality Checklist: Board Loop Works Maintenance Backlog Lines

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-03
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

- All three clarifications were resolved from the reply on lifecycle issue #1080 (2026-11-06): FR-003 a short id written into the line on claim, FR-004 oldest first, FR-009 a loop-authored comment on the backlog issue keyed by the line's id. See the spec's Clarifications section.
- The issue's other two questions were given documented defaults in Assumptions: lines only when the issue queue is empty (the proposal's own wording), and bundled lines worked as one item bounded by the backstop.
- Repository-specific names (`WING_COMMANDER_*` variables, labels, the board loop's step names) appear because they are the domain vocabulary of this pipeline, not implementation choices.
- Spec review (2026-11-06) corrected requirements that could not be built on main as written: the backlog's title match (FR-002), body order as the oldest-first order (FR-004), "claimed" vs "held" (FR-006, FR-010, SC-004), all triage close-evidence classes (FR-012), spec 108's duplicate disposition and the `board:stalled` sites (FR-013, FR-014), the read-modify-write window GitHub cannot close (FR-015, SC-003), and finding a line-born PR's item without `Fixes #N` (FR-021).
- Second spec review (2026-11-06) completed lists that named fewer sites than board-loop.yml has (FR-014's `board:stalled` sites, FR-021's `Fixes #N` readers), derived a line's fix branch from its id (FR-007; every line shares one issue number and title), aligned FR-024's re-apply with FR-015's bound, and scoped SC-001 to the switch.
- Third spec review (2026-11-06) aligned Story 2, FR-012, SC-002 and the Assumptions with `board_triage.py` (an already-fixed proposal is a handover hold, never a close: spec 057 FR-012), extended FR-017's no-closing-keyword rule to the PR title and branch commit messages a squash merge carries onto `main`, and kept a line-born PR's merge ticking its line after the switch is off (FR-020, FR-023).
- Fourth spec review (2026-11-06) named FR-025's literal (`Maintenance backlog line`, singular, as #1115 states it), extended FR-017's commit check to every push to a line's branch (review-fixup pushes included, since a human may squash-merge), and kept a line-born PR's merge handling (tick, prove entry, recovery) on after the PR has closed, which FR-020/FR-023's "no line-born fix PR open" otherwise switched off.
- Fifth spec review (2026-11-06) extended FR-013 to the two other sites that file a `spec-proposal` and dispose of the originating issue (fix's post-push breach, readiness's forced-breach retry), whose spec 108 disposition would close the backlog issue; made FR-017's deterministic check cover the PR body the owner's answer names (a line's own text quoted into it may carry a closing keyword) and hold the line on a refusal; and kept the prove job's closing arms off the backlog issue (FR-021).
- Sixth spec review (2026-11-07) swept board-loop.yml for every action on the item issue: a line's branch must still match the merge step's `fix/<issue>-<slug>` shape, a line's PR and `spec-proposal` titles come from the line's text, not the backlog issue's title (FR-007), and FR-011's run link is required only for proof outcomes that have a run.
- Seventh spec review (2026-11-07) confirmed a line branch `fix/<backlog>-<line id>` stays unique per line, never collides with an issue's branch (the backlog issue is never an issue item) and passes `FIX_BRANCH_RE`, and that FR-011's run-link outcomes match the prove job; it required a title taken from a line's text to fit GitHub's 256-character limit (FR-007) and added FR-007's branch and title derivations to FR-019's fixture list.
- Eighth spec review (2026-11-07) confirmed FR-007's title cut is testable (line text minus the loop's id and annotations, prefix included, at most 256 characters) and constrained the line id itself (FR-003) to the fix branch's slug alphabet and length, so the branch carries it verbatim and no two ids fold into one branch name.
