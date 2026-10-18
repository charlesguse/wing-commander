# Contract: `wc_convergence` module (consuming instrument; internal)

Not part of the published, adopter-pinned surface.

## API
```
measure(base, heads, findings, cwd) -> report        # attribution, churn, growth (moved from thrash_signals.py)
validate_line(path, line, head, cwd) -> bool
classify_recurrence(findings, ledger) -> (fresh, recurrences)
decide(history, thresholds=THRESHOLDS, budget=None) -> {signals, tripped, stop, reason}
round_findings(findings, issue) -> [{fingerprint, file, line, title}]   # in-scope only
round_record_marker(round, head_sha, entries) -> "<!-- wing-commander-convergence-round: {...} -->"
read_round_records(reviews, bot_login) -> [record]                     # newest per round
evaluate(records, current, base, cwd, resolved=None, budget=None,
         resolved_from_history=False, pending=None, dismissed=None)
    -> decision + {recurrences, git_ok, open_findings}
render_handoff(decision) -> markdown
```
`THRESHOLDS = {min_round: 3, self_inflicted_share: 0.5, consecutive_churn_rounds: 2, growth_ratio: 0.5}` — the only place these numbers live.

`budget` is the loop's own budget-stop round: a trip on that round names the budget (`reason: budget-spent`) and still lists the tripped signals; the budget alone never makes `decide` stop (the loop's own check does, FR-009).

## Round records
Each loop appends one record per parsed round, last, to the review it posts on the PR: `{round, head_sha, findings: [{fingerprint, file, line}]}`. Only the App's own bot-authored reviews count, and only the last marker opener in a body. The lifecycle gate's ledger is its marker's `folded_fingerprints`, and its dismissed list is every fold the owner answered `/fold-hold drop`: `wc_fold_hold.dropped_fingerprints` reads the App-authored `wing-commander-fold-hold-resolved` markers whose resolution is `drop` and, for each, the `fingerprints` of the `folded_json` entries in that fold's newest App-authored hold state before it. A dismissed finding raised again is neither a recurrence nor folded again, and `evaluate` subtracts dismissed entries from every round's count, the current round and the recorded rounds alike (`count − |dismissed ∩ entries|`), and leaves them out of `open_findings`, so count-not-falling and the hand-off read only findings the loop still owes; pending findings (fold task still open) stay counted. The board loop's ledger is every earlier round's findings (`--resolved-from-history`), since review-fixup fixed them. Board-loop rounds are 0-based, so it passes `round + 1` and `BOARD_LOOP_ROUND_BUDGET + 1`.

## CLI
`python .github/scripts/wc_convergence.py decide --history <json> --base <ref> [--json]`, plus `record`, `evaluate` (what both loops call; writes `stop`, `reason`, `tripped`, `recurrences` to `$GITHUB_OUTPUT`) and `render-handoff`. `thrash_signals.py` retains its flags, gains `--recurring` and `--history`, and delegates.

## Hand-off (FR-008)
Comment on the lifecycle issue (lifecycle gate) or the originating issue (board loop, where its budget-exhaustion hand-off already posts) with marker `<!-- wing-commander-not-converging: round=N -->`, stall reason `not-converging`, a per-round table of trend/self-inflicted/churn/growth/recurrence, the unattributable count, and the open in-scope findings. The PR is left open and unmerged; stall labelling follows the existing budget-exhaustion path. A recurrence is named on the lifecycle issue (lifecycle gate) or in the round's review on the PR (board loop) (FR-003).

## Reviewer schema change
Finding objects gain optional `line` (integer ≥ 1, `.github/schemas/board-review-finding.schema.json`). Not part of the fingerprint.

## Invariants
- Same history in → same signals out, for the skill and both loops (SC-003).
- Round < 3 never stops early. Budget stop is independent.
- Invalid or missing line ⇒ unattributable, never a guessed nearby line.
