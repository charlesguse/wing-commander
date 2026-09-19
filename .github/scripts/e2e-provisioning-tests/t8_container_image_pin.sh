#!/usr/bin/env bash
# FR-017 / US1 Acceptance Scenario 1 (partial): container_image_pin actually
# exercises act_container_image_pin when this repository pins a real,
# non-empty image and the target's variable is absent or mismatched --
# t1_new_target.sh only ever sees both sides default to "", which is
# vacuously ready without the privileged action ever running.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- Scenario 8: container_image_pin converges a real pinned image onto the target ---"
new_gh_state
export WC_SOURCE_CONTAINER_IMAGE="ghcr.io/example/wc-image:v3"
seed_fully_onboarded "wc-user/wc-e2e-pin" true
# seed_fully_onboarded fixes WING_COMMANDER_CONTAINER_IMAGE at "", which now
# mismatches the real pinned value set above.

CHECK="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-pin --profile auto-release --check-only 2>/dev/null)"
check "T8 check-only exits 1 (image not yet pinned)" "$?" "1"
check "T8 check-only reports not ready" "$(jq -r .ready <<<"$CHECK")" "false"
check "T8 check-only: container_image_pin is not ready" \
  "$(jq -r '.elements[] | select(.key=="container_image_pin") | .ready' <<<"$CHECK")" "false"
check_contains "T8 check-only names WING_COMMANDER_CONTAINER_IMAGE in remaining_action" \
  "$(jq -r '.elements[] | select(.key=="container_image_pin") | .remaining_action' <<<"$CHECK")" \
  "WING_COMMANDER_CONTAINER_IMAGE"
check_not_contains "T8 check-only performs no variable set" "$(cat "$GH_CALLS")" "variable set"

: > "$GH_CALLS"
FIRST="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-pin --profile auto-release 2>/dev/null)"
check "T8 first real run exits 0 (converges the pin)" "$?" "0"
check "T8 first real run reports ready" "$(jq -r .ready <<<"$FIRST")" "true"
check "T8 first real run: container_image_pin is ready" \
  "$(jq -r '.elements[] | select(.key=="container_image_pin") | .ready' <<<"$FIRST")" "true"
check_contains "T8 first real run sets WING_COMMANDER_CONTAINER_IMAGE to the pinned value" \
  "$(cat "$GH_CALLS")" "variable set WING_COMMANDER_CONTAINER_IMAGE --repo wc-user/wc-e2e-pin --body ghcr.io/example/wc-image:v3"

: > "$GH_CALLS"
SECOND="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-pin --profile auto-release 2>/dev/null)"
check "T8 second real run exits 0" "$?" "0"
check "T8 second real run reports ready" "$(jq -r .ready <<<"$SECOND")" "true"
check_not_contains "T8 second real run sets no further variable" "$(cat "$GH_CALLS")" "variable set"

report "T8 container_image_pin"
