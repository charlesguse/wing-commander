# Contract: Stand-down classification in metrics/cost-line (FR-015, SC-008)

## Mechanism

Each of the six resume-stage jobs (`triage`, `route`, `fix`, `review`,
`readiness`, `prove`) gains one additional step, placed after every other
step in the job, `if: always()`:

```yaml
- name: Record run outcome (<job>)
  if: always()
  continue-on-error: true
  uses: ./.wc-pristine-repo/.github/actions/wing-commander-metrics-summary
  with:
    transcript-path: ${{ runner.temp }}/wing-commander-no-transcript.json
    model: ''
    stage: board-loop
    run-label: <computed below>
    record-path: ${{ runner.temp }}/wing-commander-metrics-record-<job>-outcome.json
```

modeled directly on the `select` job's own existing accounting-only
invocation (`board-loop.yml:901-911`) — no agent cost, no transcript, a
label-only record. Uploaded as an artifact the same way (`actions/
upload-artifact`, `retention-days: 90`), following the `select` job's
existing precedent exactly.

This is a **second, separate** record from each job's own per-agent
`wing-commander-metrics-summary` call (e.g. `triage-propose`'s, `board-
loop.yml:1264-1274`) — that call runs earlier (before the stop check can
even be evaluated) and keeps reporting the agent invocation's own outcome
unchanged. This new step reports what the *job as a whole* did with that
result.

## `run-label` value (priority order)

```text
1. stop-cause == "stop-request"  → "<job>: stopped (stop-request)"
2. stop-cause == "kill-switch"   → "<job>: stood down (kill-switch)"
3. stop-cause == "closed-issue"  → "<job>: stood down (issue closed)"   [prove only]
4. otherwise                     → "<job>: " + the job's own existing outcome
                                    (e.g. triage's $outcome, readiness's
                                    ready/not-ready, route's route verdict)
```

The exact literal strings in branch 4, and which existing shell variable
each job substitutes, are a tasks-stage/implementation detail — the fixed
requirement is that the three stand-down branches are distinguishable from
each other and from every "otherwise" value, using the same `run_label`
field (an existing top-level field in `wing-commander-metrics-summary`'s
emitted JSON record) rather than a new field or a changed `outcome` enum.

## Why not the `outcome` field

`wing-commander-metrics-summary`'s `outcome` field
(`healthy|exhausted|rate-limited|failed|unclassifiable|unavailable`)
describes a Claude agent invocation's own transcript-derived result. A
job's durable-action stand-down is orthogonal to that — the agent step
earlier in the same job may have completed `healthy` even though the job
then stood down before acting on it. Overloading `outcome` to also carry
stand-down meaning would make a `healthy`-outcome record ambiguous between
"the agent worked and its result was acted on" and "the agent worked but
the result was discarded because of a stop." `run_label`, already free text
used for exactly this kind of per-run differentiation (`select`'s own "no
eligible issue" vs "selected issue #N"), carries the distinction cleanly
with no schema change.

## Acceptance mapping

- User Story 1, AS3 (a run that selects nothing else "completes as a no-op
  with its own cost line and metrics record") — already true today via the
  `select` job's own accounting step; unaffected by this feature.
- User Story 2, AS4 / SC-008 — the new per-job "Record run outcome" step's
  `run_label` field is the durable, auditable signal; grepping uploaded
  metrics-record artifacts (or wherever they are aggregated) for `"stopped
  (stop-request)"` counts stop-request stand-downs across runs without
  reading any run's logs.
