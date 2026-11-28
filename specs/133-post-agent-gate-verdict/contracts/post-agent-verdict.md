Lifecycle comment and step summary name "post-agent full suite" and quote the
first failing gate in a fence, distinct from the unchecked-tasks reason.

## Cycle outcome record (watchdog artifact)

The implement job's "Record cycle outcome for watchdog" step writes its
`converged` field before the post-agent job runs, so it keeps the
**tasks-only** reading (the `tasks-converged` value). The final decision is
the `converged` output of `implement-dispatch` (the workflow_call output) and
the lifecycle comment it posts; the watchdog artifact's `converged` is a
signal about the agent's own report, not the cycle's final verdict (FR-006,
partial, by decision).

## Gate invariants

- `verify-gate-suite-credential-free.py`: `gate-suite-implement-post` holds
  `contents: read` only and no App-token step; `implement-dispatch` is its
  registered reader.
- No `run-local-gates.py` invocation in `implement-dispatch`.
- The dispatch step exists exactly once in `implement.yml`, in
  `implement-dispatch` (`verify-implement-post-verdict.py`, Gate 185, which
  also pins the post job's `if:` and budget, the `converged` output's
  source, finalize's inputs, the reason strings and the by-name guidance).
