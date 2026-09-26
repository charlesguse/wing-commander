# Contract: FR-009, FR-010 — Gate 60's `board-stop-check` check

## `.github/scripts/verify-single-home-idioms.py`, `check_board_stop_check()`

**Before**: file-wide literal co-occurrence of three fragments
(`BOARD_STOP_CHECK_FRAGMENTS`): `"from board_stop_check import
find_stop_request"`, `"gh run cancel"`, `"board-stop-check-comments.json"`.

**After**: a structural, per-step-list scan, following `check_token_mint()`'s
existing pattern (data-model.md, research.md D7):

1. YAML-parse the subject (`load_yaml`) — never grep the raw file text, same
   discipline `check_token_mint`, `check_failure_issue`, and
   `check_outstanding_task_item` already use.
2. Resolve every job's (or, for a composite action, the one `runs.steps`)
   step list via the existing `_step_lists(doc)` helper.
3. For each step list not under the declared home's own directory
   (`.github/actions/wing-commander-board-stop-check/`, same exclusion
   `check_dispatch_and_wait` already applies to its own home), concatenate
   the `run:` text of every step in that list and test two facts against the
   concatenation:
   - **Obtains a stop decision from the stop-check module**: matches
     `board_stop_check\.py` (the post-change CLI invocation) OR
     `from board_stop_check import find_stop_request` (the pre-change import
     style — kept so a paste of the *old* idiom is still caught, per FR-009's
     "regardless of the style it is written in").
   - **Performs a run cancellation**: contains `gh run cancel` (unchanged
     literal fragment; this fragment is not deleted by this feature).
4. A step list is a finding only when **both** facts are present somewhere
   within it (not merely somewhere in the file) — this is what lets
   Acceptance Scenario 3 hold: a file whose steps reference
   `board_stop_check.py` but orchestrate no cancellation is never flagged,
   because fact 2 never fires for it.

The `board-stop-check-comments.json` filename fragment is dropped entirely —
it named an implementation detail (a temp-file name), not the idiom's
essential shape, and is not needed once facts 1 and 2 already require
co-occurrence within one orchestration.

**Finding message**: unchanged format — `path:line: board-stop-check
(<detail>) -- see <declared home>` — `<detail>` now names which of the two
facts matched and where, rather than the removed three-fragment tuple.

## `DECLARED_HOMES["board-stop-check"]` comment (FR-010)

Rewritten to describe the post-change idiom: obtain a decision from
`board_stop_check.py`'s documented CLI (piping a comments/current-run/
bot-login payload to it), then `gh run cancel` whatever earlier run it names.
The comment keeps its issue-#462 provenance note; it drops any implication
that importing `find_stop_request` is how the declared home itself now
invokes the module (contracts/composite-invocation.md: it no longer does).

## `_clean_tree()`'s planted fixture (FR-010)

The synthetic fixture `_clean_tree()` writes at
`DECLARED_HOMES["board-stop-check"]` is rewritten from today's
three-literal-fragment shell (which includes the import line only as a
`# from board_stop_check import find_stop_request` comment, never executed)
to a shell that actually resembles the post-change idiom: pipes a payload to
`.github/scripts/board_stop_check.py` and calls `gh run cancel` on the
result — so `selftest_clean_tree_passes()` is exercising the shape Gate 60
must actually stay silent on once this feature ships, not a shape that
predates it.

## `run_selftest()`'s board-stop-check cases (FR-010)

Three self-test directions, matching User Story 3's Acceptance Scenarios:

1. **A planted second site, post-change style, is caught.** The existing
   `selftest_third_paste_fails("board-stop-check", ...)` call plants a
   workflow whose step pipes a comments payload to `.github/scripts/
   board_stop_check.py` and calls `gh run cancel` — the shape a future
   contributor would actually copy after this feature ships — and asserts a
   `board-stop-check` finding at that site (Acceptance Scenario 1).
2. **The declared home and any helper beside it stay silent.** Already
   covered by `selftest_clean_tree_passes()` once (1) above is rewritten
   (Acceptance Scenario 2).
3. **A legitimate non-loop consumer is not flagged.** A new self-test case
   plants a file whose steps reference `board_stop_check.py` (fact 1) but
   perform no `gh run cancel` (no fact 2) — e.g. a hypothetical future
   workflow that only runs `is_stop_command` for a dry-run report — and
   asserts **no** `board-stop-check` finding for that file (Acceptance
   Scenario 3, and FR-010's explicit third self-test direction).
4. **The gate's own `--self-test` passes in every direction, and the real
   gate suite stays green.** Covered by SC-006/Acceptance Scenario 4 —
   verified by running `python .github/scripts/run-local-gates.py` after the
   change, per quickstart.md.

The pre-change import-style third-paste case (if kept as a *second* variant
of case 1, proving the "regardless of style" half of FR-009) plants a
workflow using `from board_stop_check import find_stop_request` alongside
`gh run cancel` and asserts the same finding — proving the structural check
still catches the old style even though the declared home itself no longer
uses it.
