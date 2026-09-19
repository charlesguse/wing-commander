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

## No resolve job

The wrapper used to open with a `resolve` job (no checkout,
`permissions: actions: read` only) that branched on `github.event_name`
to produce one `run-id` output. It is gone: the same value is a one-line
expression, `${{ format('{0}', inputs.run-id || github.event.workflow_run.id) }}`
(`inputs` is empty, not an error, under `workflow_run`; `format()`
because `workflow_run.id` is a number and the published workflow's
`run-id` input is typed `string`), and every job a
wrapper declares is a runner allocation GitHub counts as a whole minute
however briefly it runs -- a 2-second resolve job cost as much as the
9-second persist it fed, on every one of the ~3,000 completions a month
this wrapper hears.

## Persist job

```yaml
persist:
  if: >-
    vars.WING_COMMANDER_METRICS_PAUSED != 'true' &&
    github.event.workflow_run.conclusion != 'skipped'
  uses: ./.github/workflows/metrics-persist.yml
  with:
    # format(): workflow_run.id is a number and run-id is typed string
    run-id: ${{ format('{0}', inputs.run-id || github.event.workflow_run.id) }}
    destination-branch: ${{ vars.WING_COMMANDER_METRICS_BRANCH || 'metrics' }}
    destination-path: ${{ vars.WING_COMMANDER_METRICS_PATH || 'records.jsonl' }}
  secrets:
    pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
    # ... the registry pair, named explicitly (PR #267 re-review)
```

Two clauses gate it. The kill switch,
`vars.WING_COMMANDER_METRICS_PAUSED != 'true'`, matches the watchdog
wrapper's pause convention. The skipped-source guard declines a
`workflow_run` whose `conclusion` is `skipped`: that run executed no job
(the source wrapper's own `if:` gated it off), so it owns no
metrics-record artifact and persisting it is FR-021's zero-record no-op
paid for at a job-minute per job -- and it is the common case, because
every comment the pipeline posts wakes the clarify and pr-conversation
wrappers, which skip. `workflow_dispatch` carries no `workflow_run`
payload, so the comparison is against `''` and the manual re-drive path
stays open. Cancelled runs are deliberately NOT excluded: a cancelled
stage can have uploaded a record before the cancel landed.

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
- The pause/kill switch and the skipped-source guard.
- The secrets handed to the published workflow, named one by one
  (`inherit` would hand the Claude credentials into the one chain that
  deliberately runs no agent).

Everything else — discovery, retrieval, validation, retry, rollup — is
`metrics-persist.yml`'s (contracts/persist-workflow.md), identical for
every adopter.
