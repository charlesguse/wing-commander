# Contract: Gate Coverage for Spec 058

Per constitution VIII ("A Green Check Means What It Says") and FR-006,
FR-007, FR-008, FR-012, FR-032, SC-012, each gate below is a
`verify-*.py`/`.sh` script (or an amendment to an existing one) wired
into exactly one `run:` line inside a PR-triggered job of
`lint-workflows.yml`, runs the same subject with the same arguments
locally as in CI (`run-local-gates.py` picks it up automatically once
wired), and ships with the fixtures listed in `data-model.md`'s "Gate
fixtures" table. Gate numbers are assigned sequentially at
implementation time (research.md, following spec 043's own precedent);
this document uses names, not numbers.

## A. The image check

### `verify-gate-22` (amended)

**Subject**: the `verify-image-prerequisites` job body across all 13
published stages.

**Asserts** (new, in addition to today's byte-for-byte comparison): the
job carries `if: inputs.container-image != ''` at the job level,
identical across all 13.

**Fixture**: one stage with the line, one stage missing it — the second
must fail, naming the stage.

### `verify-gate-23` (amended)

**Subject**: every job in every published stage whose `needs:` includes
`verify-image-prerequisites`.

**Asserts** (new, alongside today's tool-list/entry-job-dependency
checks): the job's `if:` contains the literal comparison
`needs.verify-image-prerequisites.result != 'failure'`. A job with
`needs:` naming the check but no `if:` at all, or an `if:` that omits
this comparison (including one that narrows it back to `== 'success'`),
fails — naming the stage and the job (FR-007).

**Fixtures** (data-model.md): a bare-`needs:` reversion; an `if:` that
checks `== 'success'` instead of `!= 'failure'`.

### `verify-gate-15` self-test (extended, no production-code change)

**Subject**: unchanged — every job whose `if:` contains a status
function.

**Asserts**: unchanged logic; the self-test fixture set gains one case —
a rewritten entry job (research.md's R-A1 shape) — to prove the
existing walk actually covers the ~40 newly-rewritten jobs, not just
structurally includes them by accident of shared regex.

## B. The watchdog's clean path

### `verify-watchdog-clean-path` (new)

**Subject**: `watchdog.yml`'s `collect` job — the new deterministic
passed-inspection step, and `diagnose`'s amended `if:`.

**Asserts**:
- A `collect`-job fixture where every collector reports and the signal
  set is empty: `diagnose` is skipped, no agent step executed, and the
  full-pass wording was posted.
- A fixture with one failed collector, one reporting collector, and an
  empty signal set: `diagnose` is skipped, and the partial-pass wording
  (naming counts) was posted — the edge case spec.md names explicitly
  (FR-019, FR-011).
- A fixture where every collector fails: the pre-existing "could not
  inspect" path runs unchanged, and no passed-inspection record is
  posted (FR-013 — proves the new step does not fire here).
- A fixture where the `aggregate` step itself fails: no passed-inspection
  record is posted, regardless of what its (stale) outputs contain
  (spec.md's edge case).
- A fixture with at least one signal: `diagnose` runs, matching today's
  filing/triage/action behavior exactly (FR-012 — a regression guard,
  not new behavior).

### `verify-watchdog-no-record-on-clean-path` (new)

**Subject**: the run-summary call site inside `diagnose`.

**Asserts**: on the full-pass and partial-pass fixtures above, no
`metrics-record*` artifact is produced and the lifecycle rollup's
"every agent run appears exactly once" computation (spec 043) does not
list the run at all — never as a record that existed and could not be
retrieved (FR-031, spec.md's edge case).

### `verify-watchdog-wrapper-resolve-fold` (new or extends an existing
wrapper-shape gate)

**Subject**: `wing-commander-8-watchdog.yml`.

**Asserts**: the wrapper has exactly one job (`watchdog`), it is a bare
`uses:` call, and `run-name` is not among the inputs it passes (letting
the stage's own default/resolution apply) — and, on the stage side, that
`watchdog.yml`'s `collect` job resolves `run-name` internally when the
input is empty (FR-020).

**Fixture**: a `run-name`-omitted invocation; asserts the stage's own
resolution step ran and produced a non-empty value used in the posted
comments.

### `verify-watchdog-self-floor` (amended)

**Subject**: `verify-watchdog-run.sh`'s duration-floor and
diagnose-ceiling checks.

**Asserts**: the new healthy shape (`diagnose` skipped, passed-inspection
comment present, no execution-output artifact, no metrics record, a
whole-run duration under today's absolute floor) is verified and files
nothing. Every existing failure branch — crashed/stalled agent,
could-not-inspect degradation, fired safety net, fabricated verdict —
still fails on its own fixture (FR-032, SC-014). The checked-in
failure-path fixture harness (`verify-watchdog-run-failure-paths.sh`,
Gate 36) gains the new healthy shape as a passing case alongside its
existing failing ones.

## C. Metrics persistence

### `verify-metrics-sweep-idempotence` (new)

**Subject**: sweep mode's discover→append pipeline (research.md R-C1).

**Asserts**: a fixture with one run already persisted via the completion
trigger and one run reachable only by the sweep — after a sweep pass,
each appears in `records.jsonl` exactly once, and re-running the sweep a
second time over the same window adds nothing new (FR-022, FR-027).

### `verify-metrics-sweep-high-water-mark` (new)

**Subject**: `sweep-state.json`'s read/write cycle.

**Asserts**: a sweep run's mark advances to the latest concluded-run
timestamp it processed, in the same commit as any records append (a
fixture forcing a push rejection proves both files retry together, not
independently — research.md R-C2); a second sweep started from the
advanced mark does not re-list runs the first one already accounted for
except within the fixed one-hour overlap (research.md R-C3).

### `verify-metrics-expired-artifact-outcome` (new)

**Subject**: `unpersisted.jsonl`.

**Asserts**: a discovered run whose artifact fixture returns
expired/404 produces exactly one ledger line naming it, the high-water
mark advances past it, and a subsequent sweep does not re-list or
re-log it (FR-028).

### `verify-metrics-wrapper-trigger-drops-watchdog` (new or extends an
existing wrapper-contract gate)

**Subject**: `wing-commander-metrics-persist.yml`'s
`workflow_run.workflows` list.

**Asserts**: `"Wing Commander · 8 watchdog"` is absent from the list,
and `schedule:` is present with exactly one cron entry that does not
collide (same minute+hour) with any other scheduled workflow in the
repository (FR-030(b), FR-030(c) — a literal-list comparison, matching
the discovery-based convention this repository already uses for its
comment-canonical-pointer and wiring gates).

## Wiring assertions common to all new/amended gates

- `verify-gate-wiring.py` (existing, unchanged) picks up each new script
  automatically once it has exactly one `run:` invocation inside
  `lint-workflows.yml` — no separate manifest edit.
- Each new gate's job step carries `!cancelled()` (not bare `always()`),
  so an unrelated job's cancellation doesn't suppress it, and is not
  made conditional on any other gate's outcome (constitution VIII).
- Each gate's PR trigger path list includes the files it actually reads,
  including this feature's three contract-delta documents and
  `data-model.md`, so a documented shape that drifts from the code it
  describes is caught the same way spec 043's gates already do for their
  own contracts.
