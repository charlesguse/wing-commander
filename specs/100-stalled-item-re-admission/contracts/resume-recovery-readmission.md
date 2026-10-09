# Contract: Resume Recovery — Re-Admission Split (FR-006/FR-006a/FR-006b)

Extends `specs/061-marker-owned-in-flight/contracts/resume-recovery.md`'s
"Step resolution" clause 2. Read that document first — this states only the
delta FR-006 makes. **This is the change spec 100 makes to that live
contract; it is applied to `resume-recovery.md` itself in the same change
that implements this feature (FR-019), not a permanent second document.**
This file records the delta's rationale for review; the merged tasks stage
folds its text into `resume-recovery.md` clause 2 directly.

## Why clause 2 changes

FR-030 of spec 057 (`labels-and-cross-links.md`) makes removing
`board:stalled` "the sole condition that makes the item eligible again."
FR-006 does not touch that — it states what happens *next*. Every stall
site's marker is `stalled`, always `pr=None` (research.md D1), so a
label-removed stalled item always reaches resume clause 2's `board:owned`
fallback. Today that clause resolves unconditionally to `review` (except
the `breach` carve-out, #530). Spec 093's FR-007 needs a case where a
review-round budget was spent on an unmoved head to resume at `readiness`
instead, so nothing already reviewed is re-reviewed; FR-006b is the shared
mechanism this feature builds first (research.md D3) so spec 093 does not
need to build a second one.

## Amended clause 2

```text
2. No marker-named pr resolved, but the FR-007 (spec 061) fallback recovers
   an open board:owned pr citing this issue:

   a. The marker's step is `breach` (a post-push breach whose spec-request
      is not yet filed) -> step = "breach" (#530, unconditional — the
      review/readiness split below never applies to a breach marker).

   b. Otherwise, compute `head_moved_since_last_review` (FR-006b, see
      reviewed-head-determination.md in this same contracts directory):

      - `head_moved_since_last_review == True` -> step = "review", with a
        fresh round budget (round 0). This covers four cases:
        - the newest review verdict naming this PR is not a converged one:
          no review ever covered it, or the newest verdict is review's
          budget-spent, parse-failed or malformed-findings arm, none of
          which establishes a reviewed head;
        - the live head SHA differs from the SHA that converged verdict
          recorded;
        - the live `gh pr view` lookup failed;
        - the lookup returned no `headRefOid`.

        The run records that this PR was recovered via the label fallback,
        not a marker (FR-014, unchanged), and that step resolved to
        `review` because the head moved or no converged head was
        resolvable — FR-011.

      - `head_moved_since_last_review == False` (the newest review verdict
        for this PR is a converged one, and the PR's live `headRefOid` is
        exactly the head SHA it recorded) -> step = "readiness". The run
        records the same FR-014 fallback-recovery fact, plus that step
        resolved to `readiness` because the head had not moved since the
        last converged review — FR-011.
```

Clauses 0, 1, 3, and 4 of `resume-recovery.md` are unchanged: none of them
reach `pr_from_fallback`, so nothing about the awaiting-merge hold, the
marker-named-PR clause, the branch-only `fix` clause, or the empty-marker
`triage` clause is touched by this feature.

## FR-007's "undisposed" precondition

This clause is only ever evaluated for an issue `select()` chose, which is
always open (`board_eligibility.select()`/`in_flight_candidate()` both
operate over `open_issues`). An issue spec 108 later disposes of (closes as
a duplicate of its filed `spec-request`) is excluded from ever reaching this
clause by that same open-issue scoping — no additional check is added here
for FR-007 (research.md D7).

## FR-008 (no second branch/PR)

Unaffected: whichever of `review`/`readiness`/`breach` clause 2 resolves to,
none of them are `triage`, so none of them can reach the branch-cutting or
PR-opening code paths. This is true both before and after this feature's
change — FR-008 is a restated invariant of the existing clause structure,
not new behavior.

## Acceptance mapping

| Spec scenario | This contract's clause |
|---|---|
| US3 AS1 (stalled by review's spent budget, PR open, human push since last review) | clause 2b, head moved → `review` |
| US3 AS1b (stalled by review's spent budget, PR open, head unchanged) | clause 2b → `review` with a fresh round budget, never `readiness` (a budget-spent verdict establishes no reviewed head) |
| US3 AS2 (PR open, newest review verdict converged, head SHA unchanged since it) | clause 2b, head unmoved → `readiness` |
| US3 AS3 (stalled by triage's already-fixed hand-over, no PR ever opened) | clause 2 not reached (no PR from fallback) → falls to clause 4 → `triage` |
| US3 AS4 (any re-admitted item, own PR still open) | clause 2 never resolves to `triage`, so FR-054/FR-008 hold regardless of the 2b split |
| US3 AS5 (re-admitted at `review`, fresh round budget spent again) | clause 2b `review` branch + research.md D4's round-0 restart |
| FR-006b edge case (no converged verdict is the newest — including budget-spent/parse-failed/malformed-findings — or the lookup failed) | clause 2b defaults to `review` |
| FR-006a (label-less stall is always deliberate) | precondition of this whole clause — see resume-recovery.md's "Marker source" section and FR-001/FR-002 |
