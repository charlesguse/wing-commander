# Phase 1 Data Model: Scratch Spec A (pipeline serialization validation)

This feature has no application data model. The only artifact is a file-system entity:

## Entity: Note File

| Field | Type | Description |
|-------|------|--------------|
| Path | string (constant) | `specs/990-scratch-a/notes.md` |
| Content | text | One or more short lines documenting scratch-scenario markers; no schema is enforced |

**Validation rules**: None beyond FR-001/SC-001 — the file must exist. No format, size,
or content validation is required.

**State transitions**: None. The file may be appended to by later scratch scenarios but
has no defined states or transitions.
