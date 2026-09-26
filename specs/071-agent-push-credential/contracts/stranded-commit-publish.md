# Contract: `wing-commander-publish-stranded-commits`

**File**: `.github/actions/wing-commander-publish-stranded-commits/
action.yml` (composite, new).

## Why this exists, precisely

Research.md D8 traced how the two evidence runs this spec cites actually
recovered stranded commits: not through any deterministic push, but
because a *later agent step's own* `git push` happened to carry every
locally-ahead commit with it once the credential was fresh again. That
path has no rescue when no later agent step runs — a cycle that converges
on its first pass needs no retry, and a killed or runaway-ceiling-cut
agent step may be the last step of its job ever to run. This composite
replaces the incidental rescue with a deterministic one.

## Inputs

| Input | Required | Meaning |
|---|---|---|
| `before-sha` | yes | The spec branch's HEAD SHA before this agent step ran — the same value the existing convergence-signal step already resolves (`implement.yml`'s `before_sha`, reused rather than re-derived) |

## Outputs

| Output | Meaning |
|---|---|
| `commits-published` | Count of commits `git push` actually moved to `origin` this invocation — `0` when the agent had already pushed everything itself (the common case, and the only case FR-004 requires stay silent) |
| `push-ok` | `"true"`/`"false"` — whether the push attempt itself succeeded. `"false"` covers a genuine race (a concurrent force-push, e.g. from `auto-rebase`), not a credential failure — the credential helper installed by `wing-commander-agent-push-credential` (still active at this point in the job) resolves this step's own credential fresh too |

## Behaviour

1. `git fetch origin <branch> --quiet` is NOT performed first — this step
   pushes the *local* working tree's current branch tip as-is; it does not
   attempt to reconcile with a remote that moved for an unrelated reason
   (that is `push-ok=false`'s job to surface, not this step's job to
   resolve).
2. `git rev-list --count <before-sha>..HEAD` — the count of commits this
   job's own agent step(s) created locally, published or not.
3. `git push origin HEAD:<branch>`. `push-ok=true` and
   `commits-published=<the count from step 2>` on success; `push-ok=false`
   and `commits-published=<the same count>` on failure (the count is
   informational either way — it answers "how much was at stake," not "how
   much succeeded").

## Gating (every call site)

Identical to the existing post-agent `wing-commander-context` re-mint this
step runs alongside: `if: "!cancelled() && steps.<agent-id>.outcome !=
'skipped'"`, `continue-on-error: true`. This is spec 052's own FR-019
exclusion (a run cancelled at the run level performs no network mint and
no remote rewrite in the cancellation window) — this feature does not
widen or narrow it (spec.md FR-019, Edge Cases).

## Consumption

Each stage's existing stall-path callout (spec 041's
`wing-commander-chain-stop-notice` family) reads `commits-published`; when
nonzero, one additional rendered line names the count (FR-016). When zero,
nothing is added to the notice (FR-017) — matching the "record appears
only when there is something to report" convention
`wing-commander-post-agent-credential-status`'s own `ok=false` warning
already established.

## What Gate 99 checks here

That every job containing a push-capable agent step has exactly one call
to this composite positioned immediately alongside (same `if:` shape as)
that agent step's existing post-agent `wing-commander-context` re-mint. See
`agent-push-credential-gate.md`.
