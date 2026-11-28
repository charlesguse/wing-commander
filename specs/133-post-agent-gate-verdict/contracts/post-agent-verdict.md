# Contract: post-agent verdict (live; fixed like code)

## Jobs in `implement.yml`

- `implement` — outputs added: `tasks-converged` (today's tasks-only
  reading), `handoff`, `routed`, `truncated`, `head-sha`, plus the values
  `implement-dispatch` needs. It no longer dispatches.
- `gate-suite-implement-post` — `needs: [implement]`;
  `if: !cancelled() && needs.implement.result == 'success' &&
  (needs.implement.outputs.tasks-converged == 'true' ||
  needs.implement.outputs.handoff == 'true')`; `permissions: contents: read`;
  no App token, no `environment:` secrets; same `runs-on`/`container` as
  `gate-suite-implement-cycle`; `timeout-minutes: 30`; composite input
  `suite-timeout-minutes: "25"` (budget < timeout); outputs `script-exists`,
  `ready`, `missing`.
- `implement-dispatch` — `needs: [implement, gate-suite-implement-post]`;
  `if: !cancelled() && needs.implement.result == 'success'`; holds the App
  token; reads the verdict with `wing-commander-gate-verdict`
  (`site: implement-post`, `expected-head-sha: needs.implement.outputs.head-sha`,
  `gate-job-result`). Publishes the final `converged`.

## workflow_call outputs

`converged` is sourced from `jobs.implement-dispatch.outputs.converged`.
Other outputs keep their names.

## Decision rule

See `data-model.md` table. Any unreadable input → not converged when the
repository has a suite and the cycle would converge.

## Stall hand-off to finalize

Before dispatching finalize with `converged=false` on a `handoff=true` cycle,
`implement-dispatch` posts one comment on the lifecycle issue starting
`<!-- wing-commander:post-agent-verdict -->` carrying outcome, head and the
fenced first failing gate (or "no verdict produced: <reason>"). Finalize reads
the newest such comment and includes it in the final PR body. Finalize's
`workflow_dispatch` inputs are unchanged.

## Non-convergence rendering

Lifecycle comment and step summary name "post-agent full suite" and quote the
first failing gate in a fence, distinct from the unchecked-tasks reason.

## Gate invariants

- `verify-gate-suite-credential-free.py`: `gate-suite-implement-post` holds
  `contents: read` only and no App-token step; `implement-dispatch` is its
  registered reader.
- No `run-local-gates.py` invocation in `implement-dispatch`.
- The dispatch step exists exactly once in `implement.yml`, in
  `implement-dispatch`.
