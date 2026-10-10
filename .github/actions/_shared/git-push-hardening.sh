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
# What this cannot do: neutralise a `url.<base>.insteadOf` in the
# repository's own .git/config (local config cannot be switched off
# through the environment). A push that must also be immune to that goes
# through _shared/hardened-push.sh, which pushes from a fresh shim
# repository to an explicit URL.
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
