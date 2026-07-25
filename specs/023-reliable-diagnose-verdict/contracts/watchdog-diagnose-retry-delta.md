# Contract Delta: `watchdog.yml` `diagnose` job (Reliable Watchdog Diagnosis)

This is a delta against `specs/015-pipeline-watchdog/contracts/
watchdog-workflow.md`'s `diagnose` job contract, further refined by
`specs/020-fix-watchdog/contracts/watchdog-workflow-delta.md`. Only the parts
this feature adds or changes are listed here; the job's trigger (`needs:
collect`, skipped when `evidence-available == false`), model tier, tool
allowlists, prompt framing, and structured-output schema are all unchanged.

## Step addition: `Classify diagnose attempt` (new, between `Diagnose` and `Diagnose (retry)`)

```yaml
- name: Classify diagnose attempt
  id: diagnose-classify
  if: always()
  run: |
    # reads ${{ runner.temp }}/claude-execution-output.json (attempt 1),
    # copies it to claude-execution-output-diagnose-attempt1.json for
    # forensic upload, and emits:
    #   agent-ok:   same boolean the existing read-back step computes
    #   retryable:  true only for a genuine terminal "result" record that
    #               is not OK (is_error / non-success subtype) — a shape
    #               the SDK reached and failed *during* execution
```

**Purpose**: decide, using only signals already written to disk by the SDK
before this step runs, whether attempt 1's failure is the recognized-
transient/infrastructure shape FR-010 allows a retry for, or the
deterministic shape that must report an honest failure immediately with no
retry. See research.md R2 for the exact rule and why it cannot depend on the
diagnose job's own still-in-progress raw log.

**Behavior**:

1. If `steps.diagnose.outcome == 'success'` and the execution-output file's
   last `type=="result"` record has `is_error == false` and
   `subtype == "success"`: `agent-ok=true`, `retryable=false` (no retry
   needed — this is a healthy attempt, findings or none).
2. Else if the file exists and contains at least one `type=="result"`
   record (regardless of whether it is the last event): `agent-ok=false`,
   `retryable=true`.
3. Else (file missing, empty, or contains no `type=="result"` record at
   all): `agent-ok=false`, `retryable=false`.
4. Always copies whatever `claude-execution-output.json` exists at this
   point to `${{ runner.temp }}/claude-execution-output-diagnose-
   attempt1.json`, before the retry step (if it runs) can overwrite the
   fixed-path file.

## Step addition: `Diagnose (retry)` (new, immediately after `Classify diagnose attempt`)

```yaml
Diagnose (retry):
  id: diagnose-retry
  if: >-
    steps.diagnose-classify.outputs.agent-ok != 'true' &&
    steps.diagnose-classify.outputs.retryable == 'true'
  continue-on-error: true
  timeout-minutes: 10
  uses: anthropics/claude-code-action@v1
  # identical with:/claude_args: to the Diagnose step above — same model
  # (steps.resolve-diagnose-model.outputs.model), same prompt, same
  # --json-schema, same --allowedTools/--disallowedTools. A genuine repeat
  # attempt, not a degraded fallback (research.md R2).
```

**Purpose**: give a recognized-transient/infrastructure crash exactly one
more chance to produce a genuine verdict (FR-010), bounded to a single
retry (two attempts total).

**Non-goals**: this step never changes the prompt, model, or tool access
between attempts; it never retries more than once; it never runs when
`retryable == 'false'` (a deterministic failure reports immediately, per
FR-010's "no retry" branch) or when attempt 1 already succeeded.

## Step change: `Upload Claude execution log`

Adds a second, conditional upload:

```yaml
- name: Upload attempt-1 execution log (only if retried)
  if: always() && steps.diagnose-retry.outcome != 'skipped'
  uses: actions/upload-artifact@v4
  with:
    name: claude-execution-output-diagnose-attempt1
    path: ${{ runner.temp }}/claude-execution-output-diagnose-attempt1.json
    if-no-files-found: ignore
```

The existing `Upload Claude execution log` step (artifact name
`claude-execution-output-diagnose`, unchanged) continues to upload whatever
is at the fixed path — attempt 2's output when a retry ran, attempt 1's
otherwise. **This artifact name must not change**:
`verify-watchdog-run.sh` check 7 downloads it by this exact name; keeping it
stable is what makes this feature's retry entirely invisible to the verifier
(FR-007).

## Step change: `Read back diagnose outcome`

Unchanged logic, but now reads `steps.diagnose-retry.outcome` when that step
ran (not `skipped`), else `steps.diagnose.outcome`, as the "pre-`continue-on-
error` outcome" input to the existing `agent_ok`/`outcome` computation. Adds
one new job output:

| Output | Value |
|---|---|
| `retried` | `true` iff `steps.diagnose-retry.outcome != 'skipped'` |

`outcome`, `findings`, and `agent-step-outcome` keep their existing shapes
and meanings (data-model.md) — `agent-step-outcome` now reflects whichever
attempt was final, which is what `report-unhandled-failure`'s safety net
needs to see.

## Step change: `Report "diagnose failed" to lifecycle issue`

Same trigger condition (`steps.diagnose-outcome.outputs.outcome ==
'diagnose-failed'`). Message gains attempt-count wording when
`needs.diagnose.outputs.retried == 'true'` (data-model.md's Lifecycle issue
verdict table) — otherwise byte-for-byte unchanged.

## Job change: `diagnose`

`timeout-minutes: 20` → `timeout-minutes: 35` (research.md R4). No change to
`needs`, the job-level `if`, or any other job's `needs`/`if` — `triage` and
`act` still gate on the same three `outcome` values, unaffected by whether
zero or one retry happened underneath.

## Unchanged: `verify-watchdog-run.sh` and the stage-8b workflow

No change. Every check it performs (run conclusion, duration bands, the
"diagnose failed"/"could not inspect"/safety-net reporter step conclusions,
the execution-output artifact's terminal-result check, and the raw-log
crash-signature grep) reads state this feature does not alter the shape of —
a retried-and-recovered run reports `passed-inspection`/`findings` exactly as
a first-try success would; a retried-and-still-failed run reports
`diagnose-failed` exactly as a no-retry failure would. This is what makes
FR-007 ("must not weaken, disable, or bypass the stage-8b verifier") hold by
construction rather than by a review step.

## Root-cause fix for the issue-#117 signature (FR-005)

Not a contract addition of its own — it is a targeted code change inside
whichever part of `watchdog.yml` research.md R3's decision tree points to,
once the implement stage confirms which of the four known crash signatures
fired in run 30161188955. Recorded here so the eventual diff is traceable
back to this contract rather than appearing as an unscoped change.
