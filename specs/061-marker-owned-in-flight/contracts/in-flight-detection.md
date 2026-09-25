# Contract: In-Flight Detection

Extends `specs/057-autonomous-board-loop/contracts/eligibility-and-selection.md`
(read that first — this document only states the delta). This is the
FR-011 "single home" for the question "is this issue an in-flight board
item of mine?"; do not re-derive it anywhere else, including inline in a
workflow's `run:` step.

## `.github/scripts/board_eligibility.py` (additions)

```python
AWAITING_MERGE_STEP = "awaiting-merge"   # #532
BREACH_STEP = "breach"                   # #530
PRE_FIX_STEPS = frozenset({"triage", "route"})
FIX_OR_LATER_STEPS = frozenset({"fix", BREACH_STEP, "review", "readiness", AWAITING_MERGE_STEP, "prove"})
TERMINAL_STEPS = frozenset({"closed", "stalled", "proven"})

def in_flight_candidate(
    open_issues: list[dict],
    comments_by_issue: dict[int, list[dict]],
    pr_state_by_number: dict[int, str],
    bot_login: str,
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
    bot_login: str,
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

`bot_login` (#555) is the loop's own App login, `<app-slug>[bot]`. Both
functions read markers only through `board_item_marker.
read_marker_with_timestamp(comments, bot_login)`, which ignores any comment
not posted by that App (`is_loop_marker_author()`, see spec 057's
board-item-marker.md "Author rule"). A marker from anyone else, an OWNER
included, neither makes an issue in-flight nor triggers the fallback's
`prove`/`awaiting-merge` skip.

`UNOWNED_OPEN_PR_STATE = "OPEN_UNOWNED"` (#555): the select job's PR
lookup records an OPEN PR that fails `BOARD_PR_OWNED_JQ` (no `board:owned`,
or head in another repository) as this state instead of `OPEN`. It is not
`OPEN`, so the marker does not make its issue in-flight, and `select()`'s
fallback passes over an issue whose fix-or-later marker names such a PR
(`_unowned_open_pr_holds()`) until the PR is CLOSED or MERGED. Resume holds
that item as a no-op (resume-recovery.md), so without this skip the item
would be re-selected and do nothing every run (cf. #532).

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
   `--jq` projection additionally extracts `body` and (#555)
   `user: {login, type}`, alongside the `login`/`association`/`created_at`
   fields it already keeps — one API round-trip serves both purposes.
   The step's `BOT_LOGIN` env is `${{ steps.ctx.outputs.bot-slug }}[bot]`
   from `wing-commander-context`; the stdin payload to
   `board_eligibility.py` carries it as `bot_login`, and `main()` exits
   non-zero without it. (#557) A failed comments fetch fails the select
   step with an `::error::` annotation. It is never recorded as `[]`,
   which would hide that issue's in-flight marker and let an older item
   start alongside it (FR-048 / User Story 7). The one exception is HTTP
   404/410, which means the issue is gone. That issue is dropped from the
   run's candidates with a `::warning::`.
2. `pr_state_by_number`: after calling `board_item_marker.
   read_marker_with_timestamp(comments, bot_login)` (via `in_flight_candidate`'s own internal
   scan, or a pre-pass over `comments_by_issue` before calling `select()` —
   implementation's choice) to find markers naming a fix-or-later step
   (`FIX_OR_LATER_STEPS`, which includes `awaiting-merge`) and a
   `pr` number, resolve exactly those PR numbers' `state` via `gh api
   repos/:owner/:repo/pulls/:number` (`BOARD_PR_STATE_JQ`; an OPEN PR that
   fails `BOARD_PR_OWNED_JQ` is recorded as `UNOWNED_OPEN_PR_STATE`, #555).
   Never a `gh pr list` call, never a body/text search (FR-001).
   (#564) A 404 leaves that PR's state absent; any other lookup error
   fails the select step with an `::error::` annotation, as step 1 does.
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

13. `forged-marker-outsider`, `forged-marker-owner-human`,
    `forged-marker-other-app` (#555). Markers posted by an outside (NONE)
    user, an OWNER human and a different App's bot: a `triage`/`route`/
    `review` marker on an ineligible issue does not make it in-flight
    (`(null, false)`), and a `prove`/`awaiting-merge` marker on the
    oldest eligible issue does not make `select()` pass it over.
    `own-marker-newer-forged-ignored`: the loop's own `triage` marker
    stays in force when newer markers from another App and from a User
    account carrying the App's login follow it. Every fixture marker
    comment carries `user: {login, type}`; the gate's bot login is
    `wing-commander-bot[bot]`. The gate also swaps weaker author
    predicates into `board_item_marker` and requires each to fail a case,
    and requires `main()` to refuse a payload without `bot_login` or
    with a bare `[bot]`. `unowned-open-pr`: the oldest eligible issue's
    `review` marker names a PR recorded as `OPEN_UNOWNED` → `(null,
    false)`, and `select()` returns the newer issue.
14. `breach-pr-open`, `breach-pr-closed` (#530). A `breach` marker (fix's
    post-push breach, spec-request not yet filed) naming a PR is in
    flight like any other fix-or-later marker: `OPEN` → that issue,
    `CLOSED` → `(null, false)`.

Each fixture directory's four files are all required; the gate fails loudly
(non-zero exit, `::error::` annotation) if any is missing, per Gate 81's
existing pattern (`verify-board-eligibility.py` already does this for its
`classify_issue` fixtures — the new loop mirrors it, not a new mechanism).
A case whose `expected.json` also carries `select_issue_number` requires
the fifth `labeled_events_by_issue.json` file and is additionally asserted
against `select()`'s own return value.

## `.github/scripts/board_item_marker.py` (addition)

```python
def read_marker_with_timestamp(issue_comments: list[dict], bot_login: str) -> tuple[str, dict] | None:
    """Same well-formed-marker scan as read_marker(), returning
    (created_at, marker) for the newest one, or None. read_marker()
    becomes a thin wrapper over this. #555: bot_login is required, and
    only comments is_loop_marker_author(comment, bot_login) accepts are
    scanned."""
```
