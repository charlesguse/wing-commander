# shellcheck shell=bash
# The one home of the git hardening environment for a git operation that
# runs with a write credential after agent code has run in the same job
# (spec 095 FR-015/FR-016, research R7). Sourced, never executed:
#
#   . "$GITHUB_ACTION_PATH/../_shared/git-push-hardening.sh"
#   wc_harden_git_env
#
# After wc_harden_git_env, in this shell and every child:
#   - global config is an empty file of our own and system config is off,
#     so neither can add a hook, a credential helper or a URL rewrite;
#   - core.hooksPath=/dev/null and core.fsmonitor=false are set through
#     GIT_CONFIG_COUNT, which outranks the repository's own .git/config,
#     so a planted pre-push hook or fsmonitor command cannot run.
# The entries are APPENDED after any GIT_CONFIG_KEY_n the caller already
# set (a container job's safe.directory entry -- see clarify.yml), never
# written over them. Global and system config are dropped whole, by design
# (spec 095 FR-018): a proxy, CA bundle or credential helper there is just
# what a planted value would use to steer the token. A self-hosted runner
# that needs one supplies it through the environment (HTTPS_PROXY,
# GIT_SSL_CAINFO) or a GIT_CONFIG_KEY_n entry of its own.
#
# What the environment cannot do: neutralise a `url.<base>.insteadOf` or a
# `remote.*.pushurl` in the repository's own .git/config (local config
# cannot be switched off through the environment). wc_push_from_shim is
# the push that is immune to those too: it pushes from a fresh shim
# repository that borrows the workspace's objects and shares none of its
# config, to an explicit URL (spec 095 FR-016/FR-017, research R7).
wc_harden_git_env() {
  local n
  GIT_CONFIG_GLOBAL="$(mktemp)"
  export GIT_CONFIG_GLOBAL
  export GIT_CONFIG_NOSYSTEM=1
  n="${GIT_CONFIG_COUNT:-0}"
  case "$n" in
    '' | *[!0-9]*) n=0 ;;
  esac
  export "GIT_CONFIG_KEY_${n}=core.hooksPath" "GIT_CONFIG_VALUE_${n}=/dev/null"
  n=$((n + 1))
  export "GIT_CONFIG_KEY_${n}=core.fsmonitor" "GIT_CONFIG_VALUE_${n}=false"
  n=$((n + 1))
  export GIT_CONFIG_COUNT="$n"
}

# wc_push_from_shim SHA BRANCH REPO TOKEN -- push SHA (present in the
# current repository's object store) to refs/heads/BRANCH of REPO on
# $PUSH_SERVER_URL (else $GITHUB_SERVER_URL, else https://github.com), from
# a shim repository with no config of its own. The token travels as an auth
# header, never in the URL, so a failed push cannot echo it into the log.
# BRANCH must be a real branch name: an empty one, or `HEAD` from a detached
# checkout, is refused rather than pushed as a branch literally named HEAD.
# The one home of the push URL and its authentication (spec 095
# FR-016/FR-017). Call wc_harden_git_env first. Returns git push's status.
wc_push_from_shim() {
  local sha="$1" branch="$2" repo="$3" token="$4" server common shim basic n
  case "$branch" in
    '' | HEAD | refs/*)
      echo "::error::wc_push_from_shim: '$branch' is not a branch name to push to" >&2
      return 1 ;;
  esac
  server="${PUSH_SERVER_URL:-${GITHUB_SERVER_URL:-https://github.com}}"
  # The object store of a linked worktree lives in the common directory.
  common="$(git rev-parse --git-common-dir)" || return 1
  common="$(cd "$common" && pwd -P)" || return 1
  shim="$(mktemp -d)"
  git init --quiet "$shim" || return 1
  printf '%s\n' "$common/objects" > "$shim/.git/objects/info/alternates"
  git --git-dir="$shim/.git" update-ref refs/heads/shim "$sha" || return 1
  (
    if [ -n "$token" ]; then
      basic="$(printf 'x-access-token:%s' "$token" | base64 | tr -d '\n')"
      echo "::add-mask::${basic}"
      n="${GIT_CONFIG_COUNT:-0}"
      export "GIT_CONFIG_KEY_${n}=http.${server}/.extraheader"
      export "GIT_CONFIG_VALUE_${n}=AUTHORIZATION: basic ${basic}"
      export GIT_CONFIG_COUNT=$((n + 1))
    fi
    git --git-dir="$shim/.git" push --no-verify "${server}/${repo}.git" \
      "refs/heads/shim:refs/heads/${branch}"
  ) || return 1
  # What a plain `git push origin` would have done to the checkout's own
  # remote-tracking ref, so a later origin/<branch>..HEAD count is right.
  git update-ref "refs/remotes/origin/${branch}" "$sha"
}

# wc_current_branch -- the branch the checkout is on, unabbreviated: `git
# rev-parse --abbrev-ref HEAD` says `heads/<name>` when a tag shares the
# name, and `HEAD` when detached. Prints nothing when detached, which
# wc_push_from_shim refuses as a destination.
wc_current_branch() {
  local ref
  ref="$(git symbolic-ref -q HEAD)" || return 0
  printf '%s\n' "${ref#refs/heads/}"
}
