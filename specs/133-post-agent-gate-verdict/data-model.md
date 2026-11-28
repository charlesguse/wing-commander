# Data Model: Post-agent full-suite verdict

## Post-agent verdict (artifact `wc-gate-verdict-implement-post`)

Same JSON shape as the existing gate verdict (spec 095
`contracts/gate-verdict.schema.json`), site `implement-post`.

| Field | Meaning |
|-------|---------|
| site | `implement-post` |
| outcome | `pass` or `fail` |
| head_sha | commit the suite judged |
| trusted_sha | `github.sha` of the run that wrote it |
| first_failure | first failing gate line, or the time-budget message (untrusted text) |

Validation: reader (`wc_gate_verdict.py read`) returns `fail` for absent,
unreadable, malformed, wrong-site, wrong-head or wrong-trusted-commit input.

## Cycle decision (computed in `implement-dispatch`)

Inputs: `tasks-converged`, `handoff`, `routed`, `truncated`, `head-sha`,
`script-exists`, `ready`, `missing`, post-job result, verdict
(`outcome`, `reason`, `first-failure`).

| tasks-converged | script-exists | ready | verdict bound to head | converged |
|-----------------|---------------|-------|-----------------------|-----------|
| false | any | any | not read | false (no suite run) |
| true | false | n/a | not read | true (tasks alone) |
| true | true | false | not read | false, reason names `missing` |
| true | true | true | pass | true |
| true | true | true | fail / absent / other head | false, reason names post-agent suite + first failure |

State transitions: `not converged` below the iteration cap → next implement
cycle; at the cap → finalize with `converged=false`; `converged` → finalize
with `converged=true`.

## Stall hand-off verdict (informational)

`handoff=true` cycles also run the suite; verdict never changes the
hand-off. Carried to finalize as a marker issue comment:

| Field | Meaning |
|-------|---------|
| marker | `<!-- wing-commander:post-agent-verdict -->` |
| outcome | pass / fail / none |
| head | SHA judged (or "none") |
| first_failure | fenced, untrusted text |
