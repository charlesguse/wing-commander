# Contract: `wing-commander-metrics-persist.yml` (consuming instrument)

**Layer**: consuming instrument (constitution VII) — this repository's
own configuration of the published `metrics-persist.yml`. Not pinned by
adopters; free to change; the worked example an adopter copies and edits
for their own destination.

## Trigger

```yaml
on:
  workflow_run:
    workflows:
      # These MUST be the WRAPPER workflows' display names in YOUR
      # repository - the values of their `name:` keys - because a
      # workflow_run payload carries the wrapper's identity; a
      # workflow_call-only (reusable) workflow never owns a run, so
      # naming one here silently never fires (PR #267 review, B1).
      - "Wing Commander · 1 intake"
      - "Wing Commander · 2 clarify"
      - "Wing Commander · 3 plan"
      - "Wing Commander · 4 tasks"
      - "Wing Commander · 5 implement"
      - "Wing Commander · 6 finalize"
      - "Wing Commander · 7 cleanup"
      - "Wing Commander · rebase"
      - "Wing Commander · 8 watchdog"
      - "Wing Commander · 9 pr conversation"
    types: [completed]
  workflow_dispatch:
    inputs:
      run-id:
        description: "An already-concluded workflow run to collect metrics for"
        required: true
```

`workflow_run` only fires for workflows already on the default branch
(research.md R11) — the `workflow_dispatch` branch exists specifically
so this wrapper's wiring can be exercised before it ever fires live, and
so a human can re-run collection for a historical run (spec.md's
"records that cannot be retrieved... reports what it could not find"
edge case is most likely to be manually re-driven this way, after
raising the destination's `retention-days` or otherwise investigating).

## Resolve job (no checkout, `permissions: actions: read` only)

Mirrors `wing-commander-8-watchdog.yml`'s `resolve` job: branches on
`github.event_name` to produce one `run-id` output regardless of which
trigger fired. Gated by a kill switch,
`if: vars.WING_COMMANDER_METRICS_PAUSED != 'true'`, matching the
watchdog wrapper's existing pause convention.

## Persist job

```yaml
persist:
  needs: resolve
  uses: ./.github/workflows/metrics-persist.yml
  with:
    run-id: ${{ needs.resolve.outputs.run-id }}
    destination-branch: ${{ vars.WING_COMMANDER_METRICS_BRANCH || 'metrics' }}
    destination-path: ${{ vars.WING_COMMANDER_METRICS_PATH || 'records.jsonl' }}
  secrets: inherit
```

`vars.WING_COMMANDER_METRICS_BRANCH` / `_PATH` are this repository's own
choice of destination (R5) — an adopter forking this wrapper supplies
their own values or none at all. Setting no destination (or omitting
this wrapper entirely) is a fully-supported "no persistence" configuration:
emission still runs unconditionally at every stage (contracts/emission-contract.md),
nothing pushes to any branch, and no configuration was required to reach
that state (FR-002, spec.md Edge Case).

## What this file owns that the published workflow does not

- The trigger (`workflow_run` + the specific workflow name list).
- The destination (`vars.WING_COMMANDER_METRICS_BRANCH` / `_PATH`).
- The pause/kill switch.
- The token used to call the published workflow (`secrets: inherit`,
  this repository's own convention for wrapper→stage calls elsewhere).

Everything else — discovery, retrieval, validation, retry, rollup — is
`metrics-persist.yml`'s (contracts/persist-workflow.md), identical for
every adopter.
