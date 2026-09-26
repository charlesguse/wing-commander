# Phase 1 Data Model: Clarify's Turn Budget Reflects the Work Clarify Actually Does

No application database — this feature edits a workflow's declared
default, a docs table, and adds one deterministic gate. Every "entity"
below is either a value already flowing through existing mechanism (spec
037's ceiling, spec 046's turn-budget-trend signal, spec 009/043's metrics
record) or the new gate's own input/output shape.

## Declared turn budget (clarify)

| Field | Before | After |
|---|---|---|
| `clarify.yml` `workflow_call.inputs.max-turns.default` | `40` | `65` |
| Accepted range (recorded beside the value, FR-001) | none | `39-61` counted turns, the three recorded runs (issue #587) |
| Derived ceiling (`wing-commander-turn-ceiling`, unchanged ×2.5 multiplier) | `ceil(40 * 2.5) = 100` | `ceil(65 * 2.5) = 163` |

This is the single value FR-008/FR-012 require: `clarify.yml` passes
`inputs.max-turns` unchanged to `wing-commander-turn-ceiling` (ceiling),
`wing-commander-metrics-summary` (reported metrics + 80%-warning +
over-budget summary line), and (via the metrics record it writes) the
`wing-commander-agent-verdict`-derived over-budget callout on the
lifecycle issue. No second value is introduced; the ceiling multiplier
(`2.5`) is untouched (FR-003, Out of Scope).

## Recorded run history (read-only, already persisted — spec 043/046)

The evidence R1's arithmetic reads, unchanged by this feature:

```json
{"run": "35665831869", "counted-turns": 39, "intended-budget": 40}
{"run": "35554001500", "counted-turns": 61, "intended-budget": 40}
{"run": "35422301482", "counted-turns": 45, "intended-budget": 40}
```

Sourced from the `metrics` branch's `records.jsonl`
(`.turns.counted`/`.turns.intended_budget`/`.turns.enforced_ceiling` per
record, `watchdog.yml`'s `collect-turn-budget` step) filtered to
`stage == "clarify"`. This feature reads it once, at plan time, to derive
the R1 decision; it does not change how the history is collected, stored,
windowed, or replayed (FR-015, Out of Scope).

## Turn-budget trend signal (unchanged mechanism, re-evaluated inputs)

Per spec 046's own data-model (`specs/046-watchdog-supervision-collectors/data-model.md`),
reproduced here only to show the before/after of feeding it clarify's new
default:

| | Before (budget 40, ceiling 100) | After (budget 65, ceiling 163) |
|---|---|---|
| `max-consumed-ceiling-fraction` over {39,45,61} | `61/100 = 0.61` | `61/163 = 0.374` |
| `consecutive-at-or-over-budget` | `0` | `0` |
| Band (`climb_fraction` threshold `0.6`) | `elevated` | none |

Confirms SC-001/SC-007's independent test without any change to the
collector's own arithmetic, signal identity, or suppression (FR-015).

## Published-stage turn-budget doc table (new gate's subject)

The full set of `{stage, workflow default, docs/adoption.md default}`
triples the new gate (R5) walks — every published stage whose
`workflow_call.inputs` declares a `max-turns` default, and its matching
`docs/adoption.md` `### <stage>` section:

| Stage | Workflow file | Default (before this feature) | `docs/adoption.md` section |
|---|---|---|---|
| intake | `intake.yml` | `50` | `### intake` (line 1122) |
| clarify | `clarify.yml` | `40` -> **`65`** | `### clarify` (line 1161) -> updated |
| plan | `plan.yml` | `110` | `### plan` (line 1178) |
| tasks | `tasks.yml` | `60` | `### tasks` (line 1215) |
| implement | `implement.yml` | `180` | `### implement` (line 1235) |
| finalize | `finalize.yml` | `20` | `### finalize` (line 1254) |
| cleanup | `cleanup.yml` | `20` | `### cleanup` (line 1269) |
| rebase | `rebase.yml` | `50` | `### rebase` (line 1313) |
| pr-conversation | `pr-conversation.yml` | `40` | `### pr-conversation` (line 1329) |

Only the `clarify` row changes (FR-002/FR-009/SC-005); the gate asserts
equality for all nine, so it fails loudly if a future PR moves a
workflow's default without moving its docs row (or vice versa) — the
mechanism FR-017/FR-018 ask for, not just clarify's own edit.

## New gate: `verify-stage-turn-budget-docs.py`

| | |
|---|---|
| Input | `.github/workflows/<stage>.yml` (parsed for `workflow_call.inputs.max-turns.default`), `docs/adoption.md` (parsed for each `### <stage>` section's `Inputs` row) |
| Output | Exit 0 (all nine stages' workflow default and docs default agree) or exit 1 naming every `{stage, workflow-default, docs-default}` triple that disagrees |
| Failure mode when subject unreachable | Loud failure, not a silent pass — zero stage files found, or a stage file with no `max-turns` default paired with a docs section that states one (or the reverse), is reported explicitly rather than skipped (constitution VIII) |
| Fixtures (constitution VIII: one per failure branch, checked in) | (a) all nine agree — pass; (b) one workflow default changed, docs untouched — fail, names the stage; (c) one docs default changed, workflow untouched — fail, names the stage; (d) a stage's docs section is missing its `max-turns` cell entirely while the workflow declares one — fail, names the stage, does not silently skip it |
| Registration | `lint-workflows.yml` gate registry (number assigned at implementation time, following the existing highest-numbered gate — see spec 058's identical precedent for "final count and numbering assigned at implementation time") |
| Local invocation | Automatically included in `python .github/scripts/run-local-gates.py`'s derived set (CLAUDE.md: gates are derived from what `lint-workflows.yml` invokes) — no separate wiring needed once registered there |

## Written procedure (FR-013/FR-014) — new `docs/architecture.md` subsection

Not a data entity but a documented procedure; recorded here because
tasks.md needs its exact shape to author it:

| Step | Content |
|---|---|
| Evidence to read | A `turn-budget-trend` signal's `facts.history` — the window's `{run, counted-turns, intended-budget}` triples the collector already emits |
| Arithmetic | New budget = smallest multiple of 5 strictly greater than the window's max counted-turns; accepted range = window's min-max, stated beside the new number |
| Cost consequence | State `ceil(new_budget * 2.5)` explicitly in the same change (the resulting ceiling) |
| When to accept instead | The window's max is a single diagnosed-contaminated run (e.g. denied-tool-call turn inflation, spec 037), or the band is `critical` with a rising `consecutive-at-or-over-budget` that a bigger number would only relabel — close the `pipeline-defect` as accepted (spec 046's suppression-by-closed-fingerprint mechanism), do not move the number |
| Worked example | This feature's own clarify numbers: `{39, 45, 61}` -> budget `65`, ceiling `163` — applying the stated arithmetic reproduces the landed values (FR-014) |
