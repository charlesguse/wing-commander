# Contract: In-Flight Detection

Extends `specs/057-autonomous-board-loop/contracts/eligibility-and-selection.md`
(read that first — this document only states the delta). This is the
FR-011 "single home" for the question "is this issue an in-flight board
item of mine?"; do not re-derive it anywhere else, including inline in a
workflow's `run:` step.

## `.github/scripts/board_eligibility.py` (additions)

```python
PRE_FIX_STEPS = frozenset({"triage", "route"})
FIX_OR_LATER_STEPS = frozenset({"fix", "review", "readiness", "prove"})
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
    from pr_state_by_number or not OPEN there.
    """

def select(
    open_issues: list[dict],
    labeled_events_by_issue: dict[int, list[dict]],
    comments_by_issue: dict[int, list[dict]],
    pr_state_by_number: dict[int, str],
) -> int | None:
    """FR-004/FR-011: in_flight_candidate() first; falls through to the
    existing oldest-first/classify_issue/is_excluded scan (unchanged) when
    it returns (None, ...)."""
```

`classify_issue()` and `is_excluded()` keep their existing signatures and
behavior verbatim (Out of Scope: "the exclusion rule... is reused
unchanged"; "the oldest-first eligibility scan... is not modified").

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
   implementation's choice) to find markers naming a fix-or-later step and a
   `pr` number, resolve exactly those PR numbers' `state` via `gh api
   repos/:owner/:repo/pulls/:number --jq .state`. Never a `gh pr list` call,
   never a body/text search (FR-001).
3. The old unrestricted `gh pr list --state open --json number,body |
   ...capture("Fixes #...")` shortcut is deleted; `select()`'s return value
   is the run's only source of the selected issue number.

## Gate: `verify-board-eligibility.py` (Gate 81, extended — no new gate)

FR-012's ten fixture cases, each a checked-in directory under
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

Each fixture directory's four files are all required; the gate fails loudly
(non-zero exit, `::error::` annotation) if any is missing, per Gate 81's
existing pattern (`verify-board-eligibility.py` already does this for its
`classify_issue` fixtures — the new loop mirrors it, not a new mechanism).

## `.github/scripts/board_item_marker.py` (addition)

```python
def read_marker_with_timestamp(issue_comments: list[dict]) -> tuple[str, dict] | None:
    """Same well-formed-marker scan as read_marker(), returning
    (created_at, marker) for the newest one, or None. read_marker()
    becomes a thin wrapper over this."""
```
