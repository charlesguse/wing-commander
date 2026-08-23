# Contract: `watchdog.yml` + `wing-commander-8-watchdog.yml`

This project has no library/API surface; its "interfaces" are the GitHub
Actions trigger contract and the deterministic checks/writes that must
run in order. This document is the contract the implementation (tasks
phase, next stage) must satisfy.

## Trigger contract (wrapper only — the reusable stage never reads `github.event.*`)

```yaml
on:
  workflow_run:
    workflows:
      - "1 - Intake"
      - "1b - Clarify"
      - "3 - Plan"
      - "4 - Tasks"
      - "5 - Implement"
      - "6 - Finalize"
      - "7 - Cleanup"
      - "Rebase"
      - "8 - Watchdog"
    types: [completed]
  workflow_dispatch:
    inputs:
      run-id:
        description: "The run ID to (re-)inspect"
        required: true
```

The wrapper extracts `run-id` (`workflow_run.id` or the dispatch input),
`run-name` (`workflow_run.name` or resolved via `gh run view` for the
dispatch path), and passes both as typed inputs to `watchdog.yml`
(`uses: ./.github/workflows/watchdog.yml`, matching every other
wrapper's local-path-calls-published-stage shape). No path filter — this
stage is run-completion-driven, not file-change-driven.

## Job contract (`watchdog.yml`, `workflow_call` only)

Four jobs, sequential (`needs:`), one `concurrency:
wing-commander-watchdog-${{ inputs.run-id }}` group so re-inspection of
the same run never races itself, while different runs' inspections
proceed in parallel:

### `collect`

1. Preflight (`wing-commander-preflight` composite) — same fail-fast as
   every other stage (credential present, spec-kit artifacts present).
2. Resolve the inspected run's spec slug from `head_branch` (best-effort
   for `main`-based runs, e.g. cleanup — see data-model.md); this is a
   read-only lookup, never a refusal gate (unlike every write-capable
   stage's identity check) — a run the watchdog can't tie to a spec can
   still be inspected and reported against its own run URL, just without
   a lifecycle issue to post to (in which case the run's job summary
   carries the report instead, and the job records that no lifecycle
   issue destination exists).
3. Five deterministic collector steps (one per FR-006 source, research.md
   table), each tolerating "this source produced nothing for this run"
   as success, never as a failure — a source being empty is data, not an
   error.
4. Emit `signals.json` as a job output / uploaded artifact for `diagnose`
   to consume.

**Failure mode**: if every collector step fails outright (not "empty,"
but actually errors — e.g. the run's artifacts are expired past
retention), `collect` sets an output `evidence-available: false` and the
workflow skips straight to the "could not inspect" report (FR-005),
never fabricating signals.

### `diagnose` (`needs: collect`, skipped if `evidence-available == false`)

`claude-haiku-4-5`, `--max-turns` bounded,
`--allowedTools "Read,Grep,Bash(gh:*),Bash(git log:*),Bash(git diff:*)"`,
`--disallowedTools "WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*)"`,
structured output via `--json-schema` matching data-model.md's Finding
array shape. Prompt frames `signals.json` and anything it reads via
`Read`/`Grep`/`gh` explicitly as untrusted data, never instructions
(FR-023) — same framing convention every comment-triggered stage already
uses. Zero Findings in the output ⇒ `diagnose` sets
`outcome: passed-inspection`.

### `triage` (`needs: diagnose`, one matrix entry per Finding, skipped if `outcome == passed-inspection`)

Per Finding, deterministic (no agent):

1. **Coexistence check** (research.md): if `finding.alreadyHandledBy` is
   set, mark this finding `suppressed` — no fingerprint/dedup step runs
   for it, but it's still listed in the final lifecycle-issue report as
   "already reported by \<job\>."
2. **Fingerprint**: `sha256(class + canonical(normalizedFacts))`.
3. **Dedup search**: `gh search issues --state all
   "wing-commander-watchdog: fingerprint=$FP in:body"`.

No fix attempt is ever made — the watchdog is a pure reporter with no
diff-producing step (FR-014 of spec 024).

### `act` (`needs: triage`, one matrix entry per non-suppressed Finding)

Executes exactly what the dedup outcome selected:

- **Dedup miss**: create a new pipeline-defect issue carrying the
  Finding's evidence; comment on the lifecycle issue linking it.
- **Dedup hit, open**: comment the fresh evidence on the existing
  pipeline-defect issue; comment on the lifecycle issue linking it.
- **Dedup hit, closed**: reopen the existing pipeline-defect issue and
  comment the fresh evidence; comment on the lifecycle issue linking it.

No PR is ever opened by `act` (FR-014 of spec 024).

Every `act` outcome, plus the `passed-inspection`/`could-not-inspect`
short-circuits from `collect`/`diagnose`, is appended as one comment (or
one comment covering all findings from this run, implementation's
choice) to the run's lifecycle issue — this is the one write every path
through this workflow performs unconditionally (FR-022).

## Self-dispatch cap contract (FR-018, applies to `act` only, all rungs)

Before any write in `act`, if `workflow_run.name == "8 - Watchdog"` (this
is a self-inspection), walk `gh run list --workflow "8 - Watchdog" --json
databaseId,event,createdAt --limit <cap + 5>` backward from the inspected
run, counting a consecutive chain of `event == "workflow_run"` entries.
Depth `>= vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`)
⇒ every Finding this run produced is forced to report-only (as if paused,
research.md) regardless of what the dedup outcome would otherwise
select — `collect` and `diagnose` still ran and still get reported, only
`act`'s writes are suppressed.

## Pause contract (FR-019)

`vars.WING_COMMANDER_WATCHDOG_PAUSED == 'true'` ⇒ identical short-circuit
to the self-dispatch cap: `act` performs no write for any Finding, and
the lifecycle-issue report says so explicitly.

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- A scheduled catch-up sweep for missed runs (FR-025 explicitly defers
  this beyond v1).
- Opening a pull request of any kind — the watchdog's entire remediation
  surface is the pipeline-defect issue tracker (FR-014 of spec 024); a
  human decides on and makes any code change a filed finding warrants.
- Detecting problem classes beyond the FR-003 v1 pair with the same
  crisp, pattern-matched confidence — other sources (step summaries,
  annotations, general `spec-meta.json` drift) feed the diagnose step's
  judgment, not a second deterministic pattern matcher, and are
  explicitly accepted as carrying more false-positive risk (FR-006).
- Re-litigating or replacing `implement.yml`'s own stalled-retry logic
  or `cleanup.yml`'s three outcomes — both are unchanged; this stage only
  reads their resulting state to avoid duplicating their reports
  (FR-024).
