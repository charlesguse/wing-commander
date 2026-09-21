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

```yaml
concurrency:
  group: wing-commander-board-loop
  cancel-in-progress: false
```

One item in flight repository-wide (FR-048); a second scheduled or
dispatched run queues rather than cancels or races.

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
