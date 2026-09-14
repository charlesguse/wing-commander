# Phase 1 Data Model: Rate-limited agent verdict

This feature has no application database — every "entity" below is
either a computed shape passed between GitHub Actions steps as
inputs/outputs, transcript data read a specific new way, or the body of
a GitHub issue used as a durable record. This is `spec.md`'s Key
Entities section made concrete against the actual composite/gate
contracts research.md designs.

## Rate-limit event (transcript record, read-only)

A record already written by the runtime into the execution transcript
when a model call is rejected for usage-window exhaustion (spec.md Key
Entities). Read by `wing-commander-agent-verdict`; never written by
anything in this repository.

| Field | Type | Notes |
|---|---|---|
| `type` | string, literal `"rate_limit_event"` | The only field this feature's detection treats as required (research.md R1). |
| `status` | string, e.g. `"rejected"` | Tolerated absent — a bare `rate_limit_event` with no `status` still counts as evidence (research.md R1). |
| `rateLimitType` | string, e.g. `"five_hour"` | Reported in `reason` prose only; never gates classification (spec.md Assumptions). |
| `resetsAt` | string (ISO-8601) or absent | Surfaced verbatim as the `rate-limit-reset` output (research.md R2) when present; `"unknown"` when absent or unparseable. |

## Terminal result record (transcript record, read-only, extended reading)

The same last `.type=="result"` record `wing-commander-agent-verdict`
already isolates (`result_json`) — no new extraction, only new fields
read from it.

| Field | Type | Notes |
|---|---|---|
| `subtype` | string | Already read. `"error_max_turns"` → `exhausted` (unchanged, checked first); anything else non-`"success"` combined with a rate-limit signal (below) → `rate-limited`. |
| `is_error` | `"true"`/`"false"` (string) | Already read. Must be `"true"` (or `subtype != "success"`) for `rate-limited` to apply — a recovered call stays `healthy` (spec.md edge case). |
| `terminal_reason` | string, e.g. `"api_error"` | NEW read. Corroborating signal when present (research.md R1); not required. |
| `api_error_status` | number or numeric string, e.g. `429` | NEW read. Corroborating signal when present; not required. |

## Verdict (composite output, extended)

Computed once per agent step by `wing-commander-agent-verdict`, consumed
by every downstream step at that call site. Gains one value and one new
output field.

| Field | Type | Values / Shape | Notes |
|---|---|---|---|
| `verdict` | enum (action output, string) | `healthy` \| `exhausted` \| `rate-limited` \| `failed` \| `unclassifiable` | NEW value inserted between `exhausted` and `failed` in the classification order (checked after `error_max_turns`, before the generic `is_error`/bad-`subtype` fallthrough — research.md R1). Only `healthy` means "continue as success" (unchanged). |
| `reason` | string (action output) | Gains new text for the rate-limited case, e.g. `"usage window (five_hour) exhausted, resets at 2026-09-14T18:00:00Z"` or `"...resets at unknown"` | Existing four cases' text unchanged. |
| `rate-limit-reset` | string (action output, NEW) | ISO-8601 timestamp, or the literal `"unknown"` | Empty string for every verdict other than `rate-limited` (never fabricated for a non-rate-limited run). This is the field every programmatic caller reads (research.md R2) — `reason` is prose-only. |
| `counted-turns` / `reported-turns` / `over-budget` / `subagent-turns` | unchanged | unchanged | Independent of the verdict branch, per the existing "a counting failure never demotes a verdict" contract; unaffected by this feature. |

State transitions: none — computed fresh per invocation, same as every
existing verdict value.

## Diagnose outcome (watchdog-internal, extended)

The `steps.diagnose-outcome.outputs.outcome` value the watchdog's "Read
back diagnose outcome" step already produces, consumed by the two
existing report steps and (now) one new one.

| Value | Existing/New | Condition | Consumer |
|---|---|---|---|
| `diagnose-failed` | existing | `steps.diagnose.outcome != 'success'` OR the agent's own terminal result isn't a real success, **and** `steps.diagnose-verdict.outputs.verdict != 'rate-limited'` (narrowed — see below) | "Report 'diagnose failed' to lifecycle issue" |
| `rate-limited` | NEW | `steps.diagnose-verdict.outputs.verdict == 'rate-limited'` (checked before the `diagnose-failed` test, since a rate-limited rejection also fails the pre-existing `agent_ok` test and must not fall into the crash branch) | NEW "Report 'rate-limited' to lifecycle issue" step; NEW "Ensure usage-limit issue" step |
| `passed-inspection` | existing | `count == 0` | "Report 'passed inspection' to lifecycle issue" |
| `findings` | existing | `count > 0` | triage/act matrix |

The three outcome branches remain mutually exclusive — a rate-limited
run's "Report 'diagnose failed'..." step is skipped by construction,
which is also what lets `verify-watchdog-run.sh`'s existing check 3
(reading that exact step's conclusion) stay unmodified (research.md R4).

## Uninspected-run record (the `usage-limit` issue)

The durable statement FR-012/FR-013 require: one GitHub issue, labelled
`usage-limit`, that a rate-limited watchdog run appends to rather than
duplicates.

| Field | Source | Notes |
|---|---|---|
| Label | literal `usage-limit` | Created on first use via `gh label create usage-limit --force` (same bootstrap pattern as `pipeline-defect`); never carries `pipeline-defect` (FR-012). |
| Dedup key | "any currently OPEN issue labelled `usage-limit`" | No fingerprint (research.md R5) — deliberately looser than the `pipeline-defect` dedup's marker-comment match. |
| Title (on create) | fixed, e.g. `"watchdog: usage window exhausted"` | Stable across creates so a maintainer recognizes it without opening it. |
| Body (per run, appended) | one bullet: run URL/id, `steps.diagnose-verdict.outputs.rate-limit-reset`, the fact that the run went uninspected | Never contains `pipeline-defect` language; never the crash/failure wording FR-008 forbids. |
| Closure | manual (spec.md Assumptions) | No automatic closure in scope; a maintainer closes it, after which the next exhausted window opens a fresh issue (R5). |

## Stage-8b verification suppression (verifier-internal, extended)

New evidence variable inside `verify-watchdog-run.sh`, plus two narrowed
existing reasons.

| Field | Type | Source | Notes |
|---|---|---|---|
| `rate_limited` | boolean (shell) | `step diagnose 'Report "rate-limited" to lifecycle issue'` conclusion is non-empty and not `skipped` | Same evidence-reading pattern the script already uses for `diagnose-failed`/`could-not-inspect` (research.md R4). |
| Check 7 reason ("no successful terminal result record") | suppressed when `rate_limited` | unchanged text/condition otherwise | FR-010. |
| Check 2's floor-breach reason ("under the Ns floor... too fast to have done real work") | suppressed when `rate_limited` | the ceiling-breach (stall) arm is never suppressed | FR-010; FR-011/US1 AS4 keeps the ceiling arm live. |
| Every other check (1, the ceiling arm of 2, 3, 4, 5, 6, 8) | unchanged | unchanged | FR-011 — an independent defect alongside a rate-limited run still fails the job. |

## Exemption registry (FR-015a/b)

Not a data file — a small Python constant inside the new gate script
(research.md R6), listed here as the shape `tasks.md` will populate:

| Field | Type | Notes |
|---|---|---|
| `EXEMPT_SITES` | list of `(workflow file, step name)` pairs | Seeded with the two new watchdog steps this feature adds. Grows only when a future feature adds a new sanctioned rate-limited-aware issue/comment writer — itself enforced by the same gate failing loud if it doesn't. |

Every other verdict-gated `gh issue create`/`gh issue comment`/`gh pr
comment` step discovered by the gate's YAML walk must instead exclude
`rate-limited` in its own `if:` condition (an allow-list or
not-equals-chain) — there is no third registry for those; the condition
itself is the evidence, read fresh from the workflow file every gate
run (never trusted to a separate hand-kept list, per research.md R6's
whole rationale).
