# Specification Quality Checklist: The Cost Line Names Its Own Run — Run-Stamped Cost Attribution

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-24
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

- Both original `[NEEDS CLARIFICATION]` markers were answered on lifecycle
  issue #491 on 2026-09-25 and are folded in: FR-002 now names the metrics
  record key as what the stamp carries, and FR-008 now states the
  conservative fallback (only a foreign stamp excludes a comment; unstamped
  comments in the window stay eligible). See the Clarifications section of
  [spec.md](../spec.md).
- One `[NEEDS CLARIFICATION]` marker remains, newly raised by folding that
  answer in: the metrics record key the answer selects is
  `<workflow run id>:<job key>:<step index>`, none of which varies across
  re-run attempts, so it does not by itself separate a re-run's cost line
  from the original attempt's as the answer intends. Whether the attempt
  number is added to the record key itself (shared with the rollup line's
  identity, pinned by existing metrics-record gates) or carried in the
  stamp alongside it is an owner decision with materially different blast
  radius, so it is posted back to #491 rather than defaulted.
- "Users" in this spec are the repository's maintainers and the watchdog
  that supervises pipeline runs on their behalf; the cost line is a
  maintainer-facing report, so maintainer-facing language is the
  non-technical register here.
- Named repository artefacts (the cost-line formatter, the cost-report
  collector, the gates covering it) are referred to by role rather than by
  file path, except in the Overview's single quotation of the source comment
  that documents the defect.
