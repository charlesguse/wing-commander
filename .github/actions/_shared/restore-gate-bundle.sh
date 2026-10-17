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
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=gate-bundle-import.sh
. "$here/gate-bundle-import.sh"
if ! wc_is_sha "$expected"; then
  echo "::error::restore-gate-bundle: expected head '$expected' is not a 40-hex SHA"
  exit 1
fi
if [ ! -f "$bundle" ]; then
  echo "::error::restore-gate-bundle: no workspace bundle at $bundle"
  exit 1
fi
# shellcheck source=git-push-hardening.sh
. "$here/git-push-hardening.sh"
wc_harden_git_env
rc=0
fetched="$(wc_import_bundle "$bundle")" || rc=$?
case "$rc" in
  0) ;;
  2) echo "::error::restore-gate-bundle: the workspace bundle failed verification -- a corrupt bundle, or a prerequisite commit (the agent's base) this checkout does not hold. The containment could not be established; nothing is pushed."
     exit 1 ;;
  *) echo "::error::restore-gate-bundle: fetching the workspace bundle failed -- the containment could not be established; nothing is pushed."
     exit 1 ;;
esac
if [ "$fetched" != "$expected" ]; then
  echo "::error::restore-gate-bundle: the bundle does not hold $expected (its head is ${fetched:-nothing})"
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
