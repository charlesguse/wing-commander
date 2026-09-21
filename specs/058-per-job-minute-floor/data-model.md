# Phase 1 Data Model: The Per-Job Minute Floor

No application database. Every entity below is either the shape of a
GitHub Actions job-graph condition, a workflow input, or a small durable
file on the `metrics` branch. This is spec.md's Key Entities section made
concrete against research.md's designs.

## Image check outcome

One of three values, reported by GitHub for the
`verify-image-prerequisites` job of a given stage run:

| Outcome | Condition | Billed job? | Dependent jobs |
|---|---|---|---|
| `skipped` | `inputs.container-image == ''` | No (research.md R-A1) | Run, subject to their own other dependencies |
| `success` | image configured, pull + tool-probe succeeded | Yes | Run, subject to their own other dependencies |
| `failure` | image configured, pull/credential/tool-probe failed | Yes | Skipped |

## Dependent-job condition (per research.md R-A1)

Not a stored entity — the shape every job naming
`verify-image-prerequisites` in `needs:` carries after this feature,
keyed by whether it has other dependencies:

| Job shape | `needs:` | `if:` |
|---|---|---|
| Entry, no other deps | `verify-image-prerequisites` | `!cancelled() && needs.verify-image-prerequisites.result != 'failure'` |
| Entry, N other deps | `[verify-image-prerequisites, X1, ..., XN]` | `!cancelled() && needs.verify-image-prerequisites.result != 'failure' && needs.X1.result == 'success' && ... && needs.XN.result == 'success'` |
| Survivor (pre-existing status-function `if:`) | unchanged | the clause referencing `verify-image-prerequisites.result` narrows from `== 'success'` to `!= 'failure'`; every other clause is byte-for-byte unchanged |
| Chain (depends only on a rewritten job, never on the check directly) | unchanged | unchanged (research.md R-A2 — no rewrite needed) |

Applies identically across all 13 published stages (FR-002); the
~40-job count is this table's population, not a new count this feature
introduces (research agents found "any `needs.verify-image-prerequisites
.result`/`.outputs` reference" in `intake.yml`, `clarify.yml`,
`tasks.yml`, `watchdog.yml`, `pr-conversation.yml`, `finalize.yml`,
`implement.yml`, `auto-update-spec-kit.yml` — that same file set, plus
`cleanup.yml`, `rebase.yml`, `metrics-persist.yml`, `private-image-
dogfood.yml`, is where the entry-job rewrite lands).

## Aggregate inspection evidence

Computed once per watchdog inspection, in `collect`'s `aggregate` step,
unchanged in shape by this feature — this feature reads two outputs
that already exist (`signals`, `collectors-failed`) in a new way,
rather than computing new ones:

| Field | Type | Read by |
|---|---|---|
| `evidence-available` | `'true'` \| `'false'` | `diagnose`'s `if:` (unchanged clause), the passed-inspection step's `if:` (new, research.md R-B2) |
| `signals` | JSON array (string-encoded) | `diagnose`'s `if:` (new clause, research.md R-B1), the passed-inspection step's `if:` (new) |
| `collectors-failed` | integer (string-encoded) | the passed-inspection step's full-vs-partial wording choice (research.md R-B2) |
| `collectors-total` | integer (string-encoded) | unchanged (informational) |
| `untrusted-collectors` | JSON array (string-encoded) | unchanged — still an input to `diagnose` on the signal-bearing path only (FR-019) |

## Passed-inspection record

The deterministic lifecycle-issue comment posted when an inspection
finds nothing (research.md R-B2). Two variants, distinguished by
`collectors-failed`:

| Variant | Condition | Wording source |
|---|---|---|
| Full pass | `collectors-failed == 0` | Relocated, unchanged, from `diagnose`'s existing full-pass string |
| Partial pass | `collectors-failed > 0` | Relocated, unchanged, from `diagnose`'s existing partial-pass string |

Posted from `collect`, gated on `steps.aggregate.outcome == 'success'`
(never on an aggregate that did not complete — spec.md's edge case).
Distinct from the pre-existing "diagnose ran and found nothing
actionable" passed-inspection comment, which keeps its own code path
inside `diagnose` unchanged (FR-012).

## Watchdog stage input: `run-name` (amended)

| Field | Before | After |
|---|---|---|
| `run-name` | string, required | string, optional, default `''` |
| Resolution when empty | n/a (wrapper always supplied it) | stage resolves it itself inside `collect`'s existing inspected-run lookup, via `gh run view --json workflowName` (research.md R-B4) |

Additive, non-breaking per `contracts/versioning.md`; a caller that still
passes `run-name` explicitly (an adopter who has not moved to the
wrapper-side removal, or this repository's own transition commit) sees
no behavior change.

## Metrics-persist stage input: `since` (new)

| Field | Type | Default | Behavior |
|---|---|---|---|
| `since` | string (ISO-8601 timestamp) | `''` | Empty: process the single `run-id` exactly as today. Non-empty: list every run concluded at or after `since` minus a one-hour overlap (research.md R-C3), and process each through the existing discover→retrieve→validate→append-with-retry pipeline in one batched commit (research.md R-C1). |

Additive, non-breaking per `contracts/versioning.md`. `run-id` remains
required at the schema level but is ignored when `since` is set (sweep
mode names no single run).

## Persistence high-water mark

Durable state on the destination branch (default `metrics`), beside
`records.jsonl`:

| File | Shape | Written by | Read by |
|---|---|---|---|
| `sweep-state.json` | `{"high_water_mark": "<ISO-8601>"}` | A sweep run only, in the same commit as any `records.jsonl` append (research.md R-C2) | The next sweep run, to compute its own `since` value minus the one-hour overlap |
| `unpersisted.jsonl` | one line per run, `{"run_id", "workflow", "reason": "artifact_expired", "discovered_at"}` | A sweep run, same commit, when a discovered run's artifacts have expired (research.md R-C4) | Not read by any pipeline code — a durable, human-readable ledger; a future gate or maintainer query, not a runtime dependency |

A completion-triggered `persist` run (the nine-stage path) writes
neither file — only `records.jsonl`, exactly as today.

## Metrics record

Unchanged shape (schema version 1, spec 043) — this feature changes
*which completions produce one and when it is written*, never the
record's own fields. The relevant change: after FR-031, a healthy
watchdog inspection contributes zero records (research.md R-B3), and a
signal-bearing one is reached only by a sweep, not the completion
trigger (research.md R-C5).

## Gate fixtures (not runtime entities, checked-in test data)

| Fixture | Used by |
|---|---|
| A stage workflow snippet where an entry job's `needs:` includes `verify-image-prerequisites` with no `if:` at all | Amended Gate 23 (negative case — FR-007) |
| A stage workflow snippet where the same job's `if:` checks `== 'success'` instead of `!= 'failure'` | Amended Gate 23 (negative case — a silent narrowing back to today's behavior) |
| The 13 stages' `verify-image-prerequisites` job bodies, post-rewrite | Amended Gate 22 (positive case — byte-for-byte match including the new `if:` line) |
| An entry job carrying the new `if:` shape but only a partial ancestor reference | Gate 15's self-test (new case — proves the broadened population is exercised) |
| A `collect`-job fixture: every collector reports, zero signals | New watchdog gate (full-pass wording, no agent step) |
| A `collect`-job fixture: one collector fails, one reports, zero signals | New watchdog gate (partial-pass wording, no agent step — the edge case spec.md names explicitly) |
| A `collect`-job fixture: all collectors fail | Existing "could not inspect" gate coverage (unchanged — proves the new step does not fire on this path) |
| An `aggregate` step fixture that itself fails | New watchdog gate (negative case — no passed-inspection record posted) |
| A self-verifier fixture: `diagnose` skipped, passed-inspection comment present, no artifact, no record, whole-run duration under today's absolute floor | Amended self-verifier gate (new passing case, FR-032) |
| A wrapper `resolve`-removal fixture: `run-name` omitted, `workflow` job resolves it internally | New/amended watchdog wrapper gate (FR-020) |
| A sweep fixture: one run already persisted by the completion trigger, one run reachable only by the sweep | New metrics-persist gate (idempotence across both paths — FR-022/FR-027) |
| A sweep fixture: a discovered run whose artifact has expired | New metrics-persist gate (FR-028 — ledger entry, mark still advances) |
| The wrapper's `workflow_run.workflows` list with and without `"Wing Commander · 8 watchdog"` | New/amended wrapper-contract gate (FR-030(b)) |
