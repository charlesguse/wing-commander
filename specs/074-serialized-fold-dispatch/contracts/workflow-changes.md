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
| `fold-turn-act` (**NEW**) | `needs: classify-and-announce`. `if:` mirrors `act`'s own qualifying condition (`:1485-1491`) plus `needs.classify-and-announce.outputs.stop-only != 'true'` (T054/B2) so it is skipped exactly when `act` would have been skipped (zero legs) OR when every classified leg is `stop` — the stop procedure runs INSIDE `act`, so a stop-only run's `legs` is never actually empty; `stop-only` is the real signal, computed by `classify-and-announce` alongside `concurrency-group` (same `all(.category == "stop")` check). Carries no `concurrency:` block. Calls `wing-commander-fold-queue-admit` once (`kind: act`, `spec-dir: needs.classify-and-announce.outputs.spec-dir`) — one ticket for the whole run's fold phase, not one per leg (research.md D1). Skipped entirely for a `stop`-only run (its `concurrency-group` output is the per-PR stop group, not the per-spec one, and it never touches the ledger — FR-005/FR-017a/SC-009 preserved unchanged). |
| `act` | `needs:` gains `fold-turn-act`. `if:` accepts `needs.fold-turn-act.result == 'skipped'` only when `needs.classify-and-announce.outputs.stop-only == 'true'` (T054/B2) — otherwise it still requires `'success'`, so a skip for any other reason never substitutes for a real grant. `concurrency:` block **unchanged** (`:1526-1528`). Each leg's existing final step gains a call to `wing-commander-fold-queue-release` (`kind: act`, one call per leg id, `if: always()`) before the job ends, recording that leg's outcome (research.md D3) instead of relying on `report-fold-outcomes`' external job-conclusion read for attribution — `report-fold-outcomes` keeps its own job-conclusion cross-check as today (it is a genuine independent signal, not redundant: it is what still catches a leg that died before it could call `release` at all) but sources its *fold-happened* signal from the ledger's completion record instead of the `BASE_SHA..TIP_SHA` git-log scan. |
| `fold-turn-dispatch` (**NEW**) | `needs: [classify-and-announce, act]`, `if: always()`, the same qualifying condition `dispatch-once` already has (`:2583-2588`), plus `needs.classify-and-announce.outputs.stop-only != 'true'` (T054/B2, same reasoning as `fold-turn-act`). No `concurrency:` block. Calls `wing-commander-fold-queue-admit` (`kind: dispatch`). **T045 (maintainer review of #821):** also now does everything the round's dispatch decision needs — reads the post-fold tip, computes this run's own fold evidence (`wing-commander-fold-evidence`), counts it (`own-folds`), and calls `wing-commander-fold-queue-claim-dispatch` (with `implement-configured: inputs.implement-workflow != ''`, T046) — because it carries no `concurrency:` block, its own internal requeue-reawait wait never blocks the run it is waiting on. Exposes `tip-sha`, `should-dispatch`, `outcome`, `own-folds`, `folded-json`, `round-folded-json` and `implement-token` as job outputs for `dispatch-once` to read. Originally this all lived in `dispatch-once` itself, which deadlocked: `dispatch-once` holds `wing-commander-<spec-dir>`, so a requeue-reawait loop running there waiting on another run's `act`-kind ticket could never see that ticket clear, since the owning run's `act` job cannot itself join the group `dispatch-once` occupies. |
| `dispatch-once` | `needs:` gains `fold-turn-dispatch`. `if:` accepts `needs.fold-turn-dispatch.result == 'skipped'` only when `stop-only == 'true'` (T054/B2, same shape as `act`'s acceptance) — a stop-only run then falls straight through every should-dispatch-gated step (`needs.fold-turn-dispatch.outputs.*` are all empty) to the no-op path, posting no reply. `concurrency:` block **unchanged**. `permissions:` gains `contents: write` (was `contents: read`, which could never have let the ledger-release call at the end of this job push — found while wiring T043, not merely a design addition). Reads `needs.fold-turn-dispatch.outputs.*` (T045) instead of computing its own tip/fold-evidence/own-folds/claim: `own-folds == 0` → `outcome: declined` unconditionally (spec 075 FR-014, preserved) — a "Reply that this run folded nothing of its own" step posts spec 075's declined-dispatch notice; `own-folds > 0` and another run's `act`-kind ticket still outstanding → `fold-turn-dispatch`'s own call already requeued and re-awaited internally before this job even started (a GitHub Actions job's static step list cannot loop across separate `uses:` steps); `own-folds > 0`, round empty, unclaimed → `outcome: won`, `should-dispatch: true`. Only a winning claim calls `wing-commander-fold-dispatch`, passing `needs.fold-turn-dispatch.outputs.folded-json`/`round-folded-json` (the latter mapped to `{id, summary}`, `id` = `run_id/leg_id` since a leg id is unique only within its own run) and `implement-token` as `fold-queue-token`. A `should-dispatch: false` result from an already-claimed round (another run won first) posts nothing — the winning run's own reply already names this run's folds via `folded-items`. A new step ("Record this round's dispatched implement run") correlates the dispatched run's own id (parsed from `wing-commander-fold-dispatch`'s `run-url` output) into the ledger via `record-implement-run`, which `fold-cycle-guard.yml` reads. **T046 (maintainer review of #821):** a final step ("Release an implement ticket this run's claim created but never handed to a real run"), `if: always()` and run AFTER the dispatch ticket's own release, releases `needs.fold-turn-dispatch.outputs.implement-token` whenever no dispatched-run id was ever recorded (standalone mode, a failed `gh workflow run`, or an unfound `run-url`) — otherwise that ticket sits granted at the queue head forever, since nothing will come to release it. |
| `report-fold-outcomes` | Read-path change only: the "folded" signal per item now reads the ledger's round record for this run's own `run_id` (research.md D3) instead of `git log ... BASE_SHA..TIP_SHA`; the existing job-conclusion cross-check (`gh api .../jobs`) is unchanged. No `concurrency:` block (unchanged — this job never mutates the branch). |

## `implement.yml`

| Job / input | Change |
|---|---|
| `fold-queue-token` (**NEW** `workflow_call` input) | Optional, default `''`. Widens the published contract deliberately (Constitution VII); no existing input, secret, or output is touched. |
| `fold-turn-implement` (**NEW**) | `needs:` none beyond the workflow's existing prerequisite jobs. No `concurrency:` block. When `inputs.fold-queue-token != ''`, calls `wing-commander-fold-queue-admit` with `existing-token: inputs.fold-queue-token` (await-only, no enqueue — research.md D5). When empty, the job is a no-op success immediately (`if: inputs.fold-queue-token != ''` gates the real work; the job itself still exists so `implement`'s `needs:` is uniform whether or not a token was supplied), preserving today's behavior for a manual/standalone dispatch (FR-019). |
| `implement` | `needs:` gains `fold-turn-implement`. `concurrency:` block **unchanged** (`:363-365`). Final steps gain an `if: always()` call to `wing-commander-fold-queue-release` (`kind: implement`) once both `implement` and `stalled` have concluded (a small new terminal job, `fold-turn-release`, `needs: [implement, stalled], if: always()`, is the natural home for this rather than duplicating the release call into two jobs). |
| `stalled` | `concurrency:` block **unchanged** (`:2715-2717`). No other change — its `!cancelled()` gate is left exactly as it is (research.md D7 explains why no rewrite of this gate can fix the pending-cancel case). |

## `wing-commander-fold-dispatch` (existing composite, additive change)

**T047 (maintainer review of #821):** an implement wrapper predating this
feature has no `fold_queue_token` `workflow_dispatch` input declared, so
GitHub rejects the pipeline's `-f fold_queue_token=` argument outright with
a 422 "Unexpected inputs provided" before even queuing a run. The
composite's dispatch step now retries once, without `fold_queue_token`,
when it sees exactly that rejection — the fold still dispatches, just
unticketed for that one cycle (today's pre-serialization behavior, not a
new failure mode) — and releases the `implement`-kind ticket the winning
claim already enqueued (`docs/adoption.md` documents declaring the input
in your own wrapper to avoid the retry and keep the ticket).

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
