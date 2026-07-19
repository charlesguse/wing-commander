# Quickstart: Scratch Spec A (pipeline serialization validation)

## Prerequisites

- A checkout of this repository on any branch under the `990-scratch-a`
  spec lineage (e.g. `spec/990-scratch-a`, `plan/990-scratch-a`).

## Validation

1. Confirm the note file exists and is non-empty:

   ```bash
   test -s specs/990-scratch-a/notes.md && echo OK
   ```

2. Expected outcome: `OK` is printed. Per SC-001, nothing else is required
   for this feature to be considered complete.

## Notes

This spec exists to exercise the pipeline's per-specification concurrency
group (`wing-commander-specs/990-scratch-a`, see
`specs/013-serialize-rebase-stages/quickstart.md`). No build, test, or run
steps beyond the single check above apply.
