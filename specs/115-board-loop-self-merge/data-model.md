# Data Model: Board Loop Self-Merge

## MergeCandidate

| Field | Type | Notes |
|-------|------|-------|
| class | `fix` \| `bump` | Fix: a PR the loop opened for a board item. Bump: an auto-update stage PR (research D4). |
| pr_number | int | |
| head_sha | string | `headRefOid` from the merge job's own fresh fetch |
| issue_number | int | The resolved issue (fix) or the `auto-update:tracking` issue (bump) |

Never a candidate: a spec PR, a plan PR, a lifecycle PR, or a PR touching `.specify/memory/constitution.md` (FR-012).

## MergeSnapshot

The `gh pr view --json headRefOid,statusCheckRollup,author,headRefName,commits,files,comments` result at one head SHA, plus the values of `WING_COMMANDER_BOARD_AUTO_MERGE` and `WING_COMMANDER_BOARD_LOOP_PAUSED`. The fix class adds `backstop_holds` and `review_converged`, computed in the same job.

## BumpVerificationRecord

A hidden-marker comment authored by the App.

| Field | Notes |
|-------|-------|
| head_sha | The SHA the verification ran on |
| tier | The verification assigned to the jump, e.g. `lightweight` or `e2e` |
| result | `passed` or `failed` |
| run_id | The act job's run |

Only records whose `head_sha` equals the fresh head count; a record for another head says nothing about this one. Among those, the latest by the bot wins, ordered by `createdAt` and then the comment's numeric id (createdAt has one-second resolution).

## MergeDecision

```text
{head_sha, class, may_merge, unmet_reason|null,
 conditions: {name: bool, ...}}
```

- Fix conditions, in order: `switch_on`, `kill_switch_clear`, `eligible_class`, `checks_green`, `gate_suite_green`, `review_converged`, `backstop_holds`.
- Bump conditions, in order: `switch_on`, `kill_switch_clear`, `attributed_to_auto_update`, `checks_green`, `gate_suite_green`, `verification_passed_at_head`. There is no backstop.
- `unmet_reason` is the first failing condition's name.

## MergeOutcome

`merged` (with the merge commit SHA), `refused` (with `refusal_class` and the quoted reason), `transient` (a self-clearing failure that persisted through one re-derived retry; not a handover), or `not-merged` (an unmet condition). Each is announced on the PR and the issue (FR-008, FR-009, FR-010), once per head, outcome and reason, with a `wc-board-merge-outcome` marker on the PR.

## State transitions (issue marker `step`)

`awaiting-merge` is the existing switch-off terminal. With the switch on, readiness-ready leads to `merged` (stand down, prove follows) or `handed-over` (a refusal; released like `awaiting-merge`). An unmet condition or a `transient` outcome leaves the step unchanged (readiness's `awaiting-merge` hand-off stands). A bump PR is not a board item: a `refused` outcome marker at its head releases it until the head moves, and any other outcome leaves it for the next run.
