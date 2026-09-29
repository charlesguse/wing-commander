# Contract: Eligibility and Re-Admission Delta

A delta against `specs/057-autonomous-board-loop/contracts/
eligibility-and-selection.md`, which remains the base contract for
`.github/scripts/board_eligibility.py` (CLAUDE.md: contracts a gate reads
remain live and are fixed like code — `verify-board-eligibility.py` reads
this module, so this delta is folded into that base contract's own text by
tasks.md, not left as a separate permanently-standing file).

## `is_excluded()` gains one carve-out (FR-005/FR-006/FR-007)

```python
def is_excluded(issue: dict, spec_request_state_by_number: dict[int, str] | None = None) -> tuple[bool, str | None]:
    """Unchanged base rule (spec 057): True + reason when CLOSED, any
    disposition:*, board:stalled, or stage:*/spec:*.

    NEW (spec 108): when the only exclusion reason found is
    `disposition:duplicate` AND the issue is OPEN AND its newest loop
    marker (already resolved by the caller, same as in_flight_candidate()
    resolves markers today) has step == "duplicate" with a `spec_request`
    field, the caller resolves that spec-request's CURRENT state live
    (spec_request_state_by_number, keyed by issue number) and:
      - state == "CLOSED"  -> NOT excluded (re-admitted, FR-006)
      - state == "OPEN" (or absent/unresolved) -> still excluded (FR-006's
        last sentence: a reopen while the linked spec-request is still open
        must not re-admit)
    """
```

Every OTHER exclusion reason (plain `state == CLOSED`, `board:stalled`,
any other `disposition:*` value, `stage:*`/`spec:*`) is unaffected — the
carve-out is specific to the `disposition:duplicate` + open + step==
"duplicate" combination, never a general "any disposition label can be
argued past."

## "At most once per reopen" (FR-006) needs no counter

Once `select()` returns a re-admitted issue and the loop posts its next
marker for it (an ordinary triage/route marker), the newest marker's
`step` is no longer `"duplicate"`, so the carve-out's own precondition
stops matching on the very next evaluation — re-admission is a property of
"the newest marker is still the disposal marker," not a count. This is the
same newest-marker-wins property `read_marker_with_timestamp()` already
guarantees (data-model.md, research.md D6).

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
