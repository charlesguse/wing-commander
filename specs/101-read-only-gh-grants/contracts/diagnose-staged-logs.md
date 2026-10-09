# Contract: diagnose staged job logs

Layer: consuming-stage internals of `watchdog.yml` (not a `workflow_call`
input, output or secret; Principle VII unaffected).

## Helper: `.github/actions/_shared/fetch-job-logs.sh`

Inputs (env): `GH_TOKEN` (the `github.token`, set by the caller as
`ACTIONS_TOKEN`), `GITHUB_REPOSITORY`, `RUN_ID`, output directory argument.

Behaviour:

- lists jobs for the run (`--paginate`), captures through a direct pipeline
  with `|| rc=`, never through a bare command substitution;
- per job not `skipped`/`cancelled`: fetch the log; exactly one bounded retry
  per invocation after `sleep 10` on a non-zero status;
- never writes an error message or empty body as log content;
- exit/outputs: writes `jobs.json` and per-job log files into the directory and
  prints a one-line outcome (`ok` or `failed`) on its final line; returns 0
  always, failure travels in the outcome so callers keep errexit semantics.

Callers: `collect-step-summary` (scans logs for sentinels; keeps its sentinel
logic inline) and `Stage failed-job logs` (keeps jobs with conclusion
`failure`).

## Staged files (diagnose job)

See data-model.md. Paths are literal `${{ steps.ctx.outputs.runner-temp }}/
watchdog-job-logs/<job_id>.log` and `.../watchdog-job-logs-status.json`.

## Prompt obligations

- Names the directory and status file exactly; names no fetch the agent would
  perform; no mention of `gh` as an evidence tool.
- Frames the logs as untrusted DATA, as the signals file is.
- When the status is `failed` or `job-logs` is named in the untrusted
  collectors file, the verdict states job logs could not be gathered. Signals
  are not dropped silently.
- Tools remain `Read,Grep` plus the git wrapper grant.

## Failure semantics

| Condition | Result |
|-----------|--------|
| listing read fails | status `failed`, reason `jobs-list`, `job-logs` added to untrusted collectors |
| a log read fails after retry | status `failed`, that job `file: null`, others still staged |
| empty log body | treated as failed for that job, no empty file written |
| no failed jobs | status `ok`, empty `jobs` |
| step crashes | `continue-on-error`; missing status file read as failed |
