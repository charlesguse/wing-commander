# Phase 1 Data Model: Run-Stamped Cost Attribution

No application database. Every entity below is either the shape of a JSON
document/string already flowing through the pipeline (a metrics record, a
posted comment, a collector signal), widened by this feature, or a new,
small entity this feature introduces (the run stamp, the attribution
partition). This is spec.md's Key Entities section made concrete against
research.md's decisions.

## Metrics record key (widened)

The identity of one metrics record, and — after this feature — of the run
stamp too (research.md R1). Composed once at emission time inside
`wing-commander-metrics-summary/action.yml`; carried through, never
recomputed except for its `job_key`→`job_id` segment, at persist time.

```text
<workflow_run_id>:<run_attempt>:<job_key-or-job_id>:<step_index>
```

- `workflow_run_id`: `github.run_id`, string.
- `run_attempt` (**new field**): `github.run_attempt`, string. Constant
  across every record emitted within one workflow run attempt; differs
  between two attempts of the same run.
- `job_key`: `github.job` at emission; replaced by the numeric `job_id`
  the jobs API resolves at persist time, when that resolution is
  unambiguous (unchanged rule — an ambiguous or absent match keeps the
  emission-time `job_key` form, per the existing comment at
  `wing-commander-metrics-persist/action.yml`).
- `step_index`: the `step-index` composite input, default `0`,
  distinguishing repeated invocations within one job.

**Run-identity portion**: `workflow_run_id:run_attempt` — the prefix the
cost-report collector matches a stamp against (FR-002). Order matters:
this is exactly the first two colon-delimited fields, so a collector can
split on `:` and take the first two segments without needing to know
anything about `job_key`'s own content.

**Shape regex** (new, Gate 39 — research.md R9):
`^[0-9]+:[0-9]+:[^:]+:[0-9]+$`

**Record `run` object** (schema-version-1, widened):

```json
{
  "workflow_run_id": "18234567890",
  "run_attempt": "1",
  "job_key": "clarify",
  "job_id": null,
  "step_index": 0,
  "record_key": "18234567890:1:clarify:0"
}
```

## Run stamp

New entity. A machine-readable, human-invisible statement of which run
posted a cost-bearing comment, carrying the metrics record key verbatim —
nothing more (spec.md Key Entities: "not a superset of the record
identity").

```text
<!-- wing-commander-cost-stamp:18234567890:1:clarify:0 -->
```

- **Single home**: computed by one unconditional, first step
  (`id: run-stamp`) inside `wing-commander-metrics-summary/action.yml`
  (research.md R2), from the same four ambient values `RECORD_KEY` is
  built from — no new lookup.
- **Two carriers**: (a) appended as the trailing term of the `cost-line`
  output's own text (the normal and internally-degraded paths, zero
  call-site changes needed); (b) exposed standalone as the composite's
  new `stamp` output, consumed by exactly one more line at each of the 12
  call sites' degraded literal fallback (research.md R3).
- **Parse regex** (collector side):
  `<!-- wing-commander-cost-stamp:([^:]+):([^:]+):([^:]+):([^:]+) -->` — a
  non-match (truncated, extra segments, non-numeric run id/attempt) is not
  an error; it degrades the comment to "unstamped" (research.md R7).
- **Invisibility**: an HTML comment, identical rendering behavior to the
  existing rollup marker (`wing-commander-metrics-persist`'s
  `<!-- wing-commander-metrics-rollup:begin -->`) in every surface these
  comments render in — issue comments, PR comments, step summaries
  (FR-004, SC-004).
- **Cardinality**: zero or more per comment (a comment either carries
  exactly one stamp or none — nothing produces two); zero or more per run
  (a stage that posts more than one cost-bearing comment, e.g. a
  questionnaire and then a PR link, produces one stamp per comment, each
  sharing the same run-identity portion but potentially differing
  `job_key`/`step_index`, per spec.md's edge case).

## Attribution partition (collector-side, per inspected run)

Not a persisted entity — the collector's working classification of the
lifecycle issue's comments for one inspection, computed fresh every run
(research.md R4).

| Set | Membership | Window-bounded? |
|---|---|---|
| `authored` | Comment's `userLogin` is one of the pipeline's own identities (unchanged author filter, FR-007) | n/a |
| `stamped_own` | `authored`, stamp parses, stamp's run-identity portion equals the inspected run's (subject to R6's attempt-unresolvable demotion) | No — never bounded by `since`/`until` (FR-006, and the "posted after `updatedAt`" edge case) |
| `stamped_foreign` | `authored`, stamp parses, stamp's run-identity portion names a *different* run | Excluded unconditionally (FR-006) — never enters `own` regardless of window |
| `unstamped` | `authored`, no stamp or an unparseable stamp (R7), OR a same-run-id stamp whose attempt could not be confirmed (R6) | Yes — eligible only if `createdAt` falls in `[since, until]` (FR-008) |
| `own` | `stamped_own ∪ (unstamped ∩ window)` | — |

The existing "first cost line wins, ordered by creation time" rule applies
to `own` unchanged. `comment_found` (the existing distinction between "no
comment of the run's own was found" and "a comment was found but it
carried no parseable cost figure") is computed over `own` exactly as
today.

## Cost-line claim signal (widened)

Spec 046's `cost-report` source, `cost-line-claim` signal kind
(`ident: {run, stage, claim-type}`, unchanged — research.md R8 keeps this
signal's identity untouched). Facts gain one new key.

```json
{"source": "cost-report", "class-hint": "cost-line-missing",
 "facts": {"stage": "plan", "run": "<workflow_run_id>",
           "cost-available": true, "lifecycle-comment-found": false,
           "attribution": "window"}}
```

```json
{"source": "cost-report", "class-hint": "cost-line-malformed",
 "facts": {"stage": "implement", "run": "<workflow_run_id>",
           "observed-text": "Cost: $COST_LINE · 40 turns",
           "expected-pattern": "currency amount, 2dp if >= $1 else 4dp",
           "attribution": "stamp"}}
```

- `attribution`: `"stamp"` when the comment(s) the verdict was decided
  from (or, for `cost-line-missing`, the fact that *no* comment of the
  run's own could be found) rest on `stamped_own` membership;
  `"window"` when they rest on the `unstamped ∩ window` fallback,
  including R6's attempt-unresolvable demotion case (FR-010, SC-007).
  `diagnose`'s existing `stage`/`expected`/`actual` `normalizedFacts`
  mapping for this class folds `attribution` into the `actual` value's
  free text (e.g. `"no cost line found for this run (window-attributed)"`)
  — no `normalizedFacts` schema widening (constitution IX does not apply:
  this is a descriptive fact, not a new judgment).

## Gate fixtures (checked-in test data, FR-012/SC-005)

Extending `verify-gate-19.py`'s `COST_SCENARIOS` and
`verify-cost-report-collector.sh`'s fixtures (research.md R9); no new
fixture directory needed, following the existing convention (inline
dict/JSON fixtures in both files today).

| Fixture | Asserts |
|---|---|
| Two overlapping runs, only run A posts a stamped cost line | Run A: no signal. Run B: `cost-line-missing`, `attribution: window` (no stamp of its own to find) |
| Two overlapping runs, both post stamped cost lines | Neither produces a signal; each reads its own amount, not the other's |
| A window containing a comment stamped by a different run plus an unstamped well-formed one | The foreign-stamped comment is excluded; the unstamped one is still accepted — no `cost-line-missing` |
| Several stamps from one run (differing job/step, same run-identity) inside one window | All treated as this run's own; first-by-creation-time rule unaffected |
| Two attempts of one workflow run, only the second posts | First attempt: `cost-line-missing`. Second: no signal. Verdicts independent |
| Inspected run's attempt number unresolvable, window also present | Same-run-id stamped comments demoted to `unstamped`; window decides; `attribution: window` even though a stamp was present (R6) |
| A malformed/truncated stamp | Degrades to unstamped; window decides; no collector error |
| A stamp inside a comment from a non-pipeline author | Ignored — author filter unchanged (FR-007) |
| Replay of #369/#370 (two clarify runs, windows overlapping, 8s apart) | Correct, independent verdict for each (SC-002) |
| Mutation: stamp preference removed | Suite fails (reproduces the reported defect) |
| Mutation: stamp preference inverted (prefers foreign stamp) | Suite fails |
| Mutation: attempt number dropped from the matched run-identity portion | Suite fails (reproduces the re-run defect, FR-002) |
| A workflow file outside the canonical action reconstructing the stamp marker literally | `case_run_stamp_has_exactly_one_home` fails |
| A workflow file consuming `steps.*.outputs.stamp` via `$RUN_STAMP` (the real 12 call sites) | Same gate passes |
| A `record_key` missing its attempt segment, fed to the schema gate | Gate 39's new shape regex fails it |
