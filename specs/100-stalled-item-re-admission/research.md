# Research: A Stall Holds Until a Maintainer Re-Admits It

**Input**: `specs/100-stalled-item-re-admission/spec.md` (Clarifications already
resolved on lifecycle issue #752 — Q1/Q2/Q3 answered, no
`[NEEDS CLARIFICATION]` marker remains in the spec). This document resolves
the remaining *technical* unknowns Phase 0 needs before Phase 1 design: how
each functional requirement is realized in `board-loop.yml` and its scripts,
given the actual state of `main` as of 2026-09-30.

## D1 — What FR-001–FR-005 and FR-012–FR-015 mean for this plan

**Decision**: Treat FR-001–FR-005 (label-before-marker, every stall site) and
FR-012–FR-015 (readiness's per-write stand-down gating) as **already-built
invariants** to preserve and gate, not as work items. #782 (`aaaa1405`) landed
both. Verified directly against current `main`:

- Every one of the eight stall sites (`board-loop.yml:1427` triage,
  `1906` route, `2263`/`2467` fix, `3306`/`3311`/`3319` review, `3913`
  readiness) calls `board_item_marker.py --step stalled --issue <n>
  --add-label board:stalled`, which is `add_stalled_label()` followed by
  `write_marker()` — label first, marker second, loud failure otherwise
  (`board_item_marker.py:170-213`).
- Readiness's durable steps (ready report, not-ready comment, breach-retry
  lookup, `spec-request` create, cross-link) are each gated
  `if: steps.killswitch-recheck.outputs.paused == 'false'`
  (`board-loop.yml:3696-3934`), with the stand-down record-only step gated
  the complementary way. This is named **Gate 97**
  (`verify-board-loop-resume-gating.py`) at `board-loop.yml:3698`.

**Rationale**: Re-verifying and re-deriving this (rather than re-reading it
as new work) matches the spec's own "Owner scope note" and keeps this
feature's diff scoped to what FR-006 through FR-011 actually add: the
re-admission rule, its shared reviewed-head determination, and the run
summary records.

**Alternatives considered**: Re-stating FR-001-005/FR-012-015 as fresh tasks
with fresh tests was rejected — it would duplicate Gate 97's existing
fixture coverage and violate CLAUDE.md's "shared logic has exactly one
home" by inventing a second check for something already checked.

## D2 — Where the re-admission rule (FR-006) lives in code

**Decision**: The rule is encoded in the resume step-resolution's clause 2
(the `board:owned` fallback), which today (as of `main`) reads, inline in
the `select` job's `resume` step Python (`board-loop.yml:811-814`):

```python
elif pr_from_fallback:
    step = BREACH_STEP if marker_step == BREACH_STEP else "review"
```

and is documented in `specs/061-marker-owned-in-flight/contracts/
resume-recovery.md`'s "Step resolution" clause 2. FR-006 changes this one
`elif` to a three-way split:

```python
elif pr_from_fallback:
    if marker_step == BREACH_STEP:
        step = BREACH_STEP
    elif head_moved_since_last_review:
        step = "review"
    else:
        step = "readiness"
```

`head_moved_since_last_review` is computed once, upstream of this clause,
by the shared determination (D3), and is `True` (never `readiness`) when no
reviewed head can be established (FR-006b's safe default). The `breach`
carve-out (#530) is unconditional and untouched — a breach marker never
takes the review/readiness split.

**Rationale**: This is the smallest change that preserves every other
clause's behavior (clauses 0, 1, 3, 4 are untouched — none of them reach
`pr_from_fallback`), matches the spec's own framing ("the resume fallback's
clause order" is exactly what FR-006 makes an explicit, gated rule instead
of an emergent one), and is the one place `resume-recovery.md` already
names as the contract for this decision.

**Alternatives considered**: Resolving the split inside `board_eligibility.py`
(e.g., a new `resolve_readmission_step()` function consumed by the heredoc)
was considered and preferred for the *reviewed-head determination* itself
(D3), but not for the three-way branch, which is a one-clause change to
existing inline logic with no reuse pressure from elsewhere — pulling it
into a module would add an import for a three-line `if` with no second
caller.

## D3 — The shared "has the head moved since the last review" determination (FR-006b)

This is the one substantive open design question Phase 0 must settle. Spec
093 (`specs/093-not-ready-board-release`) FR-007 names the same determination
as one this feature and that one both consume, but **spec 093 is at
`spec-meta.json` `"stage": "spec"`, `"spec_branch": null` — its own plan
stage has not run, and no code implementing FR-007 exists on `main` today**.
Spec 100's own "Status update" section describes specs 092/093/108 as
"merged," which as verified below is inaccurate (D_finding); regardless of
that framing, the practical consequence for this plan is unchanged: nothing
exists yet for this feature to reuse, so **this feature is the one that
builds the shared determination**, exactly as spec 100's own text anticipates
("built once, here, and spec 093 consumes them").

**What already exists to build on**: the board-item marker schema
(`step, round, pr, branch, base_sha` — `board_item_marker.py:139`) records no
head SHA, and FR-019/FR-006b forbid extending it. Readiness's own snapshot
(`board-loop.yml:3736`) fetches `headRefOid` fresh, but only at readiness
time, not as a durable record. Review's *converged* round-outcome comment
names the PR and the head SHA it converged on directly in its body ("Review
round N converged ... PR #P (head <sha>)"); the inconclusive arms
(parse-failed, malformed-findings, budget-spent) share the same generic
"Review round N on PR #P" prefix but name no verdict and no head. No
`gh pr review` (formal GitHub review, which would carry a `commitId`) is
ever posted — every round's verdict is an ordinary issue comment.

**Decision**: Determine "has the head moved since the last review" from live
state only, with no new durable record and no marker extension:

1. Find the loop's own most recent **converged** review-round verdict
   comment on the issue that names `pr_number` and a head SHA (matched by a
   pattern on the converged comment's own fixed wording — never the
   budget-spent or other inconclusive wording, which names no SHA at all).
2. If no such comment is found, resolve to `review` (FR-006b's safe
   default) without making a live call at all — this covers a stall reached
   before any review, and every inconclusive review arm including
   budget-spent: a spent budget never finished clearing the PR's findings,
   so it must never be treated as a baseline a later, unmoved head could
   satisfy (maintainer review of #885 — an earlier version of this
   determination compared a commit timestamp to the inconclusive comment's
   own `created_at`, which let a budget-spent stall with an unmoved head
   resolve to `readiness` with findings still open, breaking FR-006b/
   SC-004).
3. Otherwise fetch the PR's live head SHA (`gh pr view <pr> --json
   headRefOid`) and compare it directly to the SHA the converged comment
   recorded. Equal SHAs mean the head has **not** moved (`readiness`); any
   difference, or a failed/unparsable lookup, means moved (`review`, the
   safe default).

This determination is implemented once, as a function taking the resume
step's own already-fetched flat comments array and the bot's login, making
its own live `gh pr view` call only when a converged verdict comment is
found. Because it depends only on data the `select`/resume step already has
access to, spec 093 — when it plans — reuses the same function rather than
re-deriving the same read.

**Rationale**: This satisfies FR-006b's exact wording ("from live state or
an existing record, without extending the stall marker") using data that
already exists on `main` — the converged comment's own recorded head SHA,
compared against a live, authoritative head-SHA lookup rather than an
inferred timestamp ordering. It requires no new marker field, no new
comment convention and no `gh pr review` migration, and it cannot
mistake an inconclusive verdict for a baseline the way a timestamp
comparison could.

**Alternatives considered**:
- *Compare the head commit's timestamp against the matched comment's
  `created_at`* — this was the original design and was built, then
  reverted by maintainer review of #885: a commit authored before the
  verdict but pushed after it (or a push landing mid-run) could resolve to
  "not moved" even though the live head was never reviewed, and extending
  the same timestamp match to the inconclusive review arms (to avoid a
  second, differently-shaped lookup) let a budget-spent stall with an
  unmoved head resolve to `readiness` with findings still open. Comparing
  SHAs directly, sourced only from a converged comment's own recorded head,
  removes both failure modes.
- *Embed a head SHA in a new, non-marker HTML comment tag on each review
  round's comment* — rejected as unnecessary: the converged comment's own
  existing wording already names the head SHA in plain text, so no new
  record shape is needed, and CLAUDE.md's "shared logic has exactly one
  home" cautions against a second small format when live state suffices.
- *Post real GitHub PR reviews (`gh pr review`) instead of issue comments,
  so `commitId` is available directly* — rejected as out of scope: it
  changes review's posting mechanism repository-wide for every arm
  (converged and stalled alike), which is a larger behavior change than
  this feature's narrow re-admission question, and touches
  `review-and-findings.md`'s contract far beyond FR-006's scope.
- *Compare `base_sha` recorded on the last non-stalled marker* — rejected:
  `base_sha` is the diff base for the size-and-path backstop, not the head
  under review, and no stall site records it for the stall marker itself
  (FR-019 keeps the schema as-is).

## D4 — FR-009: the re-admitted item's budget is already a fresh one, by construction

**Decision**: State and gate today's already-correct behavior rather than
change it. Every stall site's `stalled` marker call passes no `--round`
(confirmed at all eight sites), so `write_marker()` always records
`round: 0` for a stall. Resume clause 2 (`pr_from_fallback`) does not carry
a round value forward from the stalled marker — the `select` job's own
round output derives from the (now label-less) `stalled` marker's `round`
field, which is `0`. Review's own round-outcome step reads
`steps.pr.outputs.round` (`board-loop.yml:2603-2608`, sourced from
`needs.select.outputs.round`), so a re-admitted item that resumes at
`review` starts at round 0 — a full fresh budget — without any code change.

**Rationale**: This is exactly the "one full round budget, the same as a
newly selected item" FR-009/SC-006 ask for, already true today. The work
this feature adds is: (a) a checked-in fixture proving it (SC-006 — "a
checked-in case shows the item stalling again once it is spent" after
re-admission), and (b) FR-011's run-summary line naming the fresh budget
explicitly, so the behavior is stated rather than left to be inferred from
the fact that stall markers happen to omit `--round`.

**Alternatives considered**: None — changing the round-reset mechanism
itself would be new behavior beyond what Q2's answer authorizes ("today's
behaviour... stated and gated").

## D5 — FR-010: no additional agent invocation on an FR-002 retry

**Decision**: Confirm and gate as an invariant, not new work. FR-002's loud
failure happens *before* any agent step in every stall site — the label-add
call is the first durable action attempted once the job has already decided
to stall (post-agent, in review's case; pre-agent, in triage/route/fix's
gate-red case). A retry re-enters the job, which re-derives the stall
decision from the marker's already-recorded state (the previous run's
non-`stalled` marker, e.g. still `review` with the spent round) before any
agent runs again — this is what the existing round-outcome / route-verdict /
gate-suite steps already do on every run, retry or not. No new mechanism is
needed; FR-010 is a property to check (a fixture asserting the retry path's
job graph reaches the label-add call without an intervening agent step),
not a behavior to build.

**Rationale**: Matches the spec's own edge case ("the retry must reach the
stall decision without spending another agent invocation") as a statement
about existing control flow, consistent with D1's framing of FR-001-005 as
invariants.

## D6 — FR-011: run summary records for re-admission, retries, and stand-downs

**Decision**: Extend the existing `GITHUB_STEP_SUMMARY` writing pattern
readiness's stand-down already uses (#782) to two more sites: the `select`
job's resume step (when clause 2's split fires, name which of `review` /
`readiness` / `triage` resolved and why — head moved, head unmoved, or no
open PR), and each stall site's retry path (when FR-002's loud failure is
followed by a later successful retry, name that this is a retry of a
previously failed label-add). This reuses the same summary-writing
mechanism (`echo ... >> "$GITHUB_STEP_SUMMARY"`) already present for
readiness's stand-down record, rather than inventing a second one.

**Rationale**: CLAUDE.md's "shared logic has exactly one home" — one
summary-writing idiom, three call sites, not three formats.

**Alternatives considered**: A separate structured summary file (JSON)
consumed by a later step was rejected as unnecessary machinery for
human-readable narration; the existing plain-text summary lines already
serve every other invariant this loop records (readiness's stand-down,
FR-014 of resume-recovery.md's "recovered via the label fallback").

## D7 — FR-007's "undisposed" carve-out needs no new code

**Decision**: No code change. `board_eligibility.select()` and
`in_flight_candidate()` both operate over `open_issues` only
(`board_eligibility.py:145` treats a `CLOSED` issue as excluded; the
`select` job's own issue fetch is scoped to open issues,
`board-loop.yml:356`). Spec 108's disposition (closing the originating issue
as a duplicate of its filed `spec-request`) is not implemented on `main`
today (`specs/108-routed-original-disposition/spec-meta.json`:
`"stage": "spec"`, and `board-loop.yml` has no code that closes an
originating issue — confirmed by grep). Consequently:

- Today, no stalled issue is ever "disposed" in spec 108's sense, so FR-007's
  carve-out is vacuously satisfied — every open, labeled-`stalled` issue is
  "undisposed" by definition until spec 108 lands.
- Once spec 108 lands (closing the originating issue on filing), a disposed
  issue is *closed*, and the board loop's selection already excludes closed
  issues structurally. FR-006's rule only ever runs against an issue
  `select()` chose, which is always open. No additional exclusion check is
  needed in this feature for FR-007 to hold both before and after spec 108
  ships.

**Rationale**: This is the simplest reading consistent with "shared logic
has exactly one home" — the exclusion already lives in one place
(`open_issues` scoping), and duplicating it here as a second, redundant
"is this disposed" check would be exactly the kind of second mechanism
FR-020/FR-018 warn against.

**Note for the record (not this feature's task to fix)**: this feature's own
spec.md states, in its 2026-09-30 status update, that specs 092/093/108 are
"merged," and describes their FRs in present tense as already-landed
behavior. Their `spec-meta.json` files each show `"stage": "spec"` with
`spec_branch: null` — the same stage a spec sits at once its own spec.md PR
has merged to `main`, well before that feature's plan/tasks/implementation
stages have run (contrast with specs 057/061, both fully implemented and at
`"stage": "review"` with a recorded `spec_branch`). "Merged" in spec 100's
text appears to mean "the spec.md document merged," not "the feature
shipped." This plan does not rely on any of specs 092/093/108's described
mechanisms existing in code (D3, D7 above confirm the two points of
apparent reliance — the reviewed-head determination and the disposed-issue
exclusion — both resolve correctly without them), but the spec's wording is
misleading to a future reader and is reported separately (see this run's
`wing-commander-findings` block).

## D8 — Gate design

**Decision**: Add one new gate script, fixture-driven in the same style as
`verify-board-loop-resume-gating.py` (Gate 97) and
`verify-board-eligibility.py`, that:

- Simulates the resume step-resolution's clause 2 split (D2) across the
  fixture matrix SC-005 implies: open owned PR + head moved → `review`;
  open owned PR + head unmoved → `readiness`; open owned PR + no reviewed
  head resolvable → `review` (FR-006b default); no open PR → `triage`;
  `breach` marker → `breach` regardless (#530 carve-out preserved).
- Exercises FR-006's own failure mode: reverting clause 2 to the
  unconditional `"review"` it is today must fail this gate (mirrors
  Constitution VIII/FR-005's existing style for the stall-site check).
- Asserts FR-009's budget-reset property (D4) with a case that spends a
  fresh budget after re-admission and stalls again.
- Is registered in `lint-workflows.yml` per `gates.md`'s existing
  convention (a `Gate N — <description>` step name; the exact number is
  assigned at registration time, per `wc_gate_registry.py`'s convention
  that gate numbers are informal labels, not a maintained list).

**Rationale**: Gate 97 checks resume *reachability* (job graph gating);
this is a distinct concern (resume *step resolution correctness*), so a new
gate rather than folding into Gate 97 keeps each gate's subject singular
(Constitution VIII: "a gate that cannot fail its own subject...").

**Alternatives considered**: Extending `verify-board-loop-resume-gating.py`
itself was considered and rejected — its docstring and existing checks are
scoped to job-level `if:` reachability, not clause-level step-resolution
correctness; conflating the two would make one gate's failure ambiguous
about which property broke.

## Summary of NEEDS CLARIFICATION status

None remain. All three of the spec's own clarification questions (Q1/Q2/Q3)
were resolved by the owner on issue #752 before this plan ran. This
document resolves the plan-level technical unknowns Phase 0 is responsible
for (D1-D8); none required a new round of clarification with the owner.
