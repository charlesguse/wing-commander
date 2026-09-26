# Contract: Changes to `pr-conversation.yml` and `implement.yml`

This is the diff-shaped contract the implementation (tasks phase, next
stage) must satisfy against the two existing published stages this
feature touches. Every existing `concurrency:` block listed below is
**unchanged** — this feature adds prerequisite jobs and read-path changes,
never a new group string, per research.md D1.

## `pr-conversation.yml`

| Job | Change |
|---|---|
| `classify-and-announce` | **Unchanged.** Still joins `wing-commander-pr-conversation-pr-<n>` (or the stop-only per-PR-stop group, unchanged carve-out logic at `:1306-1327`). Still computes `concurrency-group` output exactly as today. |
| `fold-turn-act` (**NEW**) | `needs: classify-and-announce`. `if:` mirrors `act`'s own qualifying condition (`:1485-1491`) so it is skipped exactly when `act` would have been skipped (a `stop`-only run, or zero legs). Carries no `concurrency:` block. Calls `wing-commander-fold-queue-admit` once (`kind: act`, `spec-dir: needs.classify-and-announce.outputs.spec-dir`) — one ticket for the whole run's fold phase, not one per leg (research.md D1). Skipped entirely for a `stop`-only run (its `concurrency-group` output is the per-PR stop group, not the per-spec one, and it never touches the ledger — FR-005/FR-017a preserved unchanged). |
| `act` | `needs:` gains `fold-turn-act`. `concurrency:` block **unchanged** (`:1526-1528`). Each leg's existing final step gains a call to `wing-commander-fold-queue-release` (`kind: act`, one call per leg id, `if: always()`) before the job ends, recording that leg's outcome (research.md D3) instead of relying on `report-fold-outcomes`' external job-conclusion read for attribution — `report-fold-outcomes` keeps its own job-conclusion cross-check as today (it is a genuine independent signal, not redundant: it is what still catches a leg that died before it could call `release` at all) but sources its *fold-happened* signal from the ledger's completion record instead of the `BASE_SHA..TIP_SHA` git-log scan. |
| `fold-turn-dispatch` (**NEW**) | `needs: [classify-and-announce, act]`, `if: always()` and the same qualifying condition `dispatch-once` already has (`:2583-2588`). No `concurrency:` block. Calls `wing-commander-fold-queue-admit` (`kind: dispatch`). |
| `dispatch-once` | `needs:` gains `fold-turn-dispatch`. `concurrency:` block **unchanged** (`:2614-2616`). First new step calls `wing-commander-fold-queue-claim-dispatch`; when `should-dispatch: false`, the job releases its ticket and ends (no reply posted — research.md D4). When `true`, the existing dispatch/reply logic (`:2659-2751`) runs using the composite's `folded-items`/`not-folded-items`/`iteration` outputs in place of its own `BASE_SHA`/`TIP_SHA`/git-log-range computation, and passes `implement-token` as the new `fold-queue-token` input on its `gh workflow run` call. |
| `report-fold-outcomes` | Read-path change only: the "folded" signal per item now reads the ledger's round record for this run's own `run_id` (research.md D3) instead of `git log ... BASE_SHA..TIP_SHA`; the existing job-conclusion cross-check (`gh api .../jobs`) is unchanged. No `concurrency:` block (unchanged — this job never mutates the branch). |

## `implement.yml`

| Job / input | Change |
|---|---|
| `fold-queue-token` (**NEW** `workflow_call` input) | Optional, default `''`. Widens the published contract deliberately (Constitution VII); no existing input, secret, or output is touched. |
| `fold-turn-implement` (**NEW**) | `needs:` none beyond the workflow's existing prerequisite jobs. No `concurrency:` block. When `inputs.fold-queue-token != ''`, calls `wing-commander-fold-queue-admit` with `existing-token: inputs.fold-queue-token` (await-only, no enqueue — research.md D5). When empty, the job is a no-op success immediately (`if: inputs.fold-queue-token != ''` gates the real work; the job itself still exists so `implement`'s `needs:` is uniform whether or not a token was supplied), preserving today's behavior for a manual/standalone dispatch (FR-019). |
| `implement` | `needs:` gains `fold-turn-implement`. `concurrency:` block **unchanged** (`:363-365`). Final steps gain an `if: always()` call to `wing-commander-fold-queue-release` (`kind: implement`) once both `implement` and `stalled` have concluded (a small new terminal job, `fold-turn-release`, `needs: [implement, stalled], if: always()`, is the natural home for this rather than duplicating the release call into two jobs). |
| `stalled` | `concurrency:` block **unchanged** (`:2715-2717`). No other change — its `!cancelled()` gate is left exactly as it is (research.md D7 explains why no rewrite of this gate can fix the pending-cancel case). |

## Non-goals of this diff

- No change to `classify-and-announce`'s own per-PR group or the
  `stop`-only carve-out logic.
- No change to `act`'s within-run `max-parallel: 1` matrix ordering
  (including the confirm-gated-legs-run-last sort at `:1279-1292`).
- No change to `implement.yml`'s iteration-cap or converge-loop logic.
- No change to any *other* stage's concurrency group (`plan.yml`,
  `tasks.yml`, `finalize.yml`, `rebase.yml`, `cleanup.yml`) — they are not
  ticket participants and keep joining `wing-commander-<spec-dir>`
  directly, exactly as spec 013's contract already describes.
