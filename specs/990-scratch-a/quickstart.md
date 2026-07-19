# Quickstart: Scratch Spec A (pipeline serialization validation)

## Prerequisites

- A checkout of this repository on a branch descending from `spec/990-scratch-a`.

## Validation Scenario (SC-001)

1. Confirm the note file exists:

   ```bash
   test -f specs/990-scratch-a/notes.md && echo "PASS: notes.md exists"
   ```

2. Confirm no application code, workflow, or test files were introduced by this feature
   (per FR-001):

   ```bash
   git diff --stat main...HEAD -- . ':!specs/990-scratch-a'
   ```

   Expected outcome: no output (no changes outside `specs/990-scratch-a/`).

## Expected Outcome

Both checks pass: `notes.md` exists in `specs/990-scratch-a/`, and the feature's diff is
confined to that spec directory. No further runtime verification is applicable since this
feature has no executable behavior.
