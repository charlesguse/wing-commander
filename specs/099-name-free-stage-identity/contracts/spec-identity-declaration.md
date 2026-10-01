# Contract: Record Spec-Identity Declaration

**Owner (schema)**: `specs/043-durable-metrics-record/contracts/metrics-
record-schema.md` — this feature adds `spec.identity_is_own` there as an
additive schema-version-1 field per that document's rule 1. This file
records the requirement this feature places on that live contract; the
edit itself lands in the cited document, not a copy here.

**Owner (emission)**: `.github/actions/wing-commander-metrics-summary/
action.yml`.

**Sole consumer**: the slug-fallback step inside
`wing-commander-inspected-run-identity/action.yml` (`action.yml:207`
today; replaced by this feature).

## Field

| Path | Type | Required | Meaning |
|---|---|---|---|
| `spec.identity_is_own` | boolean | Optional (additive; see FR-008a) | `true` when the record's `spec.*` fields describe the emitting run's own advance; `false`/absent when they describe a spec the run merely reported on (borrowed) |

## Rule 1 — Absence means borrowed

A record with no `spec.identity_is_own` key (every record written before
this feature ships) MUST be read as `false`. This MUST NOT be reported
as a schema violation by `verify-metrics-record-schema.py` — the field is
additive, not newly required on old data.

## Rule 2 — Every new record declares explicitly

`wing-commander-metrics-summary` gains a required input,
`spec-identity-is-own` (`'true'`/`'false'`, no default), written verbatim
into `spec.identity_is_own`. Every call site added or already existing
across intake, clarify, plan, tasks, implement, finalize, watchdog,
cleanup, rebase, pr-conversation, board-loop, and lifecycle-review-gate
MUST pass it. The six single-spec stages (intake, clarify, plan, tasks,
implement, finalize) pass `'true'`; every other stage passes `'false'`.

## Rule 3 — This is the only consumer

No other collector, gate, or composite reads `spec.identity_is_own`. In
particular, the resolved-stage-identity contract
(`resolved-stage-identity.md`) does not consume it — Q2-A (deriving trust
from the resolved stage) was rejected in spec.md as circular.

## Verified by

- `specs/043-durable-metrics-record/contracts/metrics-record-schema.md`'s
  `## Shape` fence, kept in sync with `verify-metrics-record-schema.py`'s
  `REQUIRED_SPEC` dict by that gate's own `check_fields_match_contract()`.
- New fixtures under `.github/scripts/fixtures/metrics-record-schema/`:
  a record declaring `true`, a record declaring `false`, and a record
  predating the field (proving FR-008a's read).
- The FR-012 gate additionally scans every `wing-commander-metrics-
  summary` call site for a literal `spec-identity-is-own:` key (SC-008).
