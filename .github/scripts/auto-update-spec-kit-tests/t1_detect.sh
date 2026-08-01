#!/usr/bin/env bash
# Scenarios 1, 2, 7 (classification half): detect's semver compare step.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

mkfixture() { # mkfixture <out> <tag:prerelease> ...
  local out="$1"; shift
  local items=()
  for spec in "$@"; do
    local tag="${spec%%:*}" pre="${spec##*:}"
    items+=("{\"tag_name\":\"$tag\",\"prerelease\":$pre,\"html_url\":\"https://github.com/github/spec-kit/releases/tag/$tag\",\"body\":\"notes for $tag\"}")
  done
  printf '[%s]\n' "$(IFS=,; echo "${items[*]}")" > "$out"
}

detect() { # detect <pinned> <releases-file>  -> sets D_NEWER D_LATEST D_TYPE
  new_step_env
  "$PY" -c "
import json,sys
json.dump({'releases_file': sys.argv[1], 'default_branch':'main'}, open(sys.argv[2],'w'))" "$2" "$GH_STATE"
  GHA_SUBST=()
  export GH_TOKEN=stub PINNED_VERSION="$1"
  run_step 'auto-update-spec-kit__detect__*compare*.sh' >/dev/null 2>&1
  D_NEWER="$(out newer)"; D_LATEST="$(out latest-upstream)"; D_TYPE="$(out release-type)"
  D_SUMMARY="$(summary)"
}

echo "--- Scenario 1: pinned == latest stable -> no-op, no churn (SC-007) ---"
F="$(mktemp)"; mkfixture "$F" "v0.15.1:false" "v0.15.0:false" "v0.14.4:false"
detect "0.15.1" "$F"
check "S1 newer" "$D_NEWER" "false"
check "S1 release-type not emitted" "$D_TYPE" ""
check_contains "S1 summary says up to date" "$D_SUMMARY" "up to date"
check_not_contains "S1 no issue/PR language" "$D_SUMMARY" "newer"

echo "--- Scenario 1b: pinned AHEAD of upstream (repo ahead) -> still no-op ---"
detect "0.16.0" "$F"
check "S1b newer" "$D_NEWER" "false"

echo "--- Scenario 1c: upstream unreadable (API failure) -> treated as up to date ---"
EMPTY="$(mktemp)"; echo '[]' > "$EMPTY"
detect "0.12.4" "$EMPTY"
check "S1c newer" "$D_NEWER" "false"
check_contains "S1c warns rather than churns" "$D_SUMMARY" "could not read upstream releases"

echo "--- Scenario 2/7: release-type classification ---"
detect "0.15.0" "$F"
check "patch jump 0.15.0->0.15.1 newer" "$D_NEWER" "true"
check "patch jump release-type" "$D_TYPE" "patch"

detect "0.14.4" "$F"
check "minor jump 0.14.4->0.15.1 release-type" "$D_TYPE" "minor"

MAJ="$(mktemp)"; mkfixture "$MAJ" "v1.0.0:false" "v0.15.1:false"
detect "0.15.1" "$MAJ"
check "major jump 0.15.1->1.0.0 release-type" "$D_TYPE" "major"
check "major jump newer" "$D_NEWER" "true"

echo "--- prerelease exclusion (only stable releases are eligible) ---"
PRE="$(mktemp)"; mkfixture "$PRE" "v0.16.0:true" "v0.15.1:false"
detect "0.15.1" "$PRE"
check "prerelease ignored -> up to date" "$D_NEWER" "false"
detect "0.15.0" "$PRE"
check "prerelease ignored -> latest is stable 0.15.1" "$D_LATEST" "0.15.1"

echo "--- ordering: sort is numeric, not lexicographic (0.9 < 0.12) ---"
ORD="$(mktemp)"; mkfixture "$ORD" "v0.9.9:false" "v0.12.4:false" "v0.10.0:false"
detect "0.9.9" "$ORD"
check "numeric sort picks 0.12.4 not 0.9.9" "$D_LATEST" "0.12.4"

echo "--- LIVE upstream data vs this repo's real pinned version ---"
detect "0.12.4" "$SP/fixtures/spec-kit-releases.json"
echo "    live: pinned=0.12.4 latest=$D_LATEST newer=$D_NEWER type=$D_TYPE"
check "live newer" "$D_NEWER" "true"
check "live latest" "$D_LATEST" "0.15.1"
check "live release-type" "$D_TYPE" "minor"

report "T1 detect"
