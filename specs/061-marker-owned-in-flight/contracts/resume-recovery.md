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

```text
step = the marker's own step, IF:
  - the step is pre-fix (triage, route), OR
  - the step is fix-or-later AND the recovered pr's state == OPEN
  EXCEPT: step == "route" with no re-derived branch and no recovered pr
    still collapses to "triage" (unchanged pre-existing behavior -- see
    board-loop.yml's own comment at the triage job's marker-write step;
    route is stateless and cheap to redo, so an item interrupted between
    triage and route resumes by re-running triage, not by a dedicated
    "resume at route" path).
  step == fix-or-later AND recovered pr's state != OPEN:
    -> falls through to the "no usable marker" rules below, WITH the
       reason recorded (FR-009: "stale marker -- recorded pr <n> is
       <state>, not open").

no usable marker (missing, unparsable, or just fell through above):
  - a branch is re-derived and no pr is recovered -> step = "fix"
    (this is the case board-loop.yml's fix job `if:` already expects --
    `needs.select.outputs.step == 'fix' && branch != '' && pr == ''` --
    but which today's resume logic can never produce; see research.md D5)
  - a pr is recovered (marker-named or FR-007 fallback) and its state is
    OPEN -> step = "review" (matches contracts/fix-step.md's own guard
    language: "resumes at whatever step the existing PR's state implies")
  - neither -> step = "triage", and the run records that this item's
    prior state could not be recovered and why (FR-009) -- e.g. "no
    marker and no board:owned PR citing this issue" or "marker's step was
    X but its recorded PR is Y".
```

`step` is never left empty (FR-008) — every branch above ends in one of the
loop's named steps.

## Acceptance mapping

| Spec scenario | This contract's clause |
|---|---|
| US2 AS1 (marker + live branch + live PR) | step = marker's step (fix-or-later, PR OPEN) |
| US2 AS2 (no marker, no board:owned PR) | step = triage, "no usable marker" branch |
| US2 AS3 (no marker, board:owned PR citing issue) | PR recovery step 2, step = review, FR-014 recorded |
| US2 AS4 (marker's branch and PR both gone) | branch empty, PR recovery finds nothing (marker PR 404s, no board:owned match) → step = triage |
| US2 AS5 (marker fix-or-later, PR closed/merged) | "falls through... WITH the reason recorded" clause → step = triage |
| US2 AS6 (step never empty) | every branch above ends in a named step |
