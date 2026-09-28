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

- Both original `[NEEDS CLARIFICATION]` markers were answered on lifecycle
  issue #491 on 2026-09-25 and are folded in: FR-002 now names the metrics
  record key as what the stamp carries, and FR-008 now states the
  conservative fallback (only a foreign stamp excludes a comment; unstamped
  comments in the window stay eligible). See the Clarifications section of
  [spec.md](../spec.md).
- The one remaining `[NEEDS CLARIFICATION]` marker — where the re-run
  attempt number lives, given that no part of
  `<workflow run id>:<job key>:<step index>` varies across attempts — was
  answered on #491 on 2026-09-28 and is folded in: the attempt number goes
  into the **metrics record key itself**, so one run identity serves the
  stamp, the record, and the per-run rollup line. No markers remain.
- That choice's blast radius is now specified rather than implied: FR-014
  requires every composition site of the record key, the rollup line's
  identity, the record idempotence resting on the key, and the existing
  metrics-record gates pinning its shape to be widened in the same change,
  with SC-009 as the measurable outcome. FR-002a specifies the collector
  side (resolve the inspected run's attempt number; degrade the
  attempt-level discrimination alone to the window when it cannot), and
  FR-012 gains the re-run pair and unresolvable-attempt scenarios plus a
  mutation check for dropping the attempt number from the matched key.
- "Users" in this spec are the repository's maintainers and the watchdog
  that supervises pipeline runs on their behalf; the cost line is a
  maintainer-facing report, so maintainer-facing language is the
  non-technical register here.
- Named repository artefacts (the cost-line formatter, the cost-report
  collector, the gates covering it) are referred to by role rather than by
  file path, except in the Overview's single quotation of the source comment
  that documents the defect.
