# Contract: FR-006 through FR-009 — the PR-branch resolution composite

research.md D4 explains the sequencing constraint (both call sites run
before their job's checkout) and the round pass-through.

## `.github/actions/_shared/resolve-pr-branch/action.yml` (NEW)

**Internal, never published** (FR-009): header comment states this
explicitly, matching `orphan-branch-reset/action.yml` and
`scoped-app-token/action.yml`'s own canonical sentence — never resolved by
a `workflow_call`-only stage or a published (non-underscore) composite;
Gate 60's promotion-prevention check enforces it. `board-loop.yml` is this
composite's only caller.

**Inputs**:

| Input | Required | Notes |
|---|---|---|
| `pr-number` | yes | The PR to resolve |
| `token` | yes | `GH_TOKEN` for the `gh pr view` call; callers pass `${{ github.token }}` |
| `round` | no (default `""`) | Pass-through only — the composite never derives a round from the PR (FR-007) |

**Outputs**:

| Output | Value |
|---|---|
| `pr-number` | Echoes the `pr-number` input |
| `branch` | `gh pr view <pr-number> -R <repo> --json headRefName --jq .headRefName` |
| `round` | Echoes the `round` input |

`REPO` is read from `${{ github.repository }}` inside the composite step
(no `repo` input — the composite runs in the same job/run context as its
caller, matching today's `-R "$GITHUB_REPOSITORY"`).

**Failure handling (FR-008 — a behavior change; neither current call site
does this today)**:

```bash
set -euo pipefail
branch="$(gh pr view "$PR_NUMBER" -R "$REPO" --json headRefName --jq .headRefName)"
if [ -z "$branch" ]; then
  echo "::error::resolve-pr-branch: PR #$PR_NUMBER resolved an empty head branch" >&2
  exit 1
fi
{
  echo "pr-number=$PR_NUMBER"
  echo "branch=$branch"
  echo "round=$ROUND"
} >> "$GITHUB_OUTPUT"
```

A failed `gh pr view` aborts the step under `set -e` (its exit code
propagates through `branch="$(...)"`); an empty-but-successful read is
caught explicitly. Both cases fail the step loudly rather than writing an
empty `branch=` that a subsequent `actions/checkout@v5` would resolve to
the default branch.

**Call-site replacement**: both `board-loop.yml` sites —
`review` job's "Resolve the PR under review" (`id: pr`, currently
`:2233-2250`) and `readiness` job's "Resolve the PR under readiness"
(`id: pr`, currently `:3159-3170`) — become:

```yaml
- name: Resolve the PR under review   # or "under readiness"
  id: pr
  uses: ./.github/actions/_shared/resolve-pr-branch
  with:
    pr-number: ${{ needs.fix.outputs.pr-number || needs.select.outputs.pr }}
    token: ${{ github.token }}
    round: ${{ needs.select.outputs.round || 0 }}   # review job only
```

The `id: pr` is unchanged, so every existing `steps.pr.outputs.pr-number`
/ `.branch` / `.round` reference downstream (18 call sites across the two
jobs, per research.md's precedent report) needs no edit. Both steps
remain the first step of their job, before `actions/checkout@v5` — the
composite needs no checkout of its own (`gh pr view` only), preserving
today's ordering exactly.

## Wiring

No new gate registration for the composite itself (it is not a
`verify-*` script). The structural single-home check for this idiom is
`pr-branch` in `verify-single-home-idioms.py` — see
`single-home-gate-extension.md`.
