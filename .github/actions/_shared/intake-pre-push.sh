#!/usr/bin/env bash
# Intake's label-first check for a routed subfolder lifecycle (spec 114,
# FR-014, FR-021). Deterministic code, not the agent's prompt, decides what
# the first push of a subfolder spec may carry:
#
#   * the only ref intake may push is <branch-prefix>P/<NNN-slug>, where NNN
#     is the number intake allocated -- no deletion, no other branch;
#   * len(<NNN-slug>) must fit the spec-label budget (project-name.sh
#     slug-budget P): an over-budget slug fails here, so no branch exists;
#   * every commit the push publishes stays inside P (containment.sh).
#
# It validates only and makes no API call: creating the `spec:P/<NNN-slug>`
# label, putting it on the issue and the push itself belong to
# wing-commander-publish-stranded-commits (label-first-* inputs), which runs
# after the agent under the step's declared token, label first.
#
# Usage (stdin: `<local ref> <local sha> <remote ref> <remote sha>` per ref):
#   intake-pre-push.sh check <branch-prefix> <P> <NNN> [<record-file>]
#     Exit 0 when every ref passes; the validated <NNN-slug> is printed on
#     stdout and, when a record file is named, written there.
#   intake-pre-push.sh hook <branch-prefix> <P> <NNN> <record-file>
#     The body of the git pre-push hook intake installs in the agent's
#     checkout: `check`, then refuse the push either way, because the
#     branch may reach the remote only after its label exists. A passing
#     check is recorded, so the agent learns its slug was accepted.
# Any refusal exits non-zero, which aborts the push.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
mode="${1:-}"
prefix="${2:-}"
project="${3:-}"
num="${4:-}"
record="${5:-}"

refuse() {
  echo "::error::wing-commander intake: push refused -- $*" >&2
  exit 1
}

case "$mode" in
  check|hook) ;;
  *) echo "intake-pre-push.sh: unknown mode '$mode' (want check or hook)" >&2; exit 2 ;;
esac
if [ -z "$project" ] || [ -z "$num" ]; then
  refuse "the check was run without a project or feature number"
fi
if [ "$mode" = hook ] && [ -z "$record" ]; then
  refuse "the hook was installed without a record file"
fi
budget="$(bash "$here/project-name.sh" slug-budget "$project")" || refuse "could not compute the slug budget for '$project'"

input="$(cat)"
want="refs/heads/$prefix$project/"
slugs=""
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
  case $'\n'"$slugs" in *$'\n'"$slug"$'\n'*) ;; *) slugs="$slugs$slug"$'\n' ;; esac
done <<< "$input"

[ -n "$slugs" ] || refuse "nothing to push"
[ "$(printf '%s' "$slugs" | wc -l)" -eq 1 ] || refuse "intake pushes one branch, not $(printf '%s' "$slugs" | tr '\n' ' ')"
printf '%s\n' "$input" | bash "$here/containment.sh" pre-push "$project" || exit 1

slug="${slugs%$'\n'}"
if [ -n "$record" ]; then
  printf '%s\n' "$slug" > "$record" || refuse "could not record the validated slug in $record"
fi
if [ "$mode" = hook ]; then
  echo "wing-commander intake: '$prefix$project/$slug' passed the label-first check and is recorded. This push is refused on purpose: after you finish, the pipeline creates the spec:$project/$slug label, publishes this branch and opens the pull request. Do not retry the push." >&2
  exit 1
fi
printf '%s\n' "$slug"
