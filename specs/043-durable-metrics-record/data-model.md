# Phase 1 Data Model: Durable Agent Run Metrics

No application database. Every entity below is either the shape of a
JSON document passed between GitHub Actions steps/artifacts/a git branch,
or a piece of already-existing transcript data now read once and shared.
This is spec.md's Key Entities section made concrete against the
composite/workflow contracts research.md designs.

## Agent run metrics record (schema version 1)

Produced once per `wing-commander-metrics-summary` invocation (R1/R2),
written to `record-path`, uploaded as the `metrics-record[-<label>]`
artifact (R3), and — once persisted — one line of `records.jsonl` on the
`metrics` branch (R5). Field names are the contract surface (FR-005);
nothing here is renamed or removed within schema version 1 (FR-025a).

Unavailable-value convention (FR-007): every field that can legitimately
be unknown is paired with a sibling `*_available: boolean`. When
`false`, the value field is `null` — never a fabricated `0`, `""`, or
omission. A record's own top-level `record_available` is `false` only
when the transcript itself was missing/empty/unparseable (T004); in that
case every nested `*_available` is also `false`, but the record still
exists and still carries `schema_version`, `run`, and `stage`/`spec`
(whatever identity information the job environment itself could supply,
independent of the transcript).

| Field | Type | Notes |
|---|---|---|
| `schema_version` | integer | `1` for every record this feature writes (FR-006). |
| `run.workflow_run_id` | string | From `github.run_id` at the call site. |
| `run.job_id` | string | From `github.job` resolved to the numeric job id via the same `gh api .../jobs` lookup the collector performs (the call site itself only knows `github.job`, the *job key*, not the numeric id — the collector fills this in in the persisted copy; the artifact-time record carries `github.job` as `run.job_key` instead, see below). |
| `run.job_key` | string | `github.job` — the YAML job key, known at emission time, always available. |
| `run.step_index` | integer | Ordinal position of this invocation within its job (0, 1, 2 — R6). Always available; a literal per call site. |
| `run.record_key` | string | `"<workflow_run_id>:<job_key>:<step_index>"` at emission time; the collector rewrites this to use the numeric `job_id` once resolved (R6) — both forms are unique per agent invocation, the rewrite exists only to make the persisted key stable against `job_key` reuse across workflow files. |
| `stage` | string or null | The stage name (e.g. `"plan"`, `"implement"`) — a literal each call site passes in, not inferred. `stage_available: boolean`. |
| `run_label` | string or null | The existing optional display label (e.g. `"retry"`, `"progress comment"`) when the call site passes one; `null` otherwise (not an availability failure — most sites pass none). |
| `spec.spec_dir` | string or null | `specs/NNN-slug`, when the job has spec identity (from the same source each stage already uses — its own `spec-meta.json`/context resolution). |
| `spec.issue` | integer or null | The lifecycle issue number, read alongside `spec_dir`. |
| `spec.identity_available` | boolean | `false` for a run with no attached specification (e.g. `auto-update-spec-kit.yml`'s sites) — spec.md's Edge Case "a stage that is not attached to a specification." |
| `model` | string or null | The literal model name the call site's `claude-code-action` step used. `model_available: boolean` (false only if the caller itself omitted the required `model` input, which the action's existing `required: true` on that input makes rare in practice). |
| `turns.counted` | integer or null | `main_turns` from `_shared/count-turns.sh` — the counted, budget-comparable total (FR-008). |
| `turns.reported` | integer or null | The transcript's own `.num_turns` — kept for diagnosis, per spec.md's Edge Case "the turn count the record carries is the counted one, not the reported one," never used for comparison against budget. |
| `turns.intended_budget` | integer or null | The caller's `max-turns` input value (the tunable budget). |
| `turns.enforced_ceiling` | integer or null | The caller's `ceiling` input value (`wing-commander-turn-ceiling`'s output — the literal `--max-turns` the runtime enforced). |
| `turns.available` | boolean | `false` when counting itself failed (unreadable transcript shape). |
| `tokens.input` / `.output` / `.cache_read` / `.cache_creation` | integer or null | From `.usage.*`, matching the fields the rendered summary already shows. |
| `tokens.available` | boolean | `false` when `.usage` was absent/unparseable. |
| `cost_usd` | number or null | From `.total_cost_usd`. |
| `cost_available` | boolean | | 
| `duration_ms` | integer or null | From `.duration_ms`. |
| `duration_available` | boolean | |
| `outcome` | string | One of `healthy` \| `exhausted` \| `failed` \| `unclassifiable` \| `unavailable` — `unavailable` only when the transcript itself couldn't be read; the other four match the existing verdict vocabulary spec 037 already established, computed the same way. |
| `per_model` | array of objects | One entry per model actually used (FR-005a) — `{model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_usd}`, from `.modelUsage`. A single-model run still carries one entry (not zero). The only nested array field in the record; every other field above is flat. |
| `per_model_available` | boolean | `false` when `.modelUsage` was absent/unparseable — the flat `tokens.*`/`cost_usd` fields may still be available independently (they come from `.usage`/`.total_cost_usd`, not `.modelUsage`). |
| `emitted_at` | string (ISO-8601 UTC) | Wall-clock time the record was written, from the emitting step's own clock — informational only, never used as an ordering or dedup key (that's `record_key`). |

**Invariant** (checked by gate R12.2): `sum(per_model[].input_tokens) ==
tokens.input` and the cost equivalent, whenever both `tokens.available`
and `per_model_available` are true (spec.md acceptance scenario:
"its entries sum to the record's own token and cost totals").

**State transitions**: none. A record is written once, uploaded once,
appended to the store at most once (R6's `record_key` is what makes a
second persistence pass a no-op rather than a duplicate write), and
never mutated in place — the store is append-only (FR-023).

## Durable store

One orphan git branch (`metrics` by default, R5/R8), one file
(`records.jsonl` by default), UTF-8, one JSON object per line, no
trailing content between lines other than `\n`, sorted by append order
(not re-sorted — a reader wanting spec-scoped or time-scoped views
filters/sorts client-side). Every record on it has already passed
schema validation (R12.2) and the multi-model sum invariant above;
records that fail either are reported by the collector as not persisted
(FR-017) rather than written malformed.

A reader (the rollup step, or any future consumer) that meets a record
whose `schema_version` it does not recognize keeps the line as-is and
excludes it from any computation the reader performs — the FR-025(d)
"retain and skip" rule. This repository's own reader (the rollup) only
ever needs to understand `schema_version: 1` at this feature's landing.

## Destination configuration

Not part of the record — the wrapper's own inputs to the published
`metrics-persist.yml` workflow:

| Field | Type | Source | Notes |
|---|---|---|---|
| `destination-branch` | string, required | `vars.WING_COMMANDER_METRICS_BRANCH` (wrapper default `"metrics"`) | No default inside the published workflow itself (FR-013: the mechanism must not infer or default a destination) — the *wrapper* supplies the literal default, one layer up. |
| `destination-path` | string, required | `vars.WING_COMMANDER_METRICS_PATH` (wrapper default `"records.jsonl"`) | Same reasoning. |
| `run-id` | string, required | `workflow_run` event or `workflow_dispatch` input (R11) | The pipeline run being collected for. |

An adopting repository that never includes the wrapper (or includes it
but leaves both vars unset with no wrapper-side literal default of its
own) gets emission with zero persistence and zero writes to its
repository — the wrapper is the only place a destination is ever chosen,
and choosing none is a valid, fully-supported configuration (spec.md
Edge Case: "An adopter takes the published pieces but wants no
persistence at all").

## Rollup — per-run cost line

Not a stored entity — a Markdown fragment built in-band from one record
(R9), appended to the status comment the originating stage already
posts. Content: cost, counted turns (with budget when available), model
— e.g. `**Cost**: $0.42 · 38/60 turns · claude-sonnet-5`. Degrades to
naming which figures are unavailable rather than omitting the line
entirely, matching the record's own unavailable-marking convention.

## Rollup — cumulative summary (machine-owned region)

One region, inside one comment, on the spec's lifecycle issue,
identified by the marker pair
`<!-- wing-commander-metrics-rollup:begin -->` /
`<!-- wing-commander-metrics-rollup:end -->` (R10). Regenerated in full
on every update:

```text
<!-- wing-commander-metrics-rollup:begin -->
## Cumulative spend

**Total**: $N.NN across M agent runs (as of <UTC timestamp>)
<if any contributing record has an unavailable cost/token field:>
_Incomplete: N of M runs have unavailable metrics and are excluded from the total above._

| Stage | Runs | Cost |
|---|---|---|
| intake | 1 | $0.12 |
| plan | 2 | $0.51 |
...

<details><summary>Per-run history (M entries)</summary>

- `<record_key>` — plan · $0.31 · 42 turns · claude-sonnet-5 · 2026-08-25T14:03Z
...
</details>
<!-- wing-commander-metrics-rollup:end -->
```

The per-run history list is the region's only append-only sub-part —
each update parses the existing list back out, keeps every line whose
`record_key` is already present untouched, and appends one new line per
`record_key` this update introduces that wasn't already listed (FR-031b's
"exactly one rolling summary... no duplicate line" — duplication is
prevented by checking the structured `record_key` token in each line,
not by string-matching the rendered Markdown). The totals table and the
"Incomplete" notice are recomputed fresh every time from the full set of
history entries, never carried forward incrementally.

## Gate fixtures (not runtime entities, but checked-in test data)

Each new gate from research.md R12 needs at least one fixture record or
fixture git state — either inline in the gate's own source (the form the
implementation settled on for the gates whose fixtures are short
strings, after a review found on-disk copies that nothing read) or under
a `fixtures/` directory local to its own test harness (the form the
schema and no-writeback gates use, mirroring conventions elsewhere in
`.github/scripts/`):

| Fixture | Used by |
|---|---|
| A well-formed schema-version-1 record | Gate R12.2 (positive case) |
| A record missing a required field / wrong type | Gate R12.2 (negative case) |
| A record with `schema_version: 2` (unknown) | Gate R12.3 |
| A multi-model record whose `per_model` sums to its own totals | The invariant check above |
| A local bare git repo simulating a rejected push (two branch tips racing) | Gate R12.4 |
| A composite/workflow file under `.github/actions/**` reading `vars.*` or invoking `claude-code-action` | Gate R12.1 (negative case, proves the extended scan actually fails on the defect it exists to catch) |
| An `upload-artifact` step with no `retention-days` | Gate R12.5 (negative case) |
