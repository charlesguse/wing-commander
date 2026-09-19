#!/usr/bin/env bash
# User Story 3, Acceptance Scenario 3 / data-model.md D3 / quickstart step
# 6's second command: a pre-existing, non-empty, unmarked repository is
# refused, never adopted or deleted.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- a foreign, non-empty, unmarked repository is refused (data-model.md D3) ---"
new_gh_state
tmp="$(mktemp)"
jq --arg full "wc-user/someone-elses-repo" \
  '.repos[$full] = {exists: true, description: "just a normal repository", diskUsage: 42,
    defaultBranch: "main", secrets: [], labels: [], variables: {}, contents: {}, installation: false}' \
  "$GH_STATE" > "$tmp"
mv "$tmp" "$GH_STATE"

OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/someone-elses-repo --profile spec-kit-scratch 2>&1)"
check "T5 refuses with non-zero exit" "$?" "1"
check_contains "T5 names it cannot be established as a reusable scratch target" \
  "$OUT" "cannot be established as a reusable scratch verification target"
check_contains "T5 names what was found instead" "$OUT" "just a normal repository"
check_not_contains "T5 makes no repo create call" "$(cat "$GH_CALLS")" "repo create"
check_not_contains "T5 makes no repo edit call" "$(cat "$GH_CALLS")" "repo edit"
check_not_contains "T5 makes no secret set call" "$(cat "$GH_CALLS")" "secret set"
check_not_contains "T5 makes no label create call" "$(cat "$GH_CALLS")" "label create"

echo "--- an EMPTY pre-existing repository is adopted, not refused ---"
new_gh_state
export CLAUDE_CODE_OAUTH_TOKEN="test-oauth-token-value"
tmp="$(mktemp)"
jq --arg full "wc-user/empty-preexisting" \
  '.repos[$full] = {exists: true, description: null, diskUsage: 0,
    defaultBranch: "main", secrets: [], labels: [], variables: {}, contents: {}, installation: false}' \
  "$GH_STATE" > "$tmp"
mv "$tmp" "$GH_STATE"
OUT="$(bash "$PROVISION_SCRIPT" --repo wc-user/empty-preexisting --profile spec-kit-scratch 2>/dev/null)"
check "T5 an empty pre-existing repo is adopted (repository already ready)" \
  "$(jq -r '.elements[] | select(.key=="repository") | .ready' <<<"$OUT")" "true"
check_not_contains "T5 adopting an empty repo makes no repo create call" "$(cat "$GH_CALLS")" "repo create"

report "T5 refuse foreign"
