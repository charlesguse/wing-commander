#!/usr/bin/env bash
# The single home of spec 114's FR-021 containment test: a subfolder
# lifecycle's repository changes lie inside its project folder P. Two
# consumers, one test:
#
#   containment.sh outside <P> [-z [-q]]
#     Reads newline-separated repository-relative paths on stdin (NUL-
#     separated with -z) and prints the ones outside P/, one per line. The
#     wing-commander-containment composite feeds it the post-agent
#     changed-path list from git's -z output: without -z, git quotes a
#     non-ASCII or special-character name ("a/b/caf\303\251.md"), and the
#     quoted form would read as a path outside P. -q prints a name holding
#     a control character (a newline, say) shell-quoted (printf %q), so
#     every name the agent chose is exactly one line when the composite
#     writes it to $GITHUB_OUTPUT and the step summary; other names,
#     non-ASCII ones included, print as themselves.
#
#   containment.sh inside <P>
#     The complement: prints the stdin paths inside P/. The composite's
#     filter mode narrows rebase's conflict manifest with it.
#
#   containment.sh trusted-base <P> [<default-branch>]
#     Prints the default branch's tip as the remote reports it now (`git
#     ls-remote origin refs/heads/<default-branch>`), fetching that commit
#     when the checkout lacks it. An empty <default-branch> is resolved with
#     `git ls-remote --symref origin HEAD`. Neither origin/<default> nor
#     `--not --remotes` is read: both are refs the agent can rewrite. Fails
#     closed when the branch or its tip cannot be resolved.
#
#   containment.sh pre-push <P> [<trusted-default-sha>]
#     A git pre-push hook body (stdin: `<local ref> <local sha> <remote ref>
#     <remote sha>` per ref). Refuses the push when any commit since
#     merge-base(<trusted default tip>, <local sha>) touches a path outside
#     P/ -- so content that is already on some remote branch but arrives
#     through a merge or a reset is still checked. An empty trusted sha is
#     resolved with trusted-base. Installed for agents that push themselves,
#     as an early, advisory stop: an agent can rewrite core.hooksPath, so
#     the enforcing check is the composite's post-agent check mode (see
#     contracts/containment-and-trusted-checkout.md).
#
# Every git call runs under the hardened environment of
# git-push-hardening.sh (sourced from beside this file when present: hooks,
# fsmonitor and global config off) and with replace objects ignored
# (GIT_NO_REPLACE_OBJECTS), so a planted refs/replace/* cannot swap the
# content git reports. P must be non-empty: a root lifecycle has no
# containment to check and its callers skip this script entirely.
set -uo pipefail

export GIT_NO_REPLACE_OBJECTS=1
here="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$here/git-push-hardening.sh" ]; then
  # shellcheck source=/dev/null
  . "$here/git-push-hardening.sh"
  wc_harden_git_env
fi

outside() {
  local project="$1" delim=$'\n' quote="" path
  [ "${2:-}" = "-z" ] && delim=''
  [ "${3:-}" = "-q" ] && quote=1
  while IFS= read -r -d "$delim" path || [ -n "$path" ]; do
    [ -z "$path" ] && continue
    case "$path" in
      "$project"/*) ;;
      *)
        if [ -n "$quote" ] && [[ "$path" == *[[:cntrl:]]* ]]; then
          printf '%q\n' "$path"
        else
          printf '%s\n' "$path"
        fi ;;
    esac
  done
}

trusted_base() {
  local branch="$1" sha
  if [ -z "$branch" ]; then
    branch="$(git ls-remote --symref origin HEAD 2>/dev/null | sed -n 's|^ref: refs/heads/\(.*\)\tHEAD$|\1|p')"
  fi
  if [ -z "$branch" ]; then
    echo "::error::wing-commander-containment: could not resolve the default branch from the remote -- refusing." >&2
    return 1
  fi
  # ls-remote matches its pattern as a ref-name suffix, so
  # `<x>/refs/heads/<branch>` would match too: keep the exact ref only.
  sha="$(git ls-remote origin "refs/heads/$branch" 2>/dev/null | awk -v r="refs/heads/$branch" '$2==r {print $1}')"
  case "$sha" in
    *[!0-9a-f]* | '')
      echo "::error::wing-commander-containment: the remote reports no single tip for '$branch' -- refusing." >&2
      return 1 ;;
  esac
  if ! git cat-file -e "$sha^{commit}" 2>/dev/null; then
    git fetch --quiet --no-tags origin "refs/heads/$branch" >/dev/null 2>&1
    if ! git cat-file -e "$sha^{commit}" 2>/dev/null; then
      echo "::error::wing-commander-containment: could not fetch '$branch' at $sha -- refusing." >&2
      return 1
    fi
  fi
  printf '%s\n' "$sha"
}

mode="${1:-}"
project="${2:-}"
if [ -z "$project" ]; then
  echo "containment.sh: a project path is required" >&2
  exit 2
fi

case "$mode" in
  outside)
    outside "$project" "${3:-}" "${4:-}"
    ;;
  inside)
    # `|| [ -n ... ]`: a last path with no trailing newline is still read.
    while IFS= read -r path || [ -n "$path" ]; do
      case "$path" in "$project"/*) printf '%s\n' "$path" ;; esac
    done
    ;;
  trusted-base)
    trusted_base "${3:-}" || exit 1
    ;;
  pre-push)
    tip="${3:-}"
    if [ -z "$tip" ]; then
      tip="$(trusted_base "")" || exit 1
    fi
    found=""
    while read -r _local_ref local_sha _remote_ref _remote_sha; do
      [ -n "${local_sha:-}" ] || continue
      # An all-zero local sha is a branch deletion: it publishes no content.
      case "$local_sha" in *[!0]*) ;; *) continue ;; esac
      if ! base="$(git merge-base "$tip" "$local_sha" 2>&1)"; then
        echo "::error::wing-commander-containment: no merge base of the default branch ($tip) and $local_sha ($base) -- refusing the push." >&2
        exit 1
      fi
      # -c: a merge commit's own changes (an evil merge) are listed too.
      # -z: names arrive unquoted (see `outside`); piped, never captured,
      # since a shell variable cannot hold a NUL.
      if ! bad="$(git log -z --format= --name-only --no-renames -c "$base..$local_sha" | outside "$project" -z)"; then
        echo "::error::wing-commander-containment: could not list the commits this push would publish -- refusing the push." >&2
        exit 1
      fi
      found="$found$bad"$'\n'
    done
    found="$(printf '%s' "$found" | sed '/^$/d' | sort -u)"
    if [ -n "$found" ]; then
      echo "::error::wing-commander-containment: push refused -- it carries changes outside project folder '$project': $(printf '%s' "$found" | tr '\n' ' ')" >&2
      exit 1
    fi
    ;;
  *)
    echo "containment.sh: unknown mode '$mode' (want outside, inside, trusted-base or pre-push)" >&2
    exit 2
    ;;
esac
