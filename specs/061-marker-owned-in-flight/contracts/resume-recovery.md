# Contract: Resume Recovery (Branch, PR, Step)

Extends `specs/057-autonomous-board-loop/contracts/board-item-marker.md`'s
"Read (resume)" section — read that first. This document states the delta:
how resume recovers a PR when the marker is missing/stale (FR-007), and how
it resolves `step` in every case (FR-006/FR-008/FR-009/FR-014).

This is `board-loop.yml`'s `resume` step's own logic (inside the `select`
job) — not part of `board_eligibility.py`'s in-flight decision
([in-flight-detection.md](./in-flight-detection.md)), which answers a
different question ("which issue") from this one ("what step is the
already-selected issue at").

## Branch recovery (unchanged)

`git ls-remote --exit-code --heads origin <marker's branch>` — if the
marker names no branch, or the named branch no longer exists, `branch` is
empty. Unchanged from spec 057.

## PR recovery (FR-006/FR-007 — replaces the repository-wide body search)

```text
1. If the (validated per in-flight-detection.md's FIX_OR_LATER_STEPS rule,
   where applicable) marker names a pr number:
     gh api repos/:owner/:repo/pulls/:number --jq '{number, state}'
   -- a direct lookup by number, never a search. If this 404s (deleted/
   inaccessible), treat as "not found" and continue to step 2.
2. Else (no marker, or marker names no pr):
     gh api repos/:owner/:repo/issues -X GET --paginate \
       -f state=open -f labels=board:owned --jq '{number, body}' \
     | filter in code: body matches /(?:Fixes|fixes) #<issue_number>\b/
   -- at most the small set of currently-open loop-owned PRs; the citation
   check is what stops an unrelated loop-owned PR (there should never be
   more than one, but this is what makes that structural) from being
   adopted for the wrong issue. The first (only expected) match's number
   and state are used; FR-014 requires the run to record that this PR was
   recovered via the label fallback, not from a marker.
3. Else: no PR is recovered. pr/pr-state stay empty.
```

`state` is GitHub's own value: `OPEN`, `CLOSED`, or `MERGED`.

## Step resolution (FR-008/FR-009/FR-014 — replaces "force triage when
branch and pr are both empty")

Priority by strongest live signal (research.md D5) — each clause below
fires only when the ones above it don't apply:

```text
1. The marker names a pr number, and it resolves (pre-fix: no pr required;
   fix-or-later: the resolved pr's state == OPEN)
     -> step = the marker's own step.
   (A fix-or-later marker whose pr's state != OPEN does NOT match this
   clause -- it falls through to clause 4, WITH the reason recorded,
   FR-009: "stale marker -- recorded pr <n> is <state>, not open". This
   disqualification also clears branch/round/base-sha, not just pr/
   pr-state (FR-022): they describe the same abandoned attempt as the
   disqualified pr, so leaking them would resume the fix job on an
   abandoned branch or start review partway through a stale round
   budget instead of 0.)

2. No marker-named pr resolved, but the FR-007 fallback recovers an open
   board:owned pr citing this issue
     -> step = "review" (matches contracts/fix-step.md's own guard
        language: "resumes at whatever step the existing PR's state
        implies"), and the run records that this pr was recovered via the
        label fallback, not a marker (FR-014).

3. No pr resolved by clause 1 or 2, but a branch is re-derived
   (`git ls-remote` finds it)
     -> step = "fix" -- this is the case board-loop.yml's fix job `if:`
        already expects (`needs.select.outputs.step == 'fix' && branch !=
        '' && pr == ''`) but which today's resume logic can never produce
        (see research.md D5).

4. Neither a pr nor a branch resolved (covers: no marker; a marker naming
   triage/route with nothing cut yet -- branch/pr are never present that
   early, so this is the ordinary shape of a pre-fix interruption; a
   disqualified fix-or-later marker from clause 1; an unparsable marker)
     -> step = "triage", and, whenever a marker was present but
        disqualified rather than simply absent, the run records why
        (FR-009). branch is already empty by construction here (clause 3
        would have matched otherwise); when the reason is recorded,
        round/base-sha are cleared too (FR-022), for the same reason as
        clause 1 -- they belong to the same disqualified attempt.
```

`step` is never left empty (FR-008) — every branch above ends in one of the
loop's named steps. The marker's own step name is consulted only in clause
1, and only once a live pr lookup has confirmed the marker is current —
live state, not the marker's say-so, decides which clause applies.

## Acceptance mapping

| Spec scenario | This contract's clause |
|---|---|
| US2 AS1 (marker + live branch + live PR) | step-resolution clause 1 (fix-or-later, PR OPEN) → marker's own step |
| US2 AS2 (no marker, no board:owned PR) | PR recovery finds nothing, no branch either → step-resolution clause 4 → triage |
| US2 AS3 (no marker, board:owned PR citing issue) | PR recovery step 2 → step-resolution clause 2 → review, FR-014 recorded |
| US2 AS4 (marker's branch and PR both gone) | branch empty, PR recovery finds nothing (marker PR 404s, no board:owned match) → step-resolution clause 4 → triage |
| US2 AS5 (marker fix-or-later, PR closed/merged) | clause 1 does not match (PR not OPEN) → clause 4, reason recorded → triage |
| US2 AS6 (step never empty) | every clause above ends in a named step |
