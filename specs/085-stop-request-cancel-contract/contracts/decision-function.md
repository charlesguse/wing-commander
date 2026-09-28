# Contract: FR-001, FR-002, FR-003, FR-005 — `board_stop_check.py`'s decision function and CLI

## `find_stop_request(comments, current_run_id, bot_login) -> StopDecision`

**Unchanged inputs**: `comments` (a list of `{"body", "author_association",
"created_at", "user": {"login", "type"}}`, any order — sorted internally by
`created_at`), `current_run_id`, `bot_login`. The baseline computation (the
most recent bot-authored `**Run:**` marker), the maintainer-association rule,
and the stop-command rule (`is_stop_command`) are all unchanged (FR-012).

**Changed return value**: `StopDecision(stand_down: bool, cancel_run_id:
str | None)` (data-model.md) in place of the previous bare `str | None`.

- `stand_down` is `True` iff an authorized, unactioned stop request exists at
  or after the baseline (FR-002) — this is exactly the previous "return
  value is truthy" condition, now named explicitly rather than implied by a
  non-`None` return.
- `cancel_run_id` is the earlier run's id when one announced itself
  (`last_other_run_id`, unchanged computation), and `None` in every other
  case — including, per FR-003, the case where the only run announcement
  found is the current run's own. **The function MUST NOT return the current
  run's own id as `cancel_run_id` under any input.** This is the one
  behavioural change from today's function: today's fallback
  (`last_other_run_id if last_other_run_id is not None else current_run_id`)
  is replaced by a fallback to `None`.

**Docstring**: rewritten to state the two-fact contract in its own terms —
no sentence may describe the return value as "the run_id (str) to `gh run
cancel`" (today's inaccurate sentence FR-005 exists to fix) — and to state
plainly that the current run is never a valid `cancel_run_id`.

## `main()`

**Unchanged**: reads one JSON object from stdin —
`{"comments": [...], "current_run_id": "...", "bot_login": "..."}` — exactly
as today.

**Changed stdout contract**: on success, prints exactly one line — the JSON
object `{"stand_down": <bool>, "cancel_run_id": <string> | null}` — computed
by calling `find_stop_request()` and serializing its `StopDecision`
(`json.dumps(decision._asdict())` or equivalent). This differs from today's
`main()`, which prints the bare run id and prints **nothing** when there is
no stop request; the new contract always prints one JSON object on success,
so a caller can distinguish "computed: no stop" (valid JSON, `stand_down:
false`) from "did not compute" (no stdout, non-zero exit).

**Unchanged failure behaviour**: a malformed payload (bad JSON, wrong shape)
raises inside `json.load`/dict access, printing a traceback to stderr and
exiting non-zero, with nothing written to stdout — already true of today's
`main()` and requires no new code.

## Docstring accuracy (FR-005)

Every docstring in this module that describes `find_stop_request()`'s or
`main()`'s return value — the module docstring's own summary line,
`find_stop_request()`'s docstring, and `main()`'s docstring — is updated in
the same change so that none of them describes a shape the function no
longer has. This is what closes defect 1 from the spec's Overview: the
caller no longer has to know that "the run_id it was handed is really its
own," because the function's own contract states plainly when there is
nothing to cancel.

## What does not change

- `is_stop_command`, `STOP_COMMAND_RE`, `_command_line` — the stop-command
  rule (issue #539).
- `last_run_match`, `MARKER_RUN_RE` — the last-`**Run:**`-line rule (issue
  #580).
- `is_loop_marker_author` (imported from `board_item_marker`) — the
  marker-author rule (issue #547).
- The baseline computation and the maintainer-association check.

None of these are touched by this feature; FR-012 requires every existing
fixture and command case to produce the same *outcome* (which run gets
cancelled, if any; whether the job stands down) before and after this
change — only the shape the outcome is expressed in changes.
