# Research: The Loop Recognizes Its Own Work

**Feature**: specs/061-marker-owned-in-flight | **Spec**: [spec.md](./spec.md)

This feature has no open `[NEEDS CLARIFICATION]` markers in spec.md — both
questions the spec author would otherwise have needed a decision on were
already resolved in spec.md's own Clarifications section (2026-09-23). This
document instead records the design decisions this plan makes on top of
those answers, each traced to the requirement it serves, plus the two
implementation-detail decisions the spec deliberately left to planning (the
ownership label's literal name, and the exact shape of the extended
`board_eligibility.py` inputs).

## D1: Where the in-flight decision's code lives

**Decision**: Add the decision to `.github/scripts/board_eligibility.py`
(the module FR-011 names as the single home), as new functions
`in_flight_candidate()` and a `select()` that consults it first. No new
module, no new gate number — `verify-board-eligibility.py` (Gate 81) grows
new fixture cases and assertions for the new functions, reusing its
existing "fail loudly if a fixture file is missing" pattern.

**Rationale**: FR-011 is explicit that the rule must not be a second,
parallel definition and must reuse "that decision's existing fixture-driven
gate rather than a second harness" — i.e. Gate 81 itself, not a new Gate 90.
`board_eligibility.py` already owns `classify_issue()` and `is_excluded()`,
the two other halves of "which issue does the loop act on"; the in-flight
question is a third clause of the same decision, evaluated before the
oldest-first scan (`select()`) rather than beside it.

**Alternatives considered**: A separate `board_in_flight.py` module with its
own gate — rejected by FR-011's own text (a second harness). Leaving the
decision inline in `board-loop.yml`'s `select` job shell — rejected by
FR-011 explicitly and by this repository's single-home rule (CLAUDE.md); it
is the shape that shipped the reported defect (no fixture could exercise a
`run:` block's own conditional logic).

## D2: `board_eligibility.py`'s inputs grow, not its call sites' shape

**Decision**: `select()`'s signature grows two parameters:
`comments_by_issue: dict[int, list[dict]]` (each issue's own comments, the
`{"created_at": ..., "body": ...}` shape `board_item_marker.read_marker()`
already expects) and `pr_state_by_number: dict[int, str]` (GitHub's own PR
`state` string — `OPEN`, `CLOSED`, or `MERGED` — for exactly the PR numbers
named by a fix-or-later-step marker found in `comments_by_issue`, nothing
more). `classify_issue()` and `is_excluded()` are unchanged — the eligibility
half of the decision needs no new input.

**Rationale**: FR-011 states plainly that "the eligibility decision's inputs
accordingly grow to include each issue's own comments, where the marker
lives, alongside the issues and label events it already takes." A marker
naming a fix-or-later step additionally needs to know whether its recorded
PR is still open (FR-002's second bullet) — that is one more live fact, not
a body search, and is scoped narrowly (only PRs actually named by a
qualifying marker) rather than fetched for every open PR in the repository,
keeping the same "least data needed" shape `classify_issue`/`is_excluded`
already have.

**Alternatives considered**: Resolving PR state inside `board_eligibility.py`
itself via a live `gh` call — rejected: the module is pure (stdin JSON in,
stdout number out) so it can be fixture-tested without network access
(Constitution VIII: a gate must run the same subject locally as in CI); a
live call inside it would make every fixture run hit the network. Passing
the full PR object (title, body, author) — rejected: FR-007/FR-001 forbid
deriving anything from PR text; passing only `state` makes that structurally
impossible to regress by accident.

## D3: The `select` job's own data-gathering step changes shape, not scope

**Decision**: The `select` job's existing per-issue loop (board-loop.yml's
"Fetch open issues and select the next board item" step) already calls `gh
api .../comments` once per open issue to resolve label-actor associations
(FR-008); that same call's `--jq` projection grows a `body` field (alongside
the `login`/`association`/`created_at` it already extracts), so the same
API round-trip feeds both purposes — no second per-issue comments fetch.
After `board_eligibility.py`'s marker-scan identifies which (if any) open,
non-excluded issues carry a fix-or-later-step marker naming a PR number, a
second, narrow pass resolves exactly those PR numbers' `state` via `gh api
repos/:owner/:repo/pulls/:number --jq .state` (or `gh pr view`) — at most one
call per qualifying marker, never a repository-wide PR list or search. The
existing unrestricted `gh pr list --state open --json number,body | ...
capture("Fixes #...")` shortcut (board-loop.yml lines 248-263 at the time of
writing) is deleted outright; `board_eligibility.py`'s `select()` is the only
thing that decides which issue this run acts on (FR-001/FR-004).

**Rationale**: Reusing the existing per-issue comments call keeps this
change additive rather than doubling the job's API cost; the two-pass
"discover which markers need a PR check, then check exactly those" shape
mirrors FR-002's own "only fix-or-later needs a PR" split and keeps the new
network surface proportional to how many items plausibly qualify (in the
steady state, zero or one).

**Alternatives considered**: Fetching every open PR's state up front and
matching by number — rejected: for a repository with many ordinary open fix
PRs this is no smaller than the very repository-wide scan FR-001 forbids,
even though the *decision* would ignore all but the marker-named numbers;
narrowing the fetch itself, not just the decision, keeps the fix
tool-console-visible for review (a diff that still lists every PR is harder
to trust than one that doesn't fetch them).

## D4: Resume's PR/branch recovery — marker-named lookup, not a body search

**Decision**: Resume's existing `gh pr list --search "$ISSUE_NUMBER in:body"
--state all` call (board-loop.yml's "Resume" step) is replaced by, in order:
(1) if the (re-derived, still-valid per FR-002) marker names a PR number,
resolve that exact PR by number (`gh pr view <n> --json number,state`); (2)
otherwise, the FR-007 fallback: `gh pr list --state open --label
<ownership-label> --json number,state,body`, filtered in code to PRs whose
body matches `(?:Fixes|fixes) #<issue_number>\b` — the same citation pattern
the old shortcut used, now scoped first by label so an unrelated PR that
happens to cite the same issue number in passing prose cannot match; (3)
otherwise, nothing is adopted and resume proceeds to FR-008's triage
fallback.

**Rationale**: FR-006 requires recovering "that item's own marker," which
names a specific PR number when one exists — resolving by number is a
direct GitHub lookup, not a search, and cannot return a stranger's PR. FR-007
requires the fallback to be narrowed by the ownership label *and* citation
together; label alone would still adopt an unrelated PR that happens to
carry the label from a different, unmarked issue (impossible in practice
today since nothing but this fix step applies the label, but the citation
check is what makes that non-adoption structural rather than incidental).

**Alternatives considered**: Keeping the unrestricted `--search "N in:body"`
as the sole recovery mechanism — this is exactly FR-007's prohibition and
the mechanism that produced the observed failure. Widening the fallback to
branch-naming convention (`fix/<n>-*`) — explicitly rejected by FR-007's own
text as a signal that "does not stay in sync with the fix step by itself."

## D5: Resume's step resolution — priority by strongest live signal, never empty

**Decision**: Resume derives `step` from re-derived live state, in this
priority order (each clause fires only when the ones above it don't apply),
replacing the existing "`step=$marker_step`; force to `triage` when both
branch and pr are empty" rule outright rather than patching it:

1. A PR is resolved from the marker's own recorded number (FR-002-validated:
   pre-fix markers need no PR; fix-or-later markers need that PR's state to
   be `OPEN`): `step` is exactly the marker's own step. (US2 AS1.)
2. No marker-named PR, but the FR-007 fallback recovers an open,
   `board:owned` PR citing this issue: `step` is `review` — the state a PR
   that exists but was never marked implies, matching `contracts/fix-
   step.md`'s existing guard language ("resumes at whatever step the
   existing PR's state implies (review or readiness)"). FR-014's recording
   requirement applies. (US2 AS3.)
3. No PR resolved by either of the above, but a branch is re-derived
   (`git ls-remote` finds it): `step` is `fix` — this is the case
   `board-loop.yml`'s existing `fix` job condition (`needs.select.outputs.
   step == 'fix' && branch != '' && pr == ''`, board-loop.yml line 1072 at
   the time of writing) already anticipates but which today's resume logic
   can never actually produce (a marker still naming `route`, written by
   triage before route/fix ever ran, survives untouched if the fix job dies
   after cutting a branch but before opening a PR — under today's code this
   resolves to `route`, which no job's `if:` ever matches, silently
   stranding the item exactly the way the reported defect did, just via a
   different path; found here as a second instance of the same failure
   shape while designing this fix). Fixing this makes an existing,
   previously unreachable job condition reachable; it changes no job's
   `if:` guard.
4. Neither a PR nor a branch is resolved (covers: no marker at all; a
   marker naming `triage`/`route` with nothing cut yet — the ordinary,
   frequent shape of an item interrupted before the fix step; a marker
   naming a fix-or-later step whose PR turned out closed/merged and whose
   branch is also gone; an unparsable marker): `step` is `triage` (FR-008),
   and the run records that it did so and why (FR-009) whenever a marker
   was present but disqualified (as opposed to simply absent, which needs
   no explanation).

**Rationale**: This priority order needs no special case for any individual
step name — `triage` and `route` markers both naturally fall to clause 4
when (as they always are, by construction, before the fix step ever runs)
neither branch nor PR exists yet, exactly reproducing today's correct
"route is informational only, an interrupted pre-fix item resumes by
re-running triage" behavior (board-loop.yml's own comment at the triage
job's marker-write step) without encoding it as an exception. What actually
distinguishes each outcome is the strongest live fact available — a real PR
outranks a real branch, which outranks nothing at all — which is also why
this reads each fact in a fixed order rather than switching on the marker's
step name first: the marker's step is a claim about a run that already
happened, live state is what is actually true now, and FR-002/FR-008 both
already establish that live state wins whenever it disagrees with the
marker. FR-008 requires a named step in every case; FR-010 requires a
"selected but did nothing" run to be distinguishable from a "selected and
worked" one, which a silently-unmatched `if:` (clause 3's condition, dead
under today's code) defeats identically to an empty step string.

**Alternatives considered**: Switching on the marker's own step name first
and only falling back to live state on a miss (an earlier draft of this
decision) — rejected on review: it needed an ad hoc exception for `route`
specifically to reproduce the existing collapse-to-triage behavior, and
still produced the wrong answer for "marker says `route`, but a branch
exists because route-then-fix already ran and died mid-fix" (it kept
`step` at `route`, which is unreachable). Prioritizing live facts first
handles that case for free and generalizes without per-step exceptions.
Adding a fourth trigger condition so `step == 'route'` runs the route job
directly — rejected as unnecessary scope growth; clause 4 already handles
that case correctly (route is cheap to redo) and no acceptance scenario
asks for it to change.

## D6: The loop ownership label

**Decision**: The label is named `board:owned`, following the existing
`board:stalled` naming convention (the same `board:` prefix, distinct
suffix). It is applied by `gh pr create --label board:owned` in the same
invocation that opens the PR (FR-013) — no separate `gh pr edit --add-label`
step, so there is no window where the PR exists without it. It is documented
in `docs/setup.md`'s label table and creation script alongside
`board:stalled`, created once by a maintainer (or already present) before
first use, per the spec's own assumption that label creation cannot be a
runtime concern of the fix step.

**Rationale**: `board:` is this repository's existing prefix for the board
loop's own bookkeeping labels (`board:stalled` is the only other member);
reusing it keeps the label's provenance legible without introducing a new
prefix family for a single label. Applying it via `--label` on `pr create`
itself (rather than a follow-up `pr edit`) is what makes FR-013's
"unambiguous record even if the run dies immediately after" guarantee hold —
`gh pr create --label` sets the label as part of the same API call that
creates the PR, so a run that dies the instant after `pr create` returns
still leaves a labeled PR behind.

**Alternatives considered**: `board-loop:pr` (a new prefix) — rejected in
favor of reusing the existing `board:` family. A description-based marker
(e.g. a magic string in the PR body) instead of a label — rejected: FR-013
specifically asks for a label because it is queryable by `gh pr list
--label`, unlike a body substring, without a search API's fuzzy-matching
behavior; a label is also what `board:stalled` already establishes as this
loop's ownership-signal idiom for issues, extended here to PRs.

## D7: FR-005 tie-break — "most recently written marker"

**Decision**: `board_item_marker.py` gains a
`read_marker_with_timestamp(issue_comments)` function returning `(created_at,
marker)` for the newest well-formed marker in a comment list (or `None`) —
the same scan `read_marker()` already performs, with the winning comment's
own `created_at` returned alongside the marker rather than discarded.
`in_flight_candidate()` uses this, per issue, to compare qualifying
candidates' marker timestamps directly (ISO-8601 string comparison, the same
sort key `board_eligibility.select()`'s own oldest-first scan already uses
for `createdAt`) and returns the newest one, recording in its return value
that more than one issue qualified so the calling step can post the FR-005
summary line.

**Rationale**: `read_marker()`'s existing internal `dated_markers` list
already carries exactly this pairing before collapsing to just the marker on
return; exposing it as a second, additive function avoids changing
`read_marker()`'s existing return shape (every current call site depends on
it returning the marker alone) while reusing its exact parsing/sort logic
rather than re-implementing it.

**Alternatives considered**: Comparing by the *issue's* own `createdAt`
instead of the marker comment's `created_at` — rejected: two markers could
land on issues filed in either order; FR-005 asks for "most recently
*written*" (the marker), not "most recently *filed*" (the issue), because
the marker's timestamp is what actually reflects which item the loop most
recently touched.

## D8: `is_excluded()` still gates the in-flight candidate (FR-003)

**Decision**: `in_flight_candidate()` calls the existing `is_excluded()` on
every issue before considering its marker, exactly the way `select()`'s
oldest-first scan already does, and skips excluded issues entirely rather
than adding a second, parallel closed/stalled/label check.

**Rationale**: FR-003 is explicit that exclusion must be "the same single
decision the oldest-first scan uses — never a second, parallel exclusion
rule." No new code is needed here beyond calling the existing function from
the new code path.

## Summary of touched files

- `.github/scripts/board_eligibility.py` — `in_flight_candidate()`, `select()`
  updated to consult it first (D1/D2/D8).
- `.github/scripts/board_item_marker.py` — `read_marker_with_timestamp()`
  added (D7).
- `.github/scripts/verify-board-eligibility.py` — new fixture cases and
  assertions for `in_flight_candidate()` (FR-012), same gate/job (Gate 81).
- `.github/scripts/tests/board-eligibility/` — ten new fixture case
  directories (FR-012).
- `.github/workflows/board-loop.yml` — `select` job's data-gathering step
  (D3), the in-flight shortcut block replaced by a call into
  `board_eligibility.py` alone, `resume` step's PR/branch/step derivation
  (D4/D5), the `fix` job's `gh pr create` call gains `--label` (D6).
- `docs/setup.md` — `board:owned` label documented and added to the
  creation script (D6).
