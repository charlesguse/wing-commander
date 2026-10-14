#!/usr/bin/env bash
# The single home of spec 114's FR-021 containment test: a subfolder
# lifecycle's repository changes lie inside its project folder P. Two
# consumers, one test:
#
#   containment.sh outside <P>
#     Reads newline-separated repository-relative paths on stdin and prints
#     the ones outside P/. The wing-commander-containment composite feeds it
#     the post-agent changed-path list.
#
#   containment.sh pre-push <P>
#     A git pre-push hook body (stdin: `<local ref> <local sha> <remote ref>
#     <remote sha>` per ref). Refuses the push when any commit it would
#     publish that is not already on a remote touches a path outside P/.
#     Installed for agents that push themselves (pr-conversation's act leg),
#     so an out-of-folder change is stopped before it leaves the runner, not
#     reported after it already has.
#
# Pure shell plus git, no network. P must be non-empty: a root lifecycle
# has no containment to check and its callers skip this script entirely.
set -uo pipefail

outside() {
  local project="$1" path
  while IFS= read -r path; do
    [ -z "$path" ] && continue
    case "$path" in
      "$project"/*) ;;
      *) printf '%s\n' "$path" ;;
    esac
  done
}

mode="${1:-}"
project="${2:-}"
if [ -z "$project" ]; then
  echo "containment.sh: a project path is required" >&2
  exit 2
fi

case "$mode" in
  outside)
    outside "$project"
    ;;
  pre-push)
    found=""
    while read -r _local_ref local_sha _remote_ref _remote_sha; do
      [ -n "${local_sha:-}" ] || continue
      # An all-zero local sha is a branch deletion: it publishes no content.
      case "$local_sha" in *[!0]*) ;; *) continue ;; esac
      # -c: a merge commit's own changes (an evil merge) are listed too.
      if ! paths="$(git log --format= --name-only --no-renames -c "$local_sha" --not --remotes 2>&1)"; then
        echo "::error::wing-commander-containment: could not list the commits this push would publish ($paths) -- refusing the push." >&2
        exit 1
      fi
      found="$found$(printf '%s\n' "$paths" | outside "$project")"$'\n'
    done
    found="$(printf '%s' "$found" | sed '/^$/d' | sort -u)"
    if [ -n "$found" ]; then
      echo "::error::wing-commander-containment: push refused -- it carries changes outside project folder '$project': $(printf '%s' "$found" | tr '\n' ' ')" >&2
      exit 1
    fi
    ;;
  *)
    echo "containment.sh: unknown mode '$mode' (want outside or pre-push)" >&2
    exit 2
    ;;
esac
