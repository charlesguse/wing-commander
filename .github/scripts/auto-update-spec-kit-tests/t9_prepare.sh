#!/usr/bin/env bash
# Scenario 5's missing half: the prepare job's "Write version-bump diff" step —
# the thing that actually composes the upgrade commit every other job then
# verifies, bundles, and opens a PR for.
#
# That step had no coverage of any kind, which is how PR #201 — the first
# version-bump PR this feature ever managed to open — came to ship a stray
# `.wing-commander-pipeline` gitlink. No human had looked at prepare's diff
# either, because until #201 `act` had never got far enough to open a PR that
# a diff could be read from.
#
# Executed against a real git repo + bare origin, a real `git bundle`, and a
# `uvx` stub standing in for the candidate's own Spec Kit CLI (the one thing
# here that cannot run offline).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

STEP='auto-update-spec-kit__prepare__*write-version-bump-diff*.sh'

mkopts() { printf '{\n  "ai": "claude",\n  "here": true,\n  "script": "sh",\n  "speckit_version": "%s"\n}\n' "$1" > .specify/init-options.json; }

build() { # build -> echoes work repo path; a consumer repo pinned at 0.12.4
  local base; base="$(mktemp -d)"
  # Name the branch explicitly rather than inheriting init.defaultBranch: the
  # ambient default is `main` on some machines and `master` on stock git, and
  # the step reads refs/remotes/origin/<db> by name.
  git init -q -b main --bare "$base/origin.git"
  git clone -q "$base/origin.git" "$base/repo" 2>/dev/null
  cd "$base/repo"
  git symbolic-ref HEAD refs/heads/main
  git config user.email t@t; git config user.name t
  mkdir -p .specify/scripts/bash .specify/integrations .claude/skills/speckit-plan \
           .github/actions/wing-commander-preflight
  printf 'runs:\n  steps:\n    - env:\n        SPECKIT_SUPPORTED_VERSION: "0.12.4"\n' \
    > .github/actions/wing-commander-preflight/action.yml
  mkopts 0.12.4
  printf '{\n  "version": "0.12.4",\n  "installed_integrations": ["claude"]\n}\n' > .specify/integration.json
  printf '{"version": "0.12.4", "files": {}}\n' > .specify/integrations/claude.manifest.json
  echo 'echo common at 0.12.4' > .specify/scripts/bash/common.sh
  echo '# plan skill at 0.12.4' > .claude/skills/speckit-plan/SKILL.md
  # Shipped at the pinned version, gone at the candidate's: `-A` has to stage
  # the deletion too, not only modifications and additions.
  echo 'echo legacy-helper at 0.12.4' > .specify/scripts/bash/legacy-helper.sh
  git add -A; git commit -qm "chore: bump Spec Kit to v0.12.4"
  git push -q origin main
  git fetch -q --no-tags origin main:refs/remotes/origin/main 2>/dev/null || true

  # Production fidelity, and the whole reason this suite exists. EVERY job in
  # the workflow checks the pipeline repository out to `.wing-commander-pipeline`
  # inside the consumer's working tree — actions/checkout refuses a path outside
  # GITHUB_WORKSPACE, so it has nowhere else to go — and that checkout carries
  # its own .git. Omit it from the fixture and the suite is kinder than the
  # runner in exactly the way t5's `git clone <path>` origin was.
  git init -q -b main .wing-commander-pipeline
  (
    cd .wing-commander-pipeline
    git config user.email t@t; git config user.name t
    mkdir -p .github/actions/wing-commander-context
    echo 'name: ctx' > .github/actions/wing-commander-context/action.yml
    git add -A; git commit -qm "pipeline checkout"
  )
  cd - >/dev/null
  echo "$base/repo"
}

# A `uvx` on PATH that records its argv and simulates what `specify integration
# upgrade claude` does to the working tree: restamps integration.json and the
# manifest at the candidate's version, rewrites installed scripts and skills,
# and drops an artifact the candidate no longer ships.
mk_uvx() { # mk_uvx -> echoes a bin dir to prepend to PATH
  local bin; bin="$(mktemp -d)"
  cat > "$bin/uvx" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$UVX_ARGV"
if [ "${UVX_RC:-0}" != 0 ]; then
  # What the real CLI prints when a candidate has moved the command surface —
  # the failure mode the step's error text exists to explain.
  echo "Usage: specify integration [OPTIONS] COMMAND [ARGS]..." >&2
  echo "Error: No such command 'upgrade'." >&2
  exit "$UVX_RC"
fi
if [ "${UVX_NOOP:-0}" != 0 ]; then
  # Upstream's documented no-op path, verbatim in shape: it PRINTS and exits
  # 0 without touching the working tree (src/specify_cli/integrations/
  # _migrate_commands.py, reached when the integration manifest is absent).
  echo "No manifest found for integration 'claude'. Nothing to upgrade."
  echo "Run specify integration install claude to perform a fresh install."
  exit 0
fi
printf '{\n  "version": "%s",\n  "installed_integrations": ["claude"]\n}\n' "$CANDIDATE" > .specify/integration.json
printf '{"version": "%s", "files": {}}\n' "$CANDIDATE" > .specify/integrations/claude.manifest.json
echo "echo common at $CANDIDATE" > .specify/scripts/bash/common.sh
echo "# plan skill at $CANDIDATE" > .claude/skills/speckit-plan/SKILL.md
echo "echo resolve-template at $CANDIDATE" > .specify/scripts/bash/resolve-template.sh
rm -f .specify/scripts/bash/legacy-helper.sh
STUB
  chmod +x "$bin/uvx"
  printf '%s' "$bin"
}

# A PATH with no `uvx` reachable on it, however the host happens to be set up.
# Dropping directories is the only way to hide a tool from `command -v` — PATH
# order cannot mask an executable that really is installed — so the tools the
# step legitimately needs are re-exposed through a shim directory of wrappers
# first, in case uvx was installed into a bin directory it shares with them.
path_without_uvx() {
  local shim; shim="$(mktemp -d)"
  local t p
  for t in git jq sed mv tail cat head grep awk wc; do
    p="$(command -v "$t" 2>/dev/null)" || continue
    [ -n "$p" ] || continue
    printf '#!/usr/bin/env bash\nexec %q "$@"\n' "$p" > "$shim/$t"
    chmod +x "$shim/$t"
  done
  local out="$shim" d
  local -a dirs; IFS=: read -ra dirs <<< "$PATH"
  for d in "${dirs[@]}"; do
    [ -n "$d" ] || continue
    if [ -x "$d/uvx" ] || [ -x "$d/uvx.exe" ]; then continue; fi
    out="$out:$d"
  done
  printf '%s' "$out"
}

tree_has() { # tree_has <ref> <path> -> 1 if the committed tree contains it
  git ls-tree --name-only "$1" -- "$2" | wc -l | tr -d ' '
}

echo "=== Scenario 5a: candidate regenerated, committed, and bundled ==="
R="$(build)"; new_step_env; cd "$R"
GHA_SUBST=("steps.ctx.outputs.bot-slug=wing-commander")
BIN="$(mk_uvx)"; OLDPATH="$PATH"; PATH="$BIN:$PATH"
export UVX_ARGV="$WORK/uvx-argv.log"; : > "$UVX_ARGV"
export DB=main CANDIDATE=0.16.4 BOT_SLUG=wing-commander
run_step "$STEP" >"$WORK/prep.log" 2>&1
RC=$?
sed 's/^/      /' "$WORK/prep.log" | head -5
check "S5a step exit code" "$RC" "0"
B=auto-update-spec-kit/v0.16.4
check "S5a branch output" "$(out branch)" "$B"
check "S5a branch was created" "$(git rev-parse --verify -q "$B" >/dev/null && echo yes || echo no)" "yes"
check "S5a exactly one commit on top of the default branch" \
  "$(git rev-list --count "refs/remotes/origin/main..$B")" "1"
check_contains "S5a commit subject names the candidate" "$(git log -1 --format=%s "$B")" "chore: bump Spec Kit to v0.16.4"
check_contains "S5a commit is authored by the bot" "$(git log -1 --format='%an <%ae>' "$B")" "wing-commander[bot]"

echo "    committed files:"
git diff --name-status "refs/remotes/origin/main" "$B" | sed 's/^/      /'

# The pin, in all three places a consumer's tooling reads it from.
check "S5a init-options.json pin" "$(MSYS_NO_PATHCONV=1 git show "$B:.specify/init-options.json" | jq -r .speckit_version)" "0.16.4"
check "S5a integration.json pin (written by the candidate's own CLI)" \
  "$(MSYS_NO_PATHCONV=1 git show "$B:.specify/integration.json" | jq -r .version)" "0.16.4"
check "S5a preflight constant" \
  "$(MSYS_NO_PATHCONV=1 git show "$B:.github/actions/wing-commander-preflight/action.yml" | grep -c '"0.16.4"')" "1"

# `-A` semantics, which the exclusion must not quietly narrow: regenerated
# files outside .specify (PR #201 changed ten .claude/skills files), brand-new
# files, and deletions all have to land. A "fix" that replaced -A with an
# explicit pathspec list would pass the pin assertions above and fail these.
check "S5a regenerated skill outside .specify is committed" \
  "$(MSYS_NO_PATHCONV=1 git show "$B:.claude/skills/speckit-plan/SKILL.md")" "# plan skill at 0.16.4"
check "S5a newly added script is committed" "$(tree_has "$B" .specify/scripts/bash/resolve-template.sh)" "1"
check "S5a artifact the candidate dropped is deleted" "$(tree_has "$B" .specify/scripts/bash/legacy-helper.sh)" "0"

# The defect PR #201 shipped. `.wing-commander-pipeline` carries its own .git,
# so a bare `git add -A` records a GITLINK rather than recursing — a submodule
# entry with no .gitmodules behind it, pointing at a commit in another
# repository entirely.
check "S5a the pipeline checkout is NOT committed" "$(tree_has "$B" .wing-commander-pipeline)" "0"
check "S5a no gitlink of any kind in the committed tree" \
  "$(git ls-tree -r "$B" | awk '$2 == "commit"' | wc -l | tr -d ' ')" "0"
check "S5a the pipeline checkout is still merely untracked" \
  "$(git status --porcelain -- .wing-commander-pipeline | head -1 | cut -c1-2)" "??"

# The handoff: verify and act never see this working tree, only the bundle.
check "S5a bundle written" "$([ -s "$RUNNER_TEMP/prepare.bundle" ] && echo yes || echo no)" "yes"
CLONE="$WORK/from-bundle"; git init -q -b main "$CLONE"
check "S5a bundle round-trips the prepared branch at the same commit" \
  "$(git -C "$CLONE" fetch -q "$RUNNER_TEMP/prepare.bundle" "$B:refs/heads/$B" 2>/dev/null && git -C "$CLONE" rev-parse "$B")" \
  "$(git rev-parse "$B")"

# The candidate's CLI shape is an upstream moving target the step pins
# deliberately; assert it verbatim rather than trusting that it ran.
check "S5a uvx invoked exactly once" "$(wc -l < "$UVX_ARGV" | tr -d ' ')" "1"
check "S5a uvx command shape" "$(cat "$UVX_ARGV")" \
  "--from git+https://github.com/github/spec-kit.git@v0.16.4 specify integration upgrade claude --script sh --force"
check_contains "S5a step summary reports the branch" "$(summary)" "bumped Spec Kit to v0.16.4 on $B"
PATH="$OLDPATH"
cd - >/dev/null

echo
echo "=== Scenario 5b: uvx absent from the runner (run 31658562063) ==="
R2="$(build)"; new_step_env; cd "$R2"
GHA_SUBST=("steps.ctx.outputs.bot-slug=wing-commander")
OLDPATH="$PATH"; PATH="$(path_without_uvx)"
export DB=main CANDIDATE=0.16.4 BOT_SLUG=wing-commander
run_step "$STEP" >"$WORK/prep2.log" 2>&1
RC2=$?
PATH="$OLDPATH"
sed 's/^/      /' "$WORK/prep2.log" | head -3
check "S5b step fails loudly rather than committing nothing quietly" "$RC2" "1"
check_contains "S5b error names the missing tool and the version it blocked" \
  "$(cat "$WORK/prep2.log")" "'uvx' is not available on this runner"
check_contains "S5b error names the candidate" "$(cat "$WORK/prep2.log")" "v0.16.4"
check "S5b no commit was made" "$(git rev-list --count "refs/remotes/origin/main..auto-update-spec-kit/v0.16.4")" "0"
check "S5b no bundle for verify/act to consume" "$([ -e "$RUNNER_TEMP/prepare.bundle" ] && echo yes || echo no)" "no"
cd - >/dev/null

echo
echo "=== Scenario 5c: the candidate moved Spec Kit's upgrade-CLI shape ==="
R3="$(build)"; new_step_env; cd "$R3"
GHA_SUBST=("steps.ctx.outputs.bot-slug=wing-commander")
BIN="$(mk_uvx)"; OLDPATH="$PATH"; PATH="$BIN:$PATH"
export UVX_ARGV="$WORK/uvx-argv.log"; : > "$UVX_ARGV"
export UVX_RC=2 DB=main CANDIDATE=0.16.4 BOT_SLUG=wing-commander
run_step "$STEP" >"$WORK/prep3.log" 2>&1
RC3=$?
PATH="$OLDPATH"; unset UVX_RC
sed 's/^/      /' "$WORK/prep3.log" | head -4
check "S5c step fails rather than committing a half-applied upgrade" "$RC3" "1"
check_contains "S5c error quotes the exact command that failed" "$(cat "$WORK/prep3.log")" \
  "specify integration upgrade claude --script sh --force"
check_contains "S5c error tells a maintainer what to do about a moved CLI" \
  "$(cat "$WORK/prep3.log")" "re-read it from upstream's source"
# Without this the log tail is the only evidence of WHY, and run 31658562063
# is the standing proof that a silent prepare failure costs days.
check_contains "S5c the candidate CLI's own output is surfaced, not swallowed" \
  "$(cat "$WORK/prep3.log")" "No such command 'upgrade'"
check "S5c no commit was made" "$(git rev-list --count "refs/remotes/origin/main..auto-update-spec-kit/v0.16.4")" "0"
check "S5c the pin on the default branch is untouched" \
  "$(MSYS_NO_PATHCONV=1 git show main:.specify/init-options.json | jq -r .speckit_version)" "0.12.4"
check "S5c no bundle for verify/act to consume" "$([ -e "$RUNNER_TEMP/prepare.bundle" ] && echo yes || echo no)" "no"
cd - >/dev/null

echo
echo "=== Scenario 5d: the CLI no-ops, exits 0, and changes nothing (#191) ==="
# The whole point of the post-condition: exit 0 is not evidence of an upgrade.
# Without it the two deterministic version-string edits below the CLI call
# still fire, `git add -A` still finds a diff, and a commit whose ENTIRE
# content is two version strings goes on to pass verify's lightweight tier —
# because that tier smoke-tests the .specify/scripts that are still the old
# version's and still work.
R4="$(build)"; new_step_env; cd "$R4"
GHA_SUBST=("steps.ctx.outputs.bot-slug=wing-commander")
BIN="$(mk_uvx)"; OLDPATH="$PATH"; PATH="$BIN:$PATH"
export UVX_ARGV="$WORK/uvx-argv.log"; : > "$UVX_ARGV"
export UVX_NOOP=1 DB=main CANDIDATE=0.16.4 BOT_SLUG=wing-commander
run_step "$STEP" >"$WORK/prep4.log" 2>&1
RC4=$?
PATH="$OLDPATH"
sed 's/^/      /' "$WORK/prep4.log" | head -4
check "S5d step fails rather than committing a version-string-only diff" "$RC4" "1"
check_contains "S5d error says the upgrade changed no Spec Kit artifact" \
  "$(cat "$WORK/prep4.log")" "changed no Spec Kit artifact"
check_contains "S5d error names the artifacts it expected to see move" \
  "$(cat "$WORK/prep4.log")" ".claude/skills/speckit-*/"
check_contains "S5d error excludes the pin file from what counts as evidence" \
  "$(cat "$WORK/prep4.log")" "other than .specify/init-options.json"
check_contains "S5d error names the candidate" "$(cat "$WORK/prep4.log")" "v0.16.4"
# Same reason 5c surfaces the CLI's stderr: "Nothing to upgrade" is the one
# line that tells a maintainer WHICH no-op path was taken.
check_contains "S5d the CLI's own no-op message is surfaced, not swallowed" \
  "$(cat "$WORK/prep4.log")" "Nothing to upgrade"
check "S5d uvx was actually invoked (the guard is not short-circuiting it)" \
  "$(wc -l < "$UVX_ARGV" | tr -d ' ')" "1"
check "S5d no commit was made" "$(git rev-list --count "refs/remotes/origin/main..auto-update-spec-kit/v0.16.4")" "0"
check "S5d the pin on the default branch is untouched" \
  "$(MSYS_NO_PATHCONV=1 git show main:.specify/init-options.json | jq -r .speckit_version)" "0.12.4"
check "S5d no bundle for verify/act to consume" "$([ -e "$RUNNER_TEMP/prepare.bundle" ] && echo yes || echo no)" "no"
# A failed `prepare` is the reporting channel: act's
# `needs.prepare.result == 'failure'` arm labels the tracking issue and
# comments the failure on it. That arm reads the JOB result, so the only thing
# this step owes it is a non-zero exit — asserted above — and no `gh` call of
# its own, asserted here (a step that commented directly would double-report).
check "S5d the step reports through the job result, not a channel of its own" \
  "$(wc -l < "$GH_CALLS" | tr -d ' ')" "0"
unset UVX_NOOP
cd - >/dev/null

echo
echo "--- Mutation: without the post-condition, 5d ships the version-string-only commit (T033) ---"
MUT_OLD="$(mktemp)"; MUT_NEW="$(mktemp)"
cat > "$MUT_OLD" <<'EOF'
if [ -z "$speckit_changed" ]; then
EOF
cat > "$MUT_NEW" <<'EOF'
if false; then
EOF
R5="$(build)"; new_step_env; cd "$R5"
GHA_SUBST=("steps.ctx.outputs.bot-slug=wing-commander")
BIN="$(mk_uvx)"; OLDPATH="$PATH"; PATH="$BIN:$PATH"
export UVX_ARGV="$WORK/uvx-argv.log"; : > "$UVX_ARGV"
export UVX_NOOP=1 DB=main CANDIDATE=0.16.4 BOT_SLUG=wing-commander
run_step_mutated "$STEP" "$MUT_OLD" "$MUT_NEW" >"$WORK/prep5.log" 2>&1
RC5=$?
PATH="$OLDPATH"; unset UVX_NOOP
if [ "$RC5" = 0 ]; then
  check "MUTATION: the pre-fix step commits the no-op upgrade" \
    "$(git rev-list --count "refs/remotes/origin/main..auto-update-spec-kit/v0.16.4")" "1"
  # And the commit is exactly the silent mis-application #191 describes: two
  # version strings and nothing spec-kit owns. If this list ever grows, the
  # mutation stopped reproducing the defect.
  check "MUTATION: that commit's entire diff is the two pin files" \
    "$(git diff --name-only "refs/remotes/origin/main" "auto-update-spec-kit/v0.16.4" | sort | tr '\n' ' ')" \
    ".github/actions/wing-commander-preflight/action.yml .specify/init-options.json "
else
  check "MUTATION: the pre-fix step reaches its commit (mutation applied)" "$RC5" "0"
fi
cd - >/dev/null

report t9_prepare
