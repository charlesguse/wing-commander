# Research: A Not-Ready PR Releases the Board

No `[NEEDS CLARIFICATION]` marker remains in `spec.md` — the three owner
questions were resolved on lifecycle issue #717 and are recorded in
`spec.md`'s own Clarifications section. This document resolves the
questions the spec left to "the plan stage's decision" (Assumptions) and
records the design decisions the implementation depends on.

## D1: The not-ready record extends the existing marker, not a new store

**Decision**: Add three optional fields to the board item marker's JSON
payload — `nr_count` (int), `nr_head_sha` (str), `nr_class` (`"self-clearing"`
or `"durable"`) — meaningful only on a `readiness`-step marker (the
not-ready record) and, for FR-008's own handover only, a `stalled`-step
marker (D7). Every other marker carries them as absent/null, matching how
`branch`/`base_sha` are already `null` on a pre-fix marker.

**Rationale**: `spec.md` Assumptions explicitly defers this to the plan
stage and states the record "is carried by the existing board-item marker
mechanism and the existing issue-comment convention rather than a new
store." The marker is already the loop's one fast-path state carrier
(`contracts/board-item-marker.md`, research.md D21 of spec 057); adding
fields to it is the same move spec 061 made for `branch`/`pr` recovery,
not a new mechanism.

**Alternatives considered**: A new marker step (e.g. `not-ready`) —
rejected because FR-001's hold and FR-007's re-admission both need the
item to still resolve to `readiness` (unmoved head) or `review` (moved
head), never a distinct step a job would have to additionally special-case
everywhere `readiness` is checked (`board-loop.yml`'s `readiness` job
`if:`, `in_flight_candidate()`'s `FIX_OR_LATER_STEPS`, resume's step
resolution). A second, parallel comment convention (e.g. a structured
JSON block outside the marker) — rejected because it would duplicate the
"read the newest bot comment" scan `board_item_marker.find_latest_marker()`
already is the single home for (CLAUDE.md).

## D2: Self-clearing vs. durable is computed from the rollup's own states

**Decision**: `board_readiness.py`'s `evaluate_from_snapshot()` gains a
fourth return field, `unmet_class` (`"self-clearing"` | `"durable"` |
`None` when `ready`), derived purely from `statusCheckRollup`'s per-entry
`state`/`conclusion` values already in hand: an unmet condition is
**self-clearing** only when every non-passing rollup entry is in a
not-yet-concluded state (`QUEUED`, `IN_PROGRESS`, `PENDING`, `EXPECTED`) —
the same "hasn't reached a terminal state" set `_checks_green()` already
tests against, inverted — and **durable** otherwise (a terminal failing
state, an empty rollup, an open finding, a backstop breach, or the kill
switch, though FR-006 exempts the kill switch from counting at all — D9).

**Rationale**: FR-005 requires "the distinction MUST come from the
rollup's own per-entry states, never from an agent's reading of them," and
`board_readiness.py` already owns the one fresh rollup fetch (FR-036/
FR-037) — computing the class anywhere else would mean fetching or
threading the rollup a second time. `board_eligibility.py` then only ever
*reads* the class off the marker (D3); it never re-derives it, keeping
FR-003's single-home rule intact for the *hold* decision while leaving
classification in the module that already owns the rollup.

**Alternatives considered**: Classifying in `board_eligibility.py` from a
raw rollup passed alongside the marker — rejected: it would need the
rollup at selection time too, doubling the shape `pr_state_by_number`
already narrows to state-only, and would split "read the readiness
inputs" across two modules for no benefit.

## D3: The hold decision is one new predicate beside the existing two

**Decision**: Add `board_eligibility._not_ready_holds(marker, pr_state_by_number, pr_head_sha_by_number)`,
consulted by both `in_flight_candidate()` (excludes a held item from the
priority path) and `select()`'s oldest-first fallback (excludes it there
too) — the same shape as `_awaiting_merge_holds()` and
`_unowned_open_pr_holds()` already beside them. Returns `True` (held) when:
the marker's step is `readiness`, it carries a parsable not-ready record,
`nr_class == "durable"`, and the PR's current head SHA (from the new
`pr_head_sha_by_number`, D4) equals `nr_head_sha` — or when the head SHA
cannot be determined at all (FR-011's fail-safe: unknown degrades to
held, never to admitted). Returns `False` (not held — including the
ordinary "never evaluated yet" case, a marker with no not-ready record at
all) for a self-clearing record, or a durable one whose head has moved
(FR-005, FR-007 — a moved-head item is *admitted*, not merely un-held;
the resume step's own logic, not this predicate, decides which step it
resumes to, D6).

**Rationale**: FR-003 requires the decision to live inside the existing
single home and be consulted by both selection paths, "never a hold rule
and a counting rule with separate homes" (FR-004). Mirroring the two
existing hold predicates keeps the pattern one reviewer already
recognizes, rather than inventing a second shape for the same kind of
question.

## D4: The PR head SHA rides the select job's existing per-PR lookup

**Decision**: The select job's PR-state lookup (`board-loop.yml`, the
`gh api repos/:owner/:repo/pulls/:number` call already made for every
fix-or-later marker's PR) additionally extracts `.head.sha` from the same
already-fetched JSON into a new `board-pr-head-sha-by-number.json`, passed
to `board_eligibility.py` as `pr_head_sha_by_number` (a new top-level key
in the same stdin payload `main()` already reads). No second API call.

**Rationale**: The Assumptions section states this lookup "costs no
additional API round-trip per item," and the full PR JSON the existing
call already fetches carries `head.sha` — `BOARD_PR_STATE_JQ`'s own
`jq` expression already reads fields off that same response object.

## D5: The not-ready count threads through the marker like `round`/`base_sha`

**Decision**: `nr_count` starts absent (0) the first time an item ever
reaches `readiness`. Readiness's not-ready-report step sets it to
`(carried-in nr_count) + 1` on every not-ready outcome, where
"carried-in" is `needs.select.outputs.nr-count` (or, on a same-run
review→readiness handoff, `needs.review.outputs.nr-count`) — a new output
the resume step's `step_resolution_json` heredoc parses off the marker
exactly as it already parses `round`/`base_sha`. The review job's three
marker-writing sites (converged → `readiness`; continue → `review`,
`round+1`; budget-exhausted → `stalled`) each pass `nr_count` through
**unchanged** — they never increment or reset it; only readiness's own
not-ready site increments it, and only an explicit `board:stalled`
removal resets it to absent (the Edge Case "removing the label is a
deliberate 'try again'").

**Rationale**: FR-004(a)'s threshold counts not-ready outcomes "for the
PR, not for a single head SHA" (Edge Cases), so the count must survive a
head-move re-admission that routes back through a review round before
readiness runs again (FR-007) — the marker chain is the only place that
value can live without a second, comment-history-scanning mechanism, and
`round`/`base_sha` already establish the pattern of a resume-recovered
value flowing from `select`'s outputs into the jobs below it.

**Alternatives considered**: Deriving the count by scanning back through
the issue's own not-ready comments each run — rejected: every existing
reader (the marker contract, `find_latest_marker()`) reads only the
single newest qualifying marker; a backward scan would be a second,
parallel state-recovery mechanism for the one value FR-002 says the
marker itself must carry.

## D6: The round budget survives a readiness detour by no longer being dropped

**Decision**: The review job's converged-marker write (`board-loop.yml`,
"Post the converged/stalled outcome and marker", the `OUTCOME = converged`
branch) passes `--round "$ROUND"` (the round it converged at) instead of
omitting `--round` (which defaults to 0). Resume's step resolution already
parses `round` off any marker (`marker_round`); when a moved-head
re-admission resolves `step = review` (D-below / FR-007), the round it
forwards is this preserved value, continuing rather than resetting the
budget.

**Rationale**: FR-007 requires re-admission to "**continue** the item's
existing fix→review round budget (spec 057 FR-030) rather than resetting
it." Today's converged-marker write drops `round` to its default because
nothing downstream of a converged review reads it (readiness never
consults `round`) — but a later re-admission through `review` does, so
preserving it costs nothing new and closes exactly this gap.

## D7: FR-007's review/readiness split is implemented only at this feature's own handover site

**Decision**: The moved-head hold-release (FR-001/FR-004(b)) is decided
entirely from the `readiness`-step marker's own `nr_head_sha` (D3) — no
new marker shape needed there. FR-008's own handover, however, is the one
`board:stalled` site this feature controls, and — unlike every *other*
existing stall site, which posts `--step stalled` with no `--pr` — this
site's marker additionally records `--pr <n>` and `--nr-head-sha <sha>`
(the PR and head the threshold was reached on). A **new** resume-recovery
clause (inserted before the existing generic board:owned-fallback clause)
reads a `stalled`-step marker that carries both: if the fallback-recovered
PR's current head equals the recorded `nr_head_sha`, resume resolves
`readiness` (an already-reviewed head is not re-reviewed); otherwise (or
when the older-shaped `stalled` marker carries neither field) resume
falls through unchanged to today's generic clause, which always resolves
`review`. Every other stall site (parse-failed, malformed-findings,
budget-spent, triage hand-over, route's spec-request, the backstop-breach
sites) is untouched and keeps resolving `review` unconditionally,
matching FR-015 ("existing behaviour that this feature does not govern
MUST be unchanged").

**Rationale**: FR-007's text describes the full combined rule ("resumes
at `review` too when its head has moved since the last review, and at
`readiness` when it has not") for *any* `board:stalled` removal, and
`spec.md`'s "Status update 2026-09-29" section records that spec 100
(#752, lifecycle issue not yet through plan/implement — see the reported
finding below) is the feature that generalizes this to every stall site
via `add_stalled_label()`'s own canonical statement. Implementing the full
generalization here would mean this feature edits the shared
`add_stalled_label()` docstring and every stall call site — work spec
100's own spec explicitly claims as its scope. Scoping 093's own change to
the one handover it introduces keeps FR-007 true for *this* feature's
re-admission paths (US3, the moved-head case, and US2 AS3, the
threshold-handover's own label-removal case) without pre-empting spec
100's still-undecided implementation of the other five sites. When spec
100 lands, its own convergence step should find this site's rule already
matching its target shape and generalize the pattern to the rest, per
CLAUDE.md's single-home rule, rather than re-deriving it.

**Alternatives considered**: Generalizing the split to all six stall sites
now — rejected as out of scope creep into spec 100's own lifecycle issue
(#752) and its own not-yet-merged spec; doing so here would leave spec
100 with nothing to implement, or worse, two independently-evolving
copies of the same rule (CLAUDE.md "Shared logic has exactly one home").

## D8: FR-009's dedup edits the existing comment rather than suppressing state

**Decision**: Before posting a not-ready comment, the not-ready-report
step compares this run's `(pr, head_sha, unmet_reason)` against the
current marker's own `(pr, nr_head_sha, unmet_reason)` (the unmet reason
text itself is carried in the marker's human-legible half, not the JSON,
so the comparison reads the visible line, not a new JSON field). On an
exact match, it edits the existing bot comment in place (`gh issue comment
--edit-last`, already documented as an allowed shape in
`contracts/board-item-marker.md`'s Write section — "or updates, by
editing its own most recent status comment rather than appending a
duplicate" — never yet exercised by any call site) rather than appending
a new one; the marker's `nr_count` is still updated in the edited comment
even when the visible reason is unchanged, since FR-005 still requires
the count to advance. On any difference, it posts a new comment as today.

**Rationale**: FR-009 forbids "an unmet-condition comment that is
identical to the newest one already on the issue for the same PR, head
SHA and unmet condition" while FR-002 still requires the record (now
including a higher count) to be written durably every run. Editing the
one comment in place satisfies both without inventing a second,
undocumented convention; the contract already named this option.

## D9: FR-006 needs no new code — it is already true on `main`

**Decision**: No change. `board-loop.yml`'s readiness job already gates
every durable step (the ready report, the not-ready report, the
spec-request, `board:stalled`) on `steps.killswitch-recheck.outputs.paused
== 'false'` (#782, `spec.md`'s own "Status update" section). A stand-down
therefore already writes no not-ready marker and posts no comment, so it
cannot advance `nr_count` and cannot reach the handover threshold.

**Rationale**: `spec.md` states this plainly: "FR-006 therefore already
holds on `main` and must be preserved, not built." The only new
obligation this feature adds is a fixture proving the preservation holds
once the not-ready-report step gains the marker write this feature adds
(FR-013's "kill-switch exemption" fixture) — an addition to the *test*
surface, not the production code.

## D10: Cross-spec sequencing — spec 100 is not yet built

`specs/100-stalled-item-re-admission` (lifecycle issue #752) is at
`spec-meta.json` `"stage": "spec"` on its own draft branch
(`spec-draft/100-stalled-item-re-admission`), not merged to `main`. It
targets the same `add_stalled_label()` docstring and the same
review-vs-readiness split this feature's FR-007 also describes, reconciled
by the owner (2026-09-29) so the two specs state one combined rule rather
than two competing ones. D7 above keeps 093's own implementation scoped
to the one stall site it introduces, so it does not need spec 100's own
code to exist first, and does not foreclose spec 100 generalizing the
same rule later. This sequencing risk — two specs whose FR-007/FR-006
describe the same eventual code, one of which (093) is implemented first
— is reported as a finding for the maintainer rather than resolved here:
each spec's prose (Clarifications/"Status update") names the other by
number, but neither spec's own **Dependencies** section lists the other,
so a reader who only reads Dependencies would miss the coupling.
