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

report t8_scaffold
