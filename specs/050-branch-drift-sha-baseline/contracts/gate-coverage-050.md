# Contract: New/Extended Gate Coverage for Spec 050

Per constitution VIII and FR-008/FR-009, each item below is either an
extension of an existing `verify-*.py` gate (same script, same
`lint-workflows.yml` wiring, new fixtures/assertions) or, for genuinely
new shipped behavior no existing gate exercises, a new script wired into
exactly one `run:` line inside a PR-triggered job of `lint-workflows.yml`
— reachable through `wc_gate_registry.py` automatically once wired, no
second registration point (`run-local-gates.py` picks it up the same
way). Gate numbers below for the new gate are provisional — assigned
sequentially at implementation time from the highest number in use in
`lint-workflows.yml` (52 at plan time; research.md R9).

## `verify-metrics-record-schema.py` (Gate 39, extended)

**Subject**: unchanged — `contracts/metrics-record-schema.md`'s declared
shape (now including `metrics-record-schema-delta.md`'s addition),
checked against fixture JSON files, plus the contract/code cross-check
(`check_fields_match_contract`).

**New asserts**: the `branch_advance` group's eight sub-fields are
required, correctly typed, and its presence in the code's `REQUIRED_*`
maps matches its presence in the contract's `## Shape` block exactly (so
this feature's own contract edit and code edit must land together or
Gate 39 fails by construction — the same mechanism that already governs
every other field). A record with no `branch_advance` key at all still
validates (the group is optional at the top level, unlike existing
required groups — this is the one new nesting rule Gate 39's field-
presence check must special-case, since every existing top-level group
in `REQUIRED_TOP` is unconditionally required).

**Fixtures** (data-model.md's Gate fixtures table has the full list):
both points present+different; both present+equal; before-unavailable;
after-unavailable; commits:0 with differing points; commits-unavailable
with both points present; a wrong-typed field (negative); a record with
no `branch_advance` key at all (positive — must still validate).

## `verify-metrics-summary-record-emission.py` (Gate 43, extended)

**Subject**: unchanged — the real, shipped `wing-commander-metrics-
summary` composite, invoked end-to-end.

**New asserts**: a fourth invocation, matching `implement.yml`'s new
"Record branch advance (cycle)" step's own inputs (populated `branch`/
`before-sha`/`after-sha`/`commits` inputs, an intentionally-absent
transcript path), produces a record with `record_available: false` (the
transcript-missing path, already covered for the other three call
sites) AND `branch_advance.available: true` with the exact values
passed in — proving the two degrade paths (transcript, branch-advance)
are independent, per data-model.md. The existing "three invocations per
job" shape assertion becomes four, matching `implement.yml`'s actual
shape.

## `verify-metrics-persist-retry.py` (Gate 41, extended)

**Subject**: unchanged — the shipped append-with-retry composite,
against local bare git repositories.

**New assert**: one of the existing case functions' fixture batch gains
a record carrying a populated `branch_advance` group; append, dedup (by
`record_key`, unaffected by any other field), and the concurrent-writer
retry path all behave identically to a batch without it (FR-009).

## `verify-branch-drift-sha-baseline.py` (new — provisional Gate 53)

**Subject**: the real, shipped `collect-branch-drift` step's bash text
(`watchdog.yml`), run via a `wc_shell_harness.py`-style harness against
a local git repository (for the `git fetch`/`rev-list` calls the
since-created fallback still performs) and synthetic run-metadata /
metrics-record JSON (for the exact-SHA arm, which needs no live git
state at all — research.md R7).

**Asserts**:
1. `branch_advance.available: true`, `before_sha == after_sha` →
   `class-hint: "lost-progress"` signal naming the branch, both SHAs,
   and the recorded `commits` (US1 AS1).
2. Same, `before_sha != after_sha` → no signal (US1 AS3).
3. Same as 1, but the inspected spec's lifecycle already reads
   `stalled` (or the `STALLED_LABEL` input is `true`) → the
   `alreadyHandledBy` shape, not a bare `lost-progress` class-hint (US1
   AS4, FR-014).
4. No record in the downloaded artifact set carries
   `branch_advance.available: true` → the since-created fallback fires
   unchanged, and the step summary names it as the fallback (US3,
   FR-013, FR-018).
5. A spec-branch-head run (`plan`/`tasks`) and a non-push-expected
   stage are unaffected by any of the above (FR-012 regression check).
6. A run whose `RUN_CREATED_AT`/slug cannot be resolved still exits
   quietly (pre-existing behavior, unaffected — regression check only).

**Fixture** (negative case, proving the gate actually fails on the
defect it exists to catch): a mutated collector that re-derives
`commits` via `rev-list` instead of reading the record's own value is
asserted to fail assertion 1's exact-count check when the fixture's
local git state is deliberately set up so a live walk would disagree
with the recorded value (proving the "no re-walk" invariant, FR-019, is
actually load-bearing and not just documentation).

## Wiring assertions common to all four

- `verify-gate-wiring.py` (existing, unchanged) picks up the new script
  automatically once it has exactly one `run:` invocation inside
  `lint-workflows.yml` — no separate manifest edit.
- The new gate's job step carries `!cancelled()` (not bare `always()`),
  matching this repository's existing step-gating convention, and is
  not conditional on any other gate's outcome.
- The new gate's PR trigger path list includes
  `.github/workflows/watchdog.yml` (already covered) and this feature's
  own fixture directory, if one is added under
  `.github/scripts/fixtures/`.
- Gate 39's PR trigger path list already includes
  `specs/043-durable-metrics-record/contracts/metrics-record-schema.md`
  — no change needed there, since this feature edits that same file
  in place (via `metrics-record-schema-delta.md`'s content) rather than
  adding a new contract document Gate 39 would need to learn about.
