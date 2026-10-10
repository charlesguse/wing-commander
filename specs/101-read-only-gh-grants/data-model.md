# Data Model: Read-Only Agents Hold No Write-Capable `gh` Grant

No persistent storage. The entities below are in-memory gate concepts and
runner-temp files.

## Read-only agent step (gate concept)

| Field | Meaning |
|-------|---------|
| `workflow` | repo-relative path under `.github/workflows/` |
| `label` | tool-args `step-label`, or none for an inline step |
| `route` | `tool-args` (composite inputs) or `inline` (`claude_args --allowedTools`) |
| `allowed` | shipped allowed entries (consumer `${{ inputs.* }}` stripped by `_shipped`) |

Identified per spec FR-008: named label, or no `Write`/`Edit` (whole or
path-scoped) in `allowed`. Invariant: a discovered step with any `gh` grant is
a problem unless it matches an exemption.

## Exemption (gate table)

| Field | Meaning |
|-------|---------|
| `workflow`, `label` | the one site exempted |
| `grants` | exact tuple of `gh` grants tolerated |
| `tracker` | open issue number that owns the question |

Invariant: an exemption whose site holds no `gh` grant, or holds one not in
`grants`, fails the gate (self-expiring).

## Staged job-log set (diagnose job, `$RUNNER_TEMP`)

| File | Content |
|------|---------|
| `watchdog-job-logs/<job_id>.log` | raw log of one failed job; written only when the fetch succeeded and was non-empty |
| `watchdog-job-logs-status.json` | `{"outcome":"ok"|"failed","jobs":[{"id","name","conclusion","file"|null}],"reason":string|null}` |

State: `ok` (every failed job staged) or `failed` (any listing or log read
failed, or a response was empty). `failed` also appends `"job-logs"` to
`watchdog-untrusted-collectors.json`. The status file always exists after the
step; a missing status file means the step itself did not run and is treated as
`failed` by the prompt wording.

## Gather failure record

Element of `watchdog-untrusted-collectors.json` (existing array of collector
names); this feature adds the name `job-logs`.
