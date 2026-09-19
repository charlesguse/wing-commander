#!/usr/bin/env bash
# FR-016 / SC-008: no code path in this feature ever issues a `gh repo
# delete`, `gh repo archive`, or equivalent call. Mirrors how
# auto-update-spec-kit-tests/t4_verify.sh already asserts the narrower
# e2e-stage scope.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- FR-016/SC-008: no code path ever deletes or archives a repository ---"
FILES=(
  "$REPO/.github/scripts/provision-e2e-target.sh"
  "$REPO/.github/scripts/e2e-provisioning/profiles.sh"
  "$REPO/.github/scripts/e2e-provisioning/checks.sh"
)
for f in "${FILES[@]}"; do
  name="$(basename "$f")"
  check "T6 $name issues no 'repo delete'" "$(grep -c 'repo delete' "$f")" "0"
  check "T6 $name issues no 'repo archive'" "$(grep -c 'repo archive' "$f")" "0"
  check "T6 $name issues no '--add-topic.*delete\|DELETE method' contents call" \
    "$(grep -cE 'gh api .*-X[[:space:]]+DELETE|--method[[:space:]]+DELETE' "$f")" "0"
done

report "T6 no delete"
