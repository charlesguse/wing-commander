# Contract: FR-008 — the finding schema

`data-model.md`'s "Stage Finding (proposal)" table gives the field-by-field
shape; `research.md` D4/D5 explain why this is a new checked-in JSON file
rather than a per-spec doc artifact or a third-party-validated schema.

## `.github/schemas/stage-finding.schema.json` (NEW)

A JSON Schema (draft 2020-12) document, the sole checked-in authority on a
well-formed finding:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://wing-commander/schemas/stage-finding.schema.json",
  "title": "StageFinding",
  "type": "object",
  "required": ["title", "what", "evidence", "fingerprint_basis"],
  "additionalProperties": false,
  "properties": {
    "title": { "type": "string", "minLength": 1 },
    "what": { "type": "string", "minLength": 1 },
    "evidence": {
      "type": "object",
      "required": ["file_paths"],
      "additionalProperties": false,
      "properties": {
        "file_paths": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 },
          "minItems": 1
        },
        "detail": { "type": "string" }
      }
    },
    "fingerprint_basis": {
      "type": "object",
      "required": ["file_path", "gate_or_artifact"],
      "additionalProperties": false,
      "properties": {
        "file_path": { "type": "string", "minLength": 1 },
        "gate_or_artifact": { "type": "string", "minLength": 1 }
      }
    }
  }
}
```

`stage` and `run_url` are deliberately absent from this schema — they are
supplied by the filing composite's own `stage`/`run-url` inputs, never
taken from the proposal (FR-010).

## `.github/scripts/verify-stage-finding-schema.py` (NEW)

Exposes `validate_finding(obj: dict) -> tuple[bool, str]`, hand-checking
the same required fields/types the schema above declares (research.md D5:
no third-party JSON Schema library dependency). Reads the schema file at
import time so its own required-field list is generated from the file
rather than duplicated as a second literal — a drift between the two would
otherwise be exactly the kind of invisible second copy this repository's
gates exist to catch. Used by:
- `wing-commander-stage-findings`'s validation step (runtime).
- `wing-commander-stage-findings/tests/`'s fixtures (FR-030), including the
  case that a finding with `evidence.file_paths: []` is dropped rather than
  passed with an empty list.

## Call sites

Both findings-channel shapes (research.md D2/D3) ultimately produce a JSON
array validated element-by-element against this schema before anything
else happens: a malformed element is dropped alone, never the whole array
(FR-009's "whole, never partially filed" governs the *finding*, not the
batch — one bad finding does not disqualify its siblings).
