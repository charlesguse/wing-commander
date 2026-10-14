#!/usr/bin/env bash
# Intake's pre-push hook for a routed subfolder lifecycle (spec 114, FR-014,
# FR-021). Deterministic code, not the agent's prompt, decides what the
# first push of a subfolder spec may carry:
#
#   * the only ref intake may push is <branch-prefix>P/<NNN-slug>, where NNN
#     is the number intake allocated -- no deletion, no other branch;
#   * len(<NNN-slug>) must fit the spec-label budget (project-name.sh
#     slug-budget P): an over-budget slug fails here, so no branch exists;
#   * the `spec:P/<NNN-slug>` label is created and put on the lifecycle issue
#     BEFORE the branch reaches the remote (label first);
#   * every commit the push publishes stays inside P (containment.sh).
#
# Usage, as the body of a git pre-push hook (stdin: `<local ref> <local sha>
# <remote ref> <remote sha>` per ref):
#   intake-pre-push.sh <branch-prefix> <P> <NNN> <issue-number>
# gh reads GH_TOKEN from the pushing process's environment; nothing secret is
# written into the hook. Any refusal exits non-zero, which aborts the push.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
prefix="${1:-}"
project="${2:-}"
num="${3:-}"
issue="${4:-}"

refuse() {
  echo "::error::wing-commander intake: push refused -- $*" >&2
  exit 1
}

if [ -z "$project" ] || [ -z "$num" ] || [ -z "$issue" ]; then
  refuse "the hook was installed without a project, feature number or issue"
fi
budget="$(bash "$here/project-name.sh" slug-budget "$project")" || refuse "could not compute the slug budget for '$project'"

input="$(cat)"
want="refs/heads/$prefix$project/"
labels=""
# Every check first; the issue is labelled only once nothing refuses.
while read -r _local_ref local_sha remote_ref _remote_sha; do
  [ -n "${remote_ref:-}" ] || continue
  case "$local_sha" in *[!0]*) ;; *) refuse "intake deletes no branch ($remote_ref)" ;; esac
  case "$remote_ref" in
    "$want"*) ;;
    *) refuse "intake pushes only ${want#refs/heads/}<NNN-slug>, not ${remote_ref#refs/heads/}" ;;
  esac
  slug="${remote_ref#"$want"}"
  case "$slug" in
    "$num"-*) ;;
    *) refuse "branch ${remote_ref#refs/heads/} does not carry the allocated feature number $num" ;;
  esac
  case "$slug" in */*) refuse "'$slug' is not a single <NNN-slug> segment" ;; esac
  if [ "${#slug}" -gt "$budget" ]; then
    refuse "'$slug' is ${#slug} characters; the spec:$project/<NNN-slug> label leaves at most $budget (GitHub caps labels at 50). Choose a shorter slug -- nothing was truncated."
  fi
  labels="$labels$slug"$'\n'
done <<< "$input"

printf '%s\n' "$input" | bash "$here/containment.sh" pre-push "$project" || exit 1

while IFS= read -r slug; do
  [ -n "$slug" ] || continue
  label="spec:$project/$slug"
  gh label create "$label" --color C5DEF5 --description "Lifecycle: $project/specs/$slug" --force >/dev/null \
    || refuse "could not create the label $label before the first push"
  gh issue edit "$issue" --add-label "$label" >/dev/null \
    || refuse "could not add the label $label to issue #$issue before the first push"
done <<< "$labels"
