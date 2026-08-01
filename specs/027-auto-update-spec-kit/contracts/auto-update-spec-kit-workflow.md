# Contract: `auto-update-spec-kit.yml` + `wing-commander-auto-update-spec-kit.yml`

This project has no library/API surface; its "interfaces" are the GitHub
Actions trigger contract and the deterministic checks/writes that must
run in order. This document is the contract the implementation (tasks
phase, next stage) must satisfy.

## Trigger contract (wrapper only — the reusable stage never reads `github.event.*`/`vars.*`)

```yaml
on:
  schedule:
    - cron: "13 7 * * *"
  workflow_dispatch: {}
  pull_request:
    types: [closed]
  issue_comment:
    types: [created]

jobs:
  auto-update-spec-kit:
    if: >-
      vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED != 'true'
    permissions:
      contents: write
      issues: write
      pull-requests: write
      id-token: write
    uses: ./.github/workflows/auto-update-spec-kit.yml
    with:
      trigger: >-
        ${{ github.event_name == 'schedule' && 'scheduled'
            || github.event_name == 'workflow_dispatch' && 'dispatch'
            || github.event_name == 'pull_request' && 'pr-merged'
            || 'comment-reply' }}
      pr-number: ${{ github.event.pull_request.number || '' }}
      pr-merged: ${{ github.event.pull_request.merged || false }}
      issue-number: ${{ github.event.issue.number || '' }}
      comment-id: ${{ github.event.comment.id || '' }}
      commenter-association: ${{ github.event.comment.author_association || '' }}
      commenter-id: ${{ github.event.comment.user.id || '' }}
      issue-author-id: ${{ github.event.issue.user.id || '' }}
      stabilization-checks: ${{ vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS || '1' }}
      model: ${{ vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_MODEL || 'claude-sonnet-5' }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

The pause kill-switch is checked in the wrapper's job-level `if:`
(`wing-commander-8-watchdog.yml`'s own corrected shape — a stage-side
check still bills for steps before discovering it's paused). The
`pull_request`/`issue_comment` trigger paths are additionally filtered
*inside* the stage's first job (never by the wrapper's `if:`, which
would need to read PR/comment body content to recognize "is this one of
ours" — that recognition is a data read, not a security gate, and
belongs with the rest of the deterministic logic) — a `pull_request`
event whose PR body lacks the
`<!-- wing-commander-auto-update-spec-kit:` marker, or an `issue_comment`
event on an issue that doesn't carry the settle-tracking marker, is a
no-op run that exits immediately without writing anything.

## Job contract (`auto-update-spec-kit.yml`, `workflow_call` only)

One `concurrency: wing-commander-auto-update-spec-kit` group (not
per-issue or per-run — there is only ever one active upgrade cycle at a
time, FR-015) so a scheduled run, a manual dispatch, and a comment-reply
resume can never race each other.

### `health-check` (runs only for `trigger in [scheduled, dispatch]`)

1. Preflight (`wing-commander-preflight` composite) — same fail-fast as
   every other stage.
2. Run the lightweight verification (below) against the version
   currently pinned in `.specify/init-options.json` on `main`.
3. **Fails** → skip straight to `rollback` (below); the rest of this
   job list does not run this cycle.
4. **Passes** → continue to `detect`.

### `detect` (`needs: health-check` when it ran; otherwise the entry point for `pr-merged`/`comment-reply`)

For `trigger in [scheduled, dispatch]` only:

1. `gh api repos/github/spec-kit/releases --paginate`, filter
   `prerelease == false`, semver-sort, take the highest as
   `latest_upstream`.
2. Compare to the pinned version. Not newer → record "up to date" in the
   job summary, no issue, no PR (SC-007); workflow ends here.
3. Newer → compute `release_type` (patch/minor/major) from the semver
   delta; continue to `settle`.

### `settle` (`needs: detect`)

Implements data-model.md's settle-tracking state machine via `gh search
issues` against the marker (research.md, data-model.md). Every branch
except "settled" ends the run here (a comment is posted; nothing else
happens this cycle). "Settled" continues to `evaluate-path`.

### `evaluate-path` (`needs: settle` when settled, OR the resume path from `comment-reply` after a verified maintainer picks an option)

`claude-sonnet-5` (input `model`), `--max-turns` bounded,
`--allowedTools "Read,Grep,Bash(gh api:*),Bash(git diff:*)"`,
`--disallowedTools "WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*)"`,
structured output via `--json-schema` matching data-model.md's Upgrade
decision record shape. Prompt frames every fetched release-notes body as
untrusted data, never instructions (constitution V) — identical framing
convention every comment-triggered stage already uses for issue bodies.

- `outcome: needs-migration` → comment the reasoning on the issue
  (`wing-commander-callout`, `kind: info`), no diff applied anywhere,
  workflow ends (FR-018).
- `outcome: ambiguous-options` → post the options + reasoning + sources
  as a question (`wing-commander-callout`, `kind: action`), workflow
  ends, awaiting a comment reply (FR-012).
- `outcome: clean-bump` → continue to `prepare`.

### `prepare` (`needs: evaluate-path` when `clean-bump`)

Deterministic: writes the version-bump diff to a fresh branch —
`.specify/init-options.json`'s `speckit_version`,
`wing-commander-preflight`'s `SPECKIT_SUPPORTED_VERSION` constant, and
whatever the candidate's own artifact regeneration produces (research.md
flags the exact regeneration command as a maintainer-confirmation item).
No `git push` yet — the diff is materialized locally for `verify` to
validate against before anything is proposed.

### `verify` (`needs: prepare`, or invoked directly by `health-check` against the currently-pinned version)

1. **Lightweight (always)**: in an isolated temporary worktree, run
   `.specify/scripts/bash/check-prerequisites.sh` and
   `create-new-feature.sh --json` against a throwaway feature name;
   assert exit `0` and the documented JSON shape.
2. **End-to-end (minor/major only, `release_type != patch`)**:
   additionally generate one disposable spec via the equivalent of the
   `/speckit-specify` flow in the same isolated worktree; assert the
   expected files land. Always discarded — never committed, never opens
   a real lifecycle issue, never touches the real `specs/` tree.
3. Output: pass/fail + `failure_detail` (data-model.md's Verification
   result shape).

### `act` (`needs: verify`)

- **From `health-check`'s failure path** → `rollback`: compute the prior
  pinned value from `git log -p -- .specify/init-options.json`
  (research.md), open a revert PR (`Closes` nothing — see
  data-model.md's PR contract), open or reuse a flagged
  `auto-update:failed`-labeled issue explaining what the health check
  found, comment the PR link there. Workflow ends.
- **From `prepare`/`verify` passing** → open the version-bump PR (body
  includes `Closes #<lifecycle-issue-number>`, the decision reasoning +
  sources from `evaluate-path`'s structured output, and what verification
  checked), comment the PR link on the issue. Workflow ends — this
  feature never merges the PR itself (constitution V, FR-017).
- **From `prepare`/`verify` failing** → leave the pin unchanged, comment
  the `failure_detail` on the issue (`wing-commander-callout`, `kind:
  info`), add the `auto-update:failed` label, issue stays open
  (FR-006/FR-010). Workflow ends.

### `pr-merged` job (`trigger == 'pr-merged'`, `pr-merged == 'true'`, PR body carries this feature's marker)

Posts one rich summary comment (adopted version, what was verified) to
the lifecycle issue referenced by the PR's `Closes #N` — the issue is
already closed by GitHub's own keyword-on-merge mechanism by the time
this job runs; a revert PR's merge does **not** close anything (its
issue is the failure record and stays open per FR-010). A merged PR
whose `merged` is `false` (i.e. closed without merging) is a no-op for
this job — nothing to record.

### `comment-reply` job (`trigger == 'comment-reply'`)

1. Verify the commenter:
   `contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'),
   inputs.commenter-association) || inputs.commenter-id ==
   inputs.issue-author-id` (the exact condition
   `wing-commander-2-clarify.yml` already uses). Fails → no-op, no
   comment, no error surfaced (never react to an untrusted commenter,
   constitution V).
2. The issue must carry an `outcome: ambiguous-options` question
   (recognized via the settle-tracking marker plus a "awaiting maintainer
   decision" sub-marker set when `evaluate-path` posted the question) —
   otherwise no-op.
3. `claude-haiku-4-5`, `--max-turns` bounded, read-only
   (`--allowedTools "Read"`), structured output mapping the comment body
   onto one of the previously posted options (or "unrecognized," in
   which case the workflow comments asking for a clearer reply and takes
   no further action).
4. Recognized choice → comment the human's decision on the issue
   (FR-013's "the decision made" now includes whose call it was), then
   re-enter at `prepare` with that chosen path.

## Self-recognition contract (which PRs/comments belong to this feature)

- PR body marker: `<!-- wing-commander-auto-update-spec-kit: version-bump -->`
  or `<!-- wing-commander-auto-update-spec-kit: revert -->`.
- Issue body marker: `<!-- wing-commander-auto-update-spec-kit:
  candidate=X.Y.Z observed=N -->`, with an additional
  `awaiting-decision=true` flag appended when a question is outstanding.
- A `pull_request`/`issue_comment` event lacking the relevant marker is
  always a no-op for this feature — no assumption is made about any
  other PR or issue in the repository.

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- Auto-merging or auto-approving any pull request this stage opens —
  every PR awaits an ordinary human merge click (constitution V,
  research.md; the requester's own auto-merge request is flagged back,
  not silently granted).
- Stepping through every intermediate upstream release when several have
  shipped since the last check — the process targets and verifies the
  latest eligible version directly (spec.md Assumptions).
- Adopting pre-release/release-candidate versions (spec.md Assumptions).
- A fixed calendar stabilization window — settling is cadence-driven
  (consecutive daily observations), never date-driven (FR-002, research.md).
