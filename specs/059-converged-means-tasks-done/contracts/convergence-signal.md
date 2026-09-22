# Contract: The Convergence Signal

This is the stage-internal contract this feature ships. It does not change
`implement.yml`'s published `workflow_call` contract
(`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) — see
"What stays the same" below. It documents the contract between:

1. the two read-back steps and the new composite action,
2. the two read-back steps and `Consolidate final outcome`,
3. `Consolidate final outcome` and `Dispatch next step`, and
4. `Dispatch next step` and the lifecycle-issue comment.

## 1. Composite action: `wing-commander-tasks-checkbox-count`

**Path**: `.github/actions/wing-commander-tasks-checkbox-count/action.yml`
(published surface, resolved by `implement.yml` through self-checkout, per
Constitution VII — a minor-version addition; see plan.md Complexity
Tracking).

**Inputs**:

| Name | Required | Description |
|---|---|---|
| `ref` | yes | A git ref or SHA resolvable in the checkout (e.g. `$BASE_SHA`, `origin/spec/059-...`). |
| `path` | yes | Path to `tasks.md` within that ref (e.g. `specs/059-.../tasks.md`). |

**Outputs**:

| Name | Shape | Description |
|---|---|---|
| `checked-count` | digits | Count of `- [x]`/`- [X]` task-list lines outside fenced code blocks (FR-004). |
| `unchecked-count` | digits | Count of `- [ ]` task-list lines outside fenced code blocks (FR-001, FR-004). |
| `unchecked-items` | newline-delimited text | The literal text of each counted unchecked line, in file order, for the remaining-work report (FR-012). |

**Failure behavior**: unlike `wing-commander-spec-meta` (which never fails —
a missing record is a valid state), this composite's step **fails the job**
(non-zero exit) when `ref:path` cannot be read as a file — no
`readable=false` output is offered for a caller to swallow (FR-006,
Principle VIII). A caller that needs "not yet on this ref" as a valid state
(there is none in this feature — `tasks.md` is expected to already exist on
every spec branch by the time `implement.yml` runs) must not call this
composite for such a case.

**Call sites** (four, two arms × {base, tip}):

- Primary arm, base: `ref: ${{ steps.base.outputs.base-sha }}`
- Primary arm, tip: `ref: origin/${{ env.SPEC_PREFIX }}${{ env.SLUG }}` (post-fetch)
- Retry arm, base: the retry's own recorded base (not the primary's `steps.base`, per FR-007/FR-010a "own base")
- Retry arm, tip: same tip-resolution shape as the primary arm, against the retry's post-agent push

Each call site's `path` input is `${{ steps.spec.outputs.spec-dir }}/tasks.md`.

## 2. Read-back step outputs (primary and retry, identical shape)

Step: `Read back cycle outcome` (id `outcome`) / `Read back retry outcome`
(id `retry-outcome`).

| Output | Shape | Change from today |
|---|---|---|
| `ok` | `true`/`false`/empty | unchanged |
| `truncated` | `true`/`false`/empty | unchanged |
| `reason` | text | unchanged shape; gains new narrative cases (data-model.md, "Non-convergence reason") |
| `converged` | `true`/`false`/empty | **rule replaced** — decision table in data-model.md, not "no converge commit" |
| `remaining` | text | **source replaced** — tip's outstanding-item text (D6), not a converge-commit diff |
| `progressed` | `true`/`false`/empty | **new** — FR-010a's progress test result |
| `handoff` | `true`/`false`/empty | **new** — FR-010's hand-off condition, computed here so `Dispatch next step` does not need to re-derive it from the other four |

`progressed` and `handoff` are step-local outputs consumed inside this job
only; they are not `workflow_call` outputs of `implement.yml` (FR-017).

**Preconditions unchanged**: computed under the same `if:` guard as today
(`is-open == 'true' && skip != 'true'`); `converged`/`remaining`/`progressed`/
`handoff` are only set when `ok=true` (mirroring today's `elif [ "$ok" =
"true" ]` branch) and only meaningfully evaluated when `truncated=false`
(when `truncated=true`, `converged=false` is forced and `progressed`/
`handoff` are not consulted — FR-005).

## 3. `Consolidate final outcome`

Carries `progressed` and `handoff` through the existing `RETRY_RAN`
selection alongside `ok`/`truncated`/`converged`/`remaining`/`tier`/`reason`
— same selection rule (`RETRY_RAN=true` → retry's values; else → primary's),
no new selection logic.

## 4. `Dispatch next step`

**New branch condition**, evaluated alongside the existing ones:

```
if CONVERGED == true:
    dispatch NEXT_WORKFLOW, converged=true         # unchanged
elif TRUNCATED == true and ITERATION < MAX:
    dispatch SELF_WORKFLOW, iteration+1             # unchanged
elif TRUNCATED == true:                              # at cap
    dispatch NEXT_WORKFLOW, converged=false          # unchanged
elif HANDOFF == true:                                 # NEW
    post $REMAINING to the lifecycle issue
    dispatch NEXT_WORKFLOW, converged=false
    # identical shape to the cap-reached branch below, taken regardless
    # of ITERATION vs MAX — this is the reused terminal path (FR-010, D4)
elif ITERATION < MAX:
    dispatch SELF_WORKFLOW, iteration+1, post $REMAINING if no self-workflow
else:                                                  # at cap, not converged, not handoff
    post $REMAINING to the lifecycle issue
    dispatch NEXT_WORKFLOW, converged=false            # unchanged
```

The `HANDOFF` branch and the final `else` branch post the same shape of
comment and dispatch the same workflow with the same payload
(`converged=false`) — the only observable difference is the reason text
(FR-013: "the cycle checked nothing new, so the loop is ending here" vs. the
existing cap-reached narrative), so a reader can tell the two apart without
either being a structurally different dispatch.

## 5. Lifecycle-issue comment (FR-012, FR-013, FR-014)

When `CONVERGED=false`:

- **Reason** line(s), naming which of: converge appended new work / tasks
  outstanding with progress / tasks outstanding with no progress (the
  hand-off) / truncated / cap-reached fired, never omitted, never
  double-counting when two reasons hold at once (data-model.md).
- **Remaining work**, the `remaining` text (tip's outstanding items) —
  never an empty fenced block (FR-012, SC-006).
- **Step summary** (`$GITHUB_STEP_SUMMARY`, FR-014) additionally records the
  numeric `unchecked-count` used and the `progressed` boolean, so a run's own
  log shows the inputs to its own decision without re-deriving them from the
  branch.

## What stays the same (explicitly out of this contract's scope)

- `implement.yml`'s `workflow_call` inputs/outputs
  (`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) — FR-017.
- `finalize.yml`'s own "Remaining manual work" agent-authored summary
  (`finalize.yml:715-721`) — a distinct, parallel mechanism for the final
  PR body, not touched by this feature (Out of Scope, and see research.md
  item 5 in the investigation this plan is built on: it is agent-driven by
  design, while this contract stays deterministic per FR-003).
- `max-iterations`, its default, and the cap-reached terminal path's own
  shape — FR-009; this contract only adds a new way to *reach* that same
  terminal path early.
