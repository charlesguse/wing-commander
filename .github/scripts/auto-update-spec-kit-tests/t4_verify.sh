#!/usr/bin/env bash
# Scenarios 1, 3, 4, 5, 6, 7: the verify job's per-script assertion chain,
# the e2e-stage read-back, and the verify job's tiering/result combination.
#
# Determinism (US4/T029, SC-010, FR-020): every scenario below exercises
# real, unmodified `.specify/scripts/bash/*.sh` scripts against fixture
# worktrees, or the e2e-stage read-back's own deterministic logic driven
# by a plain DECIDE_OUTCOME env var — never a live claude-code-action
# call (that step itself is untestable here, exactly like evaluate-path's
# own `decide` step; only its deterministic read-back is exercised).
# Every `gh repo create`/`delete`/`list` call in this suite goes through
# `gh_stub.py`'s JSON state file (`$GH_STATE`), never a real GitHub API
# call — running this suite twice against the same inputs produces
# identical pass/fail verdicts.
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
combine() { # combine <release-type> <lw-passed> <lw-detail> <e2e-outcome> <e2e-passed> <e2e-detail> [stage-result] [stage-passed] [stage-detail] [scratch-repo] [scratch-branch]
  new_step_env
  GHA_SUBST=()
  export RELEASE_TYPE="$1" LW_PASSED="$2" LW_DETAIL="$3" E2E_OUTCOME="$4" E2E_PASSED="$5" E2E_DETAIL="$6"
  export STAGE_RESULT="${7:-success}" STAGE_PASSED="${8:-true}" STAGE_DETAIL="${9:-}" SCRATCH_REPO="${10:-}"
  export SCRATCH_BRANCH="${11:-auto-update-spec-kit/e2e-42}"
  run_step 'auto-update-spec-kit__verify__*combine*.sh' >/dev/null 2>&1
  C_TIER="$(out tier)"; C_PASSED="$(out passed)"; C_DETAIL="$(out failure-detail)"; C_SUM="$(summary)"
}

# Scenario 8 (Edge Case, US4/T028): a patch jump never reaches e2e-stage at
# all (t7_gating.py's "e2e-stage does NOT run for a patch bump" asserts the
# job-level `if:` directly) — so no scratch repository is ever created for
# this cycle, and combine still reports the unchanged lightweight-only
# shape below, with no scratch-repo pointer appended (no SCRATCH_REPO arg).
combine patch true "" skipped "" ""
check "S7/S8 patch tier" "$C_TIER" "lightweight"
check "S7/S8 patch passed" "$C_PASSED" "true"
check_not_contains "S7/S8 patch narration names no scratch repository" "$C_DETAIL" "wc-speckit-e2e"

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
echo "--- Scenario 2: missing expected artifact fails, no fallback, single outcome (US2, FR-004, SC-002) ---"

echo "  plan-template.md missing -> setup-plan.sh's own silent-empty fallback -> zero-byte plan.md -> tier fails"
new_step_env
WT="$RUNNER_TEMP/e2e-missing-plan-template"
seed_worktree "$WT"
rm -f "$WT/.specify/templates/plan-template.md"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
printf '# spec\n' > "$FD/spec.md"
(cd "$WT" && SPECIFY_FEATURE_DIRECTORY="$FD" bash .specify/scripts/bash/setup-plan.sh --json >"$WORK/setup-plan-missing-template.log" 2>&1)
check "S2 setup-plan.sh itself still exits 0 (its own fallback, not a crash)" "$?" "0"
check "S2 plan.md written as zero-byte, not a substitute" "$([ -f "$FD/plan.md" ] && [ ! -s "$FD/plan.md" ] && echo yes || echo no)" "yes"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check "S2 tier fails on the empty plan.md" "$(out passed)" "false"
check_contains "S2 failure-detail names plan.md" "$(out failure-detail)" "plan.md"

echo "  confirm no locally-manufactured substitute exists anywhere in the extracted step's source"
STEP_SRC_FILE="$(ls "$STEPS"/auto-update-spec-kit__verify__*end-to-end*.sh | head -1)"
STEP_SRC="$(cat "$STEP_SRC_FILE")"
check_not_contains "S2 no cp-from-template fallback in source" "$STEP_SRC" "cp \"\$template\""
check_not_contains "S2 no printf-placeholder fallback in source" "$STEP_SRC" "printf '# Scratch spec"

echo "  spec-template.md missing -> create-new-feature.sh's own identical fallback -> zero-byte spec.md -> tier fails"
new_step_env
WT="$RUNNER_TEMP/e2e-missing-spec-template"
seed_worktree "$WT"
rm -f "$WT/.specify/templates/spec-template.md"
(cd "$WT" && bash .specify/scripts/bash/create-new-feature.sh --json "wing commander e2e missing spec template fixture" >"$WORK/create-new-feature-missing-template.log" 2>&1)
check "S2 create-new-feature.sh itself still exits 0 (its own fallback, not a crash)" "$?" "0"
SPEC_FILE2="$(tail -1 "$WORK/create-new-feature-missing-template.log" | jq -r '.SPEC_FILE // empty' 2>/dev/null || true)"
FD2="$(dirname "$SPEC_FILE2" 2>/dev/null || true)"
check "S2 spec.md written as zero-byte, not a substitute" "$([ -n "$SPEC_FILE2" ] && [ -f "$SPEC_FILE2" ] && [ ! -s "$SPEC_FILE2" ] && echo yes || echo no)" "yes"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD2"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check "S2 tier fails on the empty spec.md" "$(out passed)" "false"
check_contains "S2 failure-detail names spec.md" "$(out failure-detail)" "spec.md"

echo "  a missing-artifact failure reaches the exact same single act branch as every other deeper-tier failure (FR-005/FR-006)"
ACT_FAIL_STEPS="$(grep -c 'name: Comment verification failure on the issue' "$REPO/.github/workflows/auto-update-spec-kit.yml")"
check "only one 'Comment verification failure' step exists (no second outcome path)" "$ACT_FAIL_STEPS" "1"
ACT_LABEL_STEPS="$(grep -c 'name: Apply the failed label$' "$REPO/.github/workflows/auto-update-spec-kit.yml")"
check "only one unconditional 'Apply the failed label' step for verify failures" "$ACT_LABEL_STEPS" "1"

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

echo
echo "--- Scenario 6: missing-artifact narration carries the FR-008 hint; other failures don't (US3, FR-008/FR-009) ---"

echo "  missing-artifact failure (spec.md) carries the hint"
new_step_env
WT="$RUNNER_TEMP/e2e-hint-spec"
seed_worktree "$WT"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
: > "$FD/spec.md"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check_contains "S6 missing spec.md carries the FR-008 hint" "$(out failure-detail)" "FR-018"

echo "  missing-artifact failure (plan.md) carries the hint"
new_step_env
WT="$RUNNER_TEMP/e2e-hint-plan"
seed_worktree "$WT"
rm -f "$WT/.specify/templates/plan-template.md"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
printf '# spec\n' > "$FD/spec.md"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check_contains "S6 missing plan.md carries the FR-008 hint" "$(out failure-detail)" "FR-018"

echo "  a non-zero-exit failure does NOT carry the hint (FR-009: narration content only)"
new_step_env
WT="$RUNNER_TEMP/e2e-hint-exit"
seed_worktree "$WT"
printf '\nthis_command_does_not_exist_1234\n' >> "$WT/.specify/scripts/bash/common.sh"
FD="$WT/specs/029-scratch"
mkdir -p "$FD"
printf '# spec\n' > "$FD/spec.md"
GHA_SUBST=()
export WORKTREE="$WT" FEATURE_DIR="$FD"
run_step 'auto-update-spec-kit__verify__*end-to-end*.sh' >/dev/null 2>&1
check_not_contains "S6 non-zero-exit failure has no FR-008 hint" "$(out failure-detail)" "FR-018"

echo "  an e2e-stage-incomplete failure does NOT carry the hint either"
check_not_contains "S6 e2e-stage-incomplete failure has no FR-008 hint" "$S4_DETAIL" "FR-018"

echo "  every tier=lightweight+end-to-end run's narration names the scratch repository AND branch, pass or fail (SC-012)"
combine minor true "" success true "" success true "" "wing-commander/wc-speckit-e2e"
check_contains "S6 passing run names the scratch repository" "$C_DETAIL" "wing-commander/wc-speckit-e2e"
check_contains "S6 passing run names the branch that holds the evidence" "$C_DETAIL" "auto-update-spec-kit/e2e-42"
combine minor true "" success false "e2e: spec.md never landed" success true "" "wing-commander/wc-speckit-e2e"
check_contains "S6 failing run also names the scratch repository" "$C_DETAIL" "wing-commander/wc-speckit-e2e"
check_contains "S6 failing run also names the branch" "$C_DETAIL" "auto-update-spec-kit/e2e-42"
check_not_contains "S6 narration never promises a deletion this feature cannot do" "$C_DETAIL" "deleted"

echo
echo "--- Scenario 7: the pre-created scratch repository is resolved, never created or deleted (US3, FR-019/022, SC-011) ---"

echo "  the OWNER/NAME split that feeds the scratch-scoped token mint"
new_step_env
export SCRATCH_REPO="wing-commander/wc-speckit-e2e"
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*split-the-scratch-repository*.sh' >/dev/null 2>&1
check "S7 split yields the owner the token is minted against" "$(out owner)" "wing-commander"
check "S7 split yields the repository name" "$(out name)" "wc-speckit-e2e"

echo "  unconfigured: the step FAILS the stage rather than skipping the deepest check (FR-004, no second outcome path)"
new_step_env
export SCRATCH_REPO=""
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*split-the-scratch-repository*.sh' >"$WORK/split-unset.log" 2>&1
check "S7 unconfigured scratch repo fails the step" "$?" "1"
check "S7 unconfigured leaves owner unset" "$(out owner)" ""
check_contains "S7 unconfigured says the candidate is not adopted" "$(cat "$WORK/split-unset.log")" "is not adopted"
check_contains "S7 unconfigured names the variable to set" "$(cat "$WORK/split-unset.log")" "WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO"

# A malformed value must not reach create-github-app-token, where it fails
# with that action's own generic message against a nonsense owner.
for bad in "wing-commander/wc/extra" "wc-speckit-e2e" "wing-commander/" "/wc-speckit-e2e"; do
  new_step_env
  export SCRATCH_REPO="$bad"
  GHA_SUBST=()
  run_step 'auto-update-spec-kit__e2e-stage__*split-the-scratch-repository*.sh' >"$WORK/split-bad.log" 2>&1
  check "S7 malformed '$bad' fails the step" "$?" "1"
  check_contains "S7 malformed '$bad' says what shape is expected" "$(cat "$WORK/split-bad.log")" "OWNER/NAME"
done

echo "  configured and visible: resolves to the repo and this issue's own branch"
new_step_env
export GH_TOKEN=stub TOKEN_OUTCOME=success SCRATCH_REPO="wing-commander/wc-speckit-e2e" ISSUE=77
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*resolve-the-scratch-repository*.sh' >/dev/null 2>&1
check "S7 resolves the configured repository" "$(out full-name)" "wing-commander/wc-speckit-e2e"
check "S7 branch is derived from the lifecycle issue" "$(out branch)" "auto-update-spec-kit/e2e-77"

echo "  a re-dispatch for the same issue resolves identically (the branch IS the per-run isolation)"
: > "$GITHUB_OUTPUT"
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*resolve-the-scratch-repository*.sh' >/dev/null 2>&1
check "S7 re-dispatch resolves the same branch" "$(out branch)" "auto-update-spec-kit/e2e-77"

echo "  NOTHING in this stage creates or deletes a repository (the whole reason it is pre-created)"
check "S7 no repo create call was ever made" "$(grep -c 'repo create' "$GH_CALLS")" "0"
check "S7 no repo delete call was ever made" "$(grep -c 'repo delete' "$GH_CALLS")" "0"

# Run 31679204393: the shared wing-commander-context token is scoped to the
# repository the stage runs in, so it 404s on the scratch repository however
# the App is installed. The scratch-scoped mint is continue-on-error so this
# step can name what to fix — which makes "did the mint actually succeed" a
# gate this step now owns, and an unchecked one would let the stage proceed
# with an empty token and fail later with an unrelated message.
echo "  the scratch-scoped token mint failed: fails HERE, naming the fix, not later on a git error"
new_step_env
export GH_TOKEN="" TOKEN_OUTCOME=failure SCRATCH_REPO="wing-commander/wc-speckit-e2e" ISSUE=88
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*resolve-the-scratch-repository*.sh' >"$WORK/resolve-nomint.log" 2>&1
check "S7 failed token mint fails the step" "$?" "1"
check "S7 failed token mint leaves full-name unset" "$(out full-name)" ""
check_contains "S7 failed token mint names the repository" "$(cat "$WORK/resolve-nomint.log")" "wing-commander/wc-speckit-e2e"
check_contains "S7 failed token mint tells the maintainer to install the App" "$(cat "$WORK/resolve-nomint.log")" "Install the App on that repository"

echo "  ...and a mint that 'succeeded' with an empty token is caught by the same gate"
new_step_env
export GH_TOKEN="" TOKEN_OUTCOME=success SCRATCH_REPO="wing-commander/wc-speckit-e2e" ISSUE=88
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*resolve-the-scratch-repository*.sh' >"$WORK/resolve-emptytok.log" 2>&1
check "S7 empty scratch token fails the step" "$?" "1"
check "S7 empty scratch token leaves full-name unset" "$(out full-name)" ""

echo "  configured but invisible to the App token: fails, and says which of the two things to fix (T037, FR-021 edge case)"
new_step_env
export GH_TOKEN=stub TOKEN_OUTCOME=success SCRATCH_REPO="wing-commander/wc-speckit-e2e" ISSUE=88 GH_STUB_FAIL="repo view"
GHA_SUBST=()
run_step 'auto-update-spec-kit__e2e-stage__*resolve-the-scratch-repository*.sh' >"$WORK/resolve-invisible.log" 2>&1
check "S7 invisible scratch repo fails the step" "$?" "1"
check "S7 invisible leaves full-name unset" "$(out full-name)" ""
check_contains "S7 invisible names the repository" "$(cat "$WORK/resolve-invisible.log")" "wing-commander/wc-speckit-e2e"
check_contains "S7 invisible tells the maintainer to install the App" "$(cat "$WORK/resolve-invisible.log")" "install the App on it"
unset GH_STUB_FAIL

echo "  ...and the verify job's combine step still narrates the incomplete stage, distinguishable from a candidate-artifact failure"
combine minor true "" success true "" failure
check "S7 stage-not-run combined result is not passed" "$C_PASSED" "false"
check_contains "S7 combined detail states the stage did not complete" "$C_DETAIL" "did not complete"
check_not_contains "S7 combined detail is not candidate-artifact wording" "$C_DETAIL" "spec.md"

report "T4 verify"
