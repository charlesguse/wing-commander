# Feature Specification: Scratch Spec B (pipeline serialization validation)

**Feature Branch**: `spec/991-scratch-b`
**Status**: Scratch — exists only to validate feature 013 (per-spec serialization of rebase and stages). Not a real feature. It will be deleted after validation.

## Overview

This is a deliberately minimal scratch specification used to exercise the
pipeline's per-specification concurrency groups
(`wing-commander-specs/991-scratch-b`) per
`specs/013-serialize-rebase-stages/quickstart.md`. Any stage agent processing
this spec should produce the smallest possible artifacts and finish quickly.

## User Scenarios

### US1 — Placeholder

As a pipeline maintainer, I need a second throwaway spec, independent of
scratch spec A, so cross-spec concurrency can be observed.

**Acceptance**: A one-line note file exists at `specs/991-scratch-b/notes.md`.

## Requirements

- **FR-001**: The feature consists solely of maintaining `notes.md` in this
  spec directory. No application code, no workflows, no tests are to be
  designed or written.

## Success Criteria

- **SC-001**: `notes.md` exists. Nothing else is needed.
