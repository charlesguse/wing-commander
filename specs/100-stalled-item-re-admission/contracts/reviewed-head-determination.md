# Contract: Reviewed-Head Determination (FR-006b)

The single, shared computation of "has this PR's head moved since the last
review covered it?" Built once, here, and consumed by this feature's resume
clause 2 split (`resume-recovery-readmission.md`). Spec 093 FR-007, when
that feature reaches its own plan stage, MUST call this same function rather
than deriving a second determination (CLAUDE.md "shared logic has exactly
one home"; spec 100's own status note: "the rule, its resume clause ... are
built once, here, and spec 093 consumes them").

## Signature

```text
head_moved_since_last_review(pr_number, comments, bot_login, run=None) -> bool
```

In `.github/scripts/board_item_marker.py`. `comments` is the resume step's
flat per-issue comments array, read by path from
`$RUNNER_TEMP/board-issue-comments.json` (never through an environment
variable, which a long comment history can overflow). Returns whether the
PR's live head SHA differs from the head SHA recorded on the loop's own
newest review verdict for that PR, which must be a *converged* one.

## Algorithm

1. Scan `comments` for the loop's own bot-authored review verdicts naming
   this `pr_number`, of any kind: `Review round N converged -- … PR #P
   (head <sha>)`, the budget-spent, parse-failed and malformed-findings
   wordings, and a pushed follow-up round. Take the newest by `created_at`.
2. If that newest verdict is not the converged wording → return `True`
   (moved — FR-006b's safe default) without calling `gh`. This covers no
   review ever having covered the PR, and an inconclusive or budget-spent
   verdict after an earlier converged one: none establishes a head
   reviewed clean.
3. Otherwise read its recorded `<sha>` (the commit the review job checked
   out, `steps.checkout-pr.outputs.head-sha`) and run
   `gh pr view <pr> -R "$GITHUB_REPOSITORY" --json headRefOid`. If the
   lookup raises, exits non-zero, returns unparsable JSON, or has no
   `headRefOid` → return `True` (each failure is warned on stderr).
4. Return `headRefOid != <sha>`: `False` (→ `readiness`) only when the live
   head is exactly the commit the converged review covered.

## What this contract explicitly does not do

- It does not read or extend the board-item marker (FR-019). The marker's
  `stalled` step carries no head SHA and none is added.
- It does not require review to switch from posting issue comments to
  posting formal GitHub PR reviews (`gh pr review`) — research.md D3's
  "Alternatives considered" rejected that as a larger, out-of-scope change.
- It does not distinguish *which* non-converged arm produced the newest
  verdict: budget-spent, parse-failed and malformed-findings all fall
  through to step 2's default of `True` (→ `review`), consistent with
  FR-006b's rule that an inconclusive review never yields `readiness`.

## Gate coverage

Gate 134 (`verify-board-loop-readmission.py`) exercises this function
directly with fixture cases:
- converged SHA ≠ live head (moved → `review`);
- converged SHA = live head (unmoved → `readiness`);
- no verdict, or only a budget-spent one (→ `review`, no lookup);
- a converged verdict followed by a budget-spent one on the same head
  (→ `review`, no lookup);
- the lookup fails (→ `review`).
