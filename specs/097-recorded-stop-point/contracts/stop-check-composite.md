# Contract: `wing-commander-board-stop-check` — new surface (FR-001, FR-002, FR-011–FR-014, FR-018)

This extends, additively, the composite `specs/085-stop-request-cancel-
contract/contracts/composite-invocation.md` already describes. That
contract's "Unchanged surface (FR-008)" clause remains true to the letter
after this feature: every existing input/output keeps its name, default,
description, and meaning. Nothing in this document may be read as
permission to rename or repurpose `paused`, `token`, `cancel-token`,
`issue-number`, `bot-login`, `initial-paused`, or `check-issue-closed`.

## New inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `marker-branch` | no | `""` | The item's currently-known branch name (from `needs.select.outputs.branch`), passed through to the stop-point record's marker when a stop is honoured. Empty for an item with no branch yet (triage/route). |
| `marker-base-sha` | no | `""` | The item's currently-known base commit (from `needs.select.outputs.base-sha`), passed through the same way. |

Both inputs are inert unless `stop-cause` resolves to `"stop-request"` —
passing them on a kill-switch-only or closed-issue stand-down has no
effect, since no marker is written on those paths (FR-011/FR-013).

## New output

| Name | Description |
|---|---|
| `stop-cause` | One of `""`, `"closed-issue"`, `"kill-switch"`, `"stop-request"` — see data-model.md "Stand-down cause." `paused` is unchanged and remains `true` iff `stop-cause != ""`. |

## Decision order (single evaluation, inside the existing `check` step)

```text
1. if check-issue-closed == "true" and the issue reads closed:
     stop-cause = "closed-issue"
2. elif find_stop_request(comments, run_id, bot_login).stand_down:
     stop-cause = "stop-request"
3. elif initial-paused == "true":
     stop-cause = "kill-switch"
4. else:
     stop-cause = ""
paused = (stop-cause != "")
```

This order is deliberate: a closed issue suppresses recording even when an
authorized stop request is also present (spec 097 edge cases: "the loop
does not comment on an issue a human deliberately closed"), and a stop
request takes priority over the kill switch (FR-012).

The existing `cancel_run_id` handling (the `gh run cancel` sequence and its
guards) is unchanged in every respect and unaffected by `stop-cause`.

## Recording (new steps, gated on `stop-cause == "stop-request"`)

1. `gh issue view "$ISSUE_NUMBER" -R "$GITHUB_REPOSITORY" --json labels` —
   a fresh read. If the result already contains `board:stalled`, skip to
   step 4 (idempotency; research.md D6). This step's own failure is treated
   the same as "label not present yet" would be unsafe (it must fail
   loudly, not silently proceed to a possible duplicate write) — implement
   with the same fail-loud idiom the closed-check step already lacks
   deliberately (`continue-on-error: true` there is a documented exception,
   `action.yml:78-86`) but this new read is **not** given that exception:
   an unreadable label state must not be guessed.
2. Identify the winning comment and its reason:
   ```bash
   stop_comment_json="$(jq -n --slurpfile comments "$RUNNER_TEMP/board-stop-check-comments.json" \
     --arg run_id "$GITHUB_RUN_ID" --arg bot_login "$BOT_LOGIN" \
     '{comments: $comments[0], current_run_id: $run_id, bot_login: $bot_login}' \
     | python3 -I "$GITHUB_ACTION_PATH/../../scripts/board_stop_check.py" --stop-comment)"
   ```
   (exact CLI flag/subcommand shape is a tasks-stage detail; the contract is
   that this reuses `find_stop_command_comment()`/`stop_command_reason()`
   from `board_stop_check.py`, run from the composite's own trusted
   directory per D8's addendum, never a second re-implementation of the
   match rule in shell/jq. `current_run_id` is required — maintainer review
   fold leg-1, FR-006/FR-008 — so this run's own not-yet-posted stop-point
   record can never be mistaken for a different run's marker when the
   baseline is recomputed). Both the subprocess's own exit status AND its
   output shape are checked (maintainer review fold leg-4, FR-017): a
   non-zero exit fails loudly immediately; `jq -e '.html_url | type ==
   "string"'` then rejects an empty `{}` result too, since `stop-cause ==
   "stop-request"` already means `find_stop_request()` found a winner, so
   Gate 135 check 4's invariant guarantees `find_stop_command_comment()`
   finds one too — an empty result here means the two disagreed, not that
   there is legitimately nothing to record, and must not be accepted as
   data (the pre-fix shape posted a record with blank fields instead of
   failing). A one-line `gh label create "board:stalled" ... --force`
   fallback precedes step 3's marker write — maintainer review fold
   leg-0/leg-2: every caller already ensures this label exists via
   `wing-commander-board-labels` before reaching this composite, but
   `verify-board-label-creation.py` is job-scoped with no cross-file
   fallback, and a nested `uses: ./.github/actions/wing-commander-board-
   labels` step here was exactly the leg-2 RCE.
3. Write the record:
   ```bash
   marker="$(python3 -I "$GITHUB_ACTION_PATH/../../scripts/board_item_marker.py" \
     --step stalled --issue "$ISSUE_NUMBER" --add-label "board:stalled" \
     ${MARKER_BRANCH:+--branch "$MARKER_BRANCH"} \
     ${MARKER_BASE_SHA:+--base-sha "$MARKER_BASE_SHA"})" \
     || { echo "::error::wing-commander-board-stop-check: board:stalled could not be added to issue #$ISSUE_NUMBER -- no stop-point record is posted, so a later run retries the check (FR-017)."; exit 1; }
   ```
   then post the comment (contracts/stop-point-record.md), checking its own
   exit code and failing loudly on error (research.md D5 step 3).
4. Proceed; `paused`/`stop-cause` outputs are unaffected by whether step 1
   short-circuited.

## Provenance (FR-018, spec 095 FR-011/FR-012)

Both the existing `board_stop_check.py` invocation and the new
`board_item_marker.py` invocation in this composite's `run:` step execute
as `python3 -I "$GITHUB_ACTION_PATH/../../scripts/<name>.py"` — never a
bare `.github/scripts/<name>.py` workspace-relative path, and never a
caller-populated `$RUNNER_TEMP/wc-pristine` snapshot either (maintainer
review fold leg-0 supersedes research.md D8's original design: every
caller already invokes this composite as `./.wc-pristine-repo/.github/
actions/wing-commander-board-stop-check`, so `$GITHUB_ACTION_PATH` —
GitHub Actions' own ambient variable naming where a composite's action.yml
was loaded from — always points inside that same trusted checkout, spec
086 FR-003; no second, composite-populated snapshot is needed).

## Acceptance mapping

- User Story 1, AS1/AS5 — `stop-cause == "stop-request"` gates the record
  write regardless of `initial-paused` (decision order step 2 before 3).
- User Story 1, AS4 — `stop-cause == "kill-switch"` never reaches the
  recording block.
- User Story 2, AS3 — the idempotency check (recording step 1) makes a
  second reach of this composite within the same honoured stop a no-op
  write.
- Edge case "issue already closed" — decision order step 1 takes priority
  over step 2 unconditionally.
