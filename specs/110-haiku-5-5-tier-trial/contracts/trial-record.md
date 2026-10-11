# Contract: Trial record

Extends `specs/043-durable-metrics-record/contracts/metrics-record-schema.md`
(live contract). Within `schema_version` 1 only additive fields.

## Requirements

1. The diagnose shadow's record is a complete metrics record produced by
   `wing-commander-metrics-summary` with `run-label: diagnose-shadow`; the
   `per_model` sum invariant holds; `outcome` keeps its agent-verdict values.
2. It has its own `run.record_key` (its own job step index / artifact) and
   top-level `run_label == "diagnose-shadow"` (the metrics record carries
   `run_label` at the top level, not under `run`), so readers of the acting
   diagnose's record never count it: the turn-budget trend collector drops
   `run_label == "diagnose-shadow"` records and the shadow's artifact.
3. Added top-level fields: `trial` (object below) and, on every record,
   `refusal` (bool; true iff the terminal result carries `stop_reason: "refusal"`,
   false otherwise, absent on records written before this change and read as false).
4. Artifact name `metrics-record-diagnose-shadow`; file name matches persist's
   `*.json` sweep.
5. Model identity for any trial or Haiku-tier statistic is the top-level `model`
   field. A `claude-haiku-5-5` `per_model` entry on a Sonnet or Opus record is
   Claude Code's own helper and MUST NOT be counted.

## `trial` object

```json
{
  "step": "watchdog.diagnose",
  "candidate_model": "claude-haiku-5-5",
  "baseline_run_label": "diagnose",
  "outcome": "agreed",
  "baseline_verdict": "healthy",
  "filing_agree": true,
  "class_shared": 2,
  "class_agree": 2,
  "differing_fields": []
}
```

A shadow result that is not an object with a `findings` array (for example a
bare array) misses the diagnose schema and is `malformed`. The whole result is
held to the schema, top-level keys included, not only its `findings` array.
A baseline finding whose `class` or any evidence `signalId` is not a string
(the only type the diagnose schema gives them) cannot be compared with the
schema-held shadow, so the run is `no-baseline`.

`candidate_model` is the record's own top-level `model` (the
`diagnose-shadow-model` input), passed to the comparator by
`wing-commander-trial-record`.

**Comparator failure.** When the comparator itself exits non-zero,
`wing-commander-trial-record` still writes a `trial` object: `outcome:
"error"`, the baseline verdict it was given, and the additive field
`error_source: "comparator"`. Such a run is still not a compared run for the
FR-017 bar, but it marks a defect in this pipeline rather than
infrastructure, so `trial-bound.py` counts it toward the 300-run cap (a
broken comparator cannot keep the shadow spending for the whole window) and
`trial-summary.py` reports it on its own line.

`outcome` evaluation order (first match wins): `no-baseline` (baseline verdict not
`healthy`) → `refused` → `exhausted` → `error` (failed / rate-limited / unavailable /
unclassifiable shadow) → `malformed` (result fails the diagnose schema) →
`agreed` (filing agrees and every shared finding agrees on class) → `disagreed`.

## Comparator CLI

`python3 -I .github/actions/_shared/compare-diagnose-shadow.py --baseline-findings F --baseline-verdict V --shadow-findings F --shadow-verdict V --shadow-refusal true|false --schema S [--candidate-model M]` prints the `trial` object
as JSON; exit 0 always for a classifiable input, exit 2 for unreadable arguments
(loud failure, Principle VIII).
