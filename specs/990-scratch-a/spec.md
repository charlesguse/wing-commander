# Feature Specification: Scratch Spec A (pipeline serialization validation)

**Feature Branch**: `spec/990-scratch-a`
**Status**: Scratch — exists only to validate feature 013 (per-spec serialization of rebase and stages). Not a real feature. It will be deleted after validation.

## Overview

This is a deliberately minimal scratch specification used to exercise the
pipeline's per-specification concurrency groups
(`wing-commander-specs/990-scratch-a`) per
`specs/013-serialize-rebase-stages/quickstart.md`. Any stage agent processing
this spec should produce the smallest possible artifacts and finish quickly.

## User Scenarios

### US1 — Placeholder

As a pipeline maintainer, I need a throwaway spec whose stage runs hold the
per-spec concurrency group long enough to observe queuing behavior.

**Acceptance**: A one-line note file exists at `specs/990-scratch-a/notes.md`.

## Requirements

- **FR-001**: The feature consists solely of maintaining `notes.md` in this
  spec directory. No application code, no workflows, no tests are to be
  designed or written.

## Success Criteria

- **SC-001**: `notes.md` exists. Nothing else is needed.
