# Contract: `wing-commander-fold-queue-admit` (composite action)

**Published surface** (resolved by published stages via self-checkout;
Constitution VII). New in this feature.

## Purpose

Used by a new, non-scarce prerequisite job (`fold-turn-act`,
`fold-turn-dispatch`, `fold-turn-implement`) to enqueue one ticket for the
calling run and block until it is that ticket's turn, before the
downstream job (which still carries the unchanged
`wing-commander-<spec-dir>` GitHub concurrency group) is allowed to start.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `spec-dir` | yes | — | `specs/NNN-slug`, identifies which ledger entry to use. |
| `kind` | yes | — | One of `act`, `dispatch`, `implement`. |
| `run-id` | no | `${{ github.run_id }}` | Overridable only for fixture/test use. |
| `existing-token` | no | `''` | When set (implement.yml's case, research.md D5), skip `enqueue` and only `await` this token — it was already written by another run's `claim-dispatch` call. |
| `max-wait-minutes` | no | `30` | Hard ceiling; exceeding it is a step failure, never a silent pass-through. |
| `poll-interval-seconds` | no | `10` | |
| `stale-after-minutes` | no | `10` | Passed through to the reclaim check (research.md D6); must be smaller than `max-wait-minutes`. |

## Outputs

| Name | Description |
|---|---|
| `token` | The ticket token this call is now holding (either newly enqueued or the `existing-token` it awaited). |
| `round` | The round id the ticket was filed under. |
| `granted` | `'true'` once returned — the composite does not return until granted or it fails the step; there is no "false" output value, only a non-zero exit on timeout. |

## Failure behavior

A timeout (`max-wait-minutes` exceeded without being granted, and no stale
head ticket found to reclaim) is a hard step failure. This is a
deliberate, visible stop rather than a silent skip — the calling job's
`needs:` chain means the downstream mutating job simply never runs, and
the run's own summary shows why, satisfying Principle IV's "any manual
step that survives must be reported explicitly."

**T049:** hitting `max-wait-minutes` is not itself always the failure —
when the queue head is a correlated (`peek-round`'s `implement-run-id`
set), confirmed-alive (`in_progress`/`queued`) `implement`-kind ticket,
the deadline extends by another full `max-wait-minutes` window instead of
failing, since a normal `implement.yml` cycle routinely runs well past 30
minutes (recent runs: 16-125 minutes) and a review posted during that
window must still be folded, not dropped. The hard failure above still
applies once the head is not alive (or not correlated) and reclaim
genuinely can't clear it within the deadline.

**T046:** an `implement`-kind head ticket still uncorrelated (no
`implement_run_id` recorded for its round) is reclaimed outright once
`stale-after-minutes` plus a further grace period (`fold-queue-await.sh`'s
own `UNCORRELATED_IMPLEMENT_GRACE_MINUTES`, default 5) has elapsed, rather
than skipped forever — `record-implement-run` normally lands within
seconds of the ticket's grant, so a longer gap means the run that would
have correlated it never came to exist (a standalone-mode claim, a failed
`gh workflow run`, or an unfound `run-url` — `dispatch-once`'s own cleanup
step should already have released such a ticket; this is the backstop for
whatever gap remains).

## Behavioral guarantees

1. Two calls for the same `(spec-dir, kind, run-id)` are idempotent — a
   retried step (e.g., a runner hiccup before the output was recorded)
   observes its own already-enqueued ticket rather than creating a second
   one (fold-queue-ledger-schema.md's `enqueue` transform).
2. This composite never itself joins a GitHub `concurrency:` group — its
   own job has none, by contract, so it is never a contender for anyone
   else's pending slot.
3. Never invokes an agent; carries no `contents: write` beyond what
   pushing to `wing-commander-fold-queue` requires, and no
   `pull-requests`/`issues` permission at all.
