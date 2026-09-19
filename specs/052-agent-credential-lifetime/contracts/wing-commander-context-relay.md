# Contract: `wing-commander-context`'s env-var relay and the post-agent refresh convention

**File**: `.github/actions/wing-commander-context/action.yml` (amended) —
consumed by all 8 sweep-stage workflows.

## Composite amendment

`inputs:` and `outputs:` are **unchanged** — `token`, `bot-slug`,
`spec-slug`, `spec-dir` all keep their existing names, types, and meanings
(FR-002, FR-025: no published composite's declared surface widens). One new
internal step is added to `runs.steps`, after `app-token`:

```yaml
- name: Relay bot token to the job environment
  shell: bash
  env:
    TOKEN: ${{ steps.app-token.outputs.token }}
  run: |
    echo "WC_BOT_TOKEN=$TOKEN" >> "$GITHUB_ENV"
```

This step has no `id` and produces no new composite output — it is
plumbing, not contract. A caller that never adopts `env.WC_BOT_TOKEN`
(an adopter pinned to an older release, or a call site this feature's sweep
does not touch) is unaffected: the composite still emits its `token` output
exactly as before, and the extra `$GITHUB_ENV` write is inert if nothing
reads `WC_BOT_TOKEN` (FR-025's compatibility requirement).

## Call-site convention (every one of the 8 sweep-stage workflows)

1. **Before the agent step** (unchanged in count, changed in downstream
   reference): the existing "Wing Commander context" step invocation stays
   exactly where it is. Every step between it and the agent step that
   currently reads `steps.ctx.outputs.token` is migrated to
   `env.WC_BOT_TOKEN` instead — including the "Checkout spec branch as
   wing-commander-bot" step's `token:` input, which is the one caller that
   still needs the raw step-output form is *not* preserved: `actions/
   checkout@v5`'s `token:` input accepts a plain string expression, and
   `env.WC_BOT_TOKEN` is available to it exactly as `steps.ctx.outputs.
   token` was.
2. **Immediately after each agent step** (new): a step named "Re-establish
   Wing Commander context (post-agent)", `if: always()`, invoking
   `wing-commander-context` again with the same inputs the original call
   used (`app-id`, `private-key`, `issue-labels-json` when the stage passes
   it). This step's own outputs are not referenced anywhere — its only
   effect that matters is the relay step inside it rewriting
   `WC_BOT_TOKEN`.
3. **Immediately after step 2** (new): a step named "Refresh authenticated
   spec-branch remote (post-agent)", `if: always()`, `shell: bash`, running
   `git remote set-url origin "https://x-access-token:${WC_BOT_TOKEN}@github.com/${{ github.repository }}.git"` inside the job's existing checkout
   directory — no new checkout, no working-tree change (research.md D2).
4. **Every bot-acting step after the agent step** reads `env.WC_BOT_TOKEN`
   (already true by construction, since step 1 migrated the pre-agent
   references and no new reference form is introduced post-agent).

## `implement.yml`'s three-agent-step job

Steps 2–4 repeat after **each** of `cycle`, `retry`, and `progress` — three
independent refresh triples, each `if: always()` relative to its own
preceding agent step. No step between `retry` and `progress` (or between
`cycle` and `retry`) needs to change which env var it reads: `WC_BOT_TOKEN`
always names "the most recent mint," so the same expression is correct
regardless of which agent step most recently ran.

## `auto-update-spec-kit.yml`'s `e2e-stage` job

Identical shape, second credential: `env.WC_SCRATCH_TOKEN` relayed from
`steps.scratch-token.outputs.token` (research.md D8) via the same pattern —
the scratch-token minting step (not `wing-commander-context`, a distinct
composite/inline mint local to this job) gains the same internal relay, and
the job gains its own post-agent refresh pair (steps 2–3 above, scoped to
`WC_SCRATCH_TOKEN` and whatever remote it authenticates).

## Compatibility (FR-025)

No `workflow_call` input, secret, or output of any of the 8 published stage
workflows changes. No adopter action is required. An adopter who has
already pinned an older release tag is unaffected until they move their pin
forward; once they do, the change is transparent (same inputs/outputs, an
internal env var they never reference).
