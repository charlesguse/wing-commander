# Contract Delta: `wing-commander-rebase.yml`

There is no prior contract document for this wrapper — this is the first
spec to touch it since `specs/008-auto-rebase/` and
`specs/013-serialize-rebase-stages/` established its current shape. This
delta describes only what this feature adds or changes. `rebase.yml` (the
`workflow_call`-only published stage this wrapper calls) is **not** part of
this delta — it is unchanged (constitution VII, FR-006, FR-007) — see
`docs/architecture.md` and `specs/010-reusable-pipeline/contracts/` for its
existing, unmodified contract.

## Trigger contract addition

```yaml
on:
  push:
    branches: [main]
  schedule:
    - cron: "17 4 * * *"
  workflow_dispatch: {}    # NEW — the redispatch target; no inputs needed,
                            # `discover` (inside rebase.yml) re-derives the
                            # in-flight branch set from repository state
                            # every run regardless of trigger
```

**Purpose**: FR-001 — gives the `push`-triggered path a supported event to
redispatch through. `workflow_dispatch` is already proven, in this
repository, to reach a `claude-code-action` step successfully (data-model.md
Supported-Event Set table).

**Behavior**: Manual dispatch (`gh workflow run wing-commander-rebase.yml`)
now also works as a genuinely independent manual trigger, in addition to
being the redispatch target — this is additive, not a behavior change for
anyone already using `push`/`schedule`.

## Job contract: split `rebase` into `redispatch` + `rebase`

**Before**:

```yaml
jobs:
  rebase:
    if: ${{ !endsWith(github.actor, '[bot]') }}
    permissions:
      contents: write
      issues: write
      id-token: write
    uses: ./.github/workflows/rebase.yml
    with:
      model: ${{ vars.WING_COMMANDER_PLAN_MODEL || 'claude-sonnet-5' }}
      spec-prefix: ${{ vars.WING_COMMANDER_SPEC_PREFIX || 'spec/' }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

**After**:

```yaml
jobs:
  # Push cannot reach claude-code-action directly (research.md R1) —
  # redispatch through workflow_dispatch, a supported event, instead of
  # calling the reusable stage from here. Bot-loop guard stays here: it
  # exists to stop the pipeline's own push from re-triggering a cycle, and
  # that concern is push-specific (research.md R4).
  redispatch:
    if: ${{ github.event_name == 'push' && !endsWith(github.actor, '[bot]') }}
    runs-on: ubuntu-latest
    permissions:
      actions: write
    steps:
      - name: Redispatch via workflow_dispatch (a supported event for the conflict-resolution agent)
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          gh workflow run wing-commander-rebase.yml \
            --repo "$GITHUB_REPOSITORY" \
            --ref "${{ github.ref_name }}"

  # schedule and workflow_dispatch (including this file's own redispatch,
  # above) are both proven to reach claude-code-action successfully
  # (data-model.md). Allow-list form, not `!= 'push'` (research.md R5).
  rebase:
    if: ${{ github.event_name == 'schedule' || github.event_name == 'workflow_dispatch' }}
    permissions:
      contents: write
      issues: write
      id-token: write
    uses: ./.github/workflows/rebase.yml
    with:
      model: ${{ vars.WING_COMMANDER_PLAN_MODEL || 'claude-sonnet-5' }}
      spec-prefix: ${{ vars.WING_COMMANDER_SPEC_PREFIX || 'spec/' }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

**Purpose**: FR-001, FR-002, FR-003, FR-006 — the `rebase` job's `with:`/
`secrets:` block is byte-for-byte unchanged from before this feature; only
its `if:` and the job split around it change. `rebase.yml` receives
identical inputs regardless of which event ultimately reached it, so its
behavior (clean rebase, conflict resolution, abandon+escalate) is
trigger-independent by construction (FR-002).

**Behavior**:

1. A `push` to `main` by a non-bot actor now produces a lightweight
   `redispatch` run (checkout-free, single `gh` call) that ends in seconds,
   plus a second, independently-queued `workflow_dispatch` run that does
   the actual rebase work. Both are visible in the Actions run list; the
   second is where `rebase.yml`'s `discover`/`rebase` jobs and any
   escalation comment appear.
2. A bot-authored push (`<slug>[bot]`) still short-circuits at `redispatch`
   — no redispatch, no second run, matching today's loop-guard behavior
   exactly (research.md R4).
3. `schedule` is unaffected in shape — it still reaches `rebase.yml`
   directly, one run, no redispatch hop (data-model.md).
4. Manual `gh workflow run wing-commander-rebase.yml` (or the Actions UI
   "Run workflow" button) now works as a first-class entry point — the
   `rebase` job's `if:` explicitly allows `workflow_dispatch` regardless of
   whether it originated from `redispatch` or a human.

**Permissions**: `redispatch` gets exactly `actions: write` (least
privilege — constitution V) and nothing else; it performs no repository
content write, issue write, or checkout. `rebase`'s permissions are
unchanged from before this feature.

**Non-goals**: This delta does not change `rebase.yml`'s `with:` inputs, do
anything about `pipeline-repo`/`pipeline-ref`/`use-bedrock`/tool-list
inputs (all defaulted, untouched), or alter the escalation/publish logic
inside `rebase.yml` in any way — FR-005's "must not regress" holds by
construction, since that file is not part of this delta.
