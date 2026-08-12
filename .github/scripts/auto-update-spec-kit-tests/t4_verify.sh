#!/usr/bin/env bash
# Scenarios 1, 3, 4, 5, 6, 7: the verify job's per-script assertion chain,
# the e2e-stage read-back, and the verify job's tiering/result combination.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# A fixture worktree carrying real, unmodified Spec Kit scripts/templates
# (this repository's own — the harness's stand-in for "a candidate"), so
# setup-plan.sh/setup-tasks.sh run for real rather than being desk-read.
seed_worktree() { # seed_worktree <dir>
  local wt="$1"
  mkdir -p "$wt/.specify/scripts/bash" "$wt/.specify/templates"
  cp "$REPO"/.specify/scripts/bash/*.sh "$wt/.specify/scripts/bash/"
  cp "$REPO"/.specify/templates/*.md "$wt/.specify/templates/"
}

echo "--- Scenario 7: tier selection (patch = lightweight only; minor/major adds e2e) ---"
combine() { # combine <release-type> <lw-passed> <lw-detail> <e2e-outcome> <e2e-passed> <e2e-detail> [stage-result] [stage-passed] [stage-detail]
  new_step_env
  GHA_SUBST=()
  export RELEASE_TYPE="$1" LW_PASSED="$2" LW_DETAIL="$3" E2E_OUTCOME="$4" E2E_PASSED="$5" E2E_DETAIL="$6"
  export STAGE_RESULT="${7:-success}" STAGE_PASSED="${8:-true}" STAGE_DETAIL="${9:-}"
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

combine minor true "" success true "" failure false "the e2e-stage agent step did not complete"
check "S6 e2e-stage gating failure -> not passed" "$C_PASSED" "false"
check_contains "S6 e2e-stage reason carried" "$C_DETAIL" "did not complete"

echo "--- guard: a minor whose e2e step was skipped because lightweight failed ---"
combine minor false "lightweight blew up" skipped "" ""
check "lightweight failure still fails the combined result" "$C_PASSED" "false"
check_contains "and reports the lightweight reason" "$C_DETAIL" "lightweight blew up"

echo
echo "--- Scenario 1: healthy candidate — the per-script chain passes end to end (SC-002, SC-009) ---"
new_step_env
WT="$RUNNER_TEMP/e2e-healthy"
seed_worktree "$WT"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
printf '# Scratch spec (wing-commander e2e harness fixture)\n' > "$FD/spec.md"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >"$WORK/e2e-healthy.log" 2>&1
check "S1 per-script chain passes for a healthy candidate" "$(out passed)" "true"
check "S1 setup-plan.sh wrote a non-empty plan.md" "$([ -s "$FD/plan.md" ] && echo yes || echo no)" "yes"

echo "--- Scenario 1 (e2e-stage readback): a completed stage with a real spec.md passes ---"
new_step_env
HERE="$PWD"; cd "$RUNNER_TEMP" || exit 1
mkdir -p e2e-scratch/specs/001-throwaway
printf '# Throwaway feature\n' > e2e-scratch/specs/001-throwaway/spec.md
export DECIDE_OUTCOME=success
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*read-back-stage-result*.sh' >/dev/null 2>&1
cd "$HERE" || exit 1
check "S1 e2e-stage readback passes with a real spec.md" "$(out passed)" "true"

echo
echo "--- Scenario 3: a wrong-shape or non-zero-exit script result fails the tier, in isolation (SC-008) ---"

echo "  mutant: spec.md missing/empty (create-new-feature.sh's own silent-empty behaviour)"
new_step_env
WT="$RUNNER_TEMP/e2e-mut-spec"
seed_worktree "$WT"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
: > "$FD/spec.md"   # zero-byte, exactly what create-new-feature.sh's own fallback writes
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check "S3 empty spec.md fails" "$(out passed)" "false"
check_contains "S3 empty spec.md names spec.md" "$(out failure-detail)" "spec.md"

echo "  mutant: setup-plan.sh exits non-zero (its own common.sh sourced dependency broken)"
new_step_env
WT="$RUNNER_TEMP/e2e-mut-plan-exit"
seed_worktree "$WT"
printf '\nthis_command_does_not_exist_1234\n' >> "$WT/.specify/scripts/bash/common.sh"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
printf '# spec\n' > "$FD/spec.md"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check "S3 setup-plan.sh non-zero exit fails" "$(out passed)" "false"
check_contains "S3 names setup-plan.sh" "$(out failure-detail)" "setup-plan.sh"

echo "  mutant: setup-tasks.sh's TASKS_TEMPLATE field renamed (wrong JSON shape)"
new_step_env
WT="$RUNNER_TEMP/e2e-mut-tasks-shape"
seed_worktree "$WT"
sed -i 's/TASKS_TEMPLATE:\$tasks_template/TASKS_TMPL:$tasks_template/' "$WT/.specify/scripts/bash/setup-tasks.sh"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
printf '# spec\n' > "$FD/spec.md"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check "S3 setup-tasks.sh wrong-shape fails" "$(out passed)" "false"
check_contains "S3 names setup-tasks.sh" "$(out failure-detail)" "setup-tasks.sh"

echo "  mutant: setup-tasks.sh exits non-zero (tasks-template.md missing)"
new_step_env
WT="$RUNNER_TEMP/e2e-mut-tasks-exit"
seed_worktree "$WT"
rm -f "$WT/.specify/templates/tasks-template.md"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
printf '# spec\n' > "$FD/spec.md"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check "S3 setup-tasks.sh missing-template fails" "$(out passed)" "false"
check_contains "S3 names setup-tasks.sh" "$(out failure-detail)" "setup-tasks.sh"

echo
echo "--- Scenario 4: e2e-stage did not complete -> passed=false, distinct wording (FR-021) ---"
new_step_env
HERE="$PWD"; cd "$RUNNER_TEMP" || exit 1
export DECIDE_OUTCOME=failure
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*read-back-stage-result*.sh' >/dev/null 2>&1
cd "$HERE" || exit 1
check "S4 incomplete stage -> not passed" "$(out passed)" "false"
S4_DETAIL="$(out failure-detail)"
check_contains "S4 detail states the stage did not complete" "$S4_DETAIL" "did not complete"

echo "  (or: the agent step never reached a success outcome at all, simulating a timeout)"
new_step_env
HERE="$PWD"; cd "$RUNNER_TEMP" || exit 1
export DECIDE_OUTCOME=cancelled
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*read-back-stage-result*.sh' >/dev/null 2>&1
cd "$HERE" || exit 1
check "S4 cancelled stage -> not passed" "$(out passed)" "false"

echo
echo "--- Scenario 5: e2e-stage completes but produces no/wrong-shaped output (FR-018) ---"
new_step_env
HERE="$PWD"; cd "$RUNNER_TEMP" || exit 1
mkdir -p e2e-scratch   # no specs/*/spec.md at all
export DECIDE_OUTCOME=success
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*read-back-stage-result*.sh' >/dev/null 2>&1
cd "$HERE" || exit 1
check "S5 no spec.md -> not passed" "$(out passed)" "false"
S5_DETAIL="$(out failure-detail)"
check_contains "S5 detail names the expected non-empty spec.md" "$S5_DETAIL" "spec.md"
check "S4 vs S5 wording differ (a maintainer can tell infra from candidate defect)" "$([ "$S4_DETAIL" = "$S5_DETAIL" ] && echo same || echo different)" "different"

echo "  (repeat with an empty spec.md — the agent wrote the file but left it blank)"
new_step_env
HERE="$PWD"; cd "$RUNNER_TEMP" || exit 1
mkdir -p e2e-scratch/specs/001-throwaway
: > e2e-scratch/specs/001-throwaway/spec.md
export DECIDE_OUTCOME=success
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*read-back-stage-result*.sh' >/dev/null 2>&1
cd "$HERE" || exit 1
check "S5 empty spec.md -> not passed" "$(out passed)" "false"

report "T4 verify"
