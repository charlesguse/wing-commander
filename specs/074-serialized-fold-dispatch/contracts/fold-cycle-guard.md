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
   only if `redispatch_count == 0`, calls `claim-redispatch` — the same
   atomic single-winner CAS *shape* as `dispatch-once`'s `claim-dispatch`
   (reusing `iteration` unchanged, since this is the same cycle, not a new
   one), but a DISTINCT ledger transform: it recovers a cycle the round has
   already committed to dispatching, so it carries no `own-folds` gate and
   is untouched by the 2026-09-29 reconciliation with spec 075
   (spec.md Clarifications) that reworked `claim-dispatch` alone. A winning
   `claim-redispatch` call enqueues a fresh `implement`-kind ticket in the
   same write (T038) and increments `redispatch_count` to `1`; the `react`
   step threads that ticket's token onto the re-dispatch as
   `fold_queue_token`; the new run is named in a second notice line. If
   `redispatch_count == 1` already, posts the FR-016a line instead and
   dispatches nothing. T055 (maintainer review of #821, B3): once the
   re-dispatch's run id is resolved (the same `gh run list` poll the notice
   text uses), `react` records it into the round via `record-implement-run`
   (mirroring `dispatch-once`'s own step of the same name) — without this,
   the round's `implement_run_id` keeps naming the CANCELLED run, so a
   later waiter's stale-reclaim check resolves liveness against a run
   that's already done and evicts the LIVE redispatched run's ticket, and a
   second loss of the redispatched run is never found by step 5's own
   `implement_run_id == run-id` lookup (breaking FR-016a's "a maintainer's
   re-drive is the remaining step" notice for that second loss).
6. If `peek-implement-run` resolves no round at all for this `run-id`
   (T065, maintainer review of #821, round 3 — the original dispatch's own
   correlation never landed, or this is itself a second loss of an
   already-uncorrelated cycle) → `action-taken: notice-only`, reporting
   that the cycle's round could not be determined and no automatic
   re-dispatch was attempted, rather than reaching `claim-redispatch` with
   an empty `ROUND` (a caller error the ledger transform itself does not
   tolerate).
7. T069 (maintainer review of #821, round 3): the `gh run list` poll that
   finds the re-dispatched run's URL filters on a timestamp taken
   immediately before the `gh workflow run` call (`react`'s own
   `start_ts`), not the ORIGINAL run's cancellation time — the latter
   opens a window wide enough, on a shared `implement-workflow` wrapper, to
   match a different spec's run instead of this one's.
8. `react`'s own `gh workflow run` re-dispatch carries the identical T047/
   T062 422-retry fallback `wing-commander-fold-dispatch` uses for an
   un-migrated wrapper with no `fold_queue_token` input declared — but its
   TICKET-OWNERSHIP choice on that retry path is the OPPOSITE of
   `dispatch-once`'s (T056): `dispatch-once` explicitly releases the
   abandoned implement-kind ticket once its own dispatch-queue ticket (the
   implement ticket's immediate predecessor) has released and the implement
   ticket has become the queue head, because an immediate release attempt
   while still behind the head would itself be a caller error. `react`
   holds no ticket of its own ahead of this one, so there is no guaranteed
   moment at which the abandoned ticket is known to be at the head — an
   unconditional release attempt here could hit the same "not at queue
   head" error if another run's ticket (or this very round's own prior,
   still-stale head) occupies it. `react` therefore does NOT release the
   ticket on this path at all: the retried (ticketless) run is still
   correlated via step 5's `record-implement-run`, and the existing
   correlated stale-reclaim path (`fold-queue-await.sh`) is what eventually
   cleans the abandoned ticket up, once that run completes — a deliberately
   slower, poll-driven cleanup than `dispatch-once`'s own immediate one,
   not an oversight.

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
