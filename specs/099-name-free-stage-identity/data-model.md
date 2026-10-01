# Phase 1 Data Model: Name-Free Stage Identity for Watchdog Collectors

No application database. Every entity below is either a new/extended
composite-action output, a new metrics-record field, or a value flowing
through `watchdog.yml`'s existing job-output and collector-outcome
plumbing. This is spec.md's Key Entities section made concrete against
research.md's designs (R1–R7).

## Resolved stage identity

Produced once per inspection by `wing-commander-inspected-run-identity`
(R1), consumed by every FR-002 site except the slug-fallback allowlist.

| Field | Type | Values | Source |
|---|---|---|---|
| `resolved-stage` | composite output (string) | `intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase`, `pr-conversation`, `watchdog`, or `` (empty = unresolved) | `record-stage` if non-empty, else the FR-009 name fallback, else empty |
| `resolved-stage-source` | composite output (string) | `record`, `name`, `` (empty) | Which branch of the above produced `resolved-stage` |

**Precedence** (FR-009, fixed and documented in one place — R1's
composite): `record-stage` wins whenever non-empty; the name fallback
(R2's `id: name-fallback` step) runs only when `record-stage` is empty,
covering the nine stages FR-014a names plus watchdog; anything else leaves both
outputs empty.

**Consumption state** (FR-005 — one of three, at every FR-002 consumer
site except the slug-fallback allowlist):

| State | Test | Consumer behavior |
|---|---|---|
| Identified, in scope | `resolved-stage` equals this collector's expected stage(s) | Collector runs normally |
| Identified, out of scope | `resolved-stage` non-empty, does not match | Silent, on-purpose skip (unchanged from today) |
| Not identified | `resolved-stage-source == ''` | Collector skips AND records a `collector-outcomes.json` entry with `outcome: "unresolved"` (see below) |

## Record spec-identity declaration

A new optional field on the durable metrics record (schema version 1,
additive per `specs/043-durable-metrics-record/contracts/metrics-record-
schema.md` rule 1).

| Field | Type | Meaning | Default when absent |
|---|---|---|---|
| `spec.identity_is_own` | boolean | `true` when the emitting run's spec identity (`spec.spec_dir`, etc.) is the run's own advance, not borrowed from another run it was reporting on | `false` (FR-008a — a record predating this field is treated as borrowing) |

Set by `wing-commander-metrics-summary`'s new required-with-no-default
input `spec-identity-is-own` (`'true'`/`'false'`), which every call site
across the twelve stage workflows that emit a record must pass
explicitly (SC-008):

| Stage | Value passed |
|---|---|
| intake, clarify, plan, tasks, implement, finalize | `'true'` |
| watchdog, cleanup, rebase, pr-conversation, board-loop, lifecycle-review-gate | `'false'` |

**Consumed only at the slug-fallback allowlist site** (FR-002's
exception, FR-008): `action.yml`'s metrics-record fallback trusts a
downloaded record's `spec.spec_dir` only when that same record's
`spec.identity_is_own` is `true`. This fully replaces the current
six-name `case "$RUN_NAME"` allowlist — no list of stage or wrapper names
remains in the slug-resolution path (SC-008).

## Collector outcome (extended)

Existing entity (`RUNNER_TEMP/collector-outcomes.json`, one array of
`{"collector": string, "outcome": string}` per inspection), gains a third
`outcome` value.

| Outcome | Existing/new | Meaning | Feeds into |
|---|---|---|---|
| `"ok"` | existing | Collector's own read succeeded (possibly finding nothing) | `collectors-failed`/`collectors-total` (unaffected) |
| `"failed"` | existing | Collector's underlying `gh`/`git` read errored | `untrusted-collectors` (unaffected) |
| `"unresolved"` | **new** | Collector could not determine whether it was in scope because `resolved-stage-source` was empty | **new** `stage-unresolved-collectors` output |

`untrusted-collectors` (line ~2033's `jq` filter) continues to select
only `outcome=="failed"` — `"unresolved"` is deliberately not folded in,
per FR-005's "third MUST NOT be reported as the second [nor conflated
with a read failure]".

## Name-warning condition (FR-014)

Not a stored entity — a boolean gate on one new step in the `collect`
job, evaluated from two already-computed facts (R6):

| Input | Source |
|---|---|
| Stage unresolved | `resolved-stage-source == ''` |
| Run looks like a pipeline stage run | `collect-execution-output`'s new `claude-execution-output-found` output (`true` when the artifact was found and readable, `false` on "no such artifact"/expired) |

Warning fires only when both are true. `docs/adoption.md`'s new section
(R8) documents this as the one place an unrecognised display name is
ever surfaced to a maintainer.

## Name-derived stage map (FR-009 fallback, FR-014a coverage)

A single `case "$RUN_NAME"` table, living only inside the `id:
name-fallback` step (R1/R2) — the one site the FR-012 gate permits a
reference display name to gate behavior.

| Display name | Mapped stage |
|---|---|
| `Wing Commander · 1 intake` | `intake` |
| `Wing Commander · 2 clarify` | `clarify` |
| `Wing Commander · 3 plan` | `plan` |
| `Wing Commander · 4 tasks` | `tasks` |
| `Wing Commander · 5 implement` | `implement` |
| `Wing Commander · 6 finalize` | `finalize` |
| `Wing Commander · 7 cleanup` | `cleanup` |
| `Wing Commander · 8 watchdog` | `watchdog` |
| `Wing Commander · 9 pr conversation` | `pr-conversation` |
| `Wing Commander · rebase` | `rebase` |
| anything else | (no match — `resolved-stage` stays empty) |

Note (maintainer review, fold leg-3): `Wing Commander · 8 watchdog` IS
included in this table. The only watchdog record
(`metrics-record-diagnose`) is written when diagnose runs, so a clean or
early-failed watchdog run writes no record naming a stage and falls
through to this name fallback the same as every other stage's run — the
earlier premise that a watchdog run's own record always carries `stage:
watchdog` only holds once diagnose has actually run.

## Expected-stage map (FR-007, unchanged home)

Already a single home today (`watchdog.yml:1024-1029`'s spec-meta
expected-stage `case` block: intake→spec, plan→plan, tasks→tasks,
implement→implement, finalize→review). This feature changes only what
variable the block switches on (`resolved-stage` instead of `$RUN_NAME`),
not its shape or location.
