# Contract: FR-003–FR-025 — the filing composite

The composite every in-scope stage job calls once, after its own
deterministic read-back. `research.md` D10 is the design rationale;
`data-model.md` gives the entities it produces.

## `.github/actions/wing-commander-stage-findings/action.yml` (NEW)

**Inputs**:

| name | required | default | description |
|---|---|---|---|
| `token` | true | — | the pipeline's existing GitHub App identity token (FR-028) |
| `stage` | true | — | one of `intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize` |
| `enabled` | true | — | wired from the stage's own `findings-filing-enabled` input |
| `channel-mode` | true | — | `fenced-block` (plan/tasks/implement/finalize) or `structured-array` (intake/clarify) |
| `execution-output-path` | false | `""` | path to `claude-execution-output.json`; required when `channel-mode: fenced-block` |
| `findings-json` | false | `""` | the stage's own already-parsed `findings` array (or `[]`/absent), as a JSON string; required when `channel-mode: structured-array` |
| `spec-dir` | true | — | e.g. `specs/056-stage-found-defect-filing`, for the attribution line |
| `run-url` | true | — | this run's URL, for the attribution line and dedup comments |
| `lifecycle-issue-number` | false | `""` | empty when the run has no lifecycle issue (FR-019) |
| `label-prefix` | false | `found-by` | wired from `findings-label-prefix` |
| `cap` | false | `3` | wired from `findings-cap` |

**Outputs**: `filed`, `appended`, `dropped-malformed`, `dropped-cap`,
`dropped-api-failure`, `summary` (a markdown block for FR-020/FR-021).

**Steps** (all `shell: bash`/`python3`, no network calls beyond `gh`):

1. `enabled != 'true'` → write a summary saying filing is disabled for this
   stage, set all counts to `0`, exit 0. (Edge case: "switched off is not
   a failure.")
2. Extract the raw findings array per `channel-mode` (research.md D2/D3);
   a channel that produced nothing parseable (truncated output, wrong
   shape) is treated as zero findings plus one summary log line, never a
   step failure (spec's Edge Cases).
3. Validate each element with `verify-stage-finding-schema.py`
   (`stage-finding-schema.md`); drop failures with a logged reason each.
4. If survivors exceed `cap`, keep the first `cap` in proposal order
   (research.md D11); log the rest as `dropped_cap`.
5. For each surviving finding: compute the fingerprint (research.md D6),
   compose the body (`data-model.md`'s "Filed Finding Issue" template),
   call `wing-commander-durable-failure-issue` with `operation: report`,
   `label: "${LABEL_PREFIX}:${STAGE}"`, `marker`, `state-scope: all`.
   - `action-taken=created` or `created-linked-closed` → call
     `wing-commander-outstanding-task-item` (if `lifecycle-issue-number`
     is non-empty) with the "filed" phrase.
   - `action-taken=commented` → compose the short recap-comment body
     instead of the full body *before* this step (so the comment carries
     "seen again in run `<run-url>`", not the full issue text again), then
     call `wing-commander-outstanding-task-item` with the "recorded on an
     existing issue" phrase.
   - A `gh`/API failure at this step (rate limit, permission, outage) is
     caught locally (`|| true` plus explicit exit-code check, never an
     uncaught non-zero exit propagating out of the composite step) and
     counted as `dropped_api_failure`, with the finding's `title`/`what`
     written to the step log verbatim (FR-025) — the composite step itself
     still exits 0 so the calling job's own `continue-on-error` is a second,
     redundant safety net rather than the only one.
6. Emit the summary block and step outputs.

## Call-site wiring (all six stage jobs)

Each stage job gains, immediately after its existing deterministic
read-back step (per stage: `contracts/stage-wiring.md` names the exact
step each stage's call follows):

```yaml
- name: File findings from this run
  if: ${{ !cancelled() && <stage-health-signal> }}
  continue-on-error: true
  uses: ./.github/actions/wing-commander-stage-findings
  with:
    token: ${{ ... }}
    stage: <stage-name>
    enabled: ${{ inputs.findings-filing-enabled }}
    channel-mode: <fenced-block|structured-array>
    execution-output-path: ${{ runner.temp }}/claude-execution-output.json   # fenced-block stages
    findings-json: ${{ steps.<agent-result-id>.outputs.findings }}           # structured-array stages
    spec-dir: ...
    run-url: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
    lifecycle-issue-number: ...
    label-prefix: ${{ inputs.findings-label-prefix }}
    cap: ${{ inputs.findings-cap }}
```

The `if:` condition is the FR-024 gating: a cancelled run, or a run whose
agent step never reached its own read-back (failed/exhausted), does not
reach this step at all — it is not converted into "zero findings filed",
it simply never runs, which is what "does not strand or alter the stage's
existing failure reporting" requires (a run that never attempts to file
is indistinguishable, from the outside, from one where filing is off).

`<stage-health-signal>` is deliberately NOT a bare `steps.<read-back-id>.
outcome != 'skipped'` check (maintainer review, post-merge fix): a
read-back step commonly runs whenever the lifecycle gate is open,
regardless of whether the agent run underneath it actually produced a
healthy, valid result — a bare non-skipped check lets a failed/exhausted
run's read-back step still "run" and reach the filing step. Each stage
instead names the specific signal that is only true on a healthy run:

| stage | `<stage-health-signal>` |
|---|---|
| `intake` | `steps.agent-result.outputs.valid == 'true'` |
| `clarify` | `steps.<read-back-id>.outcome != 'skipped'` (unchanged) |
| `plan` | `steps.<read-back-id>.outcome != 'skipped'` (unchanged) |
| `tasks` | `steps.<read-back-id>.outcome != 'skipped'` (unchanged) |
| `implement` | `steps.final.outputs.ok == 'true'` |
| `finalize` | `steps.summarize-verdict.outputs.verdict == 'healthy'` |

## Gate coverage

- `verify-stage-findings-wiring.py` (FR-031): fails if a stage's job
  carries this `uses:` step without the FR-003 prompt paragraph, or the
  paragraph without the step, checked across all six stages regardless of
  `findings-filing-enabled`'s default.
- `verify-single-home-idioms.py` gains `DECLARED_HOMES["stage-findings"]`
  pointed at this composite (FR-032): the proposal→validate→fingerprint→
  file→cross-link sequence must not be re-pasted into a stage workflow
  directly.
