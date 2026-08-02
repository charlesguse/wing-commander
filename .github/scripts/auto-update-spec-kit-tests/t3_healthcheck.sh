#!/usr/bin/env bash
# Scenario 8 (+ the health-check half of 6): the pinned-version lightweight
# verification and the git-history rollback-target lookup, run against a REAL
# git repo carrying this repository's actual .specify scripts.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Build a throwaway repo whose history changes speckit_version three times,
# mirroring "adopted 0.11.0 -> 0.12.4 -> 0.13.0 (the regressing merge)".
mkopts() { printf '{
  "ai": "claude",
  "here": true,
  "script": "sh",
  "speckit_version": "%s"
}
' "$1" > .specify/init-options.json; }

build_repo() { # build_repo <dir> [break]
  local d="$1" brk="${2:-}"
  rm -rf "$d"; mkdir -p "$d"; cd "$d"
  git init -q -b main .
  git config user.email t@t; git config user.name t
  mkdir -p .specify/scripts/bash .specify/templates specs .github/actions/wing-commander-preflight
  cp "$REPO"/.specify/scripts/bash/*.sh .specify/scripts/bash/
  cp "$REPO"/.specify/templates/spec-template.md .specify/templates/
  printf 'SPECKIT_SUPPORTED_VERSION: "0.11.0"\n' > .github/actions/wing-commander-preflight/action.yml

  mkopts 0.11.0
  git add -A; git commit -qm "init at 0.11.0"
  mkopts 0.12.4
  git add -A; git commit -qm "chore: bump Spec Kit to v0.12.4"
  echo "unrelated" > README.md; git add -A; git commit -qm "docs: unrelated commit after the bump"
  mkopts 0.13.0
  if [ "$brk" = "break" ]; then
    # A candidate whose scripts are environment-broken — the regression
    # Scenario 8 says verification at merge time did not catch.
    printf '#!/usr/bin/env bash\necho "boom: unsupported runtime" >&2\nexit 3\n' \
      > .specify/scripts/bash/create-new-feature.sh
  fi
  git add -A; git commit -qm "chore: bump Spec Kit to v0.13.0"
  # give the step the origin/<db> ref shape it reads
  git update-ref refs/remotes/origin/main refs/heads/main
  cd - >/dev/null
}

run_verify_pinned() { # run_verify_pinned <repo-dir>
  new_step_env
  cd "$1"
  GHA_SUBST=("steps.defbranch.outputs.name=main")
  export TARGET_REF="refs/remotes/origin/main"
  run_step 'auto-update-spec-kit__health-check__*lightweight-verification*.sh' >"$WORK/vp.log" 2>&1
  V_PASSED="$(out passed)"; V_DETAIL="$(out failure-detail)"; V_SUMMARY="$(summary)"
  cd - >/dev/null
}

run_rollback_target() { # run_rollback_target <repo-dir>
  new_step_env
  cd "$1"
  GHA_SUBST=()
  export DB=main
  run_step 'auto-update-spec-kit__health-check__*rollback-target*.sh' >"$WORK/rt.log" 2>&1
  R_VERSION="$(out version)"; R_LOG="$(cat "$WORK/rt.log")"
  cd - >/dev/null
}

GOOD="$(mktemp -d)/good"; build_repo "$GOOD"
BROKEN="$(mktemp -d)/broken"; build_repo "$BROKEN" break

echo "--- health-check: a HEALTHY pinned version passes the lightweight tier ---"
run_verify_pinned "$GOOD"
check "healthy passed" "$V_PASSED" "true"
check "healthy detail empty" "$V_DETAIL" ""
check_contains "healthy summary" "$V_SUMMARY" "lightweight verification of the pinned version passed"

echo "--- health-check isolation: the real working tree is never mutated ---"
cd "$GOOD"; DIRTY="$(git status --porcelain | wc -l)"; WT="$(git worktree list | wc -l)"; cd - >/dev/null
check "no leftover changes in the working tree" "$DIRTY" "0"
check "isolated worktree removed (only the main one remains)" "$WT" "1"
check "no scratch feature dir landed in specs/" "$(ls "$GOOD/specs" | wc -l)" "0"

echo "--- Scenario 8: a BROKEN pinned version fails, with a stated reason ---"
run_verify_pinned "$BROKEN"
check "broken passed" "$V_PASSED" "false"
check_contains "failure names the failing script" "$V_DETAIL" "create-new-feature.sh"
check_contains "failure carries the captured evidence" "$V_DETAIL" "boom: unsupported runtime"
check_contains "summary states the failure" "$V_SUMMARY" "**failed**"

echo "--- Scenario 8: rollback target read back from git history ---"
run_rollback_target "$BROKEN"
echo "    rollback-target step output: version='$R_VERSION'"
echo "    step stderr/stdout:"; printf '%s\n' "$R_LOG" | sed 's/^/      /'
check "rollback target = the value before the regressing merge" "$R_VERSION" "0.12.4"

report "T3 health-check + rollback"
