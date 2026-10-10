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
# written over them.
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

# wc_push_from_shim SHA URL DEST_REF -- push SHA (present in the current
# repository's object store) to DEST_REF at URL from a shim repository with
# no config of its own. Call wc_harden_git_env first. Returns git push's
# status.
wc_push_from_shim() {
  local sha="$1" url="$2" dest="$3" objects shim
  objects="$(git rev-parse --absolute-git-dir)/objects" || return 1
  shim="$(mktemp -d)"
  git init --quiet "$shim" || return 1
  printf '%s\n' "$objects" > "$shim/.git/objects/info/alternates"
  git --git-dir="$shim/.git" update-ref refs/heads/shim "$sha" || return 1
  git --git-dir="$shim/.git" push --no-verify "$url" "refs/heads/shim:${dest}"
}
