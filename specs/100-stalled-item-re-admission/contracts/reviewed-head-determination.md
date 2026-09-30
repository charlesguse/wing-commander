# Contract: Reviewed-Head Determination (FR-006b)

The single, shared computation of "has this PR's head moved since the last
review covered it?" Built once, here, and consumed by this feature's resume
clause 2 split (`resume-recovery-readmission.md`). Spec 093 FR-007, when
that feature reaches its own plan stage, MUST call this same function rather
than deriving a second determination (CLAUDE.md "shared logic has exactly
one home"; spec 100's own status note: "the rule, its resume clause ... are
built once, here, and spec 093 consumes them").

## Signature (illustrative — the implement stage names the actual module)

```text
head_moved_since_last_review(pr_number, comments_by_issue, bot_login) -> bool
```

Given already-fetched issue comments (the `select` job already fetches
these for `read_marker`) and a PR number, returns whether the PR's current
head commit postdates the loop's own most recent review-round verdict
comment for that PR.

## Algorithm

1. Fetch the PR's current head commit's timestamp:
   `gh pr view <pr> --json headRefOid,commits`, taking the `committedDate`
   of the commit matching `headRefOid` (or the last entry in `commits`,
   which is the head by construction).
2. Scan `comments_by_issue` for the loop's own bot-authored comments
   matching the existing round-outcome wording review already posts
   (`board-loop.yml:3298-3321` — "Review round N ... on PR #P", for both
   the converged and the stalled/budget-spent bodies), filtered to this
   `pr_number`, and take the most recent by `created_at`.
3. Compare:
   - No comment found in step 2, or step 1's lookup fails → return `True`
     (moved — FR-006b's safe default; also covers "no review ever covered
     this PR").
   - A comment is found: return `True` if the head commit's
     `committedDate` is strictly after the comment's `created_at`
     (something was pushed after the last review looked); return `False`
     otherwise (the head is the same commit the last review covered, or an
     older one — which cannot happen in practice but is treated as
     "unmoved" rather than erroring).

## What this contract explicitly does not do

- It does not read or extend the board-item marker (FR-019). The marker's
  `stalled` step carries no head SHA and none is added.
- It does not require review to switch from posting issue comments to
  posting formal GitHub PR reviews (`gh pr review`) — research.md D3's
  "Alternatives considered" rejected that as a larger, out-of-scope change.
- It does not distinguish *which* review arm produced the last comment
  beyond what's needed for the default: a parse-failed or
  malformed-findings comment is, by construction, never the "converged" or
  "budget-spent" wording this lookup matches, so those arms naturally fall
  through to step 3's "no comment found" default of `True` (→ `review`) —
  consistent with FR-006b's explicit rule that an inconclusive review
  never yields `readiness`.

## Gate coverage

The new gate (research.md D8) exercises this function directly with fixture
cases: a comment older than the head commit (moved → `review`), a comment at
or after the head commit (unmoved → `readiness`), no comment at all (default
→ `review`), and a failed PR lookup (default → `review`).
