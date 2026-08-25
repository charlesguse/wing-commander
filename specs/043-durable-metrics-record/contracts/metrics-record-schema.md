# Contract: Agent Run Metrics Record (schema version 1)

**Layer**: published contract (`.github/actions/wing-commander-metrics-summary`'s
`record-path` output; the persisted form on the `metrics` branch).

**Compatibility rules** (FR-025, restated here so a reader of this file
alone has them — not left to be inferred from spec.md):

1. Within schema version 1, changes are **additive only**: a field may
   be added; no field listed below may be removed, renamed, or have its
   meaning or units changed.
2. A reader may assume every field of a record's declared version is
   present, with any unavailable value explicitly marked per the
   `*_available` convention below rather than absent.
3. Any non-additive change requires a new `schema_version`.
4. A reader encountering a `schema_version` it does not know MUST retain
   and skip that record — never drop, rewrite, or fail on it.

## Shape

```json
{
  "schema_version": 1,
  "record_available": true,
  "run": {
    "workflow_run_id": "1234567890",
    "job_key": "cycle",
    "job_id": null,
    "step_index": 0,
    "record_key": "1234567890:cycle:0"
  },
  "stage": "implement",
  "stage_available": true,
  "run_label": null,
  "spec": {
    "spec_dir": "specs/043-durable-metrics-record",
    "issue": 148,
    "identity_available": true
  },
  "model": "claude-sonnet-5",
  "model_available": true,
  "turns": {
    "counted": 42,
    "reported": 47,
    "intended_budget": 60,
    "enforced_ceiling": 150,
    "available": true
  },
  "tokens": {
    "input": 18234,
    "output": 4021,
    "cache_read": 92110,
    "cache_creation": 5510,
    "available": true
  },
  "cost_usd": 1.2345,
  "cost_available": true,
  "duration_ms": 415200,
  "duration_available": true,
  "outcome": "healthy",
  "per_model": [
    {
      "model": "claude-sonnet-5",
      "input_tokens": 18234,
      "output_tokens": 4021,
      "cache_read_tokens": 92110,
      "cache_creation_tokens": 5510,
      "cost_usd": 1.2345
    }
  ],
  "per_model_available": true,
  "emitted_at": "2026-08-25T14:03:11Z"
}
```

## Field reference

See data-model.md's "Agent run metrics record" table for the full
field-by-field description. This file is the normative shape; data-model.md
explains the rationale for each field's presence.

## Degraded record (transcript missing/empty/unparseable)

```json
{
  "schema_version": 1,
  "record_available": false,
  "run": {
    "workflow_run_id": "1234567890",
    "job_key": "cycle",
    "job_id": null,
    "step_index": 0,
    "record_key": "1234567890:cycle:0"
  },
  "stage": "implement",
  "stage_available": true,
  "run_label": null,
  "spec": { "spec_dir": "specs/043-durable-metrics-record", "issue": 148, "identity_available": true },
  "model": "claude-sonnet-5",
  "model_available": true,
  "turns": { "counted": null, "reported": null, "intended_budget": 60, "enforced_ceiling": 150, "available": false },
  "tokens": { "input": null, "output": null, "cache_read": null, "cache_creation": null, "available": false },
  "cost_usd": null,
  "cost_available": false,
  "duration_ms": null,
  "duration_available": false,
  "outcome": "unavailable",
  "per_model": [],
  "per_model_available": false,
  "emitted_at": "2026-08-25T14:03:11Z"
}
```

Fields the job environment itself supplies (`run.*`, `stage`,
`spec.*`, `model`, `turns.intended_budget`, `turns.enforced_ceiling`)
stay available even when the transcript is unreadable — they never came
from the transcript in the first place. Only transcript-derived fields
degrade.

## Invariant (checked by gate coverage, research.md R12.2)

When both `tokens.available` and `per_model_available` are `true`:

```
sum(per_model[].input_tokens)          == tokens.input
sum(per_model[].output_tokens)         == tokens.output
sum(per_model[].cache_read_tokens)     == tokens.cache_read
sum(per_model[].cache_creation_tokens) == tokens.cache_creation
sum(per_model[].cost_usd)              == cost_usd   (within floating-point tolerance)
```

A record failing this invariant is rejected by the collector (not
persisted) and reported by `record_key`, per FR-017/FR-041 — well-formedness
is decided by deterministic code, never by an agent's judgment.
