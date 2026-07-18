# Contract: Per-Specification Concurrency Group

This project has no library/API surface for this feature; its "interface"
is the GitHub Actions `concurrency:` group string every slug-bearing
operation for a specification must share. This document is the contract
the implementation (tasks phase, next stage) must satisfy, and the
correction that `specs/010-reusable-pipeline/contracts/stage-interfaces.md`
should fold in once implemented (see research.md D1) — that file is outside
this plan's edit scope and is not modified here.

## Canonical group string

```
wing-commander-<spec-dir>
```

Where `<spec-dir>` is `specs/NNN-slug` — the exact value already produced
by `implement.yml`/`finalize.yml`'s existing `inputs.spec-dir` and by
`rebase.yml`'s `discover` job's existing `matrix.spec_dir`. No new
derivation exists for these two; `plan.yml` and `tasks.yml` gain a new
`resolve-spec` prerequisite job that computes it from their raw
`head-ref`/`slug`/`mode` inputs (research.md D3, data-model.md).

`cancel-in-progress: false` on every member (unchanged from today on all
six job instances below) — a request for a held group queues rather than
cancelling the holder or being dropped (research.md D4).

## Members (MUST share the canonical group, one per specification)

| Workflow | Job | Group expression after this change |
|---|---|---|
| `rebase.yml` | `rebase` (matrix, one instance per selected branch) | `wing-commander-${{ matrix.spec_dir }}` |
| `plan.yml` | `plan` | `wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}` |
| `tasks.yml` | `tasks` (mode: generate) | `wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}` |
| `tasks.yml` | `tasks-approved` (mode: approved) | `wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}` |
| `implement.yml` | `implement` | `wing-commander-${{ inputs.spec-dir }}` (**unchanged**) |
| `implement.yml` | dispatch-next-iteration job | `wing-commander-${{ inputs.spec-dir }}` (**unchanged**) |
| `finalize.yml` | `finalize` | `wing-commander-${{ inputs.spec-dir }}` (**unchanged**) |

Any future published stage that checks out and publishes to a
specification's `spec/NNN-slug` working branch MUST declare its job-level
`concurrency.group` as `wing-commander-<spec-dir>` in this same form to
remain covered by this contract.

## Non-members (MUST NOT be folded into the canonical group)

| Workflow | Job | Group | Why excluded |
|---|---|---|---|
| `intake.yml` | `intake` | `wing-commander-intake` | No specification slug exists yet (FR-005) |
| `clarify.yml` | `clarify` | `wing-commander-${{ inputs.issue-number }}` | Keyed to the lifecycle issue, not a `spec/NNN-slug` branch (FR-005) |
| `cleanup.yml` | all three outcome jobs | `wing-commander-cleanup-${{ inputs.head-ref }}` | Runs only after a specification's terminal stage; not a contender for the rebase-vs-stage collision this spec fixes (research.md D5) |

## `resolve-spec` job contract (new, `plan.yml` and `tasks.yml` only)

```yaml
resolve-spec:
  runs-on: ubuntu-latest
  permissions: {}
  outputs:
    slug: ${{ steps.spec.outputs.slug }}
    spec-dir: ${{ steps.spec.outputs.spec-dir }}
  steps:
    - id: spec
      run: |
        # plan.yml: strip `spec-draft/`; tasks.yml: strip `plan/` (mode=generate)
        # or `tasks/` (mode=approved), selected by inputs.mode.
        # Validate ^[0-9]{3}-[a-z0-9][a-z0-9-]*$; ::error:: + exit 1 otherwise.
        # Emit slug=<slug> and spec-dir=specs/<slug>.
```

No checkout, no secrets, no GitHub API call — pure string derivation over
`inputs`, matching this job's only purpose (make the slug available before
the downstream job's `concurrency:` block is evaluated, research.md D3).
The downstream job (`plan`, `tasks`, `tasks-approved`) adds
`needs: resolve-spec` and deletes its own now-redundant
`Resolve spec identity` step, consuming `needs.resolve-spec.outputs.*`
wherever that step's outputs were previously used.

## Behavioral guarantees this contract must preserve

1. **FR-001/FR-003/FR-008**: for a single `spec-dir`, at most one of
   {rebase, plan, tasks, tasks-approved, implement, finalize} is ever
   running at a time, regardless of request order.
2. **FR-005**: a rebase or stage for a *different* `spec-dir` is on a
   different concurrency group and is never blocked by this contract.
3. **FR-006**: an uncontended request (no other holder of the same group)
   runs immediately — this contract adds no artificial delay, only a
   correctly-scoped lock that is a no-op when uncontended.
4. **FR-004**: a request that queues behind a holder is not lost — it runs
   once the holder releases the group, from a fresh checkout against
   then-current state (research.md D4 also covers the residual
   superseded-while-queued case and why it still satisfies FR-004).

## Non-goals (explicitly out of contract, per spec.md Assumptions and research.md D5)

- Joining `cleanup.yml`'s branch-deletion jobs to this group.
- Any new persisted "deferred rebase" marker, label, or `spec-meta.json`
  field — currency is achieved by GitHub Actions' native queuing plus the
  existing nightly/push rebase triggers, not by new bookkeeping.
- Changing what any stage or auto-rebase *does* once it runs — this
  contract governs only when a job is allowed to start.
