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

## `stalled` job (rewired, then split by T023)

| | Before | After |
|---|---|---|
| `needs` | `verify-image-prerequisites`, `classify-and-announce` | `verify-image-prerequisites`, `resolve-identity`, `classify-and-announce` |
| `if` | `needs.verify-image-prerequisites.result != 'failure' && !cancelled() && ( needs.verify-image-prerequisites.result == 'failure' \|\| needs.classify-and-announce.result == 'failure' \|\| needs.classify-and-announce.result == 'skipped' ) && needs.classify-and-announce.outputs.refusal-reason == ''` | Same, plus `needs.resolve-identity.result == 'failure'` as a fourth arm inside the parenthesized group (FR-005, explicit tolerance) — identical on `stalled` and the new `stalled-mark` job below |
| `concurrency.group` | `wing-commander-pr-conversation-pr-${{ inputs.pr-number }}` (the waived, unordered group) | **T023 split, then T032**: T023 first moved `stalled` onto the static per-PR group unconditionally, but that group is also `classify-and-announce`'s own, so a newer run's `classify-and-announce` could still evict an older run's still-pending `stalled` notice; T032 (Maintainer Feedback) drops `stalled`'s `concurrency:` block entirely, so nothing can evict its pending run. The per-spec fallback expression (research.md D3) moved to the new `stalled-mark` job below at T023 and is unaffected by T032 |
| Identity derivation | Own `steps.identity` step, `continue-on-error: true`, independent `gh pr view` | None — reads `needs.resolve-identity.outputs.spec-dir`/`slug` (FR-016) |
| Lifecycle-issue lookup | Own step, keyed off `steps.identity.outputs.spec-dir`/`slug`; unconditional | Same mechanism, keyed off `needs.resolve-identity.outputs.spec-dir`/`slug`; guarded by `if: needs.resolve-identity.outputs.spec-dir != ''`; duplicated independently in `stalled-mark` (each job runs its own steps; neither can read the other's) |
| `wing-commander-chain-stop-notice` call | `spec-dir: steps.identity.outputs.spec-dir`, `spec-branch: ${{ inputs.spec-prefix }}${{ steps.identity.outputs.slug }}`, `issue-number: steps.identity.outputs.issue-number \|\| inputs.pr-number` | `spec-dir: needs.resolve-identity.outputs.spec-dir`, `spec-branch: ${{ inputs.spec-prefix }}${{ needs.resolve-identity.outputs.slug }}`, `issue-number: steps.<issue-lookup>.outputs.issue \|\| inputs.pr-number`, plus `mark-record: "false"` (T023) — this job posts the notice only; it never runs the composite's checkout/push effect |
| `wing-commander-stall-reason` call | Unchanged inputs (`needs.classify-and-announce.*`) | Adds `resolve-identity-result: needs.resolve-identity.result` — a new optional composite input (default `""`, every other caller unaffected). The existing `entry-result == 'skipped'` branch reported a `resolve-identity` failure as "the pr-conversation stage was skipped because a dependency it needs did not run," which is true but does not name which dependency failed or where to look; a new branch, ranked ahead of that one, reports "the resolve-identity job failed, so the pr-conversation stage never started -- see its job log" when this new input is `"failure"` |

## `stalled-mark` job (new, T023)

Same `needs`/`if` as `stalled` above (kept identical by the workflow's own
comments, not by a shared YAML anchor — GitHub Actions has none for this
shape). Joins the canonical per-spec group via the same fallback expression
`stalled` carried before T023 (research.md D3):
`wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}`.
Runs its own copy of the bootstrap checkout, the lifecycle-issue lookup, and
the `wing-commander-stall-reason` call (all read-only, no push), then calls
`wing-commander-chain-stop-notice` with `mark-record: "true"`,
`post-notice: "false"` — the checkout-and-push effect only, no notice
comment and no `stage:stalled` label add (that stays `stalled`'s job; this
job still removes the stale `stage:<name>` label once its own mark
succeeds).

### Survivor-job condition table, in the shape spec 041's data-model.md already established

The table below applies identically to both `stalled` and `stalled-mark` —
T023 kept their `needs`/`if` in lockstep so the same criteria admit both.

| Stage | `needs:` | `if:` (abnormal-termination arm) |
|---|---|---|
| pr-conversation (before this feature) | `[verify-image-prerequisites, classify-and-announce]` | `needs.verify-image-prerequisites.result != 'failure' && !cancelled() && ( needs.verify-image-prerequisites.result == 'failure' \|\| needs.classify-and-announce.result == 'failure' \|\| needs.classify-and-announce.result == 'skipped' ) && needs.classify-and-announce.outputs.refusal-reason == ''` |
| pr-conversation (after this feature) | `[verify-image-prerequisites, resolve-identity, classify-and-announce]` | `needs.verify-image-prerequisites.result != 'failure' && !cancelled() && ( needs.verify-image-prerequisites.result == 'failure' \|\| needs.resolve-identity.result == 'failure' \|\| needs.classify-and-announce.result == 'failure' \|\| needs.classify-and-announce.result == 'skipped' ) && needs.classify-and-announce.outputs.refusal-reason == ''` |

Verified case by case (SC-003), against every combination the three jobs can
reach. The outer `needs.verify-image-prerequisites.result != 'failure'` guard
(present both before and after this feature) means the first arm inside the
parenthesized group can never itself admit the job — a failed image check
is excluded by the outer guard before the inner `||` chain is even reached:

| `resolve-identity` | `classify-and-announce` | Admits `stalled` today? | Admits `stalled` after this change? |
|---|---|---|---|
| success | success (healthy run) | No | No (unchanged) |
| success | failure | Yes | Yes (unchanged — third arm) |
| success, `qualifies=false` | success (silent stop, User Story 3) | No | No (unchanged) |
| **failure** (API read error) | **skipped** (this job's own `if:` now tolerates the failure explicitly) | N/A (job did not exist) | **Yes** — via the new explicit arm, and independently via the third arm's `skipped` case |
| skipped (image check failed) | skipped | No (outer guard) | No (outer guard) |

The "failure" row is Story 2's scenario. Two independent arms admit it
(`resolve-identity`'s own explicit arm, and `classify-and-announce`'s
resulting `skipped` status), which is intentional redundancy per D3's
rationale, not dead code — either arm alone is sufficient, and keeping both
means an independent future edit to either job's `if:` cannot silently drop
this guarantee.

## Concurrency group values (existing entity, one new member)

Post-T023 (Maintainer Feedback: the notice must not be evictable by a busy
per-spec group's single pending-run slot), the survivor job is split in two
— `stalled` (notice-only, `mark-record: "false"`) and `stalled-mark`
(mark-only, `post-notice: "false"`) — so only the job that actually pushes
joins the per-spec group; the job that must land immediately never does.
T023's split still left `stalled` in the per-PR group it shares with
`classify-and-announce`, where a newer run's `classify-and-announce` could
evict an older run's still-pending notice (Maintainer Feedback, T032); T032
drops `stalled`'s `concurrency:` block entirely so nothing can evict it.

| Group string | Who holds it | When |
|---|---|---|
| `wing-commander-specs/NNN-slug` | rebase, plan, tasks/tasks-approved, implement, finalize, tasks' `stalled`/`stalled-approved`, cleanup's three jobs, **pr-conversation's `stalled-mark` (new, qualifying case)** | One specification's writers, serialized |
| `wing-commander-pr-conversation-pr-<n>` | `classify-and-announce` (unchanged), **pr-conversation's `stalled-mark` (new, empty-`spec-dir` fallback)** | One PR's conversation-stage work, serialized |
| *(no group)* | **pr-conversation's `stalled` (T032, Maintainer Feedback)** — carries no `concurrency:` block at all, so its pending run can never be evicted, including by a newer run's `classify-and-announce` in the per-PR group above, which `stalled` shared before T032 | Not serialized against anything; posts immediately every time it is admitted |

## Push waiver (existing entity, net unchanged: one removed, one added back for a different job shape)

T005 (User Story 1) deleted
`.github/scripts/spec-branch-push-waivers.json`'s
`{"file": ".github/workflows/pr-conversation.yml", "job": "stalled", ...}`
entry in the same change that landed `stalled` in the per-spec group
(FR-003) — Gate 80 fails a waiver naming a job that is no longer
unwaived-and-outside the group, so the two edits were one atomic change.

T023 (Maintainer Feedback) splits that same job in two, and the waiver
reappears for `stalled` — for a structurally different reason than the one
T005 removed. Post-split, `stalled` calls `wing-commander-chain-stop-notice`
with `mark-record: "false"`: the composite's push-capable step never runs
on that call, regardless of `spec-dir`. Gate 80 has no per-input-value
analysis — any job calling a composite whose own steps contain `git push`
is flagged — so this is waived exactly the way `intake.yml`'s and
`clarify.yml`'s own `stalled` jobs already are (this same file, above): a
survivor job that calls the composite but structurally never reaches its
push. The job that DOES push, `stalled-mark`, declares the canonical
per-spec group directly and carries no waiver — that is what SC-001 now
measures (spec.md).

## Gate registry entry

| Gate | Change | Proves |
|---|---|---|
| 80 (`verify-spec-branch-push-concurrency.py`, amended) | `PER_SPEC_GROUP_RE`-style acceptance gains one additional, exactly-matched alternative pattern for the per-PR fallback spelling (research.md D5); existing three spellings and the waiver mechanism are untouched | FR-018 (the fallback spelling is recognized, exactly); SC-001 (the job that actually pushes, `stalled-mark`, needs zero waivers and declares the canonical group; `stalled` itself carries a waiver post-T023, for the same structural reason `intake.yml`/`clarify.yml`'s own `stalled` jobs already do); SC-008 (a degenerate `wing-commander-` group and a near-miss of either spelling are still rejected — proven by new self-test fixtures, not by the repository merely passing) |

Full contract: [contracts/gate-80-fallback-spelling.md](./contracts/gate-80-fallback-spelling.md).
