#!/usr/bin/env bash
# Build bundle.git and meta.json for a credential-free gate-suite job.
# Usage: build-gate-bundle.sh SITE BASE_SHA OUT_DIR   (spec 095)
set -eu

site="$1"
base_sha="$2"
out_dir="$3"
mkdir -p "$out_dir"
head_sha="$(git rev-parse HEAD)"
if [ -n "$base_sha" ]; then
  git bundle create "$out_dir/bundle.git" "$base_sha..HEAD" HEAD
else
  git bundle create "$out_dir/bundle.git" HEAD
fi
jq -n --arg base "$base_sha" --arg head "$head_sha" --arg site "$site" \
  '{base_sha: $base, head_sha: $head, site: $site}' > "$out_dir/meta.json"
