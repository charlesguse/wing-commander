#!/usr/bin/env bash
# .github/actions/_shared/normalise-transcript.sh
#
# The one place that turns an agent execution transcript into the shape
# every reader of it expects: one flat JSON array of objects (#572). Used by
# count-turns.sh (beside this file), wing-commander-agent-verdict and
# wing-commander-metrics-summary, which resolve it as
# "$GITHUB_ACTION_PATH/../_shared/normalise-transcript.sh". Gate 60
# (verify-single-home-idioms.py, check "transcript-normalise") fails if the
# jq program below is pasted anywhere else under .github/.
#
# Invoke with `bash .../normalise-transcript.sh "$TRANSCRIPT"`, never
# directly, so the executable bit is never load-bearing (see
# count-turns.sh).
#
# Accepted shapes: one JSON array, one object, NDJSON, or several
# concatenated documents. `jq -s` collects the documents and any document
# that is itself an array is spliced in, so all four read the same. Read
# per document instead, NDJSON made every per-record jq print one line per
# document -- the `eval` of count-turns.sh's output then ran a bare "0" as
# a command (exit 127, #551). Non-object elements (a bare number, string,
# `null` or `false`) are then dropped: `.type` on a number is a jq error
# that `|| true` swallows, hiding a real result record, and a trailing
# `false` must not make the whole transcript read as unparseable.
#
# Contract:
#   - $1 is the transcript path.
#   - On success: exactly one line on stdout, the compact array (possibly
#     `[]`), exit 0.
#   - When the path is missing, not a file, empty, or does not parse as
#     JSON: nothing on stdout, exit 1. Never partial output.
set -uo pipefail

TRANSCRIPT="${1:-}"

if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ] || [ ! -s "$TRANSCRIPT" ]; then
  exit 1
fi

normalised="$(jq -cs 'map(if type=="array" then .[] else . end) | map(objects)' \
                "$TRANSCRIPT" 2>/dev/null)" || exit 1
[ -n "$normalised" ] || exit 1
printf '%s\n' "$normalised"
