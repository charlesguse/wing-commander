# Phase 0 Research: Scratch Spec A

**Input**: `specs/990-scratch-a/spec.md`

`spec.md` contains no `[NEEDS CLARIFICATION]` markers. This document records
the small number of implicit decisions needed to move from spec to plan.

## D1: What counts as "done" for this feature

- **Decision**: Treat FR-001 / SC-001 literally — the feature is complete
  once `specs/990-scratch-a/notes.md` exists with at least one line of
  content. No additional scaffolding (tests, source files, CI changes) is
  in scope.
- **Rationale**: The spec's Overview explicitly states this is a throwaway
  artifact for validating feature 013's per-spec concurrency groups, and
  FR-001 explicitly forbids designing or writing application code, workflows,
  or tests.
- **Alternatives considered**: Building a small representative
  "hello world" style feature to more closely mimic a real pipeline run.
  Rejected — it would add artifacts to clean up post-validation and provide
  no additional signal about concurrency-group behavior, which is the only
  thing under test.

## D2: Whether to generate a `contracts/` directory

- **Decision**: Skip `contracts/`. This feature has no API, CLI surface,
  schema, or integration point for any consumer.
- **Rationale**: The Phase 1 instructions say to skip contracts when a
  project is purely internal; a one-line note file has no interface at all.
- **Alternatives considered**: None — there is nothing to contract.

## D3: Technical Context fields

- **Decision**: Mark language/dependencies/storage/testing/platform fields
  as N/A rather than NEEDS CLARIFICATION.
- **Rationale**: These fields ask about implementation technology, but this
  feature has no implementation — it is a fixture file. N/A accurately
  reflects "not applicable," distinct from "unknown and needs research."
- **Alternatives considered**: Leaving fields as NEEDS CLARIFICATION and
  raising a research task. Rejected — there is no unknown to resolve; the
  spec is unambiguous about scope.

## Outcome

All Technical Context unknowns are resolved (as N/A, per D3). No outstanding
`[NEEDS CLARIFICATION]` markers remain in `spec.md` or `plan.md`.
