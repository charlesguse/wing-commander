#!/usr/bin/env bash
# size-path-measure.sh -- measure a drafted change for the small-change size
# backstop (specs/057-autonomous-board-loop research.md D5).
#
# Reads one drafted-content.file-changes array ([{"path", "diff"}, ...]) on
# stdin and prints `<files> <lines>` on one line: the entry count, and the
# unified-diff lines starting with '+' or '-' summed across every entry's
# diff, the '+++'/'---' file-header lines excluded. Pure measurement: each
# caller compares the counts with its own threshold.
#
# The one home of that formula (CLAUDE.md "Shared logic has exactly one
# home"). Two callers:
#   - the wing-commander-size-path-backstop composite (board-loop.yml's
#     route job), as `bash "$GITHUB_ACTION_PATH/../../scripts/size-path-measure.sh"`;
#   - pr-conversation.yml's "Compute confirmation requirements" step, once
#     per small-unrelated-change leg, as `bash .wing-commander-pipeline/.github/scripts/size-path-measure.sh`
#     (#734/#850: the jq that re-routes an over-threshold leg reads the
#     counts this prints instead of carrying its own copy).
# Gate 60 (verify-single-home-idioms.py, check `size-path-backstop`) fails
# on a copy of the formula anywhere else under .github/workflows or
# .github/actions. It lives in .github/scripts, not .github/actions/_shared,
# because a published workflow may not reach into _shared (Gate 60's
# promotion check) and both callers' checkouts already carry .github/scripts.
#
# Invoke with `bash size-path-measure.sh`, never the file itself, so its
# executable bit is never load-bearing. Exits non-zero, printing nothing on
# stdout, when jq cannot measure the input.
set -euo pipefail

fc="$(cat)"
files="$(printf '%s' "$fc" | jq 'length')"
lines="$(printf '%s' "$fc" | jq '
  [.[] | (.diff // "") | split("\n")[]
    | select(test("^[+-]") and (test("^(\\+\\+\\+|---)") | not))
  ] | length')"
printf '%s %s\n' "$files" "$lines"
