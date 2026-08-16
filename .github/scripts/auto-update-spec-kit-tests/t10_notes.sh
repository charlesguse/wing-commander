#!/usr/bin/env bash
# evaluate-path's "Fetch candidate release notes" step — no suite drove this
# step before this feature (spec 036 T009); the multi-page fixture proves the
# assembled bundle is correct once upstream's release list spans more than
# one page (research.md D4/D5).
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

# mkfixture_bulk <out>: a >30-release fixture spanning the gh_stub's PAGE_SIZE
# boundary. Page 1 (entries 1-30) are all stable and all below the
# pinned..candidate range under test; page 2 (entries 31-34) carries the
# releases the bundle must resolve against, including a prerelease that must
# still be excluded regardless of which page it falls on.
mkfixture_bulk() {
  local out="$1"
  local items=() i
  for i in $(seq 1 30); do
    items+=("{\"tag_name\":\"v0.1.$i\",\"prerelease\":false,\"html_url\":\"https://github.com/github/spec-kit/releases/tag/v0.1.$i\",\"body\":\"notes for v0.1.$i\"}")
  done
  items+=("{\"tag_name\":\"v0.15.2\",\"prerelease\":false,\"html_url\":\"https://github.com/github/spec-kit/releases/tag/v0.15.2\",\"body\":\"notes for v0.15.2\"}")
  items+=("{\"tag_name\":\"v0.15.3\",\"prerelease\":true,\"html_url\":\"https://github.com/github/spec-kit/releases/tag/v0.15.3\",\"body\":\"notes for v0.15.3\"}")
  items+=("{\"tag_name\":\"v0.15.4\",\"prerelease\":false,\"html_url\":\"https://github.com/github/spec-kit/releases/tag/v0.15.4\",\"body\":\"notes for v0.15.4\"}")
  items+=("{\"tag_name\":\"v0.15.5\",\"prerelease\":false,\"html_url\":\"https://github.com/github/spec-kit/releases/tag/v0.15.5\",\"body\":\"notes for v0.15.5\"}")
  printf '[%s]\n' "$(IFS=,; echo "${items[*]}")" > "$out"
}

notes() { # notes <pinned> <candidate> <releases-file>  -> sets N_BUNDLE
  new_step_env
  "$PY" -c "
import json,sys
json.dump({'releases_file': sys.argv[1], 'default_branch':'main'}, open(sys.argv[2],'w'))" "$3" "$GH_STATE"
  GHA_SUBST=()
  export GH_TOKEN=stub PINNED="$1" CANDIDATE="$2"
  run_step 'auto-update-spec-kit__evaluate-path__*fetch-candidate-release-notes*.sh' >/dev/null 2>&1
  N_BUNDLE="$(cat "$RUNNER_TEMP/release-notes.json" 2>/dev/null || echo '[]')"
}

echo "--- Scenario: single-page fixture produces the correct release-note bundle (regression baseline) ---"
F="$(mktemp)"; mkfixture "$F" "v0.15.1:false" "v0.15.0:false" "v0.14.4:false" "v0.16.0:true"
notes "0.14.4" "0.15.1" "$F"
check_contains "single-page: bundle contains the eligible tag" "$N_BUNDLE" "\"tag\":\"v0.15.1\""
check_not_contains "single-page: bundle excludes the pinned release itself" "$N_BUNDLE" "\"tag\":\"v0.14.4\""
check_not_contains "single-page: bundle excludes the prerelease above candidate" "$N_BUNDLE" "\"tag\":\"v0.16.0\""

echo "--- Scenario: >30-release fixture spanning a page boundary (Acceptance Scenario 4) ---"
BULK="$(mktemp)"; mkfixture_bulk "$BULK"
notes "0.15.1" "0.15.5" "$BULK"
check_contains "multi-page: eligible page-2 release v0.15.2 is in the bundle" "$N_BUNDLE" "\"tag\":\"v0.15.2\""
check_contains "multi-page: eligible page-2 release v0.15.4 is in the bundle" "$N_BUNDLE" "\"tag\":\"v0.15.4\""
check_contains "multi-page: eligible page-2 release v0.15.5 is in the bundle" "$N_BUNDLE" "\"tag\":\"v0.15.5\""
check_not_contains "multi-page: the page-2 prerelease v0.15.3 is excluded" "$N_BUNDLE" "\"tag\":\"v0.15.3\""
check_not_contains "multi-page: a page-1 release outside the range is excluded" "$N_BUNDLE" "\"tag\":\"v0.1.1\""
BUNDLE_COUNT="$(printf '%s' "$N_BUNDLE" | jq 'length')"
check "multi-page: bundle contains exactly the 3 eligible releases, nothing else" "$BUNDLE_COUNT" "3"

report "T10 notes"
