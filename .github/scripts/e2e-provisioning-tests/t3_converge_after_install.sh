#!/usr/bin/env bash
# Acceptance Scenario 5 / quickstart step 3: converges to ready once
# app_installation appears, without re-performing anything already ready.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- Scenario 5: converges to ready once the App is installed ---"
new_gh_state
seed_fully_onboarded "wc-user/wc-e2e-converge" false

FIRST="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-converge --profile auto-release 2>/dev/null)"
check "T3 first run (no App install yet) exits 1" "$?" "1"
check "T3 first run reports not ready" "$(jq -r .ready <<<"$FIRST")" "false"
check "T3 first run: only app_installation is not ready" \
  "$(jq -r '[.elements[] | select(.ready==false) | .key] | join(",")' <<<"$FIRST")" "app_installation"

# Simulate a human installing the App -- the only external event.
gh_state_set "wc-user/wc-e2e-converge" "installation" "true"
: > "$GH_CALLS"

SECOND="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-converge --profile auto-release 2>/dev/null)"
check "T3 second run (after App install) exits 0" "$?" "0"
check "T3 second run reports ready" "$(jq -r .ready <<<"$SECOND")" "true"
check_not_contains "T3 second run creates no repo" "$(cat "$GH_CALLS")" "repo create"
check_not_contains "T3 second run edits no repo" "$(cat "$GH_CALLS")" "repo edit"
check_not_contains "T3 second run sets no secret" "$(cat "$GH_CALLS")" "secret set"
check_not_contains "T3 second run creates no label" "$(cat "$GH_CALLS")" "label create"
check_not_contains "T3 second run sets no variable" "$(cat "$GH_CALLS")" "variable set"
check_not_contains "T3 second run PUTs no contents" "$(cat "$GH_CALLS")" "-X PUT"

report "T3 converge after install"
