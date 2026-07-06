# Contract: `speckit-5-implement.yml`

This project has no library/API surface; its "interfaces" are the GitHub
Actions trigger contract, the repo-level configuration variables, and the
workflows it dispatches (itself, and finalize). This document is the
contract the implementation (tasks phase, next stage) must satisfy.

## Trigger contract

```yaml
on:
  workflow_dispatch:
    inputs:
      spec_dir:  { required: true }   # e.g. specs/005-implement-converge
      issue:     { required: true }   # lifecycle issue number
      iteration: { required: false, default: "1" }
```

Unlike the plan/tasks stages, this stage has no natural PR/issue event of
its own — it is dispatched by the tasks stage at `iteration=1` and
re-dispatches itself at `iteration+1` (`docs/architecture.md` §Stage 4:
"Looping is re-dispatch, not an in-job loop"). This is already the stub's
trigger contract and is unchanged by this feature.

**Refusal contract (FR-012)**: if `spec_dir` doesn't resolve to a
`specs/NNN-slug` directory matching `^specs/[0-9]{3}-[a-z0-9][a-z0-9-]*$`,
or `specs/$slug/{spec.md,plan.md,tasks.md,spec-meta.json}` are not all
present on `spec/$slug`, or `spec-meta.json`'s own `issue`/`spec_dir` fields
don't match the dispatch inputs, the job fails loudly (`::error::`,
`$GITHUB_STEP_SUMMARY`) and performs no further action — no guessing which
specification to build.

## Idempotency contract (FR-011)

Precondition for a cycle to run, checked against `spec-meta.json` on
`spec/$slug` *before* anything else:

```
(stage == "tasks" && iteration_input == 1)
  ||
(stage == "implement" && iteration_input == recorded_iteration + 1)
```

Any other observed combination — including `stage` already `"review"`,
`"done"`, or `"stalled"`, or `iteration_input <= recorded_iteration` — is a
duplicate or out-of-order dispatch: the job logs a step-summary note and
exits successfully, running no cycle, posting no comment, and dispatching
nothing (data-model.md).

## Configuration contract

| Variable/Label | Values | Behavior |
|---|---|---|
| `vars.SPECKIT_IMPLEMENT_MODEL` | unset (→ `claude-sonnet-5`), `claude-sonnet-5`, `claude-opus-4-8` | Normal-cycle model tier (FR-009) |
| `model:opus` label on the lifecycle issue | present/absent | Escalates the normal-cycle tier to `claude-opus-4-8` regardless of the variable (FR-009) |
| `vars.SPECKIT_MAX_ITERATIONS` | unset (→ `5`), positive integer | Hard cap on cycles (FR-005) |

## Cycle contract (per dispatched run that passes the idempotency guard)

1. Checkout `spec/$slug`; record `BASE_SHA` (current HEAD).
2. Resolve the normal-cycle model tier per the configuration contract above.
3. Agent step: run `/speckit-implement` (committing progress, message
   prefix `implement:`), then `/speckit-converge` (committing an appended
   `## Phase N: Convergence` section only if it finds gaps, message prefix
   `converge:`); update `spec-meta.json` (`stage: "implement"`,
   `iteration: <this cycle>`) as part of the implement commit; push.
   - **On outright failure** (the action step fails, or a post-step finds
     `spec-meta.json` wasn't updated as instructed — FR-013): if the tier
     used was not already `claude-opus-4-8`, retry the identical cycle once
     more at the next tier up. If that retry also fails, or the failing
     tier was already `claude-opus-4-8`, mark the specification `stalled`
     (see Stalled contract below) and stop — no finalize dispatch.
4. Deterministic step: walk `BASE_SHA..origin/spec/$slug` for a
   `converge:`-prefixed commit touching `$SPEC_DIR/tasks.md`.
   - Absent → **converged**.
   - Present → **not converged**; extract its appended task items for
     reporting.
5. Haiku step: post a progress comment to the lifecycle issue summarizing
   the cycle (commits made, converged/not-converged) — FR-008.
6. Outbound dispatch (deterministic, no agent turns):
   - **Converged** → `gh workflow run speckit-6-finalize.yml -f spec_dir=... -f issue=... -f converged=true` (FR-004).
   - **Not converged, `iteration_input < SPECKIT_MAX_ITERATIONS`** →
     `gh workflow run speckit-5-implement.yml -f spec_dir=... -f issue=... -f iteration=<iteration_input + 1>` (FR-003).
   - **Not converged, `iteration_input >= SPECKIT_MAX_ITERATIONS`** → post the
     remaining work (the last cycle's appended tasks) to the lifecycle issue
     (SC-005), then `gh workflow run speckit-6-finalize.yml -f spec_dir=... -f issue=... -f converged=false` (FR-006).

Exactly one of the two `gh workflow run` invocations above fires per
completed cycle — never both, never neither (FR-007).

## Stalled contract (exhausted-retry failure path, FR-013)

Triggered only when a cycle's attempt fails outright and no retry (or an
already-attempted retry) also fails:

- `spec-meta.json`'s `stage` is set to `"stalled"` (not `"implement"`) and
  committed to `spec/$slug`.
- The lifecycle issue's label transitions to `stage:stalled` (removing
  `stage:implement`).
- A comment reports the failure and that a maintainer must manually
  re-dispatch `speckit-5-implement.yml` for the same `iteration` to restart
  (no automatic restart — this is the sole exception FR-007 carves out from
  "always exactly one finalize hand-off").
- No `speckit-6-finalize.yml` dispatch occurs.

## Lifecycle issue contract

- **Every completed cycle** (converged or not): one Haiku-authored progress
  comment (FR-008); on the first cycle only, label transitions to
  `stage:implement` (removing `stage:tasks`).
- **Cap reached without convergence**: the remaining work from the final
  `converge:` commit is additionally reported on the issue (SC-005), then
  finalize is dispatched `converged=false`.
- **Converged**: finalize is dispatched `converged=true`; no additional
  label change here (finalize owns `stage:review`, `docs/architecture.md`
  §Stage 5, out of scope).
- **Stalled**: label `stage:stalled`; failure + manual-restart comment; no
  finalize dispatch.

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- The internal behavior of `/speckit-implement` and `/speckit-converge` —
  how code is written, how remaining work is judged — is unchanged by this
  feature.
- `speckit-6-finalize.yml`'s own behavior once dispatched (opening the final
  PR, etc.) — this feature only calls it with the inputs it already
  declares (`spec_dir`, `issue`, `converged`).
- The `"implement" → "review"` `spec-meta.json` transition and the
  `stage:review` label — owned by the finalize stage.
