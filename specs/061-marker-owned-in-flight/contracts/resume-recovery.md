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

## Marker source (#555)

The marker is read with `read_marker(comments, bot_login)` from a comments
fetch that projects `user: {login, type}`; only the loop's own App
comments count (spec 057 board-item-marker.md "Author rule"). A failed
fetch fails the resume step with an `::error::` annotation (#557). It is
not treated as "no marker", which would fall back to live-state recovery
and could restart the item at triage. The failed select job then skips
every later job.

## Branch recovery

`git ls-remote --exit-code --heads origin <marker's branch>` — if the
marker names no branch, or the named branch no longer exists, `branch` is
empty. Unchanged from spec 057.

#555: a re-derived branch is adopted only when it is named
`fix/<issue>-<slug>` for this issue, the name the fix job cuts
(`board_item_marker.is_loop_branch()`). Otherwise the marker is foreign
(see "Foreign marker fields" below).

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

#564: only "not found" keeps the meanings above (a step-1 HTTP 404, or
`git ls-remote` exit 2 for the branch); any other step-1 error, any
step-2 search error, or any other ls-remote exit fails the resume step
with an `::error::` annotation, as a failed comments fetch does.

#555: the step-1 lookup fetches the PR once and also computes whether it
carries `board:owned` and its head repository is this repository. A
marker-named PR that fails this is not adopted, and the step-2 fallback
is not taken in its place (the marker named a real PR).

## Foreign marker fields (#555)

A marker branch that fails the naming check, or a marker PR that fails
the ownership check, makes the marker stale. Clause 0 below still applies
first (the awaiting-merge hold adopts nothing, and the PR is not passed
on). Then, when the marker's PR fails the ownership check but resolves
OPEN (e.g. a maintainer removed `board:owned`), the step is the no-op
`awaiting-merge` with a note and pr, pr-state, branch, round and base-sha
cleared: triage could cut a second branch/PR beside that open PR
(FR-054). select does not choose such an item while the PR stays open
(in-flight-detection.md `UNOWNED_OPEN_PR_STATE`), so this hold is reached
only on a race. Otherwise (a foreign branch, or a foreign PR that is
CLOSED or MERGED) the step is `triage`, with the reason recorded and the
same fields cleared (FR-022). This check runs before clauses 1-4.

## Step resolution (FR-008/FR-009/FR-014 — replaces "force triage when
branch and pr are both empty")

Priority by strongest live signal (research.md D5) — each clause below
fires only when the ones above it don't apply:

```text
0. (#532) The marker's step is awaiting-merge (readiness reported the PR
   ready and handed it to a human), and its pr either resolves OPEN or
   does not resolve at all
     -> step = "awaiting-merge", a step no job consumes: a no-op run.
   select() never picks such an item while its PR may be open, so this
   is reached only by a race or a failed lookup here. It must never run
   fix/review/readiness (re-posting the report, or re-reviewing a PR a
   human now owns). It must never take clause 2's board:owned fallback,
   which would adopt that same PR as step "review". It must never take
   triage, which would cut a second branch/PR beside the open one. An
   awaiting-merge marker whose pr resolves CLOSED or MERGED skips this
   clause and falls to clause 1's disqualification and clause 4's triage,
   with the same FR-022 clearing as any other stale fix-or-later marker.

0.5a. (specs/093-not-ready-board-release FR-008/D7) The marker's step is
   stalled, it carries both pr and nr_head_sha (this feature's own
   not-ready handover, never any other stall site's marker, which keeps
   pr: null), and its pr resolves OPEN
     -> step = "readiness" when `head_moved_since_last_review(pr_number,
        comments, bot_login)` (`board_item_marker.py`, the one shared
        determination, same as clause 2b) is False -- the head matches the
        last converged review, so do not re-review; step = "review"
        otherwise (a moved or unresolvable head), the same outcome clause 2
        already produces for every other stalled marker. nr_head_sha is
        not compared here.
   A stalled marker lacking either field is unaffected and falls through
   unchanged to clause 2 below. A handover whose pr has since been merged
   goes to prove like any merged fix (spec 096); one closed falls to
   clause 4's triage, with the pr cleared like the rest of the abandoned
   attempt (FR-022).

0.5b. (specs/093-not-ready-board-release FR-001/FR-007/D3) The marker's
   step is readiness, its pr resolves OPEN, and it carries a not-ready
   record of either class (contracts/not-ready-hold.md) whose head SHA differs
   from the pr's current head (`board_eligibility.not_ready_head_moved()`,
   the hold's own module, never an inline comparison -- FR-003)
     -> step = "review", never "readiness" -- the held item is
        automatically re-admitted the moment its head moves, at review
        (a human's new commits have not been through an independent
        review), continuing rather than resetting the round and not-ready
        count clause 1 below would otherwise carry through unchanged. A
        self-clearing record is never held, but its moved head needs the
        same review (SC-010). A readiness marker with no not-ready record,
        or one whose head is unchanged, is unaffected and falls
        through to clause 1, which resolves step = "readiness" there (the
        hold itself, contracts/not-ready-hold.md, keeps such an item off
        select()'s candidate list in the first place).

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
   board:owned pr citing this issue:

   a. (#530) The marker's step is breach (a post-push breach whose
      spec-request is not yet filed)
        -> step = "breach", unconditional -- the review/readiness split
           below never applies to a breach marker. A PR the size check
           rejected is never reviewed, whichever lookup found it.

   b. Otherwise (spec 100 FR-006/FR-006a/FR-006b -- a label-removed
      stalled item always reaches this clause, since every stall site's
      marker is pr=None -- except spec 093's not-ready handover, which
      clause 0.5a resolves first): compute `head_moved_since_last_review(pr_number,
      comments, bot_login)` (`board_item_marker.py`) -- whether the PR's
      live head SHA differs from the SHA the loop's own most recent
      *converged* review-round verdict comment recorded for that PR.
      Only the converged wording counts: a budget-spent verdict means
      review never finished clearing the PR's findings, so (maintainer
      review of #885) it must never be treated as a baseline a later,
      unmoved head could satisfy -- it is excluded exactly like the
      inconclusive parse-failed/malformed-findings wording, both of which
      count as no verdict at all:

      - `True` (moved -- including when no converged head is resolvable
        at all: no review ever covered this PR, the stall came from
        review's budget-spent, parse-failed, or malformed-findings arm,
        or the live lookup itself failed) -> step = "review", with a
        fresh round budget (matches contracts/fix-step.md's own guard
        language: "resumes at whatever step the existing PR's state
        implies"). A re-admitted item resuming at review starts with
        `round == 0`, the same starting value a freshly selected item
        gets, because every stall site's marker call omits `--round`.

      - `False` (a converged head was established, and the PR's live
        head SHA is that same commit) -> step = "readiness", so nothing
        already reviewed is re-reviewed.

      Either way, the run records that this pr was recovered via the
      label fallback, not a marker (FR-014), and additionally which of
      review/readiness was resolved and why (FR-011).

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
0 (to hold an awaiting-merge handover, never to act on it) and clause
1, and in clause 1 only once a live pr lookup has confirmed the marker is current —
live state, not the marker's say-so, decides which clause applies.

## Acceptance mapping

| Spec scenario | This contract's clause |
|---|---|
| US2 AS1 (marker + live branch + live PR) | step-resolution clause 1 (fix-or-later, PR OPEN) → marker's own step |
| US2 AS2 (no marker, no board:owned PR) | PR recovery finds nothing, no branch either → step-resolution clause 4 → triage |
| US2 AS3 (no marker, board:owned PR citing issue) | PR recovery step 2 → step-resolution clause 2b → review or readiness (`head_moved_since_last_review`, spec 100 FR-006b), FR-014 recorded |
| US2 AS4 (marker's branch and PR both gone) | branch empty, PR recovery finds nothing (marker PR 404s, no board:owned match) → step-resolution clause 4 → triage |
| US2 AS5 (marker fix-or-later, PR closed/merged) | clause 1 does not match (PR not OPEN) → clause 4, reason recorded → triage |
| US2 AS6 (step never empty) | every clause above ends in a named step |
| #532 (awaiting-merge, PR open or unresolved) | clause 0 → awaiting-merge, no job runs |
| #532 (awaiting-merge, PR closed/merged, issue open) | clause 1 does not match → clause 4, reason recorded → triage |
| #530 (breach, PR open: post-push breach whose spec-request create failed) | clause 1 → breach (readiness retries the spec-request, no review); only the fallback finds the PR → clause 2a → breach; PR closed/merged → clause 4 → triage |
| #555 (marker branch not `fix/<issue>-<slug>`, or marker PR not board:owned / from another repository) | foreign marker fields → triage, reason recorded, FR-022 cleared; a foreign PR still OPEN, or an awaiting-merge marker: no-op hold, nothing passed on |
| spec 100 US3 AS1 (stalled by review's spent budget, PR open, human push since last converged review) | clause 2b, head moved → `review` |
| spec 100 US3 AS1b (stalled by review's spent budget, PR open, head unchanged since the budget was spent) | clause 2b always resolves a budget-spent verdict to `review` with a fresh round budget, never `readiness` -- a spent budget never finished clearing the PR's findings (FR-006b/SC-004, maintainer review of #885) |
| spec 100 US3 AS2 (PR open, newest review verdict converged, head SHA unchanged since it) | clause 2b, head unmoved since the converged verdict → `readiness` |
| spec 100 US3 AS3 (stalled by triage's already-fixed hand-over, no PR ever opened) | clause 2 not reached (no PR from fallback) → falls to clause 4 → `triage` |
| spec 100 US3 AS4 (any re-admitted item, own PR still open) | clause 2 never resolves to `triage`, so FR-054/FR-008 hold regardless of the 2b split |
| spec 100 US3 AS5 (re-admitted at `review`, fresh round budget spent again) | clause 2b `review` branch + a fresh round-0 restart |
| spec 100 FR-006b edge case (no reviewed head resolvable) | clause 2b defaults to `review` |
| spec 100 FR-006a (label-less stall is always deliberate) | precondition of this whole clause -- see "Marker source" above and FR-001/FR-002 |
| specs/093-not-ready-board-release US2 AS3 (this feature's own stalled handover marker, board:stalled removed, head unchanged) | clause 0.5a → readiness |
| specs/093-not-ready-board-release US3 AS1-AS4 (readiness marker, durable not-ready record, head moved) | clause 0.5b → review, round/nr_count carried through unchanged |
| specs/093-not-ready-board-release SC-010 (readiness marker, self-clearing not-ready record, head moved) | clause 0.5b → review |
| specs/093-not-ready-board-release handover marker, its PR merged / closed since | prove / clause 4 → `triage`, pr cleared |
