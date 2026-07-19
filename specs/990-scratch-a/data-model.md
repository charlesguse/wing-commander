# Phase 1 Data Model: Scratch Spec A

This feature introduces no persistent entities, database schema, or runtime
data structures. The only "data" involved is the fixture file itself.

## Entity: Scratch Note

| Field    | Type | Description                                                    |
|----------|------|------------------------------------------------------------------|
| path     | file path | `specs/990-scratch-a/notes.md`                              |
| content  | plain text | One or more lines of free-form marker text (see FR-001/SC-001) |

**Validation rules**: The file must exist and contain at least one line
(SC-001). No format, schema, or length constraints apply.

**State transitions**: None — the file is appended to or edited by scratch
commits over the course of the pipeline-validation exercise; it has no
lifecycle beyond that.
