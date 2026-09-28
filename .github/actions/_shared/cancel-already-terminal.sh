#!/usr/bin/env bash
# .github/actions/_shared/cancel-already-terminal.sh
#
# The one place that recognises a `gh run cancel` failure as "this run had
# already finished before the cancel attempt" (#621). Used by
# wing-commander-board-stop-check (resolved as
# "$GITHUB_ACTION_PATH/../_shared/cancel-already-terminal.sh") and
# pr-conversation.yml's Stop procedure (resolved by repo-root-relative
# path). Gate 60 (verify-single-home-idioms.py, check
# "cancel-already-terminal") fails if this vocabulary is pasted anywhere
# else under .github/.
#
# Invoke with `bash .../cancel-already-terminal.sh "$ERROR_TEXT"`, never
# sourced, never relying on the executable bit -- same invocation
# discipline normalise-transcript.sh documents for itself.
#
# Contract:
#   - $1 is the raw error/stderr text captured from a failed
#     `gh run cancel` call.
#   - Exit 0 when $1 case-insensitively contains "HTTP 409" (protocol-
#     prefixed -- bare digits "409" alone, e.g. inside a run id or URL a
#     permission error happens to quote, must NOT match), "already
#     completed", or "cannot cancel". Exit 1 otherwise.
#   - No stdout -- this is a predicate, not a transform; callers branch on
#     the exit code.
set -uo pipefail

error_text="${1:-}"

if printf '%s' "$error_text" | grep -qiE 'http 409|already completed|cannot cancel'; then
  exit 0
else
  exit 1
fi
