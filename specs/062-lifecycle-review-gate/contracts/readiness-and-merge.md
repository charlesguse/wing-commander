# Contract: Readiness and Merge Preconditions

## `.github/scripts/lifecycle_readiness.py`

```python
def evaluate(pr_number: int) -> LifecycleReadinessDecision:
    """FR-001/FR-004/FR-005/FR-006. Fetches gh pr view <pr_number> --json
    headRefOid,statusCheckRollup,mergeable,mergeStateStatus fresh — never
    a value captured earlier in this run, matching board_readiness.py's
    own stated discipline. See data-model.md §4."""
```

### Conditions, in the order the report names them

1. **Checks green on the fresh `head_sha`** — every entry in the fresh
   `statusCheckRollup` belongs to `head_sha`; an empty rollup is
   `checks_green: false` (a head with no checks is not green —
   constitution VIII).
2. **Gate suite green on `head_sha`** — the `lint-workflows` entry within
   that same fresh rollup, not a second local re-run (matching
   `board_readiness.py`'s own precedent exactly).
3. **Mergeable** (new relative to `board_readiness.py` — D5): GitHub's
   `mergeable` field is `MERGEABLE` (not `UNKNOWN`/`CONFLICTING`); the
   board loop never checks this because it never merges, so no existing
   code answers this question for a lifecycle PR yet.
4. **Not yet reviewed at this head SHA** (new relative to
   `board_readiness.py` — D5): `spec-meta.json.review_gate.head_sha !=
   head_sha` (FR-004/FR-005 — a pass never carries over to a head it was
   not derived on).
5. **Kill switch clear**: `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED !=
   'true'`, checked again at this exact moment (FR-006).

`ready: true` only when all five hold. Any single failure is a normal
outcome (FR-001 scenario 4): the unmet condition is stated on the
lifecycle issue rather than a pass reported, and the PR is picked up
again on a later run.

## `.github/scripts/lifecycle_merge_preconditions.py`

```python
def evaluate(pr_number: int) -> LifecycleMergePreconditions:
    """FR-026/FR-027/FR-030. Calls lifecycle_readiness.evaluate() fresh,
    then re-derives the three merge-only conditions below against the
    same fresh snapshot. See data-model.md §5."""
```

### Conditions

1–5. Every `lifecycle_readiness.py` condition above, re-derived fresh
   (never the `review` job's earlier evaluation — the head SHA may have
   moved since, spec.md Edge Cases: "the head SHA moves mid-round").
6. **Round clean at this exact head SHA**:
   `review_gate.head_sha == head_sha and review_gate.outcome == "clean"`.
7. **Zero open in-scope findings**: `review_gate.findings_open == 0`
   (redundant with 6 in the common case, but independently checked —
   FR-026 lists it separately, and a finding could in principle be
   reopened by a later process without changing `outcome`).
8. **No unresolved human changes-requested review**: fresh `gh pr view
   --json reviews`; any `CHANGES_REQUESTED` review whose author is not
   this App's own bot identity blocks the merge (FR-026, US4 scenario 4).

`may_merge` is the conjunction of all eight. `unmet_reason` is the first
failing condition's own name (data-model.md §5) — FR-027 requires stating
*which* condition failed, not merely that one did.

## On `may_merge: true`

`gh pr merge --squash "$PR" --match-head-commit "$SHA"` (contracts/
lifecycle-review-gate-workflow.md job 7). `--match-head-commit` is a
second, independent guard beyond the fresh re-derivation above — if
GitHub's own view of the head SHA has moved between this script's read
and the merge call, the merge itself fails rather than merging a
different commit than the one just evaluated (belt-and-suspenders against
the exact race spec.md's Edge Cases name).

On success: announce on the lifecycle issue with the head SHA, the round
number, and the conditions checked (FR-029). On failure: if the failure
text matches GitHub's workflow-scope refusal, state that reason and stop
(FR-030, research.md D14); otherwise state the generic failure and stop.
Never `--admin`, never a second merge method, never a route around the
refusal (FR-030, CLAUDE.md's "Working the issue board" merge-scope
rule).

## On `may_merge: false`

State `unmet_reason` on the lifecycle issue (FR-027); the PR remains open
for a human. This is the shipped-default path for every lifecycle PR
until a maintainer sets `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` (SC-005).

## Gate: `verify-lifecycle-readiness.py`

Fixtures (mirroring `verify-board-readiness.py`'s six-case shape, plus
the two conditions this script adds):
1. Stale check summary (rollup reflects an older `headRefOid`) → not
   ready.
2. No checks at all on the head → not ready.
3. `mergeable: CONFLICTING` → not ready, named distinctly from "checks
   not green".
4. `review_gate.head_sha` already equals the fresh head → not ready
   ("already reviewed at this SHA"), distinct from every other reason.
5. Kill switch set → not ready, stand-down recorded.
6. All five conditions hold → ready.

## Gate: `verify-lifecycle-merge-preconditions.py`

Fixtures:
1. Every readiness condition holds but `review_gate.outcome ==
   "findings"` → `may_merge: false`, reason names "round not clean".
2. Readiness holds, round clean, but an open human `CHANGES_REQUESTED`
   review exists → `may_merge: false`, reason names the human review.
3. Readiness holds, round clean, no human review, `findings_open == 0` →
   `may_merge: true`.
4. Head SHA moved between the review round and this evaluation
   (`review_gate.head_sha != current head_sha`) → `may_merge: false`,
   falls through to readiness condition 4 above, reason names "not yet
   reviewed at this SHA" rather than a merge-specific reason (the stale
   round is simply not a round for this head at all).
