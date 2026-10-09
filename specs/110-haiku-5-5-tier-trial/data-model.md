# Data Model: Haiku 5.5 Tier Upgrade and Measured Trial

## Trial record (`trial` object on a metrics record)

Additive top-level field on a `schema_version` 1 record; see
[contracts/trial-record.md](contracts/trial-record.md).

| Field | Type | Notes |
|---|---|---|
| `step` | string | `watchdog.diagnose` |
| `candidate_model` | string | the model the pipeline chose for the shadow; equals the record's top-level `model` |
| `baseline_run_label` | string | `diagnose` |
| `outcome` | enum | `agreed`, `disagreed`, `exhausted`, `malformed`, `error`, `refused`, `no-baseline` |
| `baseline_verdict` | string | the Opus agent verdict (`healthy`, `exhausted`, `failed`, `rate-limited`, `unavailable`, …) |
| `filing_agree` | bool \| null | null for `no-baseline`, `error`; false for `refused`, `exhausted`, `malformed` |
| `class_shared` / `class_agree` | int \| null | findings sharing a signal-id set / those with equal class |
| `differing_fields` | string[] | finding keys on one side only; shared keys whose class differs |

Related top-level record fields: `run.run_label = "diagnose-shadow"`, own
`run.record_key`; `refusal` (bool, additive, set by `wing-commander-metrics-summary`).

**Compared run**: `outcome ∉ {error, no-baseline}`. `refused`, `exhausted`,
`malformed` are compared runs and count as not agreeing under criterion (a).

## Trial switch state

| Name | Where | Meaning |
|---|---|---|
| `WING_COMMANDER_DIAGNOSE_SHADOW_SINCE` | repository variable (ISO date) | unset = off; set = window start |
| `diagnose-shadow-enabled` | `watchdog.yml` input (bool, default false) | computed by the wrapper from the bound |
| `model:haiku` | lifecycle issue label | per-lifecycle implement opt-in |
| `WING_COMMANDER_IMPLEMENT_HAIKU_MAX_TURNS` | repository variable | Haiku cycle turn budget, default 180 |

States of the diagnose shadow: `off` (no SINCE) → `on` (SINCE set, <60 d, <300 compared)
→ `expired` (either bound reached; stays off until a new SINCE). Owner unsets SINCE → `off`.

## Implement trial evidence

No new record: the cycle's normal metrics record (`stage` implement, top-level
`model` = `claude-haiku-5-5`, `turns`, tokens, `cost_usd`, `outcome`, `refusal`,
`spec.issue`) is the trial record. Escalations appear as the later record on the
same `spec.issue` with the escalation model.

## Trial summary (derived, not stored)

Per step: runs, agreement/success rate, refusal count, exhaustion count, median turns,
cost per run per model; diagnose adds `meets` / `misses` / `sample too small`.
A run's model is the record's top-level `model`, never a `per_model` entry.
