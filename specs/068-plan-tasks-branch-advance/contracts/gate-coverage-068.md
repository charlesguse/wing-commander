# Contract: Extended Gate Coverage for Spec 068

Per constitution VIII and FR-020–FR-022, every item below extends an
existing, already-wired `verify-*.py` gate — same script, same
`lint-workflows.yml` step, new fixtures/assertions. This feature adds no
new gate script and no new `lint-workflows.yml` wiring (FR-022 is
satisfied by construction: nothing new needs registering).

## `verify-metrics-record-schema.py` (Gate 39, extended — fixtures only, no code change)

**Subject**: unchanged — `contracts/metrics-record-schema.md`'s declared
shape (now further amended by `metrics-record-schema-delta.md`'s
prose-only change), checked against fixture JSON files.

**Why no code change**: the group's shape, its `REQUIRED_BRANCH_ADVANCE`
map, and the optional-at-top-level special case are already stage-
neutral (specs/050 shipped them that way for exactly this follow-up).
Nothing about "which stage populated this record" or "what mode it ran
in" is a distinct schema field — `branch` is a plain string, indifferent
to whether it holds `spec/<slug>` or `plan/<slug>`.

**New fixtures** (research.md R8; data-model.md's Gate fixtures table):
- `valid-branch-advance-branch-created-from-this-commit.json` — schema-
  identical to the existing both-present-different fixture; named
  separately so FR-020's "a run that created the branch it advanced" case
  has its own checked-in fixture, not only an incidental subsumption.
- `valid-branch-advance-persistent-branch.json` — `branch:
  "spec/068-plan-tasks-branch-advance"`.
- `valid-branch-advance-review-branch.json` — `branch:
  "plan/068-plan-tasks-branch-advance"`.

All three validate (positive cases) under the unchanged validator. The
eight fixtures specs/050 already shipped (both-present-different,
both-present-equal, before-unavailable, after-unavailable,
backwards-reset, commits-unavailable, both-unavailable, and the seven
wrong-typed negatives covering each sub-field) already satisfy every
other state FR-020 lists — reused, not duplicated.

## `verify-metrics-summary-record-emission.py` (Gate 43, extended)

**Subject**: unchanged — the real, shipped `wing-commander-metrics-
summary` composite, invoked end-to-end.

**New asserts**:
1. `implement.yml`'s refactored branch-advance call site (now sourcing
   `after-sha`/`commits` from the new `wing-commander-branch-advance`
   composite rather than inline bash) still produces a record with
   byte-identical `branch_advance` values to the pre-refactor step, for
   the same fixture inputs — the regression proof FR-011 requires
   ("Implement's own recorded values MUST be unchanged by the move").
2. `plan.yml`'s new call site's own inputs (an `auto`-mode `branch` value
   and a `pr`-mode one, each with populated before/after/commits and an
   intentionally-absent transcript path) each produce a record with
   `record_available: false` and `branch_advance.available: true` with
   the exact values passed in.
3. Same as 2, for `tasks.yml`'s new call site.
4. The existing "N invocations per job" shape assertions for `plan.yml`
   and `tasks.yml` become two (was one), matching each file's actual
   shape after this feature; `implement.yml`'s stays four (unchanged
   count, refactored internals).

## `verify-branch-drift-sha-baseline.py` (Gate 53, extended)

**Subject**: unchanged — the real, shipped `collect-branch-drift` step's
bash text, run via the existing harness against synthetic run-metadata/
metrics-record JSON and (for the since-created arm) a local git
repository.

**New asserts** (research.md R9; data-model.md's Gate fixtures table):
1. A plan run (`RUN_NAME = "Wing Commander · 3 plan"`), downloaded record
   `branch_advance.available: true`, `branch: "plan/068-..."`,
   `before_sha == after_sha` → `class-hint: "lost-progress"` naming the
   `plan/` branch, both SHAs, and the recorded `commits`.
2. A tasks run, same shape, `before_sha != after_sha` → no signal.
3. A plan run whose downloaded artifact set carries no
   `branch_advance.available: true` record → **no signal is emitted, and
   the since-created fallback is asserted NOT to fire** (distinguishing
   this from implement's own no-record case, which does fall back) — the
   step summary text is asserted to name "no recorded branch-advance
   evidence... skipping."
4. Same as 3, for a tasks run.
5. (Regression, unchanged) A spec-branch-head run and a non-push-expected
   stage remain unaffected by any of the above.

**Fixture**: synthetic run-metadata/record JSON inline in the harness's
Python, matching the existing style for cases 1/2 of the base gate — no
new fixture files needed, since the records are literal Python dicts the
harness already builds for the implement cases.

## `verify-single-home-idioms.py` (Gate 60, extended — new check)

**Subject**: unchanged — every workflow and composite action under
`.github/workflows/**` and `.github/actions/**`.

**New check**: `branch-advance-capture` — co-occurrence, file-wide, of
the refspec-form `git fetch origin "+refs/heads/$` fragment and the
`..`-range `git rev-list --count "$` fragment (research.md R10).
Declared home: `.github/actions/wing-commander-branch-advance/
action.yml`. Added to `DECLARED_HOMES`, `ALL_CHECKS`, and `CHECK_NAMES`
following the existing pattern of every other entry in the module; the
gate's own hard-failure check ("declared home exists on disk") covers
the new entry automatically once the composite is added.

**Self-test additions**: `selftest_clean_tree_passes` gains the new
home's shipped shell in its clean-tree fixture (mirroring every other
`DECLARED_HOMES` entry); a new
`selftest_third_paste_fails("branch-advance-capture", ...)` call proves
a third paste of the two fragments outside the declared home fails,
naming it.

## Wiring assertions common to all four

- `verify-gate-wiring.py` (existing, unchanged) confirms all four scripts
  still have exactly one `run:` invocation in `lint-workflows.yml` — this
  feature adds no new invocation, since it extends four already-wired
  gates.
- Every extended gate's job step already carries `!cancelled()` (not
  bare `always()`) and is not conditional on any other gate's outcome —
  unchanged, verified by inspection, no new assertion needed.
- Gate 39's and Gate 43's PR trigger path lists already include
  `.github/actions/wing-commander-metrics-summary/**` and
  `.github/workflows/{implement,plan,tasks}.yml` — this feature's edits
  land inside paths those gates already watch. Gate 53's PR trigger path
  list already includes `.github/workflows/watchdog.yml`. Gate 60's
  scan is file-system-wide by construction (`all_subject_files()`), so
  the new composite is discovered automatically once it exists — no
  trigger-path edit needed for any of the four.
