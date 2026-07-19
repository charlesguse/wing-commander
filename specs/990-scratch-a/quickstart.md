# Quickstart: Scratch Spec A validation

**Prerequisites**: a checkout of this repository on a branch derived from
`spec/990-scratch-a`.

## Scenario 1 — The feature's only artifact exists (SC-001)

1. From the repo root, check the file:

   ```sh
   test -s specs/990-scratch-a/notes.md && echo "PASS: notes.md exists and is non-empty"
   ```

2. Expected: `PASS: notes.md exists and is non-empty` is printed.

## Scenario 2 — No out-of-scope artifacts were introduced (FR-001)

1. Diff this spec's directory against what the constitution's Operational
   Constraints expect for a spec at the `plan` stage:

   ```sh
   git diff --stat spec/990-scratch-a...HEAD -- . ':!specs/990-scratch-a'
   ```

2. Expected: no output — every change in this branch is confined to
   `specs/990-scratch-a/` (plus, if the plan skill's agent-context update
   script ran, the single agent context file it maintains).

## Notes

This quickstart validates the scratch spec's own (deliberately trivial)
deliverable. It is unrelated to, and should not be confused with, the
broader multi-scenario quickstart at
`specs/013-serialize-rebase-stages/quickstart.md`, which uses specs like
this one as *fixtures* to validate the pipeline's concurrency-serialization
behavior.
