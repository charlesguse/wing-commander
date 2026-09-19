#!/usr/bin/env bash
# Regression coverage for charlesguse's PR #374 review (tasks.md "Maintainer
# Feedback" and "Maintainer Feedback (round 2)" sections, T034-T049): each
# of these would have failed against the pre-fix code, using only the seams
# gh_stub.py already exposes.
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

echo "--- T037/T044: --check-only against a hand-onboarded, non-empty, unmarked target reports ready ---"
new_gh_state
tmp="$(mktemp)"
jq --arg full "wc-user/wc-e2e-t37" \
  '.repos[$full] = {exists: true, description: "hand-onboarded before this feature existed", diskUsage: 42,
    defaultBranch: "main", secrets: ["CLAUDE_CODE_OAUTH_TOKEN"], labels: ["spec-request"],
    variables: {"WING_COMMANDER_CONTAINER_IMAGE": ""}, contents: {}, installation: true}' \
  "$GH_STATE" > "$tmp"
mv "$tmp" "$GH_STATE"
# Stands in for the readiness workflow, the only realistic caller of
# --check-only (T044's Independent Test is framed as the readiness check,
# not this script run bare from a maintainer's shell).
export WC_APP_INSTALLATION_KNOWN_READY=true
OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t37 --profile spec-kit-scratch --check-only 2>/dev/null)"
RC=$?
check "T9 check-only exits 0 (scratch_marker is not applicable on the read-only path)" "$RC" "0"
check "T9 check-only reports ready" "$(jq -r .ready <<<"$OUT")" "true"
check "T9 check-only reports scratch_marker as ready (not applicable, T044)" \
  "$(jq -r '.elements[] | select(.key=="scratch_marker") | .ready' <<<"$OUT")" "true"
check_not_contains "T9 check-only performs no mutating call" "$(cat "$GH_CALLS")" "repo edit"

echo "--- T038/T039: a freshly created, still-empty target is marked immediately, surviving a later content push ---"
new_gh_state
OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t38 --profile spec-kit-scratch 2>/dev/null)"
check "T9 scratch_marker is ready immediately on a freshly created, still-empty target" \
  "$(jq -r '.elements[] | select(.key=="scratch_marker") | .ready' <<<"$OUT")" "true"
check "T9 its description is set to the scratch marker while still empty" \
  "$(gh_state_get "wc-user/wc-e2e-t38" description)" "$SCRATCH_MARKER_FOR_TESTS"
# Simulate e2e-stage later pushing real content, and a human installing the
# App and that being confirmed (T043) -- the two external events that would
# otherwise coincide with the marker never having been written (pre-fix).
gh_state_set "wc-user/wc-e2e-t38" "diskUsage" "100"
export WC_APP_INSTALLATION_KNOWN_READY=true
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

echo "--- T043: app_installation never calls the JWT-only API; it trusts WC_APP_INSTALLATION_KNOWN_READY alone ---"
new_gh_state
seed_fully_onboarded "wc-user/wc-e2e-t43" false
OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t43 --profile auto-release 2>/dev/null)"
check "T9 app_installation is not ready without the hint, even though the stub has no installation endpoint at all" \
  "$(jq -r '.elements[] | select(.key=="app_installation") | .ready' <<<"$OUT")" "false"
check_not_contains "T9 never calls the nonexistent stub installation endpoint" "$(cat "$GH_CALLS")" "installation"
export WC_APP_INSTALLATION_KNOWN_READY=true
: > "$GH_CALLS"
OUT2="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t43 --profile auto-release 2>/dev/null)"
check "T9 app_installation converges to ready from the hint alone" \
  "$(jq -r '.elements[] | select(.key=="app_installation") | .ready' <<<"$OUT2")" "true"

echo "--- T045: the mutating path refuses when neither the git remote nor GITHUB_REPOSITORY resolves this repository ---"
new_gh_state
unset GITHUB_REPOSITORY
REAL_GIT="$(command -v git)"
FAKEGIT_DIR="$(mktemp -d)"
cat > "$FAKEGIT_DIR/git" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do
  if [ "\$a" = "remote.origin.url" ]; then
    exit 1
  fi
done
exec "$REAL_GIT" "\$@"
EOF
chmod +x "$FAKEGIT_DIR/git"
OUT="$(PATH="$FAKEGIT_DIR:$PATH" bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t45 --profile spec-kit-scratch 2>"$WORK/t45-stderr.log")"
RC=$?
check "T9 refuses to proceed when this repository cannot be resolved at all" "$RC" "1"
check_contains "T9 names why it refused (T045)" "$(cat "$WORK/t45-stderr.log")" "could not determine this repository"
check_not_contains "T9 makes no gh call before the unresolved-self refusal" "$(cat "$GH_CALLS")" "repo"
rm -rf "$FAKEGIT_DIR"

echo "--- T046: a failed scratch-marker write halts before any further privileged action ---"
new_gh_state
export CLAUDE_CODE_OAUTH_TOKEN="test-oauth-token-value"
tmp="$(mktemp)"
jq --arg full "wc-user/wc-e2e-t46" \
  '.repos[$full] = {exists: true, description: null, diskUsage: 0, defaultBranch: "main",
    secrets: [], labels: [], variables: {}, contents: {}, installation: false, edit_forbidden: true}' \
  "$GH_STATE" > "$tmp"
mv "$tmp" "$GH_STATE"
bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t46 --profile auto-release >/dev/null 2>"$WORK/t46-stderr.log"
check "T9 exits non-zero when the marker write fails" "$?" "1"
check_contains "T9 names the marker-write failure" "$(cat "$WORK/t46-stderr.log")" "scratch marker"
check_not_contains "T9 sets no secret after a failed marker write" "$(cat "$GH_CALLS")" "secret set"
check_not_contains "T9 creates no label after a failed marker write" "$(cat "$GH_CALLS")" "label create"

echo "--- T047: container_image_pin's comparison never folds a successful call's stderr noise into the compared value ---"
new_gh_state
export WC_SOURCE_CONTAINER_IMAGE="ghcr.io/example/wc-image:v3"
seed_fully_onboarded "wc-user/wc-e2e-t47" true
gh_state_set "wc-user/wc-e2e-t47" "variables" '{"WING_COMMANDER_CONTAINER_IMAGE": "ghcr.io/example/wc-image:v3"}'
gh_state_set "wc-user/wc-e2e-t47" "variables_noisy_stderr" "true"
OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-t47 --profile auto-release --check-only 2>/dev/null)"
check "T9 container_image_pin still reads ready despite noisy stderr on a successful call" \
  "$(jq -r '.elements[] | select(.key=="container_image_pin") | .ready' <<<"$OUT")" "true"

echo "--- T048: gh_stub prints non-ASCII scratch-marker text as UTF-8 regardless of the host's default IO encoding ---"
new_gh_state
seed_fully_onboarded "wc-user/wc-e2e-t48" true
DESC="$(PYTHONIOENCODING=ascii gh repo view wc-user/wc-e2e-t48 --json description -q .description)"
check "T9 the stub's em-dash survives a forced-ASCII default IO encoding" "$DESC" "$SCRATCH_MARKER_FOR_TESTS"

report "T9 maintainer feedback (PR #374)"
