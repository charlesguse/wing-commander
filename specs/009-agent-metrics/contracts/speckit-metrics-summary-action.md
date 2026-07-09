# Contract: `.github/actions/speckit-metrics-summary` (composite action)

This project has no library/API surface; its "interfaces" are GitHub
Actions composite-action inputs/outputs and the deterministic behavior
each call site can rely on. This document is the contract the
implementation (tasks phase, next stage) must satisfy for the new
composite action introduced by this feature.

## Inputs

| Input | Required | Default | Contract |
|---|---|---|---|
| `transcript-path` | No | `${{ runner.temp }}/claude-execution-output.json` | Path to the execution transcript to read for **this specific invocation only**. Callers with more than one agent step per job (research.md D3) must invoke this action once per agent step, immediately after it, before any later agent step in the same job can overwrite the file at this path. |
| `model` | Yes | — | The literal model name the caller's own `claude-code-action` step used (e.g. `claude-sonnet-5`). Never read from the transcript (data-model.md). |
| `max-turns` | No | *(absent)* | The literal `--max-turns` value the caller's own step configured. When omitted, the rendered summary reports turns used and omits the used/budgeted ratio and the turn-budget warning entirely (FR-005). |
| `warn-fraction` | No | `0.8` | Fraction of `max-turns` at/above which the run is flagged (FR-004). Only meaningful when `max-turns` is provided. |
| `run-label` | No | *(empty)* | Free-text label distinguishing this invocation within a job that has more than one (e.g. `cycle`, `retry`, `progress comment`) — rendered in the summary block's heading so FR-008 multi-invocation output is unambiguous. Empty is fine for single-invocation stages. |

## Outputs

None required. This action's only observable effect is appending to
`$GITHUB_STEP_SUMMARY`; it does not need to hand data back to the calling
workflow (tiers 2/3, which would consume structured output, are out of
scope — FR-012).

## Behavioral contract

1. **MUST NOT fail the step or the job** under any input condition —
   missing file, empty file, invalid JSON, JSON with no `.type == "result"`
   entry, or a result record missing individual fields. Every one of these
   resolves to rendering "metrics unavailable" (whole-block) or an
   individual field's "unavailable" (partial), never a non-zero exit
   (FR-009).
2. **MUST NOT execute, wait on, or otherwise interact with any agent** —
   pure `bash`/`jq` reading an already-produced file (FR-011, research.md
   D1). No `claude_code_oauth_token` input, no network calls.
3. **MUST render exactly one summary block per invocation** — calling this
   action twice in one job (once per agent step) must produce two
   independent, appended blocks in `$GITHUB_STEP_SUMMARY`, not one
   overwritten in place (FR-008).
4. **MUST express turns as used-against-budget when a budget is known**
   (FR-003), and **MUST NOT fabricate a budget** when `max-turns` is
   omitted (FR-005) — the ratio and warning line are absent entirely in
   that case, not rendered with a placeholder.
5. **MUST flag turns_ratio >= warn-fraction, and MUST NOT flag anything
   below it** (FR-004) — this is a strict boundary; the default is exactly
   `0.8`, matching spec.md's stated default.
6. **MUST degrade per-field, not all-or-nothing, when the result record is
   found but incomplete** (spec.md edge case) — e.g. cost present but token
   usage absent renders cost normally and marks tokens "unavailable," not
   the whole block as unavailable.
7. **Idempotent / side-effect-free beyond the step summary** — no writes to
   the transcript file, no writes to any other file the calling workflow
   might rely on later (e.g. it must not touch `spec-meta.json` or any git
   state).

## Non-goals (explicitly out of contract, per spec.md FR-012)

- No lifecycle-issue comment of any kind (tier 2).
- No durable/trend record of any kind — no new artifact upload, no write
  to a metrics branch or index (tier 3).
- No new configuration surface beyond the five inputs above — no repo
  variable, no label-driven behavior.
