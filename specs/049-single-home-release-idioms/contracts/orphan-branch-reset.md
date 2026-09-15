# Contract: FR-002, FR-004 (reset sites), FR-005, FR-006, FR-007 — the orphan-branch force-reset

`research.md` D1/D2 explain the composite-vs-script and call-site-path
choices; `data-model.md`'s "Shared Definition: Orphan-branch force-reset"
table gives the field shape.

## `.github/actions/_shared/orphan-branch-reset/action.yml` (NEW)

**Inputs**: `token` (the already-minted, already-verified token — this
composite never mints its own; that is `_shared/scoped-app-token`'s job),
`repo` (`owner/name`), `branch`, `bot-name`, `bot-email`, `workdir`,
`commit-message`.

**Steps**: one `shell: bash` step reproducing exactly today's shared shell
(both current copies read byte-identically over the detach→delete→orphan→
drop-index→clear-tree→commit sequence; only variable names differ):
```
rm -rf "$WORKDIR"
auth_url="https://x-access-token:${TOKEN}@github.com/${REPO}.git"
git clone --quiet "$auth_url" "$WORKDIR"   # on failure: ok=false, failure-stage=clone
(
  cd "$WORKDIR"
  git remote set-url origin "https://github.com/${REPO}.git"
  git config user.name "$BOT_NAME"
  git config user.email "$BOT_EMAIL"
  if git rev-parse --verify HEAD >/dev/null 2>&1; then
    git checkout --quiet --detach
    git branch -D "$BRANCH" >/dev/null 2>&1 || true
    git checkout --quiet --orphan "$BRANCH"
    git rm -rq --cached . >/dev/null 2>&1 || true
    find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  else
    git checkout --quiet -b "$BRANCH"
  fi
  git commit --quiet --allow-empty -m "$COMMIT_MESSAGE"
)
git -C "$WORKDIR" push --force --quiet "$auth_url" "HEAD:refs/heads/${BRANCH}"   # on failure: ok=false, failure-stage=push
```
The tokenised `auth_url` is constructed and used only inside this step's
own shell and is never written to `.git/config` (the `git remote set-url
origin` line rewrites it back to the plain HTTPS URL before the step
ends) — the exact property FR-002 names as load-bearing.

**Outputs**: `ok`, `failure-stage` (`clone` \| `push` \| `""`).

**What stays at the call site**: everything *after* the placeholder commit
— auto-release's issue/PR cleanup that runs *before* this step, and both
callers' own content-scaffolding commit and push that runs *after* it (see
data-model.md). This composite's contract ends at "an empty-tree branch
exists on the remote, ready for real content."

## Call site: `auto-release.yml`, `verify-e2e` job

Replaces the detach-through-push portion of today's "reset" step (lines
227-294) with `uses: ./.github/actions/_shared/orphan-branch-reset`
(`workdir: e2e-test-repo`, `bot-name: wing-commander-auto-release[bot]`,
`branch: "$DEFAULT_BRANCH"` resolved earlier in the job). The preceding
issue/PR cleanup and the following verdict-on-failure handling (reading
`ok`/`failure-stage` into `_shared/auto-release-verdict.sh`) stay in the
job's own steps.

## Call site: `auto-update-spec-kit.yml`, `e2e-stage` job

Replaces the detach-through-push portion of today's "Scaffold and
force-push" step (lines 1815-1850) with
`uses: ./.wing-commander-pipeline/.github/actions/_shared/orphan-branch-reset`
(`workdir: e2e-scratch`, `bot-name: ${{ steps.ctx.outputs.bot-slug }}[bot]`,
`branch: auto-update-spec-kit/e2e-$ISSUE`). The `uvx specify init`
scaffolding, the real-content commit, and its own push stay in the job's
own following steps (a caller pushing real content after this composite
already left an empty commit on the branch — two pushes to the same
branch in sequence, matching today's `git add -A && git commit ... && git
push` tail that follows the reset inline today).

## Fallback (FR-006)

If the composite step is skipped, `ok` is empty (falsy under both call
sites' existing `[ "$OK" = "true" ]` checks), so each caller's existing
downstream failure path already covers this with no new code.

## Gate coverage

Gate 60 fails on any occurrence, anywhere under `.github/workflows/` or
`.github/actions/` outside this composite's own `action.yml`, of the
three-fragment co-occurrence: `checkout --quiet --orphan`,
`git rm -rq --cached`, and the `find . -mindepth 1 -maxdepth 1 ! -name
.git -exec rm -rf` clause.
