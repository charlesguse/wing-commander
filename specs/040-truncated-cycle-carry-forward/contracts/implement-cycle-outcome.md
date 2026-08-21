# Contract Delta: `implement.yml`'s cycle-outcome/dispatch steps (existing stage, internal steps rewritten)

`implement.yml` is a published stage (constitution VII) — this document
records what this feature changes about its *internal* behavior. Its
`workflow_call` inputs and outputs, and every calling wrapper
(`wing-commander-5-implement.yml`), are explicitly unchanged (FR-021).
Everything not listed under "Changes" is unchanged.

## Stage `workflow_call` inputs/outputs — UNCHANGED

No new input, no new output, no new secret. `model`, `escalation-model`,
`max-turns`, `max-iterations`, `spec-prefix`, `self-workflow`,
`next-workflow`, `issue-number`, and every other declared surface is
byte-for-byte what it is today.

## Steps changed

### `outcome` ("Read back cycle outcome", `implement.yml:878-926`)

**New env input**: `VERDICT: ${{ steps.cycle-verdict.outputs.verdict }}`
(already computed upstream by the existing "Compute agent run verdict
(cycle)" step — no new agent turn, no new API call).

**New output**: `truncated` (`"true"`/`"false"`).

**Behavior change**: previously, `ok=true` required only
`CYCLE_RESULT=="success"` and the lifecycle record advancing.
Now, `ok=true` is also reached when `VERDICT=="exhausted"`, the
lifecycle record advanced, and the progress test (data-model.md)
passes — in which case `truncated=true` and the existing convergence
scan is skipped entirely in favor of `converged=false` (research.md D4).
When `VERDICT=="exhausted"` but the lifecycle record did not advance, or
the progress test fails, the step's behavior is byte-for-byte today's
failed path (`ok=false`, `truncated=false`) — FR-002's "if any one fails,
take today's path."

A `CYCLE_RESULT=="success"` cycle whose verdict is anything other than
`exhausted` (i.e. `healthy`) is completely unaffected — same branch, same
output values, as today (FR-017).

### `retry-outcome` ("Read back retry outcome", `implement.yml:1146-1196`)

Same shape as `outcome` above, reading `steps.retry-verdict.outputs.verdict`
and gaining the same `truncated` output — but its progress test is measured
against a **new** base SHA captured immediately before the retry step runs
(see "Record retry base SHA" below), not the primary cycle's `base-sha`
(research.md D7, FR-016).

### `final` ("Consolidate final outcome", `implement.yml:1201-1230`)

**New output**: `truncated`, selected from `retry-outcome`'s or
`outcome`'s value using the exact same "retry ran → use retry's values"
rule already governing `ok`/`converged`/`remaining`/`tier` — no new
selection logic, one more field added to the existing pattern.

### New step: "Record retry base SHA"

Inserted immediately before "Implement and converge (retry at escalation
model)" (`implement.yml:957`), same gate condition as that step. Records
`origin/<spec-prefix><slug>`'s current tip as `base-sha`, the same shape
as the existing "Record base SHA" step (`implement.yml:613-616`) but
scoped to the retry's own starting point.

### New step: "Record truncated-cycle count"

Inserted after "Consolidate final outcome", before "Flip stage label
(first cycle)" (`implement.yml:1401`). Deterministic jq-patch-commit-push
against `spec-meta.json`'s new `truncated_count` field (data-model.md),
gated on `steps.lifecycle-gate.outputs.is-open == 'true' &&
steps.guard.outputs.skip != 'true'` (runs on every non-skipped
consolidated outcome, including a failed one that goes on to `stalled` —
research.md D5). Commits only when the value changes. Output: `count`.

### "Retry ceiling"/"Implement and converge (retry at escalation model)" gate conditions (`implement.yml:947-964`)

**UNCHANGED text.** `steps.outcome.outputs.ok == 'false'` already excludes
a truncated cycle (`ok=='true'`) without editing the condition — this is
the point of research.md D2's design (collapse truncated onto `ok=true`
rather than inventing a value every gate must learn about).

### `stalled` job's gate (`implement.yml:1494`, `needs.implement.outputs.final-ok == 'false'`)

**UNCHANGED text.** A truncated cycle produces `final-ok=='true'`, so this
job never fires for it, at any tier (FR-009) — again no edit needed to the
condition itself.

### "Dispatch next step" (`implement.yml:1422-1485`)

**New env inputs**: `TRUNCATED: ${{ steps.final.outputs.truncated }}`,
`TRUNCATED_COUNT: ${{ steps.record-truncation.outputs.count }}`.

**New branches**, inserted ahead of the existing `CONVERGED != true`
branches: a truncated-below-cap message and a truncated-at-cap message
(data-model.md "Lifecycle issue report" table; research.md D6). The
`CONVERGED=='true'` branch (converged hand-off) and the non-truncated
`CONVERGED=='false'` branches are unchanged text, reached exactly as
today when `TRUNCATED=='false'`.

## Non-goals

- Does not change the iteration cap, the turn-budget ceiling, or any
  `max-*` input (FR-022).
- Does not change the escalation-tier resolution in
  `wing-commander-5-implement.yml` (the `model:opus` label logic) — a
  truncated cycle's next dispatch re-resolves the tier the same way every
  dispatch already does, landing on the same tier by construction (no
  `model` override is threaded through the self-dispatch call,
  `implement.yml:1447-1448`, today or after this feature).
- Does not resume a truncated agent's context — the next cycle is a fresh
  agent run reading the branch the truncated cycle left behind (spec Out
  of Scope).
- Does not add or remove any `workflow_call` input, output, or secret of
  `implement.yml` (FR-021) — no caller needs an edit.

## Caller contract — UNCHANGED

`wing-commander-5-implement.yml` and any other adopter pinned to a release
tag see only the changed *behavior* on a turn-exhausted cycle; the
`workflow_call`/`workflow_dispatch` interface it invokes is identical.
