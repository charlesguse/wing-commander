# Phase 1 Data Model: Per-Run Agent Metrics (Tier 1)

This feature has no application data model — everything below is ephemeral,
job-scoped CI data: a JSON file already produced by `claude-code-action` in
the runner's temp directory, and a Markdown block appended to
`$GITHUB_STEP_SUMMARY`. Nothing here is persisted beyond the workflow run
that produces it (that persistence is tiers 2/3, out of scope — FR-012).
The entities below are the ones named in `spec.md`'s Key Entities section,
expressed as their concrete shape for tier 1.

## Agent run (one per `claude-code-action` step invocation)

Not a file — the unit of work one metrics step reports on. A single job
may contain more than one (research.md D3/D4).

| Field | Source | Used for |
|---|---|---|
| Stage/step identity | The workflow step's own name/position (e.g. "cycle", "retry", "haiku progress comment" in `speckit-5-implement.yml`) | Disambiguating which invocation a summary block belongs to when a job has more than one (FR-008) |
| Configured model | Literal `--model` value already in that step's `claude_args` | Passed to the composite action as an input; not re-derived from the transcript |
| Configured turn budget | Literal `--max-turns` value already in that step's `claude_args`, passed as the `max-turns` input (research.md D5) | Denominator for the used/budgeted ratio; omitted entirely when the call site omits the input (FR-005) |

## Execution transcript (`claude-execution-output.json`, read-only)

The file every agent-invoking step already produces at
`${{ runner.temp }}/claude-execution-output.json` (unchanged by this
feature — FR-011 forbids altering how it's produced). Shape: a JSON array
of transcript entries, each with a `.type` field; the last entry with
`.type == "result"` is the run's final summary record and is the only
entry this feature reads.

| Field on the final `result` record | Status | Used for |
|---|---|---|
| `.result` | Confirmed (already parsed by `speckit-5-implement.yml`'s "Extract agent final message" step) | Not surfaced by this feature directly, but confirms which record is "the" result record |
| `.num_turns` | Confirmed present, but **superseded 2026-08-09** — see the amendment below | No longer the turns-used figure; retained only as a labelled fallback |
| `.subtype` | Confirmed | Detecting `error_max_turns` (budget exhausted) |
| `.duration_ms` | Assumed from spec.md's worked example | Duration |
| `.total_cost_usd` | Assumed from spec.md's worked example | Cost |
| Token usage (exact key TBD — best-effort `usage`-shaped object) | Assumed, defensively extracted | Token counts |
| Per-model breakdown (exact key TBD) | Assumed, defensively extracted | Optional per-model detail line |
| Model identity | Not assumed to be reliably on the transcript; supplied by the calling step instead (see Agent run above) | Avoids depending on an unconfirmed transcript field for something the workflow already knows literally |

A missing file, empty file, or file that fails to parse as JSON, or that
parses but has no `.type == "result"` entry, all resolve to the same
outcome: **metrics unavailable** (FR-009) — never a step failure.

## Run metrics (computed, ephemeral — exists only for the duration of the step)

| Field | Computed as | Renders as |
|---|---|---|
| `model` | From the Agent run's configured model (not the transcript) | Literal string |
| `turns_used` | Count of distinct `.message.id` over `.type == "assistant"` records with `parent_tool_use_id == null`; falls back to `.num_turns` (labelled, ratio suppressed) when that count is unavailable | `N` or `N (reported, not comparable to budget)` or `unavailable` |
| `subagent_turns` | The same count over records WITH a `parent_tool_use_id` | A separate line when non-zero, never part of the ratio |
| `turn_budget` | The `max-turns` input, or absent if the call site omitted it | `N` or omitted entirely from the ratio |
| `turns_ratio` | `turns_used / turn_budget`, only when both are known | `"N / M"` |
| `turn_warning` | `turns_ratio >= warn-fraction` (default 0.8, research.md D7), only when `turns_ratio` exists | A visible flag line, or nothing |
| `duration_ms` | `.duration_ms`, or "unavailable" | Formatted duration or `unavailable` |
| `tokens` | Best-effort read of the transcript's token-usage object, or "unavailable" | Formatted counts or `unavailable` |
| `cost_usd` | `.total_cost_usd`, or "unavailable" | Formatted `$` amount or `unavailable` |
| `per_model_breakdown` | Best-effort, optional — only rendered when present | Extra line(s), omitted entirely when absent |
| `availability` | `ok` (transcript parsed, result record found) or `unavailable` (any failure mode above) | Determines whether the whole block renders normally or as the FR-009 fallback message |

**Outcome resolution**:

```
transcript present, parses, result record found       → render full summary,
                                                          each field independently
                                                          "unavailable" if its own
                                                          value couldn't be read
transcript missing / empty / unparseable / no result
  record                                               → render "metrics unavailable
                                                          for this run" only —
                                                          step still succeeds (FR-009)
turn_budget input omitted                              → omit ratio + warning,
                                                          still render turns_used
turns_ratio >= warn-fraction                           → visible warning flag
turns_ratio <  warn-fraction, or ratio unavailable      → no warning flag
```

## Metrics summary block (the only durable-within-the-run output — `$GITHUB_STEP_SUMMARY`)

Not a separate file; a Markdown fragment appended to the step's own run
summary (research.md D8). One block per agent invocation, in invocation
order, each self-contained so a job with three invocations
(`speckit-5-implement.yml`) shows three distinct blocks rather than one
merged/overwritten block. Exact rendering format is `contracts/step-summary-format.md`.

## Amendment (2026-08-09): `.num_turns` is not the budget's counter

The table above recorded `.num_turns` as "turns used" on the strength of
spec.md's worked example. That was wrong in a way the worked example could
not reveal: `--max-turns` caps **distinct main-loop assistant API responses**
(`parent_tool_use_id == null`, deduped by `.message.id`), while `.num_turns`
is a larger total. Against this repository's own history the two diverge by
1.0x-2.3x, always upward.

The consequence was a rendered ratio that was wrong in the alarming
direction — "198 / 100 turns (198%)" with a budget warning, for an implement
cycle that used 87 of its 100 and was never at risk — while every genuinely
exhausted run stopped at exactly 100 main-loop turns (13 of 13). Nineteen of
47 implement runs carried a warning; 13 had actually exhausted the budget.

Two further properties of the real counter, both load-bearing:

- One API response can stream as several assistant records sharing a
  `.message.id`. Counting records rather than ids inflates by ~1.6x.
- Subagent (Task tool) responses are inlined into the same transcript and do
  **not** spend the parent's budget. A 2026-07-24 retry ran 180 distinct
  assistant responses under a 100 cap without tripping it; 86 were subagents'.
  They are reported on their own line, never folded into the ratio.

`.github/scripts/verify-metrics-turn-accounting.py` (lint-workflows gate 11)
executes the shipped action against fixtures for each of these and mutates
the script to prove the suite can fail.
