#!/usr/bin/env bash
# Scenarios 5, 6, 7: the verify job's tiering and result combination.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "--- Scenario 7: tier selection (patch = lightweight only; minor/major adds e2e) ---"
combine() { # combine <release-type> <lw-passed> <lw-detail> <e2e-outcome> <e2e-passed> <e2e-detail>
  new_step_env
  GHA_SUBST=()
  export RELEASE_TYPE="$1" LW_PASSED="$2" LW_DETAIL="$3" E2E_OUTCOME="$4" E2E_PASSED="$5" E2E_DETAIL="$6"
  run_step 'auto-update-spec-kit__verify__*combine*.sh' >/dev/null 2>&1
  C_TIER="$(out tier)"; C_PASSED="$(out passed)"; C_DETAIL="$(out failure-detail)"; C_SUM="$(summary)"
}

combine patch true "" skipped "" ""
check "S7 patch tier" "$C_TIER" "lightweight"
check "S7 patch passed" "$C_PASSED" "true"

combine minor true "" success true ""
check "S7 minor tier" "$C_TIER" "lightweight+end-to-end"
check "S7 minor passed" "$C_PASSED" "true"

combine major true "" success true ""
check "S7 major tier" "$C_TIER" "lightweight+end-to-end"

echo "--- Scenario 6: verification failure propagates with its reason ---"
combine patch false "create-new-feature.sh --json exited non-zero: boom" skipped "" ""
check "S6 patch lightweight failure -> not passed" "$C_PASSED" "false"
check_contains "S6 reason carried forward" "$C_DETAIL" "boom"
check_contains "S6 summary marks failure" "$C_SUM" "**failed**"

combine minor true "" success false "e2e: spec.md never landed"
check "S6 minor e2e failure -> not passed" "$C_PASSED" "false"
check_contains "S6 e2e reason carried" "$C_DETAIL" "spec.md never landed"

echo "--- guard: a minor whose e2e step was skipped because lightweight failed ---"
combine minor false "lightweight blew up" skipped "" ""
check "lightweight failure still fails the combined result" "$C_PASSED" "false"
check_contains "and reports the lightweight reason" "$C_DETAIL" "lightweight blew up"

echo
echo "--- Scenario 7 (e2e step): does it operate on the right path? ---"
# check-prerequisites.sh emits FEATURE_DIR as an ABSOLUTE path (verified
# against the real repo). The e2e step builds its target as "$WORKTREE/$FEATURE_DIR".
new_step_env
WT="$RUNNER_TEMP/verify-candidate"
mkdir -p "$WT/.specify/templates" "$WT/specs/028-scratch"
cp "$REPO/.specify/templates/spec-template.md" "$WT/.specify/templates/"
ABS_FEATURE_DIR="$WT/specs/028-scratch"     # exactly what check-prerequisites --paths-only returns
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$ABS_FEATURE_DIR"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >"$WORK/e2e.log" 2>&1
E_PASSED="$(out passed)"; E_DETAIL="$(out failure-detail)"
echo "    WORKTREE=$WT"
echo "    FEATURE_DIR=$ABS_FEATURE_DIR   (absolute, as the script emits it)"
echo "    step wrote target = \$WORKTREE/\$FEATURE_DIR/spec.md"
echo "    step log:"; sed 's/^/      /' "$WORK/e2e.log" | head -5
check "e2e passed with a real absolute FEATURE_DIR" "$E_PASSED" "true"
check "spec.md actually landed in the feature dir" "$([ -s "$ABS_FEATURE_DIR/spec.md" ] && echo yes || echo no)" "yes"

report "T4 verify"
