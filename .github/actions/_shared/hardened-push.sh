#!/usr/bin/env bash
# The one hardened-push idiom (spec 095 FR-015..FR-017, research R7).
# Usage: hardened-push.sh BRANCH EXPECTED_HEAD_SHA   (token in PUSH_TOKEN)
#
# Neutralises repository-local steering a planted hook or config could do:
# hooks are disabled, global/system config is replaced by an empty pristine
# file, and the push URL is explicit rather than read from `origin` (whose
# url/pushurl/insteadOf rewrites live in the repo's own .git/config).
set -eu

branch="$1"
expected="$2"
actual="$(git rev-parse HEAD)"
if [ "$actual" != "$expected" ]; then
  echo "::error::refusing to push: HEAD $actual is not the verified $expected"
  exit 1
fi

pristine="$(mktemp)"
export GIT_CONFIG_GLOBAL="$pristine"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=core.hooksPath
export GIT_CONFIG_VALUE_0=/dev/null

server="${PUSH_SERVER_URL:-https://github.com}"
url="${server}/${GITHUB_REPOSITORY}.git"
if [ -n "${PUSH_TOKEN:-}" ]; then
  # The token travels as an auth header, not in the URL, so a failed push
  # cannot echo it into the job log.
  basic="$(printf 'x-access-token:%s' "$PUSH_TOKEN" | base64 | tr -d '\n')"
  echo "::add-mask::${basic}"
  export GIT_CONFIG_COUNT=2
  export GIT_CONFIG_KEY_1="http.${server}/.extraheader"
  export GIT_CONFIG_VALUE_1="AUTHORIZATION: basic ${basic}"
fi
# The env override cannot beat the workspace's own `url.<base>.insteadOf`
# (local config outranks global), so the push runs from a fresh shim
# repository that borrows the workspace's objects and shares none of its
# config (research R7 fallback).
objects="$(git rev-parse --absolute-git-dir)/objects"
shim="$(mktemp -d)"
git init --quiet "$shim"
printf '%s\n' "$objects" > "$shim/.git/objects/info/alternates"
git --git-dir="$shim/.git" update-ref refs/heads/shim "$expected"
git --git-dir="$shim/.git" push --no-verify "$url" "refs/heads/shim:refs/heads/${branch}"
