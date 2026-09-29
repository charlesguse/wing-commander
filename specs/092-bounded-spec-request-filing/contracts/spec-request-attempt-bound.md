# Contract: spec-request attempt bound

Owning module: `.github/scripts/board_spec_request_filing.py` (new,
research.md D6), plus the extended `.github/scripts/board_item_marker.py`
(research.md D4). This is the *one* implementation FR-008–FR-016 and
FR-018 require.

## Configuration

`.github/workflows/board-loop.yml`'s top-level `env:` block gains:

```yaml
BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET: 3
```

beside `BOARD_LOOP_ROUND_BUDGET`. A PR-reviewed constant, never a
per-site literal (Gate 93 check 6 enforces this — see
`gate-spec-request-single-home.md`).

## Reading the current count

Every filing site reads `needs.select.outputs.spec-request-attempts`
(threaded through `select`/`resume` exactly as `round` is today — see
data-model.md). This is the count of consecutive failed attempts *since*
the last successful filing or re-admission; it is never derived by
counting comments or run history (spec.md Assumptions).

## Deciding after a failed attempt

```
python3 board_spec_request_filing.py record-attempt \
  --attempts CURRENT_ATTEMPTS --budget "$BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET"
```

Prints one JSON object to stdout:

```json
{"attempts": <CURRENT_ATTEMPTS + 1>, "stall": <attempts >= budget>}
```

Pure function, no I/O — called by the site's own failed-lookup or
failed-create branch, never by a hand-rolled `$((N+1))` (Gate 93 check 6).

## Branch behavior at each site

### `stall == false` (below cap)

1. `spec_request_attempts := attempts` is persisted: the site posts **one**
   new issue comment containing only the standard `**Run:** <url>` line and
   the marker HTML comment (`board_item_marker.py --step route
   --spec-request-attempts N`, with `round`/`pr`/`branch`/`base_sha` at
   their existing empty defaults for a pre-fix item) — no failure
   narrative, no label change, no spec-request URL (research.md D7).
2. The step fails loudly: `exit 1` (unchanged #514 guard shape). The item
   is left eligible; a later scheduled run retries it.
3. `board:stalled` is never added, no cross-link is posted, no
   spec-request URL is published (SC-007).

### `stall == true` (the Nth attempt — give-up)

1. `add_stalled_label()` is called first (unchanged #782/#604 rule: label
   before any stalled marker or comment).
2. A comment is posted stating explicitly: no `spec-request` was filed;
   the last observed failure (the `gh issue create` error or the lookup's
   own failure reason); the number of attempts spent (`budget`); and that
   removing `board:stalled` re-admits the item (FR-012).
3. A `stalled`-step marker is written, with `spec_request_attempts` reset
   to `0` in the machine field (the comment's prose is the human-readable
   record of the spent count — data-model.md "Give-up stall").
4. The step **exits 0** — a spent budget is a deliberate, successful
   hand-off, the same shape review's round-budget exhaustion already uses
   (board-loop.yml:3259-3321), not a run failure. The run does not report
   the item as routed (User Story 2, Acceptance Scenario 2).

### On success (fresh create or reuse)

`spec_request_attempts` is written as `0` in whatever marker/comment the
site already posts for a successful filing (the existing cross-link +
stalled-marker flow, unchanged in shape) — no separate write.

## Re-admission

Unchanged mechanism: removing `board:stalled` is the sole re-eligibility
condition (FR-014), identical to every other stall in this loop. No new
condition is added to `board_eligibility.is_excluded()` or to `resume`'s
step resolution.
