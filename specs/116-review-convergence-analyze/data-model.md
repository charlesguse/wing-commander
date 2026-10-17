# Data Model: 116 Review Convergence and Fold-Time Analyze

Layer: consuming instrument, except **Analyze finding** and **Fold hold**, which cross the published contract (fold composites).

## Review round record (per PR, per round)
| Field | Type | Notes |
|---|---|---|
| round | int ≥1 | |
| head_sha | string | reviewed head |
| findings[] | list | in-scope findings only |
| findings[].fingerprint | string | existing `wc_review_finding_fingerprint` |
| findings[].file | string | |
| findings[].line | int \| null | validated at `head_sha`; null ⇒ unattributable |
| findings[].attributable | bool | derived: line valid at head |
| count | int | `len(findings)` |
| signals | Convergence signals | computed, never agent-supplied |

Persistence: appended to the loop's existing round marker (D3); additive fields.

## Resolved-finding ledger (per PR)
Map `fingerprint → resolving_round`, written when a round folds (lifecycle) or fixes (board) a finding. Dismissed fingerprints are kept in a separate set and never match recurrence.

## Convergence signals (per round)
| Field | Rule |
|---|---|
| trend | list of counts, rounds 1..n |
| self_inflicted_share | loop-written attributable findings ÷ attributable findings (0 on round 1; null if none attributable) |
| unattributable | count |
| churn | lines this round rewrote that an earlier round wrote (int) |
| growth | `diff_lines(head_n) / diff_lines(head_1) - 1` |
| recurrences | fingerprints matching the ledger |
| tripped | subset of {`count-not-falling`, `self-inflicted`, `recurrence`, `churn-streak`, `growth`}; empty before round 3 |

Decision: `stop = round ≥ 3 and tripped ≠ ∅`; budget stop applies independently (FR-009).

## Stall reason
Enum extended with `not-converging` (beside clean and budget-spent). Carries the signals table.

## Analyze finding
`{severity, category ∈ {constitution-conflict, inconsistency, duplication, other}, fold_task, location, principle?, detail}`. Hold iff any `category == constitution-conflict`.

## Fold hold
`{fold_id, reason ∈ {constitution-conflict, analyze-failed}, question_comment_id, options[], resolution ∈ {pending, proceed, drop, amend, retry}}`. State: `pending → released(proceed|drop|amend) | pending(retry)`.
