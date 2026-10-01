#!/usr/bin/env bash
# .github/actions/_shared/match-issue-by-marker.sh
#
# The one home of "which issue in this JSON array carries this marker in
# its body" (review-gate-round-1 item 6). wing-commander-write-boundary-
# lookup and wing-commander-durable-failure-issue each pasted this jq
# filter in full; this is the single copy both now call.
#
# Invoke with
#   bash .../_shared/match-issue-by-marker.sh <issues-json-file> <marker> [<marker> ...]
# Prints one line per marker argument, in order: the first matching issue
# object ({number,url,state,body}) as compact JSON, or the literal `null`
# if that marker matched nothing. `null` (never an empty line) so a
# caller splitting stdout by line never loses alignment between markers
# and output lines.
#
# review-gate-round-4 item 9: accepts one or more trailing markers against
# the SAME issues-json-file, re-reading and re-parsing the file ONCE
# regardless of marker count -- wing-commander-write-boundary-lookup's own
# per-unchecked-line loop used to call this once per line, forking jq and
# re-parsing the whole issues file each time, even though the sibling
# fingerprint call in the same loop was already batched
# (compute-finding-fingerprint.sh). Backward compatible: a single-marker
# call (wing-commander-durable-failure-issue's own shape) still prints
# exactly one line.
set -uo pipefail

ISSUES_FILE="${1-}"
shift || true

if [ -z "$ISSUES_FILE" ] || [ "$#" -eq 0 ]; then
  echo "match-issue-by-marker.sh: usage: match-issue-by-marker.sh <issues-json-file> <marker> [<marker> ...]" >&2
  exit 1
fi

for marker in "$@"; do
  jq -c --arg marker "$marker" \
    '[.[] | select(.body != null and (.body | contains($marker)))] | first' \
    "$ISSUES_FILE"
done
