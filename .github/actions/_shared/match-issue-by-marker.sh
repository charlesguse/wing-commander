#!/usr/bin/env bash
# .github/actions/_shared/match-issue-by-marker.sh
#
# The one home of "which issue in this JSON array carries this marker in
# its body" (review-gate-round-1 item 6). wing-commander-write-boundary-
# lookup and wing-commander-durable-failure-issue each pasted this jq
# filter in full; this is the single copy both now call.
#
# Invoke with
#   bash .../_shared/match-issue-by-marker.sh <issues-json-file> <marker>
# Prints the first matching issue object ({number,url,state,body}) as JSON
# on stdout, or an empty string if none matched.
set -uo pipefail

ISSUES_FILE="${1-}"
MARKER="${2-}"

if [ -z "$ISSUES_FILE" ] || [ -z "$MARKER" ]; then
  echo "match-issue-by-marker.sh: usage: match-issue-by-marker.sh <issues-json-file> <marker>" >&2
  exit 1
fi

jq -c --arg marker "$MARKER" \
  '[.[] | select(.body != null and (.body | contains($marker)))] | first // empty' \
  "$ISSUES_FILE"
