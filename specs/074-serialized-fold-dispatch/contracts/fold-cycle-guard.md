# Contract: `fold-cycle-guard.yml` (new published stage) + `wing-commander-9b-fold-cycle-guard.yml` (new wrapper)

## Purpose

User Story 3's safety net (FR-012–FR-016a). An observer, external to any
implement run, that detects a concurrency-replacement cancel, posts a
lifecycle-issue notice, and re-dispatches the lost cycle at most once.
Deliberately carries no agent step (research.md D7).

## Trigger (wrapper only; the published stage itself owns no trigger, per
Constitution VII)

`wing-commander-9b-fold-cycle-guard.yml`: `on: workflow_run: workflows:
["Wing Commander · 5 implement"], types: [completed]` — the identical
wiring `wing-commander-8-watchdog.yml` already has for the same workflow
name (`.github/workflows/wing-commander-8-watchdog.yml:58-70`), so both
reactors observe every completed implement run independently.

## `workflow_call` inputs (published stage)

| Name | Required | Default | Description |
|---|---|---|---|
| `run-id` | yes | — | The completed `implement.yml`-calling run to inspect (from `github.event.workflow_run.id`, extracted by the wrapper — a stage never reads `github.event.*` itself, Constitution VII). |
| `conclusion` | yes | — | That run's conclusion, likewise extracted by the wrapper. |
| `spec-dir` | no | `''` | Resolved by the stage itself when empty, via the same `wing-commander-inspected-run-identity` composite `watchdog.yml` already uses, since a dispatched run's `head-ref` is uninformative and the wrapper cannot know the spec ahead of time. |
| `implement-workflow` | yes | — | Passed through so a re-dispatch calls the adopter's own configured implement wrapper, matching `dispatch-once`'s existing `implement-workflow` input. |
| `dry-run` | no | `false` | Quickstart/fixture use — skips the real `gh workflow run` re-dispatch, still exercises detection and notice composition. |

## Outputs

| Name | Description |
|---|---|
| `action-taken` | `none` \| `notice-only` \| `notice-and-redispatch`. Consumed only by the quickstart drill and gate fixtures — no downstream stage depends on it. |

## Detection algorithm (deterministic; research.md D7)

1. `if: github.event.workflow_run.conclusion == 'cancelled'` (wrapper-level
   gate — anything else is out of scope for this stage and it is not
   invoked).
2. Stage reads `gh api repos/.../actions/runs/<run-id>/jobs`; "never
   started" ⇔ every job's `started_at` is null.
3. If not never-started (it ran steps and was cancelled mid-flight) →
   `action-taken: none`. This is today's existing manual-cancel silence,
   unchanged (FR-013).
4. If never-started → look for a correlated entrant: another run sharing
   the resolved `spec-dir`'s concurrency group whose own `started_at`
   falls within a short window of this run's `updated_at` (cancellation
   timestamp). Found → `action-taken: notice-and-redispatch` (subject to
   the bound below) or `notice-only` (bound exhausted). Not found →
   `action-taken: none` — an unexplained pending-cancel with no positive
   replacement evidence stays silent, per research.md D7's stated
   tie-break toward FR-013's existing default.
5. On a positive finding, reads the ledger's round record for this
   spec-dir keyed by `implement_run_id == run-id` to find the owning
   round and its `redispatch_count`. Posts the FR-012 notice always; then,
   only if `redispatch_count == 0`, calls the same claim/enqueue path
   `dispatch-once` uses (reusing `iteration` unchanged, since this is the
   same cycle, not a new one) to dispatch a fresh `implement.yml` run,
   increments `redispatch_count` to `1` in the same ledger write, and
   names the new run in a second notice line; if `redispatch_count == 1`
   already, posts the FR-016a line instead and dispatches nothing.

## Behavioral guarantees

1. Never posts for a run that executed at least one step and was then
   cancelled (today's silent manual-cancel case, FR-013, US3 AC2/AC6).
2. Never re-dispatches more than once per round (FR-016a, US3 AC5) — the
   bound is the ledger's own integer field, checked and incremented in one
   transaction, never left to this stage's own judgment about how many
   times it has "already tried."
3. Runs no agent step and requests no model-tier permission — Constitution
   II's cost accounting for this feature is unaffected by how often
   implement runs get cancelled.
