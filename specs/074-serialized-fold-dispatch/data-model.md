# Phase 1 Data Model: One Fold Queue Per PR

This feature has no application data model; its "entities" are the shapes
recorded in the new fold-queue ledger and the extra fields two existing
artifacts (`spec-meta.json`, the lifecycle issue) gain. All of it is
internal bookkeeping — none of it is a published `workflow_call` input,
output, or secret (contracts/workflow-changes.md covers those separately).

## Fold Queue Ledger

**Location**: branch `wing-commander-fold-queue`, one file,
`fold-queue.json`, at the branch root.

**Shape**:

```json
{
  "specs": {
    "specs/074-serialized-fold-dispatch": {
      "round": 3,
      "queue": [
        { "token": "run-35491701810-act", "kind": "act", "run_id": "35491701810",
          "enqueued_at": "2026-09-20T05:26:58Z", "granted_at": "2026-09-20T05:26:59Z" },
        { "token": "run-35491785316-act", "kind": "act", "run_id": "35491785316",
          "enqueued_at": "2026-09-20T05:28:59Z", "granted_at": null }
      ],
      "rounds": {
        "3": {
          "opened_at": "2026-09-20T05:26:58Z",
          "folded_items": [
            { "run_id": "35491701810", "leg_id": "leg-4", "summary": "...", "commit_sha": "a1b2c3d" }
          ],
          "not_folded_items": [
            { "run_id": "35491701810", "leg_id": "leg-5", "outcome": "not-folded", "reason": "cancelled" }
          ],
          "dispatch_claimed_by": null,
          "iteration": null,
          "implement_run_id": null,
          "redispatch_count": 0
        }
      }
    }
  }
}
```

**Field notes**:

- `round` — the spec-dir's current round counter (D4). Incremented only
  when `queue` transitions from empty to containing a new `act`-kind
  ticket; every ticket and completion record is filed under the round
  active at the moment it was created.
- `queue` — an ordered list; index 0 is the head. A ticket is granted
  (`granted_at` set) only once it reaches index 0 **and** no other
  ticket's job is still holding the underlying GitHub concurrency group
  (the composite's poll checks both). `kind` is one of `act`, `dispatch`,
  `implement`. `token` is `run-<run_id>-<kind>`, globally unique per
  spec-dir since a given run only ever holds one ticket of a given kind.
- `rounds.<n>.folded_items` / `not_folded_items` — replace the base..tip
  git-log scan (research.md D3); appended by
  `wing-commander-fold-queue-release` at the moment each `act` ticket
  releases, one entry per leg that ticket's run executed.
- `rounds.<n>.dispatch_claimed_by` — `null` until one run's
  `wing-commander-fold-queue-claim-dispatch` call wins the atomic claim
  (D4); thereafter the winning `run_id`. A second claim attempt for the
  same round is a no-op read, never a second write.
- `rounds.<n>.iteration` / `implement_run_id` — set by the winning claim
  once it reads `spec-meta.json`'s `iteration` and computes `next`;
  `implement_run_id` is filled in once the dispatched run is correlated
  (mirroring `wing-commander-dispatch-and-wait`'s token-correlation, not a
  recency guess), and is what `fold-cycle-guard.yml` reads to know which
  run it is watching for this round.
- `rounds.<n>.redispatch_count` — 0 or 1, enforced by
  `fold-cycle-guard.yml` as the FR-016/FR-016a bound. Never incremented
  past 1.

Old rounds are never pruned by this feature (out of scope, matching the
existing metrics ledger's own unpruned growth — a possible shared future
cleanup, not this feature's job).

## Ticket

One entry in a ledger's `queue` array (see field notes above). State
transitions: `enqueued` (`granted_at: null`) → `granted` (`granted_at`
set, the holder may now attempt the GitHub concurrency group) →
*removed from `queue`* (released, by the holder's own
`wing-commander-fold-queue-release` step, or reclaimed by a later waiter
per research.md D6 if stale).

## Round

A maximal span of ledger activity for one spec-dir between two moments the
`queue` was empty. Owns exactly zero or one dispatch claim and zero or one
successful re-dispatch. A round that never accumulates a `folded_items`
entry still resolves (its claim fires with an empty `folded_items` list
and the claiming run posts the existing "nothing folded" reply, unchanged
from today's `dispatch-once` behavior for that case).

## Lost-Cycle Notice (new field on the lifecycle-issue record, not a new artifact)

No new file — this is a comment posted by `fold-cycle-guard.yml`, in the
same shape `wing-commander-chain-stop-notice` already produces elsewhere,
naming: spec, round/iteration, the cancelled run's URL, the cause
(concurrency replacement), and — once available — the re-dispatched run's
URL or the FR-016a "maintainer re-drive is the remaining step" line. It is
matched to its own round's earlier "Implementation cycle N dispatched"
reply by iteration number (US3 AC3), which the ledger's
`rounds.<n>.iteration` field already carries.

## spec-meta.json

No new field. `iteration` continues to be the single source the winning
dispatch claim reads and increments-for-display; the ledger's
`rounds.<n>.iteration` is a cached copy of what the winning claim
computed, not a second source of truth — `implement.yml` itself remains
the only writer of `spec-meta.json`'s own `iteration`, unchanged from
today.
