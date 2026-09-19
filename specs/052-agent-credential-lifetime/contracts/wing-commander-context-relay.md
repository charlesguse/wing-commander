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

## Corrected from this contract's original design (maintainer review of PR #407)

- Steps 2 and 3 below are each single-homed as shared composites
  (`.github/actions/wing-commander-refresh-remote/action.yml`; step 2 stays
  a direct `wing-commander-context` call, not its own composite, since a
  composite step's own `uses:` cannot reliably resolve a nested local
  composite call — CLAUDE.md single-home rule) rather than an inline `run:`
  block repeated at every call site.
- A fourth step, `wing-commander-post-agent-credential-status`, follows:
  given steps 2 and 3's own outcomes, it never fails the job itself
  (second maintainer review of PR #407) — a re-mint failure at this, the
  job's own last step, with every earlier step healthy, means the stage
  already did its work, so hard-failing here would report a false
  "stalled" outcome. It instead warns, naming the credential as cause when
  either did not succeed, and publishes a job-scoped `credential-refresh-
  ok` output for the stall path to read (FR-004, contracts/agent-ran-
  signal.md) — `wing-commander-stall-reason`'s ok-first check is what
  attributes a *later, real* failure to the credential, and a named
  post-agent step failure always outranks this credential-only diagnosis
  (third maintainer review of PR #407). This step is deferred to the
  job's own last steps — after every business-logic/report step the agent
  step's own success gates, not immediately after step 3 — so a warning
  here cannot strand any of them (review-step-gating self-review).
- Steps 1-3 (and the deferred step 4) use `if: "!cancelled() && ..."`, not
  `if: "always() && ..."`: a run cancelled during the agent step must not
  still perform a network mint or a remote rewrite in the cancel window
  (should-fix, maintainer review of PR #407).

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
   Wing Commander context (post-agent)", `if: always() && steps.<agent-id>.
   outcome != 'skipped'` (the outcome guard means a stage dispatched with
   its lifecycle gate closed, which skips the agent step itself, mints no
   unneeded token either), invoking `wing-commander-context` again with the
   same inputs the original call used (`app-id`, `private-key`,
   `issue-labels-json` when the stage passes it). This step's own outputs
   are not referenced anywhere — its only effect that matters is the relay
   step inside it rewriting `WC_BOT_TOKEN`.
3. **Immediately after step 2** (new): a step named "Refresh authenticated
   spec-branch remote (post-agent)", same `if:` guard as step 2, `shell:
   bash`, running, inside the job's existing checkout directory — no new
   checkout, no working-tree change (research.md D2):
   ```bash
   git config --local --unset-all "http.https://github.com/.extraheader" 2>/dev/null || true
   git remote set-url origin "https://x-access-token:${WC_BOT_TOKEN}@github.com/${{ github.repository }}.git"
   ```
   The `git config --unset-all` line is load-bearing, not defensive
   cleanup: `actions/checkout@v5` (default `persist-credentials: true`,
   unchanged by this feature) authenticates via that local
   `http.https://github.com/.extraheader` config entry, not via any
   credential embedded in the remote URL, and a custom `Authorization`
   header set this way takes precedence over one git's http transport would
   otherwise derive from the URL's embedded userinfo. Without clearing it
   first, `git remote set-url`'s fresh token is never actually used by any
   subsequent `git fetch`/`push` against `origin` (research.md D2's
   correction, found in this feature's own T046 code review).
4. **Every bot-acting step after the agent step** reads `env.WC_BOT_TOKEN`
   (already true by construction, since step 1 migrated the pre-agent
   references and no new reference form is introduced post-agent).
5. **Steps 2 and 3 both carry `continue-on-error: true`** in addition to
   their outcome guard: a transient failure re-minting the token or
   rewriting the remote must not flip the job to failure and skip every
   bare-conditioned step below it (each stage's own deterministic
   read-back/stall-detection logic among them) — the same reasoning already
   applied to "Fail loud on non-healthy agent verdict" and its siblings
   (found in this feature's own T046 review-step-gating pass).

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
