# Phase 1 Data Model: A Closed Lifecycle Is Inert

This feature introduces no persisted data store — every "entity" below is
either a GitHub-native object this pipeline already reads (issue, run
evidence) or a small in-workflow shape (composite outputs, a corrected
report field) that exists only for the duration of one job. This document
records the shapes and the one state machine this feature adds.

## Lifecycle issue (existing GitHub entity, new authority signal read)

| Field | Source | Used by this feature as |
|---|---|---|
| `state` | `gh issue view <issue> --json state` (live re-fetch, never the calling event's cached payload — research.md R3) | The sole input to the trigger gate: `open` → proceed, `closed` → decline |
| `number` | Already a required input (`issue-number`) on every affected `workflow_call`, or derived from `spec-meta.json` for `tasks-approved` (research.md R3) | Identifies which issue's state to check and, on decline, which issue to post the FR-012 note to |

No other issue field (labels, comments, assignees) is read by the new gate
— the existing who/what gates already read labels and commenter identity
independently and are unchanged (spec.md Assumptions).

## Trigger gate (new concept, no new storage)

The set of conditions checked before a stage acts, now three-part instead
of two:

1. **Who** acted (maintainer/requester, never a bot) — existing, unchanged.
2. **What** the issue is (carries the pipeline's spec-identity/stage
   labels) — existing, unchanged.
3. **Whether it is open** — new (this feature). Implemented as the
   `wing-commander-lifecycle-gate` composite's `is-open` output
   (contracts/wing-commander-lifecycle-gate.md), consumed by every
   subsequent step's `if:` in the calling job.

All three must hold for a stage to act; any one failing is a decline. This
feature adds only the third — the first two are out of scope (spec.md
Assumptions: "The who/what gates stay as they are").

## `wing-commander-lifecycle-gate` composite outputs (new, ephemeral)

| Field | Type | Meaning |
|---|---|---|
| `state` | string (`open`/`closed`) | Raw value from `gh issue view --json state` |
| `is-open` | string (`"true"`/`"false"`) | `"true"` iff `state == "open"`; the value every gated step's `if:` reads |

Exists only within the run of the job that calls it — not written anywhere
persistent. See contracts/wing-commander-lifecycle-gate.md for the full
input/output contract.

## Closed-lifecycle decline note (new report shape, FR-012)

Emitted at most once per declined trigger event (i.e., once per
comment/label/PR-merge/dispatch that would otherwise have started a stage
against a closed lifecycle issue), via the existing `wing-commander-
callout` composite's `kind: info` template (unchanged rendering — plain,
unwrapped message, no `[!IMPORTANT]` box, no PR link, no timing):

| Field | Value |
|---|---|
| `summary` | `"This lifecycle issue is closed — no action was taken."` |
| `body` / `body-file` | Not set — the summary alone satisfies FR-012's "single brief, non-actionable note" |
| `kind` | `info` (never `action` — this is explicitly not an actionable callout) |

This is the **only** output permitted on the decline path (FR-003, FR-012).
No branch is checked out as the bot, no commit, no push, no PR edit, no
`action`-kind callout, no agent step runs.

## State transition (new — the gate's own decision, not a persisted entity)

```
issue currently OPEN  ──trigger event (comment/label/PR-merge/dispatch)──▶ gate: is-open=true
                                                                            └─▶ stage proceeds exactly as before this feature (FR-006)

issue currently CLOSED ──same trigger event──▶ gate: is-open=false
                                                └─▶ post ONE kind:info decline note (FR-012)
                                                └─▶ every remaining step skipped (FR-003)
                                                └─▶ no branch/commit/push/PR-edit/agent-run

issue REOPENED after being closed ──any later trigger event──▶ gate re-reads current state ──▶ is-open=true
                                                                └─▶ stage proceeds again (FR-005) — closing is not permanent retirement
```

The gate is stateless across invocations — it re-derives `is-open` from a
fresh API read every single time it runs (research.md R3), so the reopen
case (FR-005) and the "race at close time" edge case (spec.md Edge Cases)
both fall out of the same mechanism with no special-case code: there is
only ever "what does `gh issue view` say right now."

## Denied-tool finding (existing entity, `specs/015-pipeline-watchdog/data-model.md`, field corrected)

The collector's `facts` shape (`{"source":"execution-output","class-
hint":"denied-tool","facts":{tool, denials, turns}}`, defined in
`specs/015-pipeline-watchdog/data-model.md:28`) is unchanged in its outer
shape; only two things inside `facts` change (FR-008–FR-010):

| Field | Before | After |
|---|---|---|
| `turns` | Array of raw zero-based indexes into the interleaved SDK message array, mislabeled as turn numbers | Renamed `record-index`; same array shape, honest name — never presented as, or compared against, the run's own `num_turns` |
| `denials` | `length` of a `group_by(tool) | select(length > 1)` group — silently drops single-tool denials, count disconnected from true occurrences | True count of denial-shaped `tool_result` entries actually observed (no size-1 drop) |

A new implicit field — whether this count came from the terminal result
record or the log-scan fallback — is carried as a label on the finding
(`"source": "log-scan (fallback — not authoritative)"` vs. a future
`"source": "result-record"` once/if the SDK adds a `permission_denials`
field, per research.md R4). See
contracts/denied-tool-collector-delta.md for the exact `jq` delta.

## Terminal result record (existing entity, confirmed shape — no new field added by this feature)

Per research.md R4, this repository's own `wing-commander-metrics-summary`
composite already establishes the fields this record carries:
`num_turns`, `duration_ms`, `total_cost_usd`, `usage`, `modelUsage`,
`is_error`, `subtype`, `result`. This feature reads `num_turns` (only to
confirm a "turn" label would be impossible against it, in the collector's
non-authoritative labeling — it does not derive real turn numbers, per
FR-010's explicit non-goal) and does not add a `permission_denials` field,
since the SDK does not emit one today; FR-009's record-sourced branch is
implemented as forward-compatible but currently unreachable code.
