#!/usr/bin/env bash
# Acceptance Scenario 1 / quickstart step 1: a brand-new target converges to
# ready except the declared manual App-installation step.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- Scenario 1: a brand-new target converges to ready except app_installation ---"
new_gh_state
export CLAUDE_CODE_OAUTH_TOKEN="test-oauth-token-value"

OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-scratch --profile auto-release 2>"$WORK/stderr.log")"
RC=$?
check "T1 exits 1 (not ready until the App is installed)" "$RC" "1"
check "T1 overall ready is false" "$(jq -r .ready <<<"$OUT")" "false"
for key in repository claude_credential spec_request_label wrapper_set container_image_pin scratch_marker; do
  check "T1 $key is ready" "$(jq -r --arg k "$key" '.elements[] | select(.key==$k) | .ready' <<<"$OUT")" "true"
done
check "T1 app_installation is not ready" "$(jq -r '.elements[] | select(.key=="app_installation") | .ready' <<<"$OUT")" "false"
check_contains "T1 app_installation names the install URL" \
  "$(jq -r '.elements[] | select(.key=="app_installation") | .remaining_action' <<<"$OUT")" \
  "https://github.com/settings/installations"
check_not_contains "T1 stdout never carries the credential value" "$OUT" "test-oauth-token-value"

report "T1 new target"
