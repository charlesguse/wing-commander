# Phase 1 Data Model: The Stall Mark Waits Its Turn

This feature introduces no new persisted data store and no new
`workflow_call` surface. Every shape below is either an ephemeral job
output (for the duration of one `pr-conversation` run) or a concurrency
group string GitHub Actions evaluates once per job.

## Specification identity (existing entity, new source)

| Field | Type | Meaning | Source before this change | Source after this change |
|---|---|---|---|---|
| `qualifies` | `"true"`\|`"false"` | Whether this PR's base/head refs make it an implementation PR this stage acts on | `steps.identity.outputs.qualifies` (inside `classify-and-announce`) | `needs.resolve-identity.outputs.qualifies` |
| `slug` | string | `NNN-slug`, stripped from `head_ref` | `steps.identity.outputs.slug` | `needs.resolve-identity.outputs.slug` |
| `spec-dir` | string | `specs/<slug>`, or empty when non-qualifying/unresolved | `steps.identity.outputs.spec-dir` | `needs.resolve-identity.outputs.spec-dir` |
| `default-branch` | string | The repository's default branch, input or `gh repo view`-derived | `steps.identity.outputs.default-branch` | `needs.resolve-identity.outputs.default-branch` |

No field is added, renamed, or removed — only relocated one job earlier,
and read by two consumers (`classify-and-announce`, `stalled`) instead of
computed once and re-derived once.

## `resolve-identity` job (new)

| | |
|---|---|
| Runs before | `classify-and-announce`, `stalled` |
| `needs` | `verify-image-prerequisites` |
| `if` | `!cancelled() && needs.verify-image-prerequisites.result != 'failure'` |
| `permissions` | `pull-requests: read`, `contents: read` — no secrets |
| Checkout | none |

| Output | Meaning |
|---|---|
| `qualifies` | See table above |
| `slug` | See table above |
| `spec-dir` | See table above |
| `default-branch` | See table above |
| `reason` | Set only on the API-read-failure branch (`exit 1`); no consumer reads it today — mirrors `resolve-spec`'s own `refusal-reason` output for observability, matching the "reported as an error" half of FR-005 via the job's own `::error::` annotation |

Full step contract: [contracts/resolve-identity-job.md](./contracts/resolve-identity-job.md).

## `classify-and-announce` job (rewired, not restructured)

| | Before | After |
|---|---|---|
| `needs` | `verify-image-prerequisites` | `verify-image-prerequisites`, `resolve-identity` |
| `if` | `!cancelled() && needs.verify-image-prerequisites.result != 'failure'` | `!cancelled() && needs.verify-image-prerequisites.result != 'failure' && needs.resolve-identity.result != 'failure'` |
| Identity derivation | Own `steps.identity` step (API calls + qualification check) | None — reads `needs.resolve-identity.outputs.*` |
| Identity-resolution refusal callout | `if: always() && steps.identity.outputs.refused == 'true'` | Removed — `resolve-identity` failing now skips this job outright; the survivor job's stall notice (below) is the replacement notification path (Story 2, FR-006) |
| `concurrency.group` | `wing-commander-pr-conversation-pr-${{ inputs.pr-number }}` | Unchanged (Assumptions: this job never itself writes `spec/<slug>`) |
| Job output `qualifies`/`spec-dir`/`slug`/`default-branch` | `steps.identity.outputs.*` | `needs.resolve-identity.outputs.*` |
| Job output `refusal-reason` | `steps.identity.outputs.reason \|\| steps.preflight.outputs.reason \|\| steps.meta.outputs.reason` | `steps.preflight.outputs.reason \|\| steps.meta.outputs.reason` |

Every other step in this job (`Preflight`, `Configure AWS credentials`,
`Wing Commander context`, `Read lifecycle issue number`, `Check lifecycle
issue state`, `Authorized-actor gate`, `Check for relay confirmation`,
`Stage the request as a data file`, `Checkout implementation branch`,
`Compose tool args`, `Compute agent turn ceiling`, `Classify the PR
conversation request` and its prompt text) is unchanged in behaviour;
every `steps.identity.outputs.X` token inside their `if:`/`env:`/prompt
text becomes `needs.resolve-identity.outputs.X` (FR-009, FR-010 — same
values, same gating, new source).

## `stalled` job (rewired, not restructured)

| | Before | After |
|---|---|---|
| `needs` | `verify-image-prerequisites`, `classify-and-announce` | `verify-image-prerequisites`, `resolve-identity`, `classify-and-announce` |
| `if` | `needs.verify-image-prerequisites.result != 'failure' && !cancelled() && ( needs.verify-image-prerequisites.result == 'failure' \|\| needs.classify-and-announce.result == 'failure' \|\| needs.classify-and-announce.result == 'skipped' ) && needs.classify-and-announce.outputs.refusal-reason == ''` | Same, plus `needs.resolve-identity.result == 'failure'` as a fourth arm inside the parenthesized group (FR-005, explicit tolerance) |
| `concurrency.group` | `wing-commander-pr-conversation-pr-${{ inputs.pr-number }}` (the waived, unordered group) | `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}` (research.md D3) |
| Identity derivation | Own `steps.identity` step, `continue-on-error: true`, independent `gh pr view` | None — reads `needs.resolve-identity.outputs.spec-dir`/`slug` (FR-016) |
| Lifecycle-issue lookup | Own step, keyed off `steps.identity.outputs.spec-dir`/`slug`; unconditional | Same mechanism, keyed off `needs.resolve-identity.outputs.spec-dir`/`slug`; guarded by `if: needs.resolve-identity.outputs.spec-dir != ''` |
| `wing-commander-chain-stop-notice` call | `spec-dir: steps.identity.outputs.spec-dir`, `spec-branch: ${{ inputs.spec-prefix }}${{ steps.identity.outputs.slug }}`, `issue-number: steps.identity.outputs.issue-number \|\| inputs.pr-number` | `spec-dir: needs.resolve-identity.outputs.spec-dir`, `spec-branch: ${{ inputs.spec-prefix }}${{ needs.resolve-identity.outputs.slug }}`, `issue-number: steps.<issue-lookup>.outputs.issue \|\| inputs.pr-number` |
| `wing-commander-stall-reason` call | Unchanged inputs (`needs.classify-and-announce.*`) | Unchanged — the existing `entry-result == 'skipped'` branch ("the pr-conversation stage was skipped because a dependency it needs did not run") already covers the resolve-identity-failed case truthfully; no composite edit needed (single-home rule: this string already exists) |

### Survivor-job condition table, in the shape spec 041's data-model.md already established

| Stage | `needs:` | `if:` (abnormal-termination arm) |
|---|---|---|
| pr-conversation (before this feature) | `[verify-image-prerequisites, classify-and-announce]` | `!cancelled() && ( needs.verify-image-prerequisites.result == 'failure' \|\| needs.classify-and-announce.result == 'failure' \|\| needs.classify-and-announce.result == 'skipped' ) && needs.classify-and-announce.outputs.refusal-reason == ''` |
| pr-conversation (after this feature) | `[verify-image-prerequisites, resolve-identity, classify-and-announce]` | `!cancelled() && ( needs.verify-image-prerequisites.result == 'failure' \|\| needs.resolve-identity.result == 'failure' \|\| needs.classify-and-announce.result == 'failure' \|\| needs.classify-and-announce.result == 'skipped' ) && needs.classify-and-announce.outputs.refusal-reason == ''` |

Verified case by case (SC-003), against every combination the three jobs can
reach:

| `resolve-identity` | `classify-and-announce` | Admits `stalled` today? | Admits `stalled` after this change? |
|---|---|---|---|
| success | success (healthy run) | No | No (unchanged) |
| success | failure | Yes | Yes (unchanged — third arm) |
| success | skipped (image check failed upstream) | Yes | Yes (unchanged — image arm and third arm both true) |
| success, `qualifies=false` | success (silent stop, User Story 3) | No | No (unchanged) |
| **failure** (API read error) | **skipped** (this job's own `if:` now tolerates the failure explicitly) | N/A (job did not exist) | **Yes** — via the new explicit arm, and independently via the third arm's `skipped` case |
| skipped (image check failed) | skipped | Yes (image arm) | Yes (unchanged — image arm) |

The "failure" row is Story 2's scenario. Two independent arms admit it
(`resolve-identity`'s own explicit arm, and `classify-and-announce`'s
resulting `skipped` status), which is intentional redundancy per D3's
rationale, not dead code — either arm alone is sufficient, and keeping both
means an independent future edit to either job's `if:` cannot silently drop
this guarantee.

## Concurrency group values (existing entity, one new member)

| Group string | Who holds it | When |
|---|---|---|
| `wing-commander-specs/NNN-slug` | rebase, plan, tasks/tasks-approved, implement, finalize, tasks' `stalled`/`stalled-approved`, cleanup's three jobs, **pr-conversation's `stalled` (new, qualifying case)** | One specification's writers, serialized |
| `wing-commander-pr-conversation-pr-<n>` | `classify-and-announce` (unchanged), **pr-conversation's `stalled` (new, empty-`spec-dir` fallback)** | One PR's conversation-stage work, serialized |

## Push waiver (existing entity, one entry removed)

`.github/scripts/spec-branch-push-waivers.json`'s
`{"file": ".github/workflows/pr-conversation.yml", "job": "stalled", ...}`
entry is deleted in the same change that lands the group above (FR-003) —
Gate 80 fails a waiver naming a job that is no longer unwaived-and-outside
the group, so the two edits are one atomic change, never sequenced.

## Gate registry entry

| Gate | Change | Proves |
|---|---|---|
| 80 (`verify-spec-branch-push-concurrency.py`, amended) | `PER_SPEC_GROUP_RE`-style acceptance gains one additional, exactly-matched alternative pattern for the per-PR fallback spelling (research.md D5); existing three spellings and the waiver mechanism are untouched | FR-018 (the fallback spelling is recognized, exactly); SC-001 (waiver count drops by exactly one, zero added); SC-008 (a degenerate `wing-commander-` group and a near-miss of either spelling are still rejected — proven by new self-test fixtures, not by the repository merely passing) |

Full contract: [contracts/gate-80-fallback-spelling.md](./contracts/gate-80-fallback-spelling.md).
