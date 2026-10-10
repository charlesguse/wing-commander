#!/usr/bin/env bash
# Build bundle.git and meta.json for a credential-free gate-suite job.
# Usage: build-gate-bundle.sh SITE BASE_SHA OUT_DIR   (spec 095)
#
# Runs in the credential-bearing job after its agent phase, on a checkout
# the agent wrote: git runs under the hardened environment (no hooks, no
# fsmonitor, no global/system config -- git-push-hardening.sh).
set -eu

site="$1"
base_sha="$2"
out_dir="$3"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=git-push-hardening.sh
. "$here/git-push-hardening.sh"
wc_harden_git_env
mkdir -p "$out_dir"
head_sha="$(git rev-parse HEAD)"
# No new commits (no base, the base is HEAD, or HEAD is behind the base):
# git refuses an empty thin bundle, so ship the head itself.
if [ -z "$base_sha" ] || [ "$base_sha" = "$head_sha" ] \
  || ! git bundle create --quiet "$out_dir/bundle.git" "$base_sha..HEAD" HEAD 2>/dev/null; then
  git bundle create --quiet "$out_dir/bundle.git" HEAD
fi
jq -n --arg base "$base_sha" --arg head "$head_sha" --arg site "$site" \
  '{base_sha: $base, head_sha: $head, site: $site}' > "$out_dir/meta.json"
echo "head-sha=$head_sha" >> "$GITHUB_OUTPUT"
