# Contract: `wc_convergence` module (consuming instrument; internal)

Not part of the published, adopter-pinned surface.

## API
```
measure(base, heads, findings, cwd) -> report        # attribution, churn, growth (moved from thrash_signals.py)
validate_line(path, line, head, cwd) -> bool
classify_recurrence(findings, ledger) -> (fresh, recurrences)
decide(history, thresholds=THRESHOLDS) -> {signals, tripped, stop, reason}
render_handoff(decision) -> markdown
```
`THRESHOLDS = {min_round: 3, self_inflicted_share: 0.5, consecutive_churn_rounds: 2, growth_ratio: 0.5}` — the only place these numbers live.

## CLI
`python .github/scripts/wc_convergence.py decide --history <json> --base <ref> [--json]`; `thrash_signals.py` retains its flags and delegates.

## Hand-off (FR-008)
Comment on the lifecycle issue (lifecycle gate) or PR (board loop) with marker `<!-- wing-commander-not-converging: round=N -->`, stall reason `not-converging`, a per-round table of trend/self-inflicted/churn/growth/recurrence, the unattributable count, and the open in-scope findings. The PR is left open and unmerged; stall labelling follows the existing budget-exhaustion path.

## Reviewer schema change
Finding objects gain optional `line` (integer ≥ 1). Not part of the fingerprint.

## Invariants
- Same history in → same signals out, for the skill and both loops (SC-003).
- Round < 3 never stops early. Budget stop is independent.
- Invalid or missing line ⇒ unattributable, never a guessed nearby line.
