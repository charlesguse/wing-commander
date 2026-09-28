# Contract: FR-005, FR-009 — the already-terminal vocabulary has one home

`research.md` D1/D2 explain why this is a new `_shared/*.sh` predicate
script rather than a jq program or a sourced function.

## `.github/actions/_shared/cancel-already-terminal.sh` (NEW)

**Invocation**: `bash .github/actions/_shared/cancel-already-terminal.sh "$ERROR_TEXT"`
— positional arg 1 is the raw error/stderr text captured from a failed
`gh run cancel` call. Never sourced; never relies on its executable bit
(matches `_shared/normalise-transcript.sh`'s and
`_shared/auto-release-verdict.sh`'s own invocation idiom).

**Exit status is the entire contract**:
- `0` — `$ERROR_TEXT` identifies the target as one that can no longer be
  cancelled (an "already-terminal refusal").
- `1` — it does not; the caller must treat the cancellation as a real
  failure.

No stdout output is defined or required; this is a predicate, not a
transform, so callers branch on `$?`, not on captured output.

**Matching rule** (case-insensitive substring, any one signature
sufficient — `data-model.md`'s "Already-terminal vocabulary" table):
- `HTTP 409` — protocol-prefixed; the bare digits `409` alone (e.g. inside a
  run id or URL a permission error happens to quote) MUST NOT match
  (FR-005, Edge Cases).
- `already completed`
- `cannot cancel`

A match on a signature that merely appears as a substring of an otherwise
unrelated error is accepted as already-terminal — spec.md's Edge Cases
names this as a deliberate trade-off inherited from the vocabulary this
script consolidates, not a defect to fix here.

## Call sites (2)

1. `.github/actions/wing-commander-board-stop-check/action.yml`, `check`
   step: `bash "$GITHUB_ACTION_PATH/../_shared/cancel-already-terminal.sh" "$cancel_error"`
   (composite invocation, per `_shared/normalise-transcript.sh`'s own
   consumption pattern in `wing-commander-agent-verdict`).
2. `.github/workflows/pr-conversation.yml`, "Stop procedure" step:
   `bash .github/actions/_shared/cancel-already-terminal.sh "$(cat "$RUNNER_TEMP/cancel-err.txt")"`
   (plain workflow job, repo-root-relative invocation, per
   `_shared/auto-release-verdict.sh`'s own consumption from `auto-release.yml`).

Each site keeps its own reporting downstream of the `if`/exit-code branch —
FR-009 is explicit that only the vocabulary is shared, not the procedure.
See `contracts/board-stop-check-classification.md` and
`contracts/pr-conversation-vocabulary-consolidation.md` for what each site
does with the outcome.

## Gate coverage (FR-009a)

`.github/scripts/verify-single-home-idioms.py` gains a `DECLARED_HOMES`
entry `"cancel-already-terminal": ".github/actions/_shared/cancel-already-terminal.sh"`
and a structural check, registered in `CHECK_NAMES` alongside
`"board-stop-check"` (`research.md` D7): any file outside the declared home
whose text co-occurrences all three vocabulary fragments (`HTTP 409`,
`already completed`, `cannot cancel`) in one recognition construct is
flagged — the same co-occurrence style `check_board_stop_check` and
`check_dispatch_and_wait` already use so an unrelated single mention of one
phrase (e.g. in a comment) does not false-positive. A mutation that
reintroduces a bare-`409` third copy must be caught by this check
(SC-007).
