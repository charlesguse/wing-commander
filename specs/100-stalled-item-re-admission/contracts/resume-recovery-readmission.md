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

      - `head_moved_since_last_review == True` (including: no reviewed
        head could be established — no review ever covered this PR, or the
        stall came from review's parse-failed or malformed-findings arm, or
        the lookup itself failed) -> step = "review". The run records that
        this pr was recovered via the label fallback, not a marker
        (FR-014, unchanged), and additionally that step resolved to
        `review` because the head moved (or because no reviewed head was
        resolvable) — FR-011.

      - `head_moved_since_last_review == False` (a reviewed head was
        established, and the PR's live head commit is the same one, or no
        newer) -> step = "readiness". The run records the same FR-014
        fallback-recovery fact, plus that step resolved to `readiness`
        because the head had not moved since the last review — FR-011.
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
| US3 AS2 (stalled at readiness or by review's spent budget, PR open, head unchanged since last review) | clause 2b, head unmoved → `readiness` |
| US3 AS3 (stalled by triage's already-fixed hand-over, no PR ever opened) | clause 2 not reached (no PR from fallback) → falls to clause 4 → `triage` |
| US3 AS4 (any re-admitted item, own PR still open) | clause 2 never resolves to `triage`, so FR-054/FR-008 hold regardless of the 2b split |
| US3 AS5 (re-admitted at `review`, fresh round budget spent again) | clause 2b `review` branch + research.md D4's round-0 restart |
| FR-006b edge case (no reviewed head resolvable) | clause 2b defaults to `review` |
| FR-006a (label-less stall is always deliberate) | precondition of this whole clause — see resume-recovery.md's "Marker source" section and FR-001/FR-002 |
