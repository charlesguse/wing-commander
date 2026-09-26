# Contract: `board-loop.yml`

## Triggers

```yaml
on:
  schedule:
    - cron: "<PR-reviewed cadence, in auto-release.yml's spirit>"
  workflow_dispatch: {}
  pull_request:
    types: [closed]
```

No `workflow_call` trigger (FR-062/FR-063). The header comment states,
following `auto-release.yml`'s own wording convention, why this workflow
is not published: it encodes this repository's own conventions (the 429
triage evidence, the `Found by the code review of #N` line, this
repository's gate-suite entry point) which would each have to become a
typed input to publish.

## Concurrency

specs/060-self-redrive-concurrency's own directed-proof-run mechanism
(contracts/concurrency-groups.md, contracts/directed-proof-run.md) replaces
the single workflow-level `concurrency:` block this section originally
documented with per-job blocks. The guarantee (FR-016/FR-048):

> One board item is in flight repository-wide. A directed proof run, which
> selects no board item and opens no fix PR, is the only run permitted to
> overlap an ordinary board-loop run. Every other pair of `board-loop.yml`
> runs queues rather than races or cancels.

| Job | Group (ordinary trigger) | Group (`directed-stage != ''`) | `cancel-in-progress` |
|---|---|---|---|
| `select` | `wing-commander-board-loop` | n/a — job is skipped for a directed dispatch | `false` |
| `triage`, `route`, `fix`, `review`, `readiness` | `wing-commander-board-loop` | `wing-commander-board-loop` when directed-reachable (`triage`/`review`/`readiness` only) | `false` |
| `prove-gate`, `prove` | `wing-commander-board-loop` (`pull_request: closed`) | `wing-commander-board-loop-directed-proof` | `false` |

See `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`
for the pre-dispatch checks (FR-001/FR-001a) and
`specs/060-self-redrive-concurrency/contracts/directed-proof-run.md` for
the dispatch mechanism itself.

## Entry gates (checked before job bodies run)

1. `vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'` — else stand down and
   record the pause as a pause, not a failure (FR-046, SC-006).
2. `board_stand_down.py` (research.md D16): no `implement.yml` run is
   `in_progress` — else stand down and record it (FR-049).
3. (`pull_request: closed` trigger only) the closing PR carries the
   loop's own marker (its body cites an issue this loop selected — see
   contracts/board-item-marker.md) — else this trigger fires for an
   unrelated PR and the run is a no-op.

## Jobs (schedule/dispatch path)

1. `select` — `board_eligibility.py` (contracts/eligibility-and-selection.md).
   No eligible issue → job summary states "nothing to do", no further job
   runs, no agent invoked (SC-009).
2. `triage` — contracts/triage.md. A close ends the run for this item.
3. `route` — contracts/route-backstop.md. A `spec-request` route ends the
   run for this item (branch/PR still cut only for the post-push breach
   case, FR-021).
4. `fix` — contracts/fix-step.md.
5. `review` (repeats with `fix`'s follow-up commits until zero open
   findings or the round budget is spent) — contracts/review-and-findings.md.
6. `readiness` — contracts/readiness-report.md. Never merges (FR-068).

## Job (resume path)

7. `prove` — contracts/prove-step.md, entered only from the
   `pull_request: closed` trigger when the PR merged (FR-041).

## Every job, uniformly

- Reads `env.WC_BOT_TOKEN` (never the composite's raw output directly) and
  refreshes it via the post-agent triple after any agent step it runs
  (research.md D19).
- Calls `wing-commander-metrics-summary` immediately after any agent step
  (research.md D20).
- Posts its outcome on the originating issue before returning (FR-044).
- Re-checks the kill switch (gate 1 above) before taking its own durable
  action, not only at job start (FR-051).
