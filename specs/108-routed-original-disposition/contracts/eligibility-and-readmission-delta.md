# Contract: Eligibility and Re-Admission Delta

A delta against `specs/057-autonomous-board-loop/contracts/
eligibility-and-selection.md`, which remains the base contract for
`.github/scripts/board_eligibility.py` (CLAUDE.md: contracts a gate reads
remain live and are fixed like code — `verify-board-eligibility.py` reads
this module, so this delta is folded into that base contract's own text by
tasks.md, not left as a separate permanently-standing file).

## `is_excluded()` gains one carve-out (FR-005/FR-006/FR-007)

```python
def is_excluded(issue: dict, spec_request_state_by_number: dict[int, str] | None = None,
                 duplicate_marker: dict | None = None) -> tuple[bool, str | None]:
    """Unchanged base rule (spec 057): True + reason when CLOSED, any
    disposition:*, board:stalled, or stage:*/spec:*.

    NEW (spec 108): when the only exclusion reason found is
    `disposition:duplicate` AND the issue is OPEN, the caller resolves
    `duplicate_marker`: the newest marker with step == "duplicate" among
    ALL of the issue's own comments (board_item_marker.
    find_latest_marker_matching(), never just the issue's overall-newest
    marker -- see "At most once per reopen" below for why). If it carries
    a `spec_request` field, the caller resolves that spec-request's
    CURRENT state live (spec_request_state_by_number, keyed by issue
    number) and:
      - state == "CLOSED"  -> NOT excluded (re-admitted, FR-006)
      - state == "OPEN" (or absent/unresolved) -> still excluded (FR-006's
        last sentence: a reopen while the linked spec-request is still open
        must not re-admit)
    """
```

Every OTHER exclusion reason (plain `state == CLOSED`, `board:stalled`,
any other `disposition:*` value, `stage:*`/`spec:*`) is unaffected — the
carve-out is specific to the `disposition:duplicate` + open +
step=="duplicate"-marker-exists combination, never a general "any
disposition label can be argued past."

## "At most once per reopen" (FR-006) is a property of the reopen, not of the newest marker

`DISPOSITION_LABEL` is never removed programmatically (docs/setup.md), so
once an issue is re-admitted it carries the label for the rest of its
life. An earlier draft of this carve-out gated re-admission on the
issue's OVERALL-newest marker still being the duplicate one, reasoning
that the very next ordinary triage/route marker the loop posts would
naturally stop the carve-out from matching again. In practice this
re-excluded the issue the moment that next marker landed:
`in_flight_candidate()`/`select()` both consult `is_excluded()` on every
run, so an issue whose newest marker is no longer `"duplicate"` would
fall straight back to "excluded on DISPOSITION_LABEL alone" and vanish
from the board mid-rework (maintainer review, fold leg-0 --
FR-005/FR-006/FR-007, SC-005 all assume the issue's second lifecycle
completes, not just its first marker). The carve-out therefore resolves
`duplicate_marker` by scanning every comment for the newest
step=="duplicate" marker specifically, independent of what the issue's
overall-newest marker now is: once that marker's spec-request resolves
CLOSED, the issue stays re-admitted for as long as DISPOSITION_LABEL
persists. "At most once per reopen" is still true -- a second re-admission
of the SAME duplicate marker never fires twice, because re-admission
alone doesn't re-file anything; it is the loop's subsequent triage/route
step (gated by ordinary, unrelated logic) that acts on the issue, exactly
once per reopen.

## `TERMINAL_STEPS` gains `"duplicate"` (defence in depth)

```python
TERMINAL_STEPS = frozenset({"closed", "stalled", "proven", "duplicate"})
```

`in_flight_candidate()` already only iterates `open_issues`, and a disposed
issue's `state == CLOSED` keeps it out of that list in the steady state —
this addition matters only for the moment between a maintainer reopening
the issue and the loop's next run seeing the reopen, where `in_flight_
candidate()` must not treat the still-present `"duplicate"` marker as an
in-flight pre-fix/fix-or-later step.

## Fixtures this delta needs (FR-012's neighbor, not FR-012 itself)

`verify-board-eligibility.py`'s existing fixture pairs (issue.json +
timeline.json, per the base contract's "Gate" section) gain:

5. An OPEN issue, `disposition:duplicate` label, newest marker `step:
   "duplicate"` naming a spec-request that resolves `CLOSED` → admitted
   (re-admission case).
6. The same shape but the named spec-request resolves `OPEN` → NOT
   admitted (still-open-spec-request case, FR-006 last sentence).
7. A CLOSED issue carrying `disposition:duplicate` → NOT admitted (ordinary
   steady-state exclusion, unaffected by the carve-out — `state == CLOSED`
   is checked before the carve-out is ever reached).
8. An OPEN issue, `disposition:duplicate` label, an OLDER marker `step:
   "duplicate"` naming a spec-request that resolves `CLOSED`, and a NEWER
   marker of a different step (an ordinary post-reopen triage/route
   marker) → still admitted, exercising `duplicate_marker`'s
   scan-every-comment resolution rather than the issue's overall-newest
   marker (fold leg-0 regression case).
