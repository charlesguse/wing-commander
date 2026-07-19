# Quickstart: Scratch Spec B

## Prerequisites

None.

## Validation Scenario (SC-001)

1. Confirm the spec directory contains a `notes.md` file:

   ```bash
   test -f specs/991-scratch-b/notes.md && echo "PASS: notes.md exists"
   ```

2. Expected outcome: the command prints `PASS: notes.md exists`. No other
   setup, build, or run steps apply — this feature has no application code,
   workflows, or tests to exercise (FR-001).

## Cross-reference

This spec exists to validate per-spec pipeline concurrency groups described in
[specs/013-serialize-rebase-stages/quickstart.md](../013-serialize-rebase-stages/quickstart.md).
