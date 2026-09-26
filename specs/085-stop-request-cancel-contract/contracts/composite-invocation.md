# Contract: FR-004, FR-006, FR-007, FR-008 — the composite's `check` step

## `.github/actions/wing-commander-board-stop-check/action.yml`, step `check`

**Unchanged surface (FR-008)**: `inputs` (`token`, `cancel-token`,
`issue-number`, `bot-login`, `initial-paused`, `check-issue-closed`) and
`outputs.paused` keep their names, defaults, descriptions, and meaning. The
`closed-check` step (the `prove` job's extra pre-check), the App-token/
cancel-token split, the `completed`-status check, and the workflow-path and
repository target guards are all unchanged in behaviour.

**Unchanged**: the paginated comment read —

```bash
gh api "repos/$GITHUB_REPOSITORY/issues/$ISSUE_NUMBER/comments" --paginate \
  --jq '.[] | {body, author_association, created_at, user: {login: .user.login, type: .user.type}}' | jq -s '.' \
  > "$RUNNER_TEMP/board-stop-check-comments.json"
```

stays exactly as today — same App token, same shape, same temp file.

**Changed (FR-006)**: the inline `python3 -c` block that inserts
`.github/scripts` onto `sys.path` and imports `find_stop_request` is removed.
In its place, the step assembles the same stdin payload `board_stop_check.py
main()` already documents (contracts/decision-function.md) — the comments
array just written, plus `$GITHUB_RUN_ID` and `$BOT_LOGIN` — and pipes it
directly into the module's CLI, e.g.:

```bash
stop_decision_json="$(jq -n --slurpfile comments "$RUNNER_TEMP/board-stop-check-comments.json" \
  --arg run_id "$GITHUB_RUN_ID" --arg bot_login "$BOT_LOGIN" \
  '{comments: $comments[0], current_run_id: $run_id, bot_login: $bot_login}' \
  | python3 .github/scripts/board_stop_check.py)"
```

No `sys.path` manipulation, no module import, appears anywhere in this step
(User Story 2's independent test and SC-002: "zero lines that import or
path-bootstrap the stop-check module").

**Changed (FR-007, "fail loudly")**: the captured `stop_decision_json` is
validated before either field is read — e.g. `jq -e '.stand_down |
type=="boolean"' >/dev/null <<<"$stop_decision_json"` — failing the step with
an explicit `::error::` if it does not hold. Combined with the shell's own
`set -e`/`pipefail` already failing the step whenever the `python3` process
itself exits non-zero, a malformed payload, a crash, or a non-zero exit from
`board_stop_check.py` all fail the step; none of them silently resolve to
`paused=false`.

**Changed (FR-004)**: the two fields are read from the validated JSON —

```bash
stand_down="$(jq -r '.stand_down' <<<"$stop_decision_json")"
cancel_run_id="$(jq -r '.cancel_run_id // empty' <<<"$stop_decision_json")"
```

and the existing cancel-guard sequence keeps exactly one shell comparison of
`cancel_run_id` against `$GITHUB_RUN_ID`, in the same position it occupies
today (guarding entry into the whole unreadable-run/workflow-path/repository/
completed-status sequence), with its comment rewritten to state:

- this check is deliberately redundant with `find_stop_request()`'s own
  contract (contracts/decision-function.md: the function never returns the
  current run as `cancel_run_id`);
- the function's contract, mutation-proven under FR-011
  (contracts/gate-87-coverage.md), is the primary guard;
- the check is kept anyway because a `gh run cancel` is not recoverable by
  retry — the same reasoning already written beside the workflow-path and
  repository-target guards in this step.

`paused` is then computed exactly as today: `true` when `$stand_down` is
`true` (or the issue is already closed, per the unchanged `closed-check`
step), `false` otherwise.

## Acceptance mapping

- User Story 2, Acceptance Scenario 1 (no import/`sys.path` line) — satisfied
  by the FR-006 change above.
- User Story 2, Acceptance Scenario 2 (a payload the module cannot parse
  fails the step loudly) — satisfied by the FR-007 change above; Gate 87
  gains a composite-shell fixture exercising this (contracts/gate-87-
  coverage.md).
- User Story 2, Acceptance Scenario 3 (unchanged inputs/outputs) — satisfied
  by FR-008, unchanged in this contract.
- User Story 1, Acceptance Scenario 4 (removing the redundant shell check
  still passes every checked-in case) — the invariant this scenario depends
  on is `find_stop_request()`'s own contract (contracts/decision-function.md),
  which SC-002/SC-004 already require to be mutation-proven independent of
  this shell comparison.
