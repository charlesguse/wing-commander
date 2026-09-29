# Contract: FR-011, FR-012 — Gate 87's fixtures and mutation coverage

## `.github/scripts/verify-board-stop-check.py`

### Fixture shape change (FR-012 — outcome preserved, shape updated)

Every fixture under `.github/scripts/tests/board-stop-check/*.json` currently
declares `"expected_run_id": <string or null>`. Each is updated to declare
the two-fact shape instead — e.g. `"expected": {"stand_down": true,
"cancel_run_id": null}` — computed from the *same outcome* the fixture
already encodes (a fixture whose `expected_run_id` equalled the announced
current run under the old contract now declares `cancel_run_id: null`, per
the `StopDecision` invariant in data-model.md; a fixture whose
`expected_run_id` named a genuinely earlier run keeps that value as
`cancel_run_id` and adds `stand_down: true`; a fixture whose `expected_run_id`
was `null` because no stop was found declares `stand_down: false,
cancel_run_id: null`). **No fixture is deleted, and no fixture's real-world
scenario changes** — this is a shape migration only, satisfying SC-003 ("no
fixture is deleted or weakened").

`run_fixtures()` and `run_command_cases()` compare
`board_stop_check.find_stop_request(...)` against this new `expected` shape
(a `StopDecision` equality check, or the equivalent dict comparison) in place
of the old bare-string comparison.

### `MUTATIONS` gains a fifth entry (FR-011, decision-function layer)

```python
("self-run returned as cancel target, pre-085", "find_stop_request",
 lambda: (lambda comments, current_run_id, bot_login: <reintroduce the
     pre-fix fallback: return StopDecision(stand_down, last_other_run_id
     if last_other_run_id is not None else current_run_id) instead of
     StopDecision(stand_down, last_other_run_id)>),
```

Wired into the existing `MUTATIONS` tuple, this entry is picked up by
`mutation_check()` automatically — no new plumbing needed there. It must be
caught by at least one fixture; `first-pass-own-run-only.json` (current run's
own marker only, a stop present) is the direct fixture for this, since under
the mutation it would report `cancel_run_id: "999"` where the fixture (per
the shape migration above) declares `cancel_run_id: null`.

**Why this proof is not attributable to an unrelated guard**: `run_fixtures`/
`run_command_cases` call `find_stop_request()` directly — there is no shell,
no stub `gh`, no `RUNS` table, and no workflow-path/unreadable-run guard in
this code path at all. A failure here can only mean the decision function's
own FR-003 contract broke, which is what FR-011 requires ("MUST NOT be
attributable to the unreadable-run or workflow-path guards suppressing the
cancel for an unrelated reason").

### `RUNS` and `SHELL_CASES` gain the missing case (FR-011, composite-shell
layer — closes the "gate gap" spec.md names explicitly)

`RUNS` gains:

```python
"999": {"status": "in_progress", "path": OWN_PATH, "repository": {"full_name": REPO}},
```

(`GITHUB_RUN_ID` is hard-coded `"999"` in `_run_shell_case`'s environment;
today `999` is deliberately absent from `RUNS`, which is exactly why the
spec's "gate gap" section found the one existing case that reaches the
self-cancel branch — the forged-marker case — gets saved by the unreadable-run
guard regardless of the self-cancel comparison's presence.)

`SHELL_CASES` gains:

```python
("a first pass through this run cancels nothing even though that run is "
 "otherwise a readable, same-workflow, non-completed run",
 [_marker(999), STOP], "true", None),
```

With the shipped (correct) `board_stop_check.py`, this case proves the
self-cancel invariant holds end-to-end through the real composite shell when
every *other* guard (unreadable-run, workflow-path, repository,
completed-status) would otherwise have let the cancel through — the precise
scenario the spec's "gate gap" section says the current fixture set cannot
exercise, because `999` was never a readable target before.

### Extending the composite-shell mutation (FR-004's redundant guard)

`composite_shell_check()`'s existing `GUARD_LINE_RE`-based mutation (today:
disables the workflow-path guard) gains a second mutation targeting the
redundant `cancel_run_id != $GITHUB_RUN_ID`-shaped comparison
(contracts/composite-invocation.md) introduced by this feature. This second
mutation is run in combination with a temporary, on-disk copy of
`board_stop_check.py` carrying the decision-function-layer mutation above
(the self-cancel bug), against the new `999`-only `SHELL_CASES` entry: with
the shipped function alone, disabling the redundant shell comparison changes
nothing (the function never hands back `999` as a target, so the guard has
nothing to catch — proving the guard really is redundant under a correct
upstream); with *both* the function bug and the guard removed, the new case
must fail (`want_cancel` becomes `"999"` where the fixture expects `None`),
proving the guard is independently load-bearing as a backstop, matching
FR-004's own stated reason for keeping it ("a cancel is not recoverable by
retry"). The existing workflow-path guard mutation is unchanged and continues
to run on its own, independent of this one.

## Acceptance mapping

- User Story 1, Independent Test ("drive the decision function over the
  existing first-pass fixture... delete the no-self-cancel rule and confirm
  at least one checked-in case fails") — satisfied by the `MUTATIONS` entry
  above plus `first-pass-own-run-only.json`.
- SC-004 ("removing the no-self-cancel rule... causes at least one
  checked-in case to fail, and the gate reports which") — `mutation_check()`
  already prints which fixture(s) failed for a caught mutation; unchanged
  mechanism, new entry.
- FR-011 in full — satisfied by the two-layer proof above: a
  function-level mutation caught by a fixture with no shell involved, and a
  shell-level mutation caught only once the `999`-readable case exists,
  closing the exact gap the spec's "gate gap" section traces.
- SC-003 ("no fixture is deleted or weakened") — the fixture shape migration
  above changes representation only, never a fixture's real scenario or
  outcome.
