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
# The bundle's one ref is HEAD; its consumers fetch exactly that, and its
# prerequisites must be commits every consumer's full-history checkout
# holds:
#   - a base this repository does not hold (a resumed branch whose base left
#     main's history): the whole history, never a guessed prerequisite;
#   - new commits since the base: base..HEAD (prerequisites on main);
#   - none (HEAD is the base or behind it): the head commit alone, whose
#     parent is on main too -- the whole history only for a root commit.
if [ -n "$base_sha" ] && ! git cat-file -e "${base_sha}^{commit}" 2>/dev/null; then
  git bundle create --quiet "$out_dir/bundle.git" HEAD
elif [ -n "$base_sha" ] && ! git merge-base --is-ancestor HEAD "$base_sha"; then
  git bundle create --quiet "$out_dir/bundle.git" "$base_sha..HEAD" HEAD
elif git rev-parse --verify --quiet "HEAD~1^{commit}" >/dev/null; then
  git bundle create --quiet "$out_dir/bundle.git" HEAD~1..HEAD HEAD
else
  git bundle create --quiet "$out_dir/bundle.git" HEAD
fi
jq -n --arg base "$base_sha" --arg head "$head_sha" --arg site "$site" \
  '{base_sha: $base, head_sha: $head, site: $site}' > "$out_dir/meta.json"
echo "head-sha=$head_sha" >> "$GITHUB_OUTPUT"
