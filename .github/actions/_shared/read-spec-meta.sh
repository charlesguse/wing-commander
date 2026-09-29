#!/usr/bin/env bash
# .github/actions/_shared/read-spec-meta.sh
#
# The one place that reads a specification's spec-meta.json off the tip of
# its spec branch (#340). Before this, the fetch-then-`git show`-then-jq
# idiom was pasted into implement.yml (both read-back steps), plan.yml,
# tasks.yml and wing-commander-inspected-run-identity, and only the last
# copy checked that the file identifies the directory it was read from — a
# fix to how the record is read safely had to land in five places with
# nothing failing on a drifted copy (CLAUDE.md, "Shared logic has exactly
# one home"). Composites source it as
# "$GITHUB_ACTION_PATH/../_shared/read-spec-meta.sh"; stage workflows reach
# it only through the wing-commander-spec-meta composite (spec 049 FR-022:
# _shared/ is not part of the adopter-pinned surface). Gate 61
# (verify-spec-meta-single-home.py) fails on any other `git show` of a
# branch's spec-meta.json.
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/read-spec-meta.sh" <spec-prefix> <slug> [<spec-dir>]
# — `bash file`, never the file itself, so its executable bit (which a plain
# checkout does not reliably preserve) is never load-bearing (count-turns.sh,
# same reason).
#
# Fetches refs/heads/<spec-prefix><slug> into refs/remotes/origin/<same>
# (forced, so a branch the rebase stage rewrote is re-read at its new tip).
# A fetch failure never fails the script, but it is not read through
# either: the local tracking ref is dropped first, so a branch that is
# gone (or a fetch that did not happen) reads as "no record", never as
# whatever an earlier step left under that ref. Then reads
# <spec-dir>/spec-meta.json (default specs/<slug>) from the ref. Prints
# `key=value` lines on stdout:
#   meta_fetch_ok=true|false     the forced fetch of the branch succeeded
#   meta_found=true|false        the file exists on the branch and parses as JSON
#   meta_identity_ok=true|false  its .spec_dir names exactly <spec-dir> — the
#                                self-identity check every reader must apply
#                                before trusting .issue/.stage/.iteration: a
#                                record that identifies some other directory
#                                is not this specification's record
#   meta_spec_dir=<specs/... or empty>
#   meta_issue=<digits or empty>
#   meta_stage=<word or empty>
#   meta_iteration=<digits or empty>
# Never exits non-zero. Callers `eval` the output, which is safe because every
# value is empty or matches the character class named for it — anything else
# found in the file is dropped, never passed through (constitution V).
set -uo pipefail

SPEC_PREFIX="${1:-}"
SLUG="${2:-}"
SPEC_DIR="${3:-}"
[ -n "$SPEC_DIR" ] || SPEC_DIR="specs/$SLUG"

meta_fetch_ok=false
meta_found=false
meta_identity_ok=false
meta_spec_dir=""
meta_issue=""
meta_stage=""
meta_iteration=""

# field JSON FILTER  -> the jq -r result, or empty on any error.
field() { printf '%s' "$1" | jq -r "$2" 2>/dev/null || true; }
# only VALUE ERE     -> VALUE when it matches the whole-line pattern, else empty.
only() { printf '%s' "$1" | grep -E "$2" || true; }

if [ -n "$SLUG" ]; then
  branch="${SPEC_PREFIX}${SLUG}"
  if git fetch --no-tags --quiet origin "+refs/heads/${branch}:refs/remotes/origin/${branch}" 2>/dev/null; then
    meta_fetch_ok=true
  else
    git update-ref -d "refs/remotes/origin/${branch}" 2>/dev/null || true
  fi
  if meta="$(git show "refs/remotes/origin/${branch}:${SPEC_DIR}/spec-meta.json" 2>/dev/null)" \
     && printf '%s' "$meta" | jq -e . >/dev/null 2>&1; then
    meta_found=true
    meta_spec_dir="$(only "$(field "$meta" '.spec_dir // empty')" '^specs/[A-Za-z0-9._-]+$')"
    if [ -n "$meta_spec_dir" ] && [ "$meta_spec_dir" = "$SPEC_DIR" ]; then
      meta_identity_ok=true
    fi
    meta_issue="$(only "$(field "$meta" '.issue // empty')" '^[0-9]+$')"
    meta_stage="$(only "$(field "$meta" '.stage // empty')" '^[A-Za-z0-9_-]+$')"
    meta_iteration="$(only "$(field "$meta" '.iteration // empty')" '^[0-9]+$')"
  fi
fi

printf 'meta_fetch_ok=%s\n' "$meta_fetch_ok"
printf 'meta_found=%s\n' "$meta_found"
printf 'meta_identity_ok=%s\n' "$meta_identity_ok"
printf 'meta_spec_dir=%s\n' "$meta_spec_dir"
printf 'meta_issue=%s\n' "$meta_issue"
printf 'meta_stage=%s\n' "$meta_stage"
printf 'meta_iteration=%s\n' "$meta_iteration"
