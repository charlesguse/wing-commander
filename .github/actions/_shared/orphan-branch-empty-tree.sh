#!/usr/bin/env bash
# .github/actions/_shared/orphan-branch-empty-tree.sh
#
# Single home (Gate 60 "orphan-reset") for the three-fragment idiom that
# resets the CURRENT git checkout to a fresh, empty orphan branch: detach,
# recreate as an orphan, and clear the working tree. orphan-branch-reset/
# action.yml (a full clone-then-push composite step) and fold-queue-
# ledger.sh (a retry loop working an already-cloned directory in place)
# both need exactly this reset, at different points in otherwise different
# flows, so the reset itself -- not either caller's surrounding clone/push
# machinery -- is what lives here.
#
# Usage: run from inside the target git working tree --
#   bash ".../_shared/orphan-branch-empty-tree.sh" <branch>
set -uo pipefail

branch="${1:?orphan-branch-empty-tree.sh: <branch> is required}"

git checkout --quiet --orphan "$branch"
git rm -rq --cached . >/dev/null 2>&1 || true
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
