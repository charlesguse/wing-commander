# Contract: `wing-commander-fold-queue-release` (composite action)

**Published surface.** New in this feature.

## Purpose

Releases a granted ticket (removing it from the ledger's queue head) and,
for an `act`-kind ticket, records this run's own fold outcome directly —
replacing the base..tip git-log range scan `report-fold-outcomes` and
`dispatch-once` use today (research.md D3).

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `spec-dir` | yes | — | |
| `token` | yes | — | The token `wing-commander-fold-queue-admit` returned. |
| `round` | yes | — | The round the ticket was filed under. |
| `leg-id` | no | `''` | Required (non-empty) when `kind` was `act` and this call reports one leg's outcome; the calling job invokes this composite once per leg it ran (`act`'s own within-run `max-parallel: 1` sequencing is unchanged, so these calls are already serial). |
| `outcome` | yes | — | `folded` \| `not-folded` \| `error`. |
| `commit-sha` | no | `''` | The `fold(<id>):` commit SHA this leg produced, when `outcome: folded`. |
| `summary` | no | `''` | Free-text summary for the eventual "Folded in this review" reply; framed as data, never as instructions to any later reader (Principle V). |

## Outputs

None — this is a best-effort, always-run step.

## Step placement contract

MUST be invoked with `if: always()` as the last step of the job holding
the ticket, so it still runs when the job's own mutating work failed —
only a job cancelled *while pending* (which, per this feature's own design,
should no longer happen for a ticket-holder; research.md D6 covers the
residual case) skips it entirely, which is exactly why D6's reclaim path
exists as the backstop.

## Behavioral guarantees

1. Releasing a token already absent from the queue (a retried `always()`
   step after a first attempt's push actually landed) is a no-op, never an
   error — `fold-queue-ledger-schema.md`'s `release` transform contract.
2. Releasing a token that is present but not at the queue head is a hard
   failure (`::error::`) — this should be unreachable by construction
   (only the head ticket's job ever runs real work) and existing as a
   loud failure rather than a silent wrong-order write is deliberate
   (Principle VIII).
3. For `kind: act`, every `leg-id` this run's `act` job actually executed
   MUST have exactly one release call recording its outcome before the
   ticket itself is removed — Gate 99 checks this invariant against
   `act`'s own matrix definition (contracts/gates.md).
