#!/usr/bin/env bash
# e2e-stage's scaffold step, run repeatedly against one scratch repository.
#
# The defect this reproduces (run 31905247552) only appears on the SECOND run.
# The first scaffold pushes "$BRANCH" into a scratch repository that has no
# commits yet, and GitHub adopts the first branch pushed to an empty repository
# as that repository's default. From then on `git clone` checks that branch
# out, and `git checkout --orphan "$BRANCH"` aborts with "a branch named ...
# already exists" — exit 128 under `set -e`, before the scaffold writes
# anything. So the step worked exactly once per scratch repository, and every
# later run failed at step 10 with the agent stage skipped behind it.
#
# Everything here is local: the remote is a bare repo on disk, reached by
# rewriting the https URL the step builds, and `uvx` is a stub that just lays
# down files the way `specify init` would.
set -uo pipefail
. "$(dirname "$0")/lib.sh"

SCAFFOLD_STEP='auto-update-spec-kit__e2e-stage__*-scaffold-and-force-push-the-candidate*'

# Stand up a scratch "remote" plus the environment the step expects. Each call
# to scaffold_run below is one pipeline run against the same remote.
setup_scratch() {
  new_step_env
  GHA_SUBST=()

  export SCRATCH_BARE="$WORK/scratch.git"
  git init -q --bare "$SCRATCH_BARE"

  export GH_TOKEN="ghs_testtoken"
  export FULL_NAME="charlesguse/wing-commander-auto-update-scratch"
  export BRANCH="auto-update-spec-kit/e2e-162"
  export CANDIDATE="0.16.4"
  export BOT_SLUG="wing-commander-bot"

  # Point both URLs the step uses (the tokenised clone/push URL and the
  # sanitised origin it resets to) at the bare repo above.
  export HOME="$WORK/home"; mkdir -p "$HOME"
  export GIT_CONFIG_GLOBAL="$HOME/.gitconfig"
  git config --file "$GIT_CONFIG_GLOBAL" \
    "url.$SCRATCH_BARE.insteadOf" "https://x-access-token:$GH_TOKEN@github.com/$FULL_NAME.git"
  git config --file "$GIT_CONFIG_GLOBAL" --add \
    "url.$SCRATCH_BARE.insteadOf" "https://github.com/$FULL_NAME.git"

  # `uvx --from ... specify init ...` stands in for the real CLI: it writes the
  # marker file named by UVX_MARKER into the current directory, so a later run
  # can prove the previous run's tree was cleared rather than added to.
  mkdir -p "$WORK/bin"
  cat > "$WORK/bin/uvx" <<'STUB'
#!/usr/bin/env bash
mkdir -p .specify/scripts/bash
printf 'scaffolded\n' > ".specify/scripts/bash/create-new-feature.sh"
printf '%s\n' "${UVX_MARKER:-marker}" > "${UVX_MARKER:-marker}"
echo "stub specify init ok"
STUB
  chmod +x "$WORK/bin/uvx"
  PATH="$WORK/bin:$PATH"; export PATH

  RUNDIR="$WORK/runs"; mkdir -p "$RUNDIR"
}

scaffold_run() { # scaffold_run <marker-file-name>  -> echoes the step's exit code
  export UVX_MARKER="$1"
  rm -rf "$RUNDIR/w"; mkdir -p "$RUNDIR/w"
  ( cd "$RUNDIR/w" && run_step "$SCAFFOLD_STEP" ) > "$WORK/scaffold-$1.log" 2>&1
  echo "$?"
}

remote() { git --git-dir="$SCRATCH_BARE" "$@"; }

echo "--- first scaffold into an empty scratch repository ---"
setup_scratch
rc="$(scaffold_run first)"
check "run 1 exit code" "$rc" "0"
check "run 1 branch commit count" "$(remote rev-list --count "$BRANCH" 2>/dev/null || echo missing)" "1"
check_contains "run 1 pushed the scaffold" \
  "$(remote ls-tree -r --name-only "$BRANCH" 2>/dev/null)" ".specify/scripts/bash/create-new-feature.sh"
check_contains "run 1 pushed its marker" \
  "$(remote ls-tree -r --name-only "$BRANCH" 2>/dev/null)" "first"

echo
echo "--- GitHub adopts that branch as the empty repository's default ---"
remote symbolic-ref HEAD "refs/heads/$BRANCH"
check "scratch default branch" "$(remote symbolic-ref --short HEAD)" "$BRANCH"

echo
echo "--- second scaffold: same step, same repository, now clones onto \$BRANCH ---"
rc="$(scaffold_run second)"
check "run 2 exit code" "$rc" "0"
check_not_contains "run 2 did not hit the branch-exists fatal" \
  "$(cat "$WORK/scaffold-second.log")" "already exists"
# Orphan, not a child of run 1: the branch is reset, never appended to.
check "run 2 branch commit count" "$(remote rev-list --count "$BRANCH" 2>/dev/null || echo missing)" "1"
check_contains "run 2 pushed its own marker" \
  "$(remote ls-tree -r --name-only "$BRANCH" 2>/dev/null)" "second"
check_not_contains "run 2 cleared run 1's tree" \
  "$(remote ls-tree -r --name-only "$BRANCH" 2>/dev/null)" "first"

echo
echo "--- third scaffold: the failure was not a one-off, so neither is the check ---"
rc="$(scaffold_run third)"
check "run 3 exit code" "$rc" "0"
check "run 3 branch commit count" "$(remote rev-list --count "$BRANCH" 2>/dev/null || echo missing)" "1"
check_contains "run 3 pushed its own marker" \
  "$(remote ls-tree -r --name-only "$BRANCH" 2>/dev/null)" "third"

echo
echo "--- a scratch repository whose default branch is NOT the scaffold branch ---"
# The other shape a scratch repository can have: real history on `main`, with
# the scaffold branch present but not checked out by `git clone`.
setup_scratch
seed="$WORK/seed"; git init -q "$seed"
( cd "$seed" && git config user.email t@t && git config user.name t \
  && echo pre-existing > README.md && git add -A && git commit -qm seed \
  && git branch -m main && git push -q "$SCRATCH_BARE" main \
  && git push -q "$SCRATCH_BARE" "HEAD:refs/heads/$BRANCH" ) >/dev/null 2>&1
remote symbolic-ref HEAD refs/heads/main
rc="$(scaffold_run onmain)"
check "default-main exit code" "$rc" "0"
check "default-main branch commit count" "$(remote rev-list --count "$BRANCH" 2>/dev/null || echo missing)" "1"
check_not_contains "default-main dropped the seeded tree" \
  "$(remote ls-tree -r --name-only "$BRANCH" 2>/dev/null)" "README.md"
check "default-main left main alone" "$(remote rev-list --count main 2>/dev/null || echo missing)" "1"

echo
echo "--- the agent stage's project root (run 31906592089) ---"
# `create-new-feature.sh` picks its project root with `get_repo_root`, which
# walks up from $(pwd) looking for a `.specify/` — NOT up from the script's own
# location. The e2e agent runs from the workspace root, and the consumer
# checkout there is itself a Spec Kit project, so the walk matched on its first
# step: the script wrote its spec.md into the CONSUMER checkout and switched
# that checkout's branch, while e2e-scratch/ stayed empty. The stage was
# verifying the wrong repository and could only ever fail the read-back.
#
# This runs the real pinned scripts, so it doubles as a contract check exactly
# like t3's: a future Spec Kit bump that drops SPECIFY_INIT_DIR fails here, on
# the PR that bumps it, rather than silently re-targeting the consumer.
new_step_env
NEST="$WORK/nest"
mkdir -p "$NEST"
# The outer directory is a Spec Kit project AND a git repo — the consumer.
cp -r "$REPO/.specify" "$NEST/.specify"
( cd "$NEST" && git init -q . && git add -A \
  && git -c user.email=t@t -c user.name=t commit -qm outer ) >/dev/null 2>&1
# The inner one is the scaffolded scratch clone.
mkdir -p "$NEST/e2e-scratch"
cp -r "$REPO/.specify" "$NEST/e2e-scratch/.specify"
( cd "$NEST/e2e-scratch" && git init -q . && git add -A \
  && git -c user.email=t@t -c user.name=t commit -qm inner ) >/dev/null 2>&1
# This repository tracks the .specify scripts as 100644, so a copy of them is
# not executable on Linux — whereas the scratch clone's copies come from
# `specify init`, which writes them executable, and the agent invokes the
# script directly. Restore the production mode rather than invoking through
# `bash`, so the fixture matches how the step is actually run. (Git Bash on
# Windows reports every file as executable, so this only ever bit on CI.)
chmod +x "$NEST/e2e-scratch/.specify/scripts/bash/"*.sh

# Without the override — the production failure, asserted so the fix cannot be
# dropped without this flipping.
( cd "$NEST" && env -u SPECIFY_INIT_DIR \
    e2e-scratch/.specify/scripts/bash/create-new-feature.sh --json "smoke" ) \
  >"$WORK/root-nofix.log" 2>&1
check "unset SPECIFY_INIT_DIR resolves to the CONSUMER checkout (the defect)" \
  "$([ -d "$NEST/specs" ] && echo consumer || echo scratch)" "consumer"
check "unset SPECIFY_INIT_DIR leaves the scratch clone empty" \
  "$([ -d "$NEST/e2e-scratch/specs" ] && echo written || echo empty)" "empty"

# With the override, as the workflow now sets it.
rm -rf "$NEST/specs"
( cd "$NEST" && SPECIFY_INIT_DIR="$NEST/e2e-scratch" \
    e2e-scratch/.specify/scripts/bash/create-new-feature.sh --json "smoke" ) \
  >"$WORK/root-fix.log" 2>&1
fix_rc=$?
check "SPECIFY_INIT_DIR exit code" "$fix_rc" "0"
check "SPECIFY_INIT_DIR writes into the scratch clone" \
  "$([ -d "$NEST/e2e-scratch/specs" ] && echo written || echo empty)" "written"
check "SPECIFY_INIT_DIR leaves the consumer checkout untouched" \
  "$([ -d "$NEST/specs" ] && echo touched || echo clean)" "clean"
check_contains "SPECIFY_INIT_DIR's SPEC_FILE points inside e2e-scratch" \
  "$(cat "$WORK/root-fix.log")" "/e2e-scratch/specs/"
check "the read-back's find pattern matches what the script produced" \
  "$(cd "$NEST" && find e2e-scratch/specs -mindepth 2 -maxdepth 2 -type f -name 'spec.md' | wc -l | tr -d ' ')" "1"

# A candidate that drops the override must fail LOUDLY, not fall back to the
# consumer — that is the whole reason this lever was chosen over a `cd`.
( cd "$NEST" && SPECIFY_INIT_DIR="$NEST/not-a-project" \
    e2e-scratch/.specify/scripts/bash/create-new-feature.sh --json "smoke" ) \
  >"$WORK/root-bad.log" 2>&1
bad_rc=$?
check "a bad SPECIFY_INIT_DIR exits non-zero" "$([ "$bad_rc" -ne 0 ] && echo nonzero || echo zero)" "nonzero"
check_contains "a bad SPECIFY_INIT_DIR says why" "$(cat "$WORK/root-bad.log")" "SPECIFY_INIT_DIR"

# The behaviour above is worthless if the workflow forgets to set it, so assert
# the wiring too — on the agent step specifically, not just anywhere in the file.
DECIDE_ENV="$("$PY" - "$REPO/.github/workflows/auto-update-spec-kit.yml" <<'PY'
import sys, yaml
wf = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
for step in wf["jobs"]["e2e-stage"]["steps"]:
    if step.get("id") == "decide":
        print(step.get("env", {}).get("SPECIFY_INIT_DIR", ""))
        break
PY
)"
check_contains "the agent step declares SPECIFY_INIT_DIR" "$DECIDE_ENV" "e2e-scratch"
check_contains "and it is absolute, not resolved against the agent's cwd" "$DECIDE_ENV" "github.workspace"

report t8_scaffold
