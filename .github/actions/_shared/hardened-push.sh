#!/usr/bin/env bash
# The one hardened-push idiom (spec 095 FR-015..FR-017, research R7).
# Usage: hardened-push.sh BRANCH EXPECTED_HEAD_SHA   (token in PUSH_TOKEN)
#
# Neutralises repository-local steering a planted hook or config could do:
# hooks are disabled and global/system config is replaced by an empty
# pristine file (git-push-hardening.sh, the env's one home), and the push
# URL is explicit rather than read from `origin` (whose url/pushurl/
# insteadOf rewrites live in the repo's own .git/config).
set -eu

branch="$1"
expected="$2"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
actual="$(git rev-parse HEAD)"
if [ "$actual" != "$expected" ]; then
  echo "::error::refusing to push: HEAD $actual is not the verified $expected"
  exit 1
fi
# shellcheck source=git-push-hardening.sh
. "$here/git-push-hardening.sh"
wc_harden_git_env

# The env override cannot beat the workspace's own `url.<base>.insteadOf`
# (local config outranks global), so the push runs from a shim repository
# to an explicit URL (wc_push_from_shim, research R7 fallback).
if ! wc_push_from_shim "$expected" "$branch" "$GITHUB_REPOSITORY" "${PUSH_TOKEN:-}"; then
  echo "::error::hardened push: pushing $expected to ${branch} was refused -- nothing that assumes it landed may run."
  exit 1
fi
