# Contract: `pr-conversation.yml`'s `stalled` job joins the per-spec group

This document is the amendment `specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`
must receive (FR-004) — written here because this plan's edit scope is
`specs/077-stalled-per-spec-group` only; the implement stage applies it
verbatim against that file's then-current text.

## Members table row to add

Immediately after the existing `tasks.yml` `stalled`/`stalled-approved` row:

| Workflow | Job | Group expression after this change |
|---|---|---|
| `pr-conversation.yml` | `stalled` | `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}` (joined 2026-09-26, #581 — falls back to the per-PR group `wing-commander-pr-conversation-pr-<n>` when `spec-dir` is empty; see `resolve-identity-job.md`) |

## `spec-branch-push-waivers.json` entry to remove

The existing entry:

```json
{
  "file": ".github/workflows/pr-conversation.yml",
  "job": "stalled",
  "pushes": "a spec-meta stalled mark on spec/<NNN-slug> through wing-commander-chain-stop-notice, when the stage's own classify-and-announce job did not start",
  "reason": "The spec directory is resolved inside this job (steps.identity), which a job-level concurrency group cannot read, and the job that would publish it is the one that did not start. Residual: the mark is unordered against a rebase on the same branch. Tracked on #437."
}
```

is deleted in the same commit that lands the group above (FR-003) — Gate 80
stale-checks every waiver, so leaving it in place after the job joins the
group fails the gate on its own (spec.md Edge Cases: "a waiver outlives its
exemption").

## `stalled` job: `needs`, `if:`, and `concurrency:` after this change

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
    group: wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}
    cancel-in-progress: false
```

The added `needs.resolve-identity.result == 'failure'` arm and the group
expression are both `if:`/`concurrency:` edits within the meaning of
CLAUDE.md's rule — this change gets a `review-step-gating` skill pass before
merge (Assumptions), specifically checking:
- the widened arm cannot admit `stalled` on a *healthy* run (it only adds a
  `failure` check, never a `success` or absent check);
- the group expression cannot silently produce the bare `wing-commander-`
  constant for any reachable value of `needs.resolve-identity.outputs.spec-dir`
  (data-model.md's condition table enumerates the reachable combinations).

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
  composites — no input, output, or internal step changes; only the values
  `stalled` passes into them change source (data-model.md).
