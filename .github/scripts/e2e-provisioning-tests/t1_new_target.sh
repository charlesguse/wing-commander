#!/usr/bin/env bash
# Acceptance Scenario 1 / quickstart step 1: a brand-new target converges to
# ready except the declared manual App-installation step.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- Scenario 1: a brand-new target converges to ready except app_installation ---"
new_gh_state
export CLAUDE_CODE_OAUTH_TOKEN="test-oauth-token-value"

OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-scratch --profile auto-release 2>"$WORK/stderr.log")"
RC=$?
check "T1 exits 2 (unverified until the App is installed)" "$RC" "2"
check "T1 overall verdict is unverified" "$(jq -r .verdict <<<"$OUT")" "unverified"
for key in repository claude_credential spec_request_label wrapper_set container_image_pin scratch_marker; do
  check "T1 $key is ready" "$(jq -r --arg k "$key" '.elements[] | select(.key==$k) | .outcome' <<<"$OUT")" "ready"
done
check "T1 app_installation is not checkable" "$(jq -r '.elements[] | select(.key=="app_installation") | .outcome' <<<"$OUT")" "not_checkable"
check_contains "T1 app_installation names the install URL" \
  "$(jq -r '.elements[] | select(.key=="app_installation") | .remaining_action' <<<"$OUT")" \
  "https://github.com/settings/installations"
check_not_contains "T1 stdout never carries the credential value" "$OUT" "test-oauth-token-value"

report "T1 new target"
