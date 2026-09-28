# Contract: FR-001–FR-004, FR-006, FR-010, FR-011 — the board-stop-check cancel branch

`research.md` D3–D5 explain the design; `data-model.md`'s "Cancellation
outcome" table gives the outcome/reporting matrix this contract pins down
for the composite specifically.

## `.github/actions/wing-commander-board-stop-check/action.yml`, `check` step (MODIFIED)

**Removed**:
- The `cancel_target_status` extraction line (`jq -r '.status // empty'`).
- The `elif [ "$cancel_target_status" != "completed" ]` branch condition —
  no execution-state value gates whether `gh run cancel` runs (FR-001,
  FR-002, SC-006).

**Unchanged**: the ownership guard immediately above it
(`cancel_target_path`/`cancel_target_repo`, the `own_workflow_path`
comparison) — still the sole gate on whether a cancellation is attempted at
all (FR-006, User Story 3). The `GH_TOKEN`/`CANCEL_TOKEN` split (App token
for the issue-comment read, cancel-token for the metadata read and the
cancel call) is unchanged (FR-006).

**Added**, once the ownership guard passes:
```
if ! cancel_error="$(GH_TOKEN="$CANCEL_TOKEN" gh run cancel "$stop_run_id" -R "$GITHUB_REPOSITORY" 2>&1)"; then
  if bash "$GITHUB_ACTION_PATH/../_shared/cancel-already-terminal.sh" "$cancel_error"; then
    echo "run $stop_run_id had already finished before the cancel attempt; nothing was cancelled"
  else
    safe_cancel_error="$(sanitize "$cancel_error")"
    echo "::warning::gh run cancel $stop_run_id failed: $safe_cancel_error"
  fi
fi
```
(exact wording of the informational line is left to `/speckit-tasks`; the
constraints below are the contract.)

A local `sanitize()` function (newline/tab flatten, collapse repeated
whitespace, 300-char truncate, `%`-escape — the same idiom
`wing-commander-lifecycle-gate`'s `check` step already defines for itself,
`research.md` D4) is added to this step's script and applied to
`$cancel_error` before it reaches the `::warning::` line (FR-011).

**Invariant, every branch** (FR-006):
- The step's own exit status is unaffected by which branch runs.
- `paused=true` is still set unconditionally once an authorized,
  unactioned stop request was found — unchanged from before this feature,
  and not conditioned on the cancellation outcome in any of the three rows.

## Outcome → reporting matrix (this site only)

| Outcome | Emits | Annotation-collector-visible? |
|---|---|---|
| `cancelled` (`gh run cancel` exits 0) | nothing | no |
| `already-terminal` (exit ≠0, vocabulary match) | one plain `echo` line naming `$stop_run_id` | **no** — no `::notice::`/`::warning::`/`::error::` prefix (FR-010; `watchdog.yml`'s "Collect: annotations" step only fetches annotation-shaped output) |
| `failed` (exit ≠0, no vocabulary match, including empty `$cancel_error`) | one `::warning::` naming `$stop_run_id`, carrying the sanitised error text | yes (FR-004) |

## Comment correction (CLAUDE.md: workflow comments are load-bearing)

The step's existing header comments describing the status-gated design
("already be terminal... `gh run cancel` on a completed run always 409s...
`completed` is the one value that always means...", the "peer review of
#465, round 2" cross-reference) describe the branch this feature removes.
They must be rewritten to describe the unconditional-attempt-then-classify
replacement and its own rationale, not deleted silently — a stale
justification for removed code is the exact defect class
`specs/088-stop-check-closed-read` was opened over.

## Fixture and mutation coverage (FR-007, FR-008)

See `contracts/gate-coverage-087.md`.
