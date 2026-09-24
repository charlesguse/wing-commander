# Contract: `board-loop.yml` Concurrency Groups

Supersedes, for implementation purposes, the single workflow-level block
`specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`
documents today (its "Concurrency" section, lines 21-30 of that file).
During implementation that section is edited to restate the sentence below
(FR-019/research.md D9); this file is the canonical source the new gate
(SC-006) diffs both `board-loop-workflow.md` and `board-loop.yml`'s own
comments against.

## The guarantee (FR-016)

> One board item is in flight repository-wide. A directed proof run, which
> selects no board item and opens no fix PR, is the only run permitted to
> overlap an ordinary board-loop run. Every other pair of `board-loop.yml`
> runs queues rather than races or cancels.

This sentence must appear, verbatim or gate-verified-equivalent, in:

1. `board-loop.yml`'s per-job `concurrency:` block comments (both the
   `wing-commander-board-loop` blocks and the `wing-commander-board-loop-directed-proof`
   block).
2. `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`'s
   "Concurrency" section.
3. This file.

## Groups, per job

| Job | Group (ordinary trigger) | Group (`directed-stage != ''`) | `cancel-in-progress` |
|---|---|---|---|
| `select` | `wing-commander-board-loop` | n/a — job is skipped for a directed dispatch | `false` |
| `triage`, `route`, `fix`, `review`, `readiness` | `wing-commander-board-loop` | `wing-commander-board-loop` when directed-reachable (`triage`/`review`/`readiness` only, contracts/directed-proof-run.md) | `false` |
| `prove-gate`, `prove` | `wing-commander-board-loop` (`pull_request: closed`) | `wing-commander-board-loop-directed-proof` | `false` |

The directed group is shared across every directed dispatch (not
per-attempt-token), so two merges proven close together contend for it
rather than each getting an unshared slot — this is what makes FR-001a's
busy-check meaningful (research.md D3's "Alternatives considered").

## Pre-dispatch checks

- **FR-001 (static)**: `board_prove.joins_directed_group(target_workflow,
  target_job)` reads the target's own `concurrency:` group expression off
  the checked-out tree and confirms it differs from the caller's own group
  before ever considering a dispatch. For the self-target case (target is
  `board-loop.yml`) this is true by construction once the groups above
  ship; the check exists so a future edit narrowing or removing the split
  fails loudly rather than silently reintroducing the deadlock.
- **FR-001a (dynamic)**: `board_prove.directed_proof_group_busy(run_list_json)`
  reads `gh run list --workflow=board-loop.yml --json
  databaseId,displayTitle,status -L 20` and reports whether any
  non-`completed` run's `displayTitle` carries the `[directed:` marker
  `board-loop.yml`'s `run-name:` expression embeds for a directed
  dispatch. `True` → record `outcome_reason: group-busy` (never dispatch);
  `False` → proceed to dispatch.

## What does not change

- The `wing-commander-board-loop` group's membership and semantics for
  every job that already joins it today (`select` through `readiness`, and
  `prove-gate`/`prove` on the `pull_request: closed` path) — including the
  "Related surface" behaviours spec.md documents and leaves unchanged: a
  non-board PR's close event still creates a run that queues in this
  group, and the hourly schedule tick can still displace a queued
  `pull_request: closed` run's pending slot (FR-010b covers detecting
  that case after the fact; this feature does not change whether it can
  happen).
- A future external dispatchable target's own concurrency group (FR-004):
  untouched by this feature, continues to be dispatched and waited on
  exactly as today, since it was never a member of either
  `wing-commander-board-loop*` group in the first place.
