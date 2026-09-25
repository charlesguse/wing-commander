# Contract: Readiness Report

## `.github/scripts/board_readiness.py`

```python
def evaluate(pr_number: int) -> ReadinessDecision:
    """FR-066/FR-067. Fetches gh pr view <pr_number> --json
    headRefOid,statusCheckRollup fresh (never a value captured earlier in
    this run — FR-036). See data-model.md "Readiness Decision"."""
```

## Conditions, in the order the report names them (FR-066)

1. **Checks green on `head_sha`** (FR-036/FR-037): every entry in the
   fresh `statusCheckRollup` belongs to `head_sha`; an empty rollup is
   `checks_green: false` (a docs-only PR with no triggered checks is never
   reported ready — Principle VIII, the `lint-workflows.yml` path-filter
   edge case named in the spec).
2. **Gate suite green on `head_sha`** (research.md D13): the
   `lint-workflows` entry within that same fresh rollup, not a second
   local re-run.
3. **Zero open findings** (FR-033): count of `in_scope: true` findings not
   yet superseded by a later commit, from the structure
   contracts/review-and-findings.md defines.
4. **Size-and-path backstop holds on the final diff** (FR-018): the same
   `wing-commander-size-path-backstop` call contracts/route-backstop.md's
   `route_final_diff()` already performs, re-read here rather than
   re-computed.
5. **Kill switch clear**: `WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`,
   checked again at this exact moment (FR-051).

`ready: true` only when all five hold. Any single failure is a normal
outcome (FR-067): the PR is left open, `unmet_reason` is named on the
issue, and the item is picked up again on a later run — never polled in a
loop.

## On `ready: true`

Post a readiness report on the PR naming `head_sha` and each condition's
result; record the same on the issue; state that a human merge is awaited
(FR-066, FR-068). Never merge, approve, or enable auto-merge (FR-068).

The issue record carries a board item marker with step `awaiting-merge`
(not `readiness`), keeping `pr` (#532). That step is the handover: the
loop stops at "ready to merge", so the item releases the board rather than
holding it until a human merges. `select` never treats an `awaiting-merge`
item as in flight, and its oldest-first fallback passes the item over
until the PR is positively known to be CLOSED or MERGED
(specs/061-marker-owned-in-flight/contracts/in-flight-detection.md). After
that, resume sends the still-open issue to a fresh `triage`
(specs/061-marker-owned-in-flight/contracts/resume-recovery.md). A human
merge still reaches `prove` through `pull_request: closed`, which reads
the PR body's `Fixes #N` and the marker's presence, never its step.
Known limit: a push to the PR head after the ready report does not bring
the item back to readiness.

A not-ready outcome leaves the marker as it was, so the next run picks the
item up at `readiness` again.

## Gate: `verify-board-readiness.py`

Fixtures (FR-064 bullet 4), each a checked-in `gh pr view` JSON snapshot:
1. Stale check summary (rollup reflects an older `headRefOid` than the
   PR's current one) → not ready, SHA mismatch named.
2. No checks at all on the head → not ready.
3. One open in-scope finding → not ready, count named.
4. Final diff breaches the backstop → routes to `spec-request` per
   contracts/route-backstop.md, not merely "not ready".
5. Kill switch set → not ready, stand-down recorded.
6. All five conditions hold → ready, report posted, no merge performed.
