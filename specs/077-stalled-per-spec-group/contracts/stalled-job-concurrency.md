# Contract: `pr-conversation.yml`'s `stalled-mark` job joins the per-spec group

This document is the amendment `specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`
must receive (FR-004) — written here because this plan's edit scope is
`specs/077-stalled-per-spec-group` only; the implement stage applies it
verbatim against that file's then-current text.

**Superseded by Maintainer Feedback (T023)**: the shape below shipped first
(User Story 1, `stalled` itself joining the group) and was then split —
`stalled` first stayed in the per-PR group, and a new `stalled-mark`
job carries the group expression this document originally assigned to
`stalled`. Maintainer Feedback (T032) then removed `stalled`'s
`concurrency:` block entirely: the notice job `stalled` declares no
concurrency group, so no newer pending run in any group can replace it;
only `stalled-mark` (the spec-branch write) joins the per-spec group. The group expression, the arm added to the admission condition,
and the deleted-waiver mechanics are otherwise unchanged; only which job
they attach to moved. `stalled-job-concurrency.md`'s file name is kept
for history — it now documents `stalled-mark`.

## Members table row to add

Immediately after the existing `tasks.yml` `stalled`/`stalled-approved` row:

| Workflow | Job | Group expression after this change |
|---|---|---|
| `pr-conversation.yml` | `stalled-mark` | `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}` (joined 2026-09-26, #581 — falls back to the per-PR group `wing-commander-pr-conversation-pr-<n>` when `spec-dir` is empty; see `resolve-identity-job.md`) |

## `spec-branch-push-waivers.json`: one entry removed, then a differently-shaped one added back

The original entry:

```json
{
  "file": ".github/workflows/pr-conversation.yml",
  "job": "stalled",
  "pushes": "a spec-meta stalled mark on spec/<NNN-slug> through wing-commander-chain-stop-notice, when the stage's own classify-and-announce job did not start",
  "reason": "The spec directory is resolved inside this job (steps.identity), which a job-level concurrency group cannot read, and the job that would publish it is the one that did not start. Residual: the mark is unordered against a rebase on the same branch. Tracked on #437."
}
```

was deleted in the commit that landed User Story 1 (FR-003) — Gate 80
stale-checks every waiver, so leaving it in place after `stalled` joined the
group failed the gate on its own (spec.md Edge Cases: "a waiver outlives its
exemption"). T023's split then re-added an entry for `stalled`, for a
different, durable reason: post-split, `stalled` calls
`wing-commander-chain-stop-notice` with `mark-record: "false"`, so it calls
the push-capable composite but structurally never reaches the push —
Gate 80 has no per-input-value analysis, so this is waived exactly the way
`intake.yml`'s and `clarify.yml`'s own `stalled` jobs already are. The job
that actually pushes, `stalled-mark`, carries no waiver — it declares the
group in the Members table row above directly.

## `stalled` and `stalled-mark` jobs: `needs:`/`if:` (identical, kept in
## lockstep) and each job's own `concurrency:` after T023's split

```yaml
stalled:
  needs: [verify-image-prerequisites, resolve-identity, classify-and-announce]
  if: |
    needs.verify-image-prerequisites.result != 'failure' &&
    !cancelled() &&
    ( needs.verify-image-prerequisites.result == 'failure' ||
      needs.resolve-identity.result == 'failure' ||
      needs.classify-and-announce.result == 'failure' ||
      needs.classify-and-announce.result == 'skipped' ) &&
    needs.classify-and-announce.outputs.refusal-reason == ''
  concurrency:
    group: wing-commander-pr-conversation-pr-${{ inputs.pr-number }}
    cancel-in-progress: false
  # ...calls wing-commander-chain-stop-notice with mark-record: "false"

stalled-mark:
  needs: [verify-image-prerequisites, resolve-identity, classify-and-announce]
  if: |
    needs.verify-image-prerequisites.result != 'failure' &&
    !cancelled() &&
    ( needs.verify-image-prerequisites.result == 'failure' ||
      needs.resolve-identity.result == 'failure' ||
      needs.classify-and-announce.result == 'failure' ||
      needs.classify-and-announce.result == 'skipped' ) &&
    needs.classify-and-announce.outputs.refusal-reason == ''
  concurrency:
    group: wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}
    cancel-in-progress: false
  # ...calls wing-commander-chain-stop-notice with post-notice: "false"
```

The added `needs.resolve-identity.result == 'failure'` arm and both group
expressions are `if:`/`concurrency:` edits within the meaning of CLAUDE.md's
rule — each gets a `review-step-gating` skill pass before merge, checking:
- the widened arm cannot admit either job on a *healthy* run (it only adds a
  `failure` check, never a `success` or absent check);
- `stalled-mark`'s group expression cannot silently produce the bare
  `wing-commander-` constant for any reachable value of
  `needs.resolve-identity.outputs.spec-dir` (data-model.md's condition table
  enumerates the reachable combinations);
- `stalled` declares no concurrency group at all (T032), so no newer
  pending run in any group can replace it — the property T023 and T032
  exist to guarantee; only `stalled-mark` (the spec-branch write) joins the
  per-spec group.

## What does not change

- `classify-and-announce`'s own `concurrency.group` — still
  `wing-commander-pr-conversation-pr-${{ inputs.pr-number }}` (Assumptions:
  it never itself writes `spec/<slug>`).
- `act`'s concurrency handling — separately waived, out of this feature's
  scope (spec.md Scope: "`clarify.yml`'s `stalled` waiver stays ... this
  feature does not address" applies by the same logic to `act`, which
  spec.md's own waiver-file excerpt shows is waived for an unrelated,
  already-documented reason).
- The `wing-commander-chain-stop-notice` and `wing-commander-stall-reason`
  composites' existing inputs, outputs, and behavior for every caller other
  than `pr-conversation.yml` — T023 widens both additively (new optional
  inputs, default-`"true"`/default-`""` respectively); only the values
  `stalled`/`stalled-mark` pass into them, and which new optional inputs
  they set, are new (data-model.md).
