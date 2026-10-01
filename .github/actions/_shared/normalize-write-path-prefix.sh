#!/usr/bin/env bash
# .github/actions/_shared/normalize-write-path-prefix.sh
#
# The one home of the no-write-paths prefix canonicalization rule
# (specs/090-stage-write-boundary, review-gate-round-3: the classifier's
# Python normalize_prefix() and wing-commander-tool-args/action.yml's bash
# compose step each reimplemented "exactly one trailing slash" independently,
# kept in sync only by comments claiming parity, not a shared helper or a
# gate. Both callers now shell out to this script for the one canonical
# transform instead of re-deriving it.
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/normalize-write-path-prefix.sh" <prefix>
# Prints the normalized prefix (trimmed, exactly one trailing slash, "" for
# an empty/whitespace-only input) on stdout. Never fails -- normalization
# has no error case, only canonical and non-canonical input.
set -uo pipefail

prefix="${1-}"
# Trim leading/trailing whitespace the same way both callers already did
# before this script existed.
prefix="${prefix#"${prefix%%[![:space:]]*}"}"
prefix="${prefix%"${prefix##*[![:space:]]}"}"

if [ -z "$prefix" ]; then
  echo ""
  exit 0
fi

case "$prefix" in
  */) echo "$prefix" ;;
  *) echo "${prefix}/" ;;
esac
