#!/usr/bin/env bash
# Regression coverage for charlesguse's PR #374 review (tasks.md "Maintainer
# Feedback" section, T034-T042): each of these would have failed against the
# pre-fix code, using only the seams gh_stub.py already exposes.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- T034: spec_request_label is checked via a real gh subcommand ---"
new_gh_state
export CLAUDE_CODE_OAUTH_TOKEN="test-oauth-token-value"
bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t34 --profile auto-release >/dev/null 2>&1
check_not_contains "T9 never calls the nonexistent 'gh label view'" "$(cat "$GH_CALLS")" "label view"
check_contains "T9 checks the label through the labels API instead" "$(cat "$GH_CALLS")" "labels/spec-request"

echo "--- T036: a permission-denied secret/variable read is reported as not-checkable, not a false ready ---"
new_gh_state
export WC_SOURCE_CONTAINER_IMAGE=""
seed_fully_onboarded "wc-user/wc-e2e-t36" true
gh_state_set "wc-user/wc-e2e-t36" "secrets_forbidden" "true"
gh_state_set "wc-user/wc-e2e-t36" "variables_forbidden" "true"
OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t36 --profile auto-release --check-only 2>/dev/null)"
check "T9 claude_credential is not ready when secrets are unreadable" \
  "$(jq -r '.elements[] | select(.key=="claude_credential") | .ready' <<<"$OUT")" "false"
check_contains "T9 claude_credential names it as not checkable, not missing" \
  "$(jq -r '.elements[] | select(.key=="claude_credential") | .remaining_action' <<<"$OUT")" "Not checkable with this token"
check "T9 container_image_pin is not ready when variables are unreadable" \
  "$(jq -r '.elements[] | select(.key=="container_image_pin") | .ready' <<<"$OUT")" "false"
check_contains "T9 container_image_pin names it as not checkable, not missing" \
  "$(jq -r '.elements[] | select(.key=="container_image_pin") | .remaining_action' <<<"$OUT")" "Not checkable with this token"

echo "--- T037: --check-only against a hand-onboarded, non-empty, unmarked target reports readiness, not a bare error ---"
new_gh_state
tmp="$(mktemp)"
jq --arg full "wc-user/wc-e2e-t37" \
  '.repos[$full] = {exists: true, description: "hand-onboarded before this feature existed", diskUsage: 42,
    defaultBranch: "main", secrets: ["CLAUDE_CODE_OAUTH_TOKEN"], labels: ["spec-request"],
    variables: {"WING_COMMANDER_CONTAINER_IMAGE": ""}, contents: {}, installation: true}' \
  "$GH_STATE" > "$tmp"
mv "$tmp" "$GH_STATE"
OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t37 --profile spec-kit-scratch --check-only 2>/dev/null)"
RC=$?
check "T9 check-only exits 1 (scratch_marker not ready)" "$RC" "1"
check "T9 check-only still emits a parseable ReadinessReport" "$(jq -r .target <<<"$OUT" 2>/dev/null)" "wc-user/wc-e2e-t37"
check "T9 check-only names scratch_marker as the not-ready element" \
  "$(jq -r '.elements[] | select(.key=="scratch_marker") | .ready' <<<"$OUT")" "false"
check_not_contains "T9 check-only performs no mutating call" "$(cat "$GH_CALLS")" "repo edit"

echo "--- T038/T039: a freshly created, still-empty target is marked immediately, surviving a later content push ---"
new_gh_state
OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t38 --profile spec-kit-scratch 2>/dev/null)"
check "T9 scratch_marker is ready immediately on a freshly created, still-empty target" \
  "$(jq -r '.elements[] | select(.key=="scratch_marker") | .ready' <<<"$OUT")" "true"
check "T9 its description is set to the scratch marker while still empty" \
  "$(gh_state_get "wc-user/wc-e2e-t38" description)" "$SCRATCH_MARKER_FOR_TESTS"
# Simulate e2e-stage later pushing real content, and a human installing the
# App -- the two external events that would otherwise coincide with the
# marker never having been written (pre-fix).
gh_state_set "wc-user/wc-e2e-t38" "diskUsage" "100"
gh_state_set "wc-user/wc-e2e-t38" "installation" "true"
: > "$GH_CALLS"
SECOND="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t38 --profile spec-kit-scratch 2>/dev/null)"
check "T9 re-provisioning after content exists is adopted, not refused as foreign" "$?" "0"
check "T9 re-provisioning reports ready" "$(jq -r .ready <<<"$SECOND")" "true"
check_not_contains "T9 re-provisioning issues no further repo edit" "$(cat "$GH_CALLS")" "repo edit"

echo "--- T040: a failed source-image read refuses to pin an empty value ---"
new_gh_state
unset WC_SOURCE_CONTAINER_IMAGE
export GITHUB_REPOSITORY="wc-user/this-repo-does-not-exist-in-state"
seed_fully_onboarded "wc-user/wc-e2e-t40" true
gh_state_set "wc-user/wc-e2e-t40" "variables" '{}'
bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t40 --profile auto-release >/dev/null 2>"$WORK/t40-stderr.log"
check "T9 a failed source-image read exits non-zero rather than pinning empty" "$?" "1"
check_not_contains "T9 no variable set call was made with a swallowed-failure empty body" \
  "$(cat "$GH_CALLS")" "variable set WING_COMMANDER_CONTAINER_IMAGE --repo wc-user/wc-e2e-t40 --body "

report "T9 maintainer feedback (PR #374)"
