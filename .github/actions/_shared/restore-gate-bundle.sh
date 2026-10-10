#!/usr/bin/env bash
# Restore an agent's commits from a workspace bundle into the current
# repository, in the credential-bearing job that publishes them (spec 095,
# contracts/workspace-bundle.md, consumer 2).
# Usage: restore-gate-bundle.sh BUNDLE_DIR EXPECTED_HEAD_SHA BRANCH
#
# EXPECTED_HEAD_SHA comes from the producing job's own output, never from
# the bundle's meta.json: the bundle artifact is reachable from the
# credential-free gate-suite job, which runs agent-authored code, so its
# metadata is not trusted. A commit SHA is content-addressed, so a bundle
# that does not hold exactly that commit cannot be made to look as if it
# did. Exits non-zero, before anything durable, on any mismatch.
set -eu

bundle_dir="$1"
expected="$2"
branch="$3"
bundle="$bundle_dir/bundle.git"
if ! printf '%s' "$expected" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "::error::restore-gate-bundle: expected head '$expected' is not a 40-hex SHA"
  exit 1
fi
if [ ! -f "$bundle" ]; then
  echo "::error::restore-gate-bundle: no workspace bundle at $bundle"
  exit 1
fi
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=git-push-hardening.sh
. "$here/git-push-hardening.sh"
wc_harden_git_env
if ! git bundle verify "$bundle" >/dev/null 2>&1; then
  echo "::error::restore-gate-bundle: the workspace bundle failed verification"
  exit 1
fi
# The bundle carries one ref, HEAD (build-gate-bundle.sh); a refs/* refspec
# would match nothing and import no objects.
git fetch --quiet --no-tags "$bundle" "+HEAD:refs/wc-gate/head"
if ! git cat-file -e "${expected}^{commit}" 2>/dev/null; then
  echo "::error::restore-gate-bundle: the bundle does not hold $expected"
  exit 1
fi
if [ -n "$branch" ]; then
  git checkout --quiet -B "$branch" "$expected"
else
  git checkout --quiet --detach "$expected"
fi
actual="$(git rev-parse HEAD)"
if [ "$actual" != "$expected" ]; then
  echo "::error::restore-gate-bundle: HEAD is $actual after the restore, not $expected"
  exit 1
fi
echo "head-sha=$actual" >> "$GITHUB_OUTPUT"
