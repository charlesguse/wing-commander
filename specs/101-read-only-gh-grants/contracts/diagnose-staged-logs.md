# Contract: diagnose staged job logs

Layer: consuming-stage internals of `watchdog.yml` (not a `workflow_call`
input, output or secret; Principle VII unaffected).

## Helper: `.github/actions/wing-commander-fetch-job-logs/action.yml`

A published composite with its own step, not a `_shared/` script: Gate 12
forbids `gh` calls in `_shared/` scripts, and Gate 60 forbids a published stage
resolving `_shared/`.

Inputs: `token` (the `github.token`, passed by the caller as
`${{ github.token }}`), `run-id`, `out-dir`, and the optional `conclusions`
(comma-separated; only jobs with a listed conclusion are fetched, so diagnose
passes `failure,timed_out,startup_failure`; empty fetches every job that has
concluded and is not skipped or cancelled).
`GITHUB_REPOSITORY` comes from the runner environment.

Behaviour:

- lists jobs for the run (`--paginate`), captures through a direct pipeline
  with `|| rc=`, never through a bare command substitution;
- clears `*.log` files of an earlier run first;
- per job not `skipped`/`cancelled`/unconcluded: fetch the log; one bounded
  retry per job after `sleep 10` on a non-zero status;
- never writes an error message or empty body as log content; an empty body
  from a successful read writes no file and is not a failed read (the staging
  step records `file: null` for it with status `ok`, and `log-read` only when
  the helper itself reported a failed read);
- outputs: writes `jobs.json`, per-job log files and (on failure) `reason.txt`
  (`jobs-list` or `log-read`) into the directory, and sets the `result` output
  (`ok` or `failed`); the step never fails the job, so failure travels in
  `result` and callers read that output rather than any stdout line.

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
| listing read fails, what gh printed does not parse as JSON, or the move into place fails | helper `failed` with reason `jobs-list` and `jobs.json` `[]` (absent if even that write fails); status `failed`, reason `jobs-list`, `job-logs` added to untrusted collectors |
| staged `jobs.json` non-empty but not an array of objects (not written by a helper that ran to completion) | status `failed`, reason `jobs-unreadable`, `job-logs` added to untrusted collectors |
| a log read fails (after that job's one retry) | status `failed`, that job `file: null`, others still staged |
| empty log body (successful read) of a failed job | that job `file: null`, no empty file written; status `failed`, reason `log-empty`, `job-logs` added to untrusted collectors, so the agent cannot read a missing log as an unneeded one |
| no failed jobs | status `ok`, empty `jobs` |
| step crashes | `continue-on-error`; missing status file read as failed; a helper that failed without naming a log-read failure (it died, or could not write its reason) makes the status `failed`, reason `fetch-incomplete` unless a more specific reason (`jobs-list`, `jobs-unreadable`, `log-read`, `log-empty`) applies |
