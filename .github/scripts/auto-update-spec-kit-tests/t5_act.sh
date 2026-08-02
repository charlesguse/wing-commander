#!/usr/bin/env bash
# Scenarios 5, 6, 8, 10: the act job's three branches, executed against a real
# git repo + bare origin and the gh stub.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

mkopts() { printf '{\n  "ai": "claude",\n  "here": true,\n  "script": "sh",\n  "speckit_version": "%s"\n}\n' "$1" > .specify/init-options.json; }

build() { # build -> echoes work repo path; history 0.11.0 -> 0.12.4 -> 0.13.0
  local base; base="$(mktemp -d)"
  # Name the branch explicitly rather than inheriting init.defaultBranch —
  # the ambient default is `main` on some machines and `master` on stock git,
  # and the steps under test read refs/remotes/origin/<db> by name.
  git init -q -b main --bare "$base/origin.git"
  git clone -q "$base/origin.git" "$base/repo" 2>/dev/null
  cd "$base/repo"
  git symbolic-ref HEAD refs/heads/main
  git config user.email t@t; git config user.name t
  mkdir -p .specify .github/actions/wing-commander-preflight
  printf 'inputs:\n  x:\n    default: y\nenv:\n  SPECKIT_SUPPORTED_VERSION: "0.11.0"\n' > .github/actions/wing-commander-preflight/action.yml
  mkopts 0.11.0; git add -A; git commit -qm "init 0.11.0"
  mkopts 0.12.4; sed -i 's/0\.11\.0/0.12.4/' .github/actions/wing-commander-preflight/action.yml
  git add -A; git commit -qm "chore: bump Spec Kit to v0.12.4"
  echo x > R.md; git add -A; git commit -qm "docs: unrelated"
  mkopts 0.13.0; sed -i 's/0\.12\.4/0.13.0/' .github/actions/wing-commander-preflight/action.yml
  git add -A; git commit -qm "chore: bump Spec Kit to v0.13.0"
  git push -q origin main
  git fetch -q --no-tags origin main:refs/remotes/origin/main 2>/dev/null || true
  cd - >/dev/null
  echo "$base/repo"
}

echo "=== Scenario 8: health-check failed WITH a recoverable rollback target ==="
R="$(build)"; new_step_env; cd "$R"
printf '{"issues":{},"prs":{},"labels":[],"next_issue":50,"next_pr":70,"default_branch":"main"}' > "$GH_STATE"
# rollback-target as the FIXED lookup would produce it (the shipped one yields "")
GHA_SUBST=("steps.ctx.outputs.token=stub" "steps.defbranch.outputs.name=main")
export GH_TOKEN=stub DB=main ROLLBACK_TARGET=0.12.4 PINNED_VERSION=0.13.0 BOT_SLUG=wing-commander
export FAILURE_DETAIL="create-new-feature.sh --json exited non-zero: boom: unsupported runtime"
run_step 'auto-update-spec-kit__act__*rollback*.sh' >"$WORK/act.log" 2>&1 || echo "    (step exit $?)"
sed 's/^/      /' "$WORK/act.log" | head -5
ST="$(cat "$GH_STATE")"
check "S8 a revert PR was opened" "$("$PY" -c "import json,os;print(len(json.load(open(os.environ['GH_STATE']))['prs']))")" "1"
PRBODY="$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(list(s['prs'].values())[0]['body'])")"
PRTITLE="$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(list(s['prs'].values())[0]['title'])")"
check_contains "S8 revert PR carries the revert self-marker" "$PRBODY" "auto-update-spec-kit: revert"
check_contains "S8 revert PR states what the health check found" "$PRBODY" "boom: unsupported runtime"
check_not_contains "S8 revert PR has NO Closes keyword (rollback must stay visible)" "$PRBODY" "Closes #"
check_contains "S8 title names both versions" "$PRTITLE" "restore v0.12.4"
check "S8 branch was pushed to origin" "$(git ls-remote origin 'refs/heads/auto-update-spec-kit/revert-v0.12.4' | wc -l)" "1"
echo "    pushed revert branch diff:"
git --no-pager diff main auto-update-spec-kit/revert-v0.12.4 -- .specify/init-options.json | grep -E '^[-+] ' | sed 's/^/      /'
check "S8 revert restores the pin to 0.12.4" "$(MSYS_NO_PATHCONV=1 git show auto-update-spec-kit/revert-v0.12.4:.specify/init-options.json | jq -r .speckit_version)" "0.12.4"
check "S8 revert also restores the preflight constant" "$(MSYS_NO_PATHCONV=1 git show auto-update-spec-kit/revert-v0.12.4:.github/actions/wing-commander-preflight/action.yml | grep -c '0.12.4')" "1"
ISSBODY="$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(list(s['issues'].values())[0]['body'])")"
ISSLABELS="$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(list(s['issues'].values())[0]['labels'])")"
check_contains "S8/SC-004 issue alone states which version failed" "$ISSBODY" "v0.13.0"
check_contains "S8/SC-004 issue alone states what was detected" "$ISSBODY" "boom: unsupported runtime"
check_contains "S8/SC-004 issue alone states what is proposed" "$ISSBODY" "restore v0.12.4"
check_contains "S10 issue is flagged" "$ISSLABELS" "auto-update:failed"
cd - >/dev/null

echo
echo "=== Scenario 8b: health-check failed with NO determinable rollback target ==="
R2="$(build)"; new_step_env; cd "$R2"
printf '{"issues":{},"prs":{},"labels":[],"next_issue":50,"next_pr":70,"default_branch":"main"}' > "$GH_STATE"
GHA_SUBST=("steps.ctx.outputs.token=stub" "steps.defbranch.outputs.name=main")
export GH_TOKEN=stub DB=main ROLLBACK_TARGET="" PINNED_VERSION=0.13.0 BOT_SLUG=wing-commander FAILURE_DETAIL="boom"
run_step 'auto-update-spec-kit__act__*rollback*.sh' >"$WORK/act2.log" 2>&1
check "S8b no PR is opened without a target" "$("$PY" -c "import json,os;print(len(json.load(open(os.environ['GH_STATE']))['prs']))")" "0"
check "S8b a flagged issue is still filed" "$("$PY" -c "import json,os;print(len(json.load(open(os.environ['GH_STATE']))['issues']))")" "1"
check "S8b nothing pushed" "$(git ls-remote origin 'refs/heads/auto-update-spec-kit/*' | wc -l)" "0"
check "S8b pin left untouched on main" "$(git show main:.specify/init-options.json | jq -r .speckit_version)" "0.13.0"
cd - >/dev/null

echo
echo "=== Scenario 8c: the SAME failure twice reuses the open issue (no duplicates) ==="
R3="$(build)"; new_step_env; cd "$R3"
printf '{"issues":{},"prs":{},"labels":[],"next_issue":50,"next_pr":70,"default_branch":"main"}' > "$GH_STATE"
GHA_SUBST=("steps.ctx.outputs.token=stub" "steps.defbranch.outputs.name=main")
export GH_TOKEN=stub DB=main ROLLBACK_TARGET="" PINNED_VERSION=0.13.0 BOT_SLUG=wing-commander FAILURE_DETAIL="boom"
run_step 'auto-update-spec-kit__act__*rollback*.sh' >/dev/null 2>&1
run_step 'auto-update-spec-kit__act__*rollback*.sh' >/dev/null 2>&1
check "S8c still exactly one flagged issue" "$("$PY" -c "import json,os;print(len(json.load(open(os.environ['GH_STATE']))['issues']))")" "1"
check "S8c second run commented instead" "$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(len(list(s['issues'].values())[0]['comments']))")" "1"
cd - >/dev/null

echo
echo "=== Scenario 5: verification passed -> version-bump PR, never merged ==="
R4="$(build)"; new_step_env; cd "$R4"
git checkout -q -B auto-update-spec-kit/v0.15.1 main
mkopts 0.15.1; git add -A; git commit -qm "chore: bump Spec Kit to v0.15.1"
git checkout -q main
printf '{"issues":{"42":{"number":42,"state":"open","body":"watching","labels":[],"comments":[]}},"prs":{},"labels":[],"next_issue":50,"next_pr":70,"default_branch":"main"}' > "$GH_STATE"
GHA_SUBST=("steps.ctx.outputs.token=stub")
export GH_TOKEN=stub BRANCH="auto-update-spec-kit/v0.15.1" CANDIDATE=0.15.1 ISSUE=42 TIER="lightweight+end-to-end" DB=main
run_step 'auto-update-spec-kit__act__*version-bump-pr*.sh' >"$WORK/act4.log" 2>&1 || echo "    (exit $?)"
sed 's/^/      /' "$WORK/act4.log" | head -3
PRBODY="$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(list(s['prs'].values())[0]['body'])")"
check_contains "S5 PR body has Closes #42 (US3 auto-close)" "$PRBODY" "Closes #42"
check_contains "S5 PR body carries the version-bump self-marker" "$PRBODY" "auto-update-spec-kit: version-bump"
check_contains "S5 PR body records what was verified" "$PRBODY" "lightweight+end-to-end"
check "S5 PR is NOT merged by the workflow" "$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(list(s['prs'].values())[0]['mergedAt'])")" "None"
check "S5 no merge call was ever made" "$(grep -c 'pr merge' "$GH_CALLS")" "0"
check "S5 issue got a comment linking the PR" "$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(len(s['issues']['42']['comments']))")" "1"
check "S5 branch pushed" "$(git ls-remote origin 'refs/heads/auto-update-spec-kit/v0.15.1' | wc -l)" "1"
check "S5 default branch pin untouched (PR not merged)" "$(git show main:.specify/init-options.json | jq -r .speckit_version)" "0.13.0"
cd - >/dev/null

echo
echo "=== Scenarios 6/10: verification failed -> no PR, flagged issue stays open ==="
R5="$(build)"; new_step_env; cd "$R5"
printf '{"issues":{"42":{"number":42,"state":"open","body":"watching","labels":[],"comments":[]}},"prs":{},"labels":[],"next_issue":50,"next_pr":70,"default_branch":"main"}' > "$GH_STATE"
GHA_SUBST=("steps.ctx.outputs.token=stub" "needs.prepare.outputs.issue-number=42")
export GH_TOKEN=stub ISSUE=42
# Globs must exclude the prepare-failed twins, whose names extend these.
run_step 'auto-update-spec-kit__act__*-label-the-issue-as-failed.sh' >/dev/null 2>&1
run_step 'auto-update-spec-kit__act__*-apply-the-failed-label.sh' >/dev/null 2>&1
S="$(cat "$GH_STATE")"
check "S6 label exists" "$("$PY" -c "import json,os;print('auto-update:failed' in json.load(open(os.environ['GH_STATE']))['labels'])")" "True"
check "S10 issue carries auto-update:failed" "$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print('auto-update:failed' in s['issues']['42']['labels'])")" "True"
check "S10 issue stays OPEN" "$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(s['issues']['42']['state'])")" "open"
check "S6 no PR opened" "$("$PY" -c "import json,os;print(len(json.load(open(os.environ['GH_STATE']))['prs']))")" "0"
check "S6 nothing pushed to origin" "$(git ls-remote origin 'refs/heads/auto-update-spec-kit/*' | wc -l)" "0"
check "S6 pin unchanged" "$(git show main:.specify/init-options.json | jq -r .speckit_version)" "0.13.0"
check "S6/S10 issue never closed" "$(grep -c 'issue close' "$GH_CALLS")" "0"
cd - >/dev/null

echo
echo "=== #157: prepare FAILED -> issue flagged and left open, nothing adopted ==="
# The silent-death path. prepare failing skipped verify, which skipped act,
# which left the lifecycle issue reading "waiting for the patch stream to
# settle" forever (SC-004/FR-010). The remediation must match the
# verification-failure arm: flag, stay open, touch nothing.
R6="$(build)"; new_step_env; cd "$R6"
printf '{"issues":{"42":{"number":42,"state":"open","body":"Waiting for the patch stream to settle","labels":[],"comments":[]}},"prs":{},"labels":[],"next_issue":50,"next_pr":70,"default_branch":"main"}' > "$GH_STATE"
GHA_SUBST=("steps.ctx.outputs.token=stub" "needs.evaluate-path.outputs.issue-number=42")
export GH_TOKEN=stub ISSUE=42 CANDIDATE=0.15.1
run_step 'auto-update-spec-kit__act__*-label-the-issue-as-failed-prepare-failed.sh' >/dev/null 2>&1
run_step 'auto-update-spec-kit__act__*-apply-the-failed-label-prepare-failed.sh' >"$WORK/act6.log" 2>&1 || echo "    (exit $?)"
check "P1 label exists" "$("$PY" -c "import json,os;print('auto-update:failed' in json.load(open(os.environ['GH_STATE']))['labels'])")" "True"
check "P1 issue carries auto-update:failed" "$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print('auto-update:failed' in s['issues']['42']['labels'])")" "True"
check "P1 issue stays OPEN for the maintainer" "$("$PY" -c "import json,os;s=json.load(open(os.environ['GH_STATE']));print(s['issues']['42']['state'])")" "open"
check "P1 issue never closed" "$(grep -c 'issue close' "$GH_CALLS")" "0"
check "P1 no PR opened" "$("$PY" -c "import json,os;print(len(json.load(open(os.environ['GH_STATE']))['prs']))")" "0"
check "P1 nothing pushed to origin" "$(git ls-remote origin 'refs/heads/auto-update-spec-kit/*' | wc -l)" "0"
check "P1 pin left untouched" "$(git show main:.specify/init-options.json | jq -r .speckit_version)" "0.13.0"
cd - >/dev/null

report "T5 act"
