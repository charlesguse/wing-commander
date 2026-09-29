# Contract: `lifecycle-review-gate.yml`

Repository-only workflow (no `workflow_call` — research.md D1). Trigger:
`schedule:` (a conservative cadence, e.g. every 15 minutes — the exact
cron expression is an implementation-time choice, not a design one) plus
`workflow_dispatch`. Single concurrency group
(`wing-commander-lifecycle-review-gate`), so a run never overlaps a prior
one, matching `board-loop.yml`'s own one-item-at-a-time discipline
(spec.md Edge Cases: "concurrent specs do not contend for the usage
window").

## Job graph

1. **`kill-switch`** — `if: vars.WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED == 'true'`
   short-circuits the whole run; no other job starts, nothing is recorded
   (there is nothing yet to stand down from until a PR is selected).

2. **`select`** — lists open PRs, filters to `spec-meta.json.stage ==
   "review"` and same-repository/default-base only (D2, T077/F5 — a fork
   PR's `headRefName` is never trusted as a same-repository branch), keeps
   those whose `review_gate.head_sha` (if any) differs from the PR's
   current `headRefOid` (T074/F3: `review_gate` is read from the lifecycle
   issue's own marker, `wc_lifecycle_review_marker.py` — nothing this gate
   does ever commits to the reviewed branch, so no peel is needed;
   T069/T075's commit-subject peel, `wc_review_gate_settled_head.py`, is
   deleted), picks the oldest. Outputs `pr-number`, `issue`, `spec-dir`,
   `head-sha` (the PR's raw current head), `review-gate-head-sha` (the
   RECORDED value read off the marker, threaded through for `readiness` to
   compare against its own fresh snapshot rather than comparing `head-sha`
   against itself), or nothing (clean exit, the common case — SC-009's "at
   most one round per SHA" starts here, before any billable step runs).

3. **`readiness`** — calls `lifecycle_readiness.py` (contracts/readiness-
   and-merge.md) against `select`'s `head-sha`. `ready: false` → posts
   `unmet_reason` on the lifecycle issue (FR-001 scenario 4) and stops;
   `ready: true` → proceeds to `review`.

4. **`review`** — the reviewer step (contracts/review-and-findings.md):
   Claude Code's `code-review` capability via the `Skill` tool, an
   explicit model/turn ceiling, a `COMMENT`-only posted review
   (`wing-commander-post-review-comment`), and the fenced
   `wing-commander-review-findings` block schema-validated against
   `board-review-finding.schema.json`.

5. **`disposition`** — deterministic (D11): reads the current `review_gate`
   marker (T074), partitions findings by `in_scope`, dedupes against its
   `folded_fingerprints`/`filed_fingerprints`, files out-of-scope survivors
   (`wing-commander-durable-failure-issue`), renders in-scope survivors
   into a tasks.md section, and — only if that section is non-empty —
   calls `wing-commander-fold-commit` then `wing-commander-fold-dispatch`
   (contracts/fold-integration.md). Writes nothing durable itself: it
   outputs this round's data (round, outcome, findings_open, the
   post-round fingerprint sets) for `report` to write, once, into the
   marker (T074/F3 — `disposition` no longer commits `review_gate`
   anywhere, since a commit to the reviewed branch is exactly what made
   auto-merge unreachable). T070/FR-013/FR-020: "clean" here means zero
   open IN-SCOPE survivors after dedup — a round whose only survivors are
   out-of-scope (still filed above) resolves `outcome: "clean"` and gets
   the same passing status as a round with no findings at all, never a
   round whose raw counts alone were nonzero.

6. **`report`** — the review_gate marker's SOLE writer (T074/F3): posts
   the round's outcome to the lifecycle issue -- round number, head SHA,
   finding count, result (FR-015) -- and the cost line via
   `wing-commander-metrics-summary`'s existing `cost-line` output
   (FR-036) — the 8-stage pattern, not `board-loop.yml`'s silent-metrics
   pattern (research finding: board-loop never renders a cost line;
   this gate follows the stages that do, since spec.md US6 scenario 3
   requires the existing single home). Appends the marker
   (`wc_lifecycle_review_marker.py write`) to that same comment, unless
   the round failed/parse-failed (in which case nothing is written, so a
   retryable round never counts against the budget or FR-021's dedup).

7. **`merge`** — `if: vars.WING_COMMANDER_LIFECYCLE_AUTO_MERGE == 'true'`,
   and needs `report` (and its success, T082): `report` is the
   `review_gate` marker's sole writer, so `merge` never reads the marker
   before this round's value has landed. Re-checks the kill switch
   immediately before this durable action through its own step `env:`
   (`KILL_SWITCH_PAUSED` from `vars.WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED`),
   which is the "equivalent minimal re-check" `wing-commander-board-stop-check`
   names — that composite itself is NOT used: it re-checks a board-loop
   issue's maintainer stop request and cancels an earlier board-loop run,
   neither of which exists for a lifecycle PR, and its paused input has to
   be resolved by the caller anyway because a composite `run:` cannot read
   `vars`. Per T078 this re-check is defence in depth, not a guaranteed
   mid-run kill (a `vars.` expression is only as fresh as the context the
   run was handed): a pause reliably takes effect on the next run, bounded
   by the `kill-switch` job and every job's job-level `if:`. It then calls `lifecycle_merge_preconditions.py` fresh against the
   *current* head SHA (not the SHA `review` evaluated, in case it moved —
   FR-026), and on `may_merge: true` runs
   `gh pr merge --squash "$PR" --match-head-commit "$SHA"`, then announces
   the merge on the lifecycle issue (FR-029). On any unmet condition,
   states which one (FR-027) and does not merge. On a workflow-scope
   refusal, states that reason and stops (FR-030, D14) — never falls back
   to `merge` (`gh pr merge` with `--admin` or similar) or any other
   route.

## Round budget

`env.LIFECYCLE_REVIEW_ROUND_BUDGET: 5` (D12). `select`/`readiness` check
`review_gate.round` against it before spending a review; on exhaustion
the run posts the reason and the still-open findings to the lifecycle
issue (US2 scenario 4, FR-022) and does not select this PR again until a
human intervenes (mirroring `board:stalled`'s "removing the label is the
sole re-eligibility condition" idiom, applied here as leaving the PR
alone rather than a label, since a lifecycle PR has no `board:stalled`
equivalent to apply).

## Edge cases this contract states explicitly

- **PR or issue closed mid-round** (spec.md Edge Cases): every job
  re-checks `wing-commander-lifecycle-gate`'s `is-open` output
  immediately before its own next durable action; a closed PR/issue mid-
  round stops the round without posting findings — the same
  re-check-before-a-durable-action discipline
  `wing-commander-board-stop-check` applies to board-loop issues (that
  composite itself is not used here; see job 7).
- **Two lifecycle PRs ready at once**: the single concurrency group
  serializes them; `select` picks the oldest each run.
- **Human changes-requested review during a round**: `disposition` and
  `merge` both re-read `gh pr view --json reviews` fresh (D6) rather than
  a value cached earlier in the same run — a round that completes after a
  human's `CHANGES_REQUESTED` review does not overwrite or race it,
  because nothing this workflow does calls `REQUEST_CHANGES` or dismisses
  an existing review.
