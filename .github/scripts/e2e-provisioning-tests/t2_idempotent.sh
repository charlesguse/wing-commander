#!/usr/bin/env bash
# Acceptance Scenario 3 / FR-005 / SC-003: re-running against an
# already-ready target is a no-op.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- Scenario 3: re-running against an already-ready target performs zero privileged calls ---"
new_gh_state
seed_fully_onboarded "wc-user/wc-e2e-ready" true

FIRST="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-ready --profile auto-release 2>/dev/null)"
check "T2 first run against an already-ready target exits 0" "$?" "0"
check "T2 first run reports ready" "$(jq -r .ready <<<"$FIRST")" "true"

: > "$GH_CALLS"
SECOND="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-ready --profile auto-release 2>/dev/null)"
check "T2 second run also exits 0" "$?" "0"
check_not_contains "T2 second run creates no repo" "$(cat "$GH_CALLS")" "repo create"
check_not_contains "T2 second run edits no repo" "$(cat "$GH_CALLS")" "repo edit"
check_not_contains "T2 second run sets no secret" "$(cat "$GH_CALLS")" "secret set"
check_not_contains "T2 second run creates no label" "$(cat "$GH_CALLS")" "label create"
check_not_contains "T2 second run sets no variable" "$(cat "$GH_CALLS")" "variable set"
check_not_contains "T2 second run PUTs no contents" "$(cat "$GH_CALLS")" "-X PUT"
check "T2 second run's report matches the first (modulo generated_at)" \
  "$(jq 'del(.generated_at)' <<<"$SECOND")" "$(jq 'del(.generated_at)' <<<"$FIRST")"

report "T2 idempotent"
