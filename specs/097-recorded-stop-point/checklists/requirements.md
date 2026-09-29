# Specification Quality Checklist: An Honoured Stop Records Its Stop Point

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-29
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

- **Three `[NEEDS CLARIFICATION]` markers remain by design** (FR-003,
  FR-010, FR-016), and are the only open item on this checklist. They are
  the owner trade-offs the lifecycle issue itself named, carried forward
  for the clarify stage rather than guessed:
  1. FR-003 — what an honoured stop leaves behind (reuse the terminal
     `stalled` marker plus `board:stalled`, or a distinct `stopped`
     state).
  2. FR-010 — how much in-flight context the record preserves, i.e.
     whether a released item resumes where it stopped or restarts.
  3. FR-016 — whether a stop request posted before the loop's first
     announcement on an item counts at all.
  Intake runs headless: the markers stay in `spec.md` and the questions
  are posted to the lifecycle issue instead of being asked here.
- The issue's fourth design question — *where* the recording lives (the
  shared stop-check composite versus each job) — was resolved rather than
  marked. FR-018 requires exactly one home (CLAUDE.md "Shared logic has
  exactly one home"); which module that is, and what item context has to
  be threaded into it, is a plan-stage decision recorded in Assumptions.
- **On "no implementation details"**: the Overview's *Observed facts*
  section deliberately cites named files, constants and current-main
  behaviour as evidence that the defect exists, following this
  repository's established spec convention (see
  `specs/088-stop-check-closed-read/spec.md`). The requirements and
  success criteria themselves stay behavioural — they name what must be
  recorded, what must be excluded from selection, and what must write
  nothing, never how.
- Requirements the spec deliberately closes rather than asks about are
  listed in Assumptions, each with the existing rule or issue it follows
  from.
