# Data Model: The Loop Recognizes Its Own Work

**Feature**: specs/061-marker-owned-in-flight | **Spec**: [spec.md](./spec.md)

This feature adds no new persistent storage and changes no schema owned by
spec 057. It adds one derived decision, one new label value, and two field
additions to data already flowing through the `select`/`resume` jobs. Entity
shapes below are the ones `board_eligibility.py` and `board_item_marker.py`
consume and return; see [research.md](./research.md) for why each shape was
chosen.

## Board Item Marker (existing, spec 057 — read here, not redefined)

```text
{"step": "<step>", "round": <int>, "pr": <int|null>,
 "branch": "<name>|null", "base_sha": "<sha>|null"}
```

Unchanged by this feature. What changes is who reads it (`board_eligibility.
in_flight_candidate()` in addition to the `resume` step) and how much of it
resume trusts before re-deriving (FR-002).

## Step (existing vocabulary, ordered here for the first time)

The loop's named steps, in the order an item passes through them:

```text
triage < route < fix < review < readiness < awaiting-merge < prove
```

(`awaiting-merge` was added by #532: the step readiness records when it
reports ready and hands the PR to a human.)

`breach` (#530) is not on this line. It branches off `fix`: fix records
it on a post-push backstop breach before filing the spec-request, and a
later run's `readiness` retries that spec-request if the create failed.
It never reaches `review`.

plus three terminal outcomes, none of which are "in flight":
`closed`, `stalled`, `proven`.

**Pre-fix** = `{triage, route}` — qualifies as in flight on the marker's step
alone (FR-002 bullet 1); no PR can exist yet at these steps.

**Fix-or-later** = `{fix, breach, review, readiness, awaiting-merge, prove}` — the steps
`in_flight_candidate()`'s "resolved PR required" branch groups together
(FR-002 bullet 2), but `prove` never actually qualifies as a candidate:
`in_flight_candidate()` only ever runs from the `select` job (schedule/
workflow_dispatch), and no job on that path consumes step `prove` (only
`prove-gate`/`prove` do, on `pull_request: closed` alone), so a `prove`
marker is skipped outright rather than being prioritized with no possible
benefit. `awaiting-merge` never qualifies either: the item has been
handed to a human and no job consumes that step (#532). It stays in this
set because its marker carries a PR, and the `select` job's PR-state
lookup pass reads this set to decide which PRs to resolve. `fix`,
`breach`, `review`, and `readiness` still require the marker's recorded PR
to resolve `OPEN`.

This ordering lives as a plain constant inside `board_eligibility.py`
(e.g. `PRE_FIX_STEPS`/`FIX_OR_LATER_STEPS` frozensets) — not a new shared
vocabulary module, since spec 057 already treats step names as string
literals scattered across `board-loop.yml`'s own `if:` conditions, and this
feature does not change that (Assumptions: "this feature does not introduce
a new vocabulary of step names").

## In-Flight Candidate (new — the decision this feature adds)

Not a stored entity — the return value of a new function:

```python
def in_flight_candidate(
    open_issues: list[dict],
    comments_by_issue: dict[int, list[dict]],
    pr_state_by_number: dict[int, str],
) -> tuple[int | None, bool]:
    """Returns (issue_number, multiple_found).

    issue_number: the in-flight issue, or None when no open, non-excluded
    issue carries a qualifying marker.

    multiple_found: True when more than one open, non-excluded issue
    carried a qualifying marker (FR-005) -- issue_number is still the
    single deterministic pick (the newest marker) even when this is True.
    """
```

**Fields consumed**:

| Field | Source | Purpose |
|---|---|---|
| `open_issues[].number`, `.state`, `.labels` | already fetched (`board_eligibility.is_excluded`) | FR-003 exclusion, reused unchanged |
| `comments_by_issue[N]` | `gh api .../issues/N/comments` — `{created_at, body}` per comment (D2/D3 in research.md) | marker discovery via `board_item_marker.read_marker_with_timestamp()` |
| `pr_state_by_number[pr]` | `gh api .../pulls/pr` — `.state` (`OPEN`\|`CLOSED`\|`MERGED`), fetched only for PR numbers a fix-or-later marker names | FR-002 bullet 2's open-PR requirement |

**Decision** (per issue, oldest-`createdAt`-first is irrelevant here — this
picks by marker recency, not issue age):

1. Skip if `is_excluded(issue)` is `(True, _)` (FR-003).
2. Read the newest marker via `read_marker_with_timestamp`; skip if none, or
   if unparsable (already `None` from `read_marker`'s own degrade rule).
3. Skip if the marker's `step` is terminal (`closed`/`stalled`/`proven`).
4. If `step` is pre-fix: candidate, keyed by the marker's own `created_at`.
5. Skip outright if `step == "prove"` — never a candidate, regardless of
   `pr` (no consumer exists for it off the `pull_request: closed` trigger
   this decision never runs on; see the Fix-or-later note above). Skip
   `awaiting-merge` outright too, whatever its PR's state (#532).
6. If `step` is fix-or-later (excluding `prove`/`awaiting-merge`, already handled): candidate
   only if `marker["pr"]` is present in `pr_state_by_number` with value
   `OPEN`; otherwise skip (this is the "stale marker" disqualification
   FR-002 exists for).
7. Among all candidates found across all issues, return the one with the
   lexicographically greatest `created_at` (ISO-8601 timestamps sort
   lexicographically); `multiple_found` is `len(candidates) > 1`.

**Validation rules**: everything above degrades to "not a candidate" on
missing/malformed input — an issue with no comments, a marker missing a
required field, or a `pr` value that doesn't parse as an int are all treated
as "no usable marker for this issue," never a raised exception (per
`board_item_marker.read_marker()`'s own existing contract, reused here
rather than re-implemented, and the spec's own Assumptions section).

## Extended `select()` signature

```python
def select(
    open_issues: list[dict],
    labeled_events_by_issue: dict[int, list[dict]],
    comments_by_issue: dict[int, list[dict]],
    pr_state_by_number: dict[int, str],
) -> int | None:
    """FR-004/FR-011: consults in_flight_candidate() first; falls through
    to the existing oldest-first/classify_issue/is_excluded scan, plus the
    same prove-marker skip in_flight_candidate() applies, when it returns
    (None, ...)."""
```

`labeled_events_by_issue`, `classify_issue`, and `is_excluded` are
byte-for-byte unchanged from spec 057. The oldest-first fallback scan
itself (ordering, `is_excluded`/`classify_issue` eligibility test) is also
unchanged, but gained one addition on top: it skips an issue whose newest
marker records step `prove`, mirroring `in_flight_candidate()`'s own
priority-path exclusion (Maintainer Feedback finding on PR #475) — without
it, a stuck `prove` marker that ages to the front of the queue would be
re-selected by this fallback every run with no consumer able to advance it.

## Loop Ownership Label (new)

A plain GitHub label, `board:owned` (decision D6), with no machine-readable
payload beyond its name — unlike the marker, it carries no JSON. Applied
exactly once, at PR-creation time, to every PR the fix step opens. Never
removed by the loop, never read by `classify_issue`/`is_excluded`/any
eligibility input (Out of Scope: "it does not become an eligibility input, a
routing signal, or a substitute for the marker").

| Property | Value |
|---|---|
| Name | `board:owned` |
| Applied by | `gh pr create --label board:owned` (fix step, single call) |
| Applied to | every PR the loop opens, from this feature onward (pre-existing loop PRs are not retrofitted — Out of Scope) |
| Read by | resume's FR-007 fallback only: `gh pr list --state open --label board:owned` |
| Removed by | nobody — it is a permanent provenance marker on the PR, not a workflow state toggle like `board:stalled` |

## `board_item_marker.py` addition

```python
def read_marker_with_timestamp(issue_comments: list[dict]) -> tuple[str, dict] | None:
    """Same scan as read_marker(), returning (created_at, marker) for the
    newest well-formed marker, or None. read_marker() becomes a one-line
    wrapper: `pair = read_marker_with_timestamp(c); return pair[1] if pair else None`."""
```

No change to `write_marker()` or the marker's own JSON shape (Out of Scope).

## State flow (resume's step resolution, decision D5)

Priority by strongest live signal — each clause fires only when the ones
above it don't apply; re-derive branch (`git ls-remote`) and resolve PR
(marker-named lookup by number, then FR-007's `board:owned` fallback)
first, then:

```text
1. marker names a PR, and that PR resolves (pre-fix: no PR needed;
   fix-or-later: PR state == OPEN)          -> step = marker's own step
2. no marker-named PR, but FR-007 fallback
   recovers an open board:owned PR          -> step = review   (FR-014 recorded)
3. no PR resolved by 1 or 2, but a branch
   is re-derived                            -> step = fix
4. neither a PR nor a branch resolved       -> step = triage   (FR-009 recorded
                                                                 when a marker
                                                                 was present but
                                                                 disqualified)
```

Clause 4 is where a `triage`- or `route`-step marker with nothing cut yet
lands (branch/PR are never present that early), reproducing today's
existing "route is informational only, resume re-runs triage" behavior
without a per-step exception — the marker's step name is only consulted in
clause 1, and only once a PR has already confirmed the marker is current.

This flow is resume's own step-resolution logic inside `board-loop.yml`'s
`resume` step — not part of `board_eligibility.py`, since it answers "what
step is *this already-selected* item at," a different question from
`in_flight_candidate()`'s "*which* item is in flight" (FR-011 governs the
latter only).
