#!/usr/bin/env bash
# .github/scripts/pipeline-checkout-guard.sh
#
# The one place that refuses a checked-out branch which tracks any path under
# .wing-commander-pipeline/ (#611).
#
# WHY THIS EXISTS
# Every published stage checks the pipeline repository out at
# .wing-commander-pipeline/ inside the workspace, then loads its composites
# and scripts from there for the rest of the job, with the App token in
# hand. Several jobs later check a consumer branch out into the workspace
# root with `clean: false` (clean: true would delete the pipeline checkout
# instead). actions/checkout does a forced checkout, so if that branch
# tracks files under .wing-commander-pipeline/, they overwrite the pipeline
# checkout's files, and every composite or script loaded from there after
# that point is code the branch wrote. Moving the pipeline checkout out of
# the workspace is a later change; this guard closes the hole until then.
#
# HOW IT IS INVOKED
# Directly after every such checkout, by a step whose whole run: block is
# pinned byte for byte by Gate 116 (verify-pipeline-checkout-guard.py,
# GUARD_RUN), with `shell: bash`, the checkout's own `if:`, and
# WC_PIPELINE_REF set to the job's resolved pipeline ref. That block first
# verifies, inline, that .wing-commander-pipeline is still the trusted
# checkout: not a symlink, holding a real .git directory, its own
# repository's top level, and (when WC_PIPELINE_REF is a full SHA) at that
# commit. A branch that tracks the path itself (say, a symlink to `.`)
# makes the forced checkout delete the whole untracked directory, .git
# included, and without that check `git -C .wing-commander-pipeline` would
# resolve to the root repository - the branch - and run the branch's own
# copy of this file. On any mismatch the block removes whatever sits at the
# path and fails. Only then does it read this file from the verified
# repository's object store at HEAD, never from its working tree (which a
# hostile branch may just have overwritten), and pipe it to `bash -s`;
# pipefail fails the step if the read fails. Git refuses to track any path
# with a `.git` component, so no branch can write into
# .wing-commander-pipeline/.git/ while the directory survives.
#
# WHAT IT DOES
# - No repository at the workspace root (a checkout that failed before
#   `git init`, under continue-on-error): nothing can be tracked; passes.
# - `git ls-files` at the root fails: fails closed.
# - The branch tracks nothing under .wing-commander-pipeline/: passes.
# - Otherwise: deletes each path the branch tracks there, restores the
#   pipeline checkout's tracked files from its own HEAD (so any always()-
#   gated step that still runs after this failure loads the trusted
#   composites, not the branch's), and fails with an ::error:: naming the
#   branch's commit and the fix. Paths are printed shell-quoted and after a
#   "- " prefix, so a crafted file name cannot become a workflow command.
set -uo pipefail

PIPE=.wing-commander-pipeline

fail() {
  printf '::error::wing-commander: %s\n' "$1"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '%s\n' "$1" >> "$GITHUB_STEP_SUMMARY" || true
  fi
  exit 1
}

if [ ! -e .git ]; then
  echo "pipeline-checkout guard: no repository at the workspace root, so nothing is tracked under $PIPE/."
  exit 0
fi

listing="$(mktemp)" || fail "pipeline-checkout guard: could not create a temporary file; refusing to continue unchecked."
trap 'rm -f "$listing"' EXIT

if ! git ls-files -z -- "$PIPE" > "$listing"; then
  fail "pipeline-checkout guard: 'git ls-files' failed at the workspace root, so whether the checked-out branch tracks $PIPE/ is unknown; refusing to continue."
fi

if [ ! -s "$listing" ]; then
  echo "pipeline-checkout guard: the checked-out branch tracks nothing under $PIPE/."
  exit 0
fi

commit="$(git rev-parse --verify -q HEAD 2>/dev/null || echo unknown)"
count=0
echo "Paths the checked-out branch tracks under $PIPE/ (shell-quoted, first 20):"
while IFS= read -r -d '' p; do
  count=$((count + 1))
  if [ "$count" -le 20 ]; then
    printf -- '- %q\n' "$p"
  fi
  rm -f -- "$p" 2>/dev/null || true
done < "$listing"

if git -C "$PIPE" checkout -q -f HEAD -- . && git -C "$PIPE" diff --quiet HEAD --; then
  restored="The pipeline checkout's tracked files were restored from its own HEAD."
else
  restored="Restoring the pipeline checkout from its own HEAD FAILED; treat every later step in this job as untrusted."
fi

fail "the checked-out branch (commit $commit) tracks $count path(s) under $PIPE/, which is where this job keeps its trusted pipeline checkout; the checkout overwrote those files, so this job stops here rather than run branch-controlled code as pipeline code (#611). $restored Remove the directory from that branch (git rm -r --cached $PIPE) and add $PIPE/ to its .gitignore, then re-run."
