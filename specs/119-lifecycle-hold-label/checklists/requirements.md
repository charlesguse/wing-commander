# Specification Quality Checklist: Hold a Lifecycle With One Label, and Check Folded Tasks Before Implement Builds Them

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-22
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

- The three [NEEDS CLARIFICATION] markers (FR-005, FR-017, FR-018) were resolved by the owner's answers on #1066 (2026-10-24): strict-only stop sets the hold, dismissal is derived from the fold task's removal from tasks.md, and the comment and amendment-PR answer paths are sufficient. See the spec's Clarifications section.
- This is pipeline infrastructure whose stakeholders are maintainers, so the spec names existing pipeline components (labels, composites, `board_stop_check.py`, the constitution's model tier) as the user-visible surface. That is deliberate and not treated as leaked implementation detail; how each is wired is left to plan.
- Review pass (2026-10-24) corrected the stop-parser, kill-switch and spec 116 dependency wording against main, and added FR-021 and edge cases for held cycles vs. stall/loss detection, fold-queue tickets, other implement dispatch paths, and which tasks.md changes count as a dismissal. Open owner questions from that pass (release trigger, drop mechanism, issue-comment stop path, analyze retry, auto-merge while held) were answered by the owner on 2026-10-24 (all option a) and are recorded in the spec's Clarifications section, FR-005, FR-007, FR-016, FR-018, FR-022 and FR-023.
- Second review pass (2026-10-24, after the owner's answers) checked them against main: widened FR-007's release trigger to every lifecycle whose implement is due (review-gate folds run under `stage:review`) with chaining inputs derived from spec-meta; replaced "fold task ids" (fold tasks carry none) with the gate's fold title line; made a dismissed finding neither re-folded nor counted open; required the drop to be checked-off-safe, serialized through the existing fold queue, authenticated beyond its commit message, and not also classified as feedback; named the retry as a re-run of the fold's analyze job; added FR-024 for the clarify default; and pointed FR-022 at spec 062's readiness contract. Constitution X's "all eight of its gates" was answered by the owner on 2026-10-26: a constitution X amendment PR lands alongside the feature (FR-022); the owner also kept FR-024, kept the shared stop parser as it is, and deferred Board status listing of held lifecycles to the Maintenance backlog (Clarifications, Session 2026-10-26).
- Third review pass (2026-10-26) checked the spec against main again and made it consistent with itself: a fold task already checked off no longer blocks a dismissal (every `Recurring review finding:` task has one), and a drop's attribution survives the rebase stage (FR-017, SC-005); FR-007 decides "implement is due" from spec-meta.json, not the issue's stage label, and callers that look up their dispatched implement run filter to `workflow_dispatch`; the hold label stays off lifecycle PRs (FR-001); a held cycle dispatches nothing (FR-002); a fail-closed read resumes by a hand dispatch, not a re-run (FR-004); a retry's re-run dependents post nothing beyond the verdict (FR-016); setting the hold has one home (FR-019); the fold-dispatch composite reports a withheld dispatch as an output (FR-003, SC-004); the wrappers are named as the consuming instrument (FR-007, SC-004); "the lifecycle's PR" is defined (FR-005); and the label-permission assumption matches GitHub's triage role.
