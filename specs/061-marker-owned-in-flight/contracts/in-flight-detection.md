# Contract: In-Flight Detection

Extends `specs/057-autonomous-board-loop/contracts/eligibility-and-selection.md`
(read that first — this document only states the delta). This is the
FR-011 "single home" for the question "is this issue an in-flight board
item of mine?"; do not re-derive it anywhere else, including inline in a
workflow's `run:` step.

## `.github/scripts/board_eligibility.py` (additions)

```python
AWAITING_MERGE_STEP = "awaiting-merge"   # #532
PRE_FIX_STEPS = frozenset({"triage", "route"})
FIX_OR_LATER_STEPS = frozenset({"fix", "review", "readiness", AWAITING_MERGE_STEP, "prove"})
TERMINAL_STEPS = frozenset({"closed", "stalled", "proven"})

def in_flight_candidate(
    open_issues: list[dict],
    comments_by_issue: dict[int, list[dict]],
    pr_state_by_number: dict[int, str],
) -> tuple[int | None, bool]:
    """FR-001/FR-002/FR-003/FR-005. Returns (issue_number, multiple_found).

    issue_number is the newest-marker in-flight issue among open,
    non-excluded issues, or None. multiple_found is True when more than
    one issue qualified (FR-005) regardless of which one issue_number
    names.

    Skips (never raises on): an issue with no comments, an issue whose
    newest marker is unparsable (per board_item_marker.read_marker's own
    degrade rule), a marker naming a fix-or-later step whose pr is absent
    from pr_state_by_number or not OPEN there. `prove` never qualifies as a
    candidate here at all: this function only ever runs from the `select`
    job (schedule/workflow_dispatch, never pull_request), and no job on
    that path consumes step == "prove" (only prove-gate/prove do, solely
    on pull_request: closed) -- prioritizing a stuck prove marker would
    starve every other candidate forever for no possible benefit.
    `awaiting-merge` (#532) never qualifies either, whatever its PR's
    state: readiness already handed the PR to a human, and no job
    consumes that step.
    """

def select(
    open_issues: list[dict],
    labeled_events_by_issue: dict[int, list[dict]],
    comments_by_issue: dict[int, list[dict]],
    pr_state_by_number: dict[int, str],
) -> int | None:
    """FR-004/FR-011: in_flight_candidate() first; falls through to the
    existing oldest-first/classify_issue/is_excluded scan when it returns
    (None, ...). That fallback skips an issue whose newest marker records
    step "prove", the same exclusion in_flight_candidate() already applies
    on its own priority path (never a second, parallel rule) -- otherwise a
    stuck prove marker that ages to the front of the oldest-first queue
    would be re-selected every run with no consumer able to advance it
    (Maintainer Feedback finding on PR #475).

    #532: the fallback also skips an issue whose newest marker records
    step "awaiting-merge" unless pr_state_by_number positively reports
    its PR CLOSED or MERGED. OPEN means the handover is still pending.
    An unknown state (a failed lookup or a malformed pr) is skipped too,
    as a fail-safe. Re-admitting it would recreate the wedge whenever the
    lookup kept failing, because resume resolves an unresolvable
    awaiting-merge PR to a no-op. A CLOSED or MERGED PR makes the issue
    eligible again, and resume sends it to a fresh triage
    (resume-recovery.md)."""
```

`classify_issue()` and `is_excluded()` keep their existing signatures and
behavior verbatim (Out of Scope: "the exclusion rule... is reused
unchanged"). The oldest-first ordering and its `classify_issue`/
`is_excluded` eligibility test are themselves unmodified; the only additions
layered in front of them are the `prove`-marker and `awaiting-merge`-marker skips above, so "which issues
can `select()` ever return" stays governed by the one function FR-011's
single-home rule designates for that decision.

## Runtime caller contract (`board-loop.yml`'s `select` job)

The `select` job's data-gathering step is the only place these new inputs
are assembled from live GitHub state — `board_eligibility.py` itself makes
no network calls (Constitution VIII: fixture runs must not depend on the
network).

1. `comments_by_issue`: for each open issue already being visited to resolve
   label-actor associations (FR-008), the same `gh api .../comments` call's
   `--jq` projection additionally extracts `body`, alongside the
   `login`/`association`/`created_at` fields it already keeps — one API
   round-trip serves both purposes.
2. `pr_state_by_number`: after calling `board_item_marker.
   read_marker_with_timestamp()` (via `in_flight_candidate`'s own internal
   scan, or a pre-pass over `comments_by_issue` before calling `select()` —
   implementation's choice) to find markers naming a fix-or-later step
   (`FIX_OR_LATER_STEPS`, which includes `awaiting-merge`) and a
   `pr` number, resolve exactly those PR numbers' `state` via `gh api
   repos/:owner/:repo/pulls/:number --jq .state`. Never a `gh pr list` call,
   never a body/text search (FR-001).
3. The old unrestricted `gh pr list --state open --json number,body |
   ...capture("Fixes #...")` shortcut is deleted; `select()`'s return value
   is the run's only source of the selected issue number.

## Gate: `verify-board-eligibility.py` (Gate 81, extended — no new gate)

FR-012's fixture cases (eleven, plus #532's four), each a checked-in directory under
`.github/scripts/tests/board-eligibility/in-flight/<case>/` containing
`open_issues.json`, `comments_by_issue.json`, `pr_state_by_number.json`, and
`expected.json` (`{"issue_number": <int|null>, "multiple_found":
<bool>}`) — a uniform shape regardless of whether the case involves one
issue or several, since "two issues with non-terminal markers" cannot be
expressed as a single `issue.json` the way Gate 81's existing
`classify_issue` fixtures are:

1. `no-marker` — no issue carries a marker anywhere → `(null, false)`.
2. `pre-fix-no-pr` — marker at `route`, no `pr` recorded → that issue,
   `false`.
3. `fix-or-later-pr-open` — marker at `review`, recorded PR `OPEN` → that
   issue, `false`.
4. `fix-or-later-pr-closed` — marker at `review`, recorded PR `CLOSED`
   (not merged) → `(null, false)` (falls through to oldest-first).
5. `fix-or-later-pr-merged` — marker at `readiness`, recorded PR `MERGED` →
   `(null, false)`.
6. `terminal-step` — marker at `proven` → `(null, false)`.
7. `excluded-issue` — marker at `route` on an issue also carrying
   `board:stalled` → `(null, false)` (FR-003).
8. `unparsable-marker` — a comment containing a marker-shaped HTML comment
   whose JSON does not parse → `(null, false)`.
9. `two-non-terminal` — two open, non-excluded issues each carry a
   non-terminal, qualifying marker with different `created_at` timestamps →
   the newer one, `true`.
10. `unrelated-pr-no-marker` — an eligible issue with no marker, and
    `pr_state_by_number`/PR data present for an unrelated open PR that cites
    it in body text → `(null, false)` — proves the decision never reads PR
    body text at all (FR-001), only markers.
11. `prove-no-pr` — marker at `prove`, no `pr` recorded → `(null, false)` —
    `prove` never qualifies as a candidate, regardless of `pr`, since no
    job consumes step `prove` off the schedule/workflow_dispatch path this
    decision runs on. This case also carries a second, eligible issue with
    no marker and a `labeled_events_by_issue.json` plus a
    `select_issue_number` key in `expected.json`, so the gate additionally
    asserts `select()` itself skips the `prove`-marker issue in its
    oldest-first fallback and returns the other issue, not just that
    `in_flight_candidate()` alone excludes it from the priority path.
12. `awaiting-merge-pr-open`, `awaiting-merge-pr-closed`,
    `awaiting-merge-pr-merged`, `awaiting-merge-pr-unknown` (#532). In each
    case the oldest issue carries an `awaiting-merge` marker naming a PR,
    and a newer eligible issue carries no marker. `in_flight_candidate()`
    returns `(null, false)` in all four. `select()` returns the newer
    issue when the PR is `OPEN` or absent from `pr_state_by_number`, and
    the `awaiting-merge` issue itself when the PR is `CLOSED` or `MERGED`.

Each fixture directory's four files are all required; the gate fails loudly
(non-zero exit, `::error::` annotation) if any is missing, per Gate 81's
existing pattern (`verify-board-eligibility.py` already does this for its
`classify_issue` fixtures — the new loop mirrors it, not a new mechanism).
A case whose `expected.json` also carries `select_issue_number` requires
the fifth `labeled_events_by_issue.json` file and is additionally asserted
against `select()`'s own return value.

## `.github/scripts/board_item_marker.py` (addition)

```python
def read_marker_with_timestamp(issue_comments: list[dict]) -> tuple[str, dict] | None:
    """Same well-formed-marker scan as read_marker(), returning
    (created_at, marker) for the newest one, or None. read_marker()
    becomes a thin wrapper over this."""
```
