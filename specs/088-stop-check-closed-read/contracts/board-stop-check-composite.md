# Contract: `wing-commander-board-stop-check`'s Reordered Steps and Output

This is the stage-internal contract this feature changes. It does not
change the composite's `inputs:`/`outputs:` names or shapes (Constitution
VII — see plan.md's Constitution Check), so it is **not** a change to a
`workflow_call` stage's published surface (`specs/010-reusable-pipeline/
contracts/stage-interfaces.md` is unaffected). It documents the contract
between:

1. the composite's caller (any of the seven `board-loop.yml` jobs) and the
   composite's declared inputs/outputs (unchanged names/shapes, changed
   internal computation);
2. the composite's own two-then-three internal steps.

## 1. Inputs and outputs (unchanged names and shapes)

| Name | Direction | Shape | Change |
|---|---|---|---|
| `token` | input | string (GitHub token) | none |
| `cancel-token` | input | string, default `github.token` | none |
| `issue-number` | input | string/number | none |
| `bot-login` | input | string | none |
| `initial-paused` | input | `"true"`/`"false"` | none |
| `check-issue-closed` | input | `"true"`/`"false"`, default `"false"` | none |
| `paused` | output | `"true"`/`"false"` | **computation changes** (§3) — name, shape, and meaning ("this job's next durable action must stand down") are unchanged |

## 2. Internal step order (before → after)

**Before** (as shipped, the FR-001/FR-002 defect):

```
1. closed-check   (id: closed-check, if: check-issue-closed=='true',
                    continue-on-error: true)
                   -> uses: wing-commander-lifecycle-gate
2. check           (id: check) reads steps.closed-check.outputs.is-open
                    via env ISSUE_IS_OPEN; computes paused
```

A total read failure in step 1 leaves `ISSUE_IS_OPEN` empty; step 2 still
runs (tolerated failure) and `paused` is computed from `initial-paused` and
the stop-request scan alone — the undocumented fail-open path.

**After** (this feature):

```
1. check           (id: check, unconditional) — kill-switch re-check +
                    stop-request scan + cancel side effect. No longer
                    reads anything from closed-check. Writes
                    steps.check.outputs.paused.
2. closed-check    (id: closed-check, if: check-issue-closed=='true',
                    NO continue-on-error)
                   -> uses: wing-commander-lifecycle-gate
                    Success: writes steps.closed-check.outputs.is-open.
                    Failure: step (and therefore this composite's own
                    `uses:` step in the caller) fails; step 3 still runs
                    (if:-scoped to this exact failure); the caller's later,
                    unguarded steps are skipped by GitHub's implicit
                    success() gate.
3. closed-check-note (id: closed-check-note,
                    if: steps.closed-check.outcome == 'failure')
                   -- ::error:: naming the issue number and the fail-loud
                    consequence (FR-004). Exits 0; does not change the
                    job's already-failed conclusion.
```

## 3. Output computation (before → after)

**Before**:
```yaml
outputs:
  paused:
    value: ${{ steps.check.outputs.paused }}
```

**After**:
```yaml
outputs:
  paused:
    value: >-
      ${{ steps.check.outputs.paused == 'true' ||
          (inputs.check-issue-closed == 'true' &&
           steps.closed-check.outputs.is-open == 'false') }}
```

For the six callers that never set `check-issue-closed: "true"`, the second
disjunct is always `false` (short-circuits on `inputs.check-issue-closed ==
'true'`), so `paused` is exactly `steps.check.outputs.paused` — unchanged
observable behavior.

## 4. Caller contract (`board-loop.yml`'s `prove` job) — unchanged, verified not to need edits

`prove`'s two durable-action steps already gate on
`steps.killswitch-recheck.outputs.paused != 'true'` with a bare `if:` (no
`success()`/`always()`/`failure()` of their own), which GitHub Actions
implicitly ANDs with `success()`. When step 2 (`closed-check`) fails
without `continue-on-error`, the calling `uses: ./.github/actions/
wing-commander-board-stop-check` step's own conclusion is `failure`, so
both downstream steps are skipped — satisfying Acceptance Scenario 4 ("the
job stops before its next durable action... the close-or-redrive step does
not run") with **zero changes to `board-loop.yml`**.

## 5. Failure-mode summary (replaces the old comment's false claim)

| `closed-check` outcome | `check.outputs.paused` | Composite `outputs.paused` | Job conclusion | `prove`'s close-or-redrive |
|---|---|---|---|---|
| not run (`check-issue-closed` unset) | any | = `check.outputs.paused` | success | runs iff not paused |
| success, OPEN | any | = `check.outputs.paused` | success | runs iff not paused |
| success, CLOSED | any | `true` | success | does not run (paused) |
| failure (any read failure, any attempt) | any | *(irrelevant — job already failed)* | **failure** | **does not run** |

The last row is FR-002's fail-loud policy: a total read failure costs one
deferred `prove` (the board loop's next scheduled run retries the same
item), never a silent proceed-as-open.

## What stays the same (explicitly out of this contract's scope)

- `wing-commander-lifecycle-gate/action.yml`'s own inputs, outputs, retry
  count, timeout, and error classification (FR-006).
- `watchdog.yml`'s `Collect: annotations` step and the diagnose classifier
  (FR-005/FR-006).
- `action.yml:171`'s `gh run cancel ... failed: $cancel_error`
  interpolation (FR-011, spec 087/#621).
- `find_stop_request()`, `is_stop_command()`, and the cancel-target
  workflow-path guard (unchanged logic, only their step's position in the
  file moves).
