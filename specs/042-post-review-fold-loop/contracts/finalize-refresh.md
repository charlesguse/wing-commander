# Contract: `finalize.yml` — re-entrant finalize (refresh, not skip)

Delta against the published stage contract
(`specs/010-reusable-pipeline/contracts/stage-interfaces.md`). No declared
`workflow_call` input, output, or secret is removed, renamed, or added —
this feature changes `finalize.yml`'s internal behavior only (FR-016).

## Guard output change

"Check for an existing final pull request" (`finalize.yml:542–557`,
`id: guard`) replaces its `skip` boolean output with `pr-state`:

| `pr-state` | Meaning | Replaces today's |
|---|---|---|
| `none` | No PR from this spec branch to the default branch exists | `skip=false` |
| `open` | An open PR exists | (new — was indistinguishable from `merged`/`closed` under `skip=true`) |
| `merged` | The existing PR is merged | (new) |
| `closed` | The existing PR is closed, not merged | (new) |

`gh pr list --head "${SPEC_PREFIX}$SLUG" --base "$DB" --state all --json number,state,url --jq '.[0] // empty'`
replaces today's `number`-only query.

## Downstream gating change

Every step currently gated `steps.diff.outputs.skip != 'true'` is regated
`steps.diff.outputs.pr-state == 'none' || steps.diff.outputs.pr-state == 'open'`:
"Assemble PR body," "Open the final PR" (renamed "Open or update the final
PR"), "Flip stage label," "Commit metadata (stage → review)," "Announce
for review," "Check remaining manual work." Each behaves identically to
today when `pr-state == 'none'`; each additionally runs, refreshing rather
than creating, when `pr-state == 'open'`.

## New step: report merged/closed

A new step, gated `pr-state == 'merged' || pr-state == 'closed'`, posts a
lifecycle-issue comment naming which state was found and that nothing was
changed (FR-009, FR-009a) — today's guard only writes a
`GITHUB_STEP_SUMMARY` line, which a maintainer watching the lifecycle issue
never sees.

## "Open or update the final PR" behavior

| `pr-state` | Action |
|---|---|
| `none` | `gh pr create ...` — unchanged from today |
| `open` | `gh pr edit "$EXISTING_PR" --body-file <assembled body>` |

The PR number used for `open` is the one the guard step already read
(`gh pr list ... --jq '.[0].number'`).

## PR body assembly (refresh path only)

See `data-model.md` §6 for the exact delimited-region shape. Summary of
the guarantee: content outside `<!-- wing-commander-finalize:state:begin -->`
… `<!-- wing-commander-finalize:fold-log:end -->` is preserved byte-for-byte
(FR-008b); the state block is fully regenerated; the fold log is
append-only, one entry per fold, keyed for idempotency by the branch tip
SHA it describes (FR-008a, FR-010a).

## Re-review request

New step, gated `pr-state == 'open'`, after the metadata/label steps:
reads `spec-meta.json`'s `pending_re_review_from` (falling back to
`gh pr view "$EXISTING_PR" --json reviews --jq '...CHANGES_REQUESTED...'`
when absent — research.md D10), issues
`gh pr edit "$EXISTING_PR" --add-reviewer <logins>` best-effort
(`continue-on-error: true` at the step level, or an inline `|| true` with
an explicit captured-failure report — FR-010b: the remaining refresh
effects MUST still occur and the failure MUST be stated, not swallowed),
then clears `pending_re_review_from` in the same metadata commit "Commit
metadata (stage → review)" already makes.

## Lifecycle-issue comment (FR-010d)

The existing "Announce for review" step's wording is extended, on the
refresh path only, to state the review feedback was acted on and name the
review(s) it answers (the same logins used for the re-review request).

## Behavioral guarantees (per FR)

- **FR-008/FR-008a/FR-008b**: see above.
- **FR-009/FR-009a**: `merged`/`closed` states produce the new report step
  and change nothing else — no PR edit, no metadata commit, no label
  change, no re-review request (all gated out by the widened `if:`).
- **FR-010**: the guard's original purpose (no second PR) is preserved —
  `open`/`merged`/`closed` never reach "Open or update the final PR"'s
  `gh pr create` branch; only `none` does.
- **FR-010a**: idempotent by construction — D9a's SHA-keyed fold-log check
  and the fact that label/metadata writes (`gh label create --force`,
  `gh issue edit --add-label`, `jq`-patch-if-different) are already
  naturally idempotent (research.md D8).
- **FR-010b**: re-review request failure is reported, not swallowed, and
  does not fail the job.
- **FR-010c**: "Commit metadata (stage → review)" runs on refresh exactly
  as it does on create — the record never reads `implement` after a
  converged fold.
- **FR-010e**: no step this feature adds or widens calls `gh pr merge` or
  `gh pr review --approve`; unchanged from today.

## What this contract does NOT change

- The empty-diff anomaly handling ("Check remaining manual work" and its
  siblings) — reused unmodified, just re-gated the same way as the other
  create-path steps.
- The duplicate-dispatch guard and the closed-lifecycle guard upstream of
  this job.
- Anything on the `pr-state == 'none'` (create) path beyond the `if:`
  condition text itself — every step's body is byte-for-byte unchanged
  for that case (FR-017).
