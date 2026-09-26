#!/usr/bin/env bash
# User Story 2 / SC-006 / FR-011: the generalized readiness-check workflow
# never invokes provision-e2e-target.sh without --check-only, and a no-input
# dispatch resolves the same target/profile as today's single-scratch-repo
# behaviour.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

WORKFLOW="$REPO/.github/workflows/auto-update-spec-kit-scratch-preflight.yml"
TEXT="$(cat "$WORKFLOW")"

echo "--- SC-005/SC-006: no privileged action is reachable from this workflow ---"
# Only executable invocations -- a `run:` line actually calling the script
# -- not a comment merely naming it.
INVOCATIONS="$(grep -nE '(^|[^#[:alnum:]])(bash )?\.github/scripts/provision-e2e-target\.sh' "$WORKFLOW" | grep -vE '^[0-9]+:[[:space:]]*#' || true)"
check "T7 the workflow calls provision-e2e-target.sh at least once" "$([ -n "$INVOCATIONS" ] && echo yes || echo no)" "yes"
BAD="$(printf '%s\n' "$INVOCATIONS" | grep -v -- '--check-only' || true)"
check "T7 every invocation carries --check-only" "$([ -z "$BAD" ] && echo none || echo "$BAD")" "none"

echo "--- FR-011: a no-input dispatch resolves the same target/profile as today's behaviour ---"
check_contains "T7 profile defaults to spec-kit-scratch" "$TEXT" 'default: "spec-kit-scratch"'
check_contains "T7 target defaults to empty (falls back to a configured variable)" "$TEXT" 'default: ""'
check_contains "T7 empty target for spec-kit-scratch falls back to the scratch repo variable" \
  "$TEXT" "WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO"
check_contains "T7 empty target for auto-release falls back to its own repo variable" \
  "$TEXT" "WING_COMMANDER_AUTO_RELEASE_E2E_REPO"
check_contains "T7 an unset resolved target fails loudly, naming docs/setup.md" "$TEXT" "docs/setup.md"

echo "--- the trigger stays workflow_dispatch only (no pause kill-switch, by design) ---"
check_not_contains "T7 no schedule trigger was added" "$TEXT" "schedule:"

echo "--- T035: app_installation is answered from the token-mint outcome, not a JWT-only API call ---"
check_contains "T7 the readiness check tells checks.sh installation is already known ready" \
  "$TEXT" "WC_APP_INSTALLATION_KNOWN_READY"

echo "--- 069 US1: the job summary renders the tri-state outcome/verdict, not the retired boolean ---"
READINESS_STEP="$(printf '%s\n' "$TEXT" | sed -n '/name: Run the readiness check/,/^      - name:/p')"
check_contains "T7 the job-summary table keys its glyph on .outcome, not the retired .ready" \
  "$READINESS_STEP" ".outcome"
check_not_contains "T7 the job-summary table never reads the retired .ready field" \
  "$READINESS_STEP" ".ready"
check_contains "T7 the job summary renders three distinct outcomes, including a not_checkable glyph" \
  "$READINESS_STEP" "➖"
check_contains "T7 the job summary names the aggregate verdict, not just pass/fail" \
  "$READINESS_STEP" ".verdict"

report "T7 readiness workflow"
