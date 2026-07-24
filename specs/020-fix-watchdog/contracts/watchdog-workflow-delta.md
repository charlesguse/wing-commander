# Contract Delta: `watchdog.yml` (Fix the Watchdog)

This is a delta against `specs/015-pipeline-watchdog/contracts/
watchdog-workflow.md`, which remains the full contract. Only the parts this
feature adds or tightens are listed here; everything else in that contract
(trigger shape, `collect`/`diagnose`/`triage`/`act` job contracts, self-
dispatch cap, pause switch, non-goals) is unchanged.

## Job contract addition: `report-unhandled-failure`

```yaml
report-unhandled-failure:
  needs: [collect, diagnose, triage, act]
  if: always()
  runs-on: ubuntu-latest
```

**Purpose**: guarantee FR-002 ("the watchdog MUST NOT end without a
verdict") holds even when a step no existing error handling anticipated
causes `collect`, `diagnose`, `triage`, or `act` to end in `failure` or
`cancelled` — the mechanism behind issue #96 (research.md R1).

**Behavior**:

1. Read `needs.collect.result`, `needs.diagnose.result`, `needs.triage.result`,
   `needs.act.result`. If none of the four is `failure` or `cancelled`, this
   job's remaining steps are skipped (`if:` guard) — every other path through
   the workflow already reported its own verdict, and this job posts nothing
   (no duplicate report).
2. If at least one is `failure` or `cancelled`, independently re-resolve (own
   GitHub App token mint, own best-effort lifecycle-issue lookup from
   `inputs.run-id`) rather than trusting `collect`'s outputs, since `collect`
   may be the job that failed:
   - Post `"🐕 **Wing Commander · watchdog** — could not inspect this run:
     the <job> job ended <result> unexpectedly. [Job logs](<url>). This is a
     pipeline defect, not a finding about the inspected run itself."` — one
     line per failed/cancelled job if more than one qualifies.
   - Destination: the lifecycle issue if one resolves, else the run's own
     `GITHUB_STEP_SUMMARY` — identical fallback rule as every existing
     verdict path (`specs/015-pipeline-watchdog/contracts/
     watchdog-workflow.md`).
3. This job's own steps tolerate their own failure gracefully (best-effort
   token/lifecycle-issue resolution, not `set -e` hard failures) — it is the
   last line of defense and must not itself become a new single point of
   failure. If even its own lifecycle-issue resolution fails, it still falls
   back to the run summary rather than producing no report at all.

**Permissions**: same job-level `issues: write` (and `actions: read` to link
job logs) already granted at the workflow level — no new permission scope.

**Non-goals**: this job never re-attempts collection/diagnosis/triage/act
itself, never retries the failed job, and never determines *why* the
underlying step failed beyond naming the job and linking its logs — it is a
reporting backstop, not a self-healing mechanism. Root-causing and fixing the
specific step that failed in issue #96's reported run remains this feature's
FR-005 (targeted fix), separate from this job (FR-002/FR-008, general
hardening).

## `collect` job tightening (existing job, no new job)

The five evidence-collector steps already use `continue-on-error: true`
(unchanged). The non-collector steps that precede them ("Checkout consumer
repository", "Resolve pipeline ref", "Checkout pipeline repository",
"Preflight", "Wing Commander context", "Fetch inspected run metadata") remain
hard-failing on error — deliberately not wrapped in `continue-on-error`,
since their outputs (pipeline ref, GitHub App token, run metadata) are load-
bearing for every step after them and a masked failure there would risk a
misleading verdict rather than an honest "could not inspect" one (research.md
R1's rejected alternative). `report-unhandled-failure` is what makes a hard
failure in any of them still end in a truthful verdict instead of silence.
