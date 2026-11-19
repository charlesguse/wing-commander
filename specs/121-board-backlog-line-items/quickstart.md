# Quickstart: Validating Board Backlog Lines

## Local (no network)

1. Run the full gate suite: `python .github/scripts/run-local-gates.py`. It must include `verify-board-backlog-lines.py` and `verify-board-backlog-edit.py`, and pass.
2. Each of those gates runs its fixtures under `.github/scripts/tests/board-backlog-lines/` and `.../board-backlog-edit/`. Expected: every branch in `contracts/backlog-lines.md` has a passing fixture, and removing a branch's code makes its fixture fail.
3. Spot-check selection: feed `{"op":"select","body":"<sample body>"}` as JSON on stdin to `python .github/scripts/board_backlog_lines.py`. Expected: the topmost unchecked, unannotated, top-level line; a fenced or nested checkbox is not chosen.

## Interleaving check

Run the edit-helper fixture that appends a line and ticks another between the helper's read and write. Expected: both concurrent changes survive and only the loop's line differs from the concurrent body (SC-003).

## After merge (Actions only; `prove-after-merge`)

Preconditions: constitution amendment #1115 merged; `WING_COMMANDER_BOARD_BACKLOG_LINES=true`; no eligible issue waiting; one fix-shaped line on the backlog.

1. Dispatch `board-loop.yml` (`gh workflow run`). Expected: the line gains `[wc:bl-… in-progress]`; the run summary names `#889 line bl-…`.
2. Let the fix PR open. Expected: branch `fix/<backlog>-bl-…`, title `Fix: <line text>`, body with `Backlog line:`, no closing keyword anywhere.
3. Merge (loop or human). Expected: the line is ticked with `fixed by #PR`, the backlog issue stays open and unlabelled changes none.
4. Set the switch off mid-run on a second line. Expected: the claimed line finishes; no new claim.
5. Record run links on the PR or the issue.
