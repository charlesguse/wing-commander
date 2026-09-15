# Quickstart: Validating the Exact-SHA Branch-Drift Baseline

Prerequisites: a checkout of this repository, Python 3, `bash`, `jq`,
`git` on `PATH` — the same prerequisites every existing shell-harness
gate documents. Every scenario below is mechanically verifiable
**locally**, without a live triggered `implement`/`watchdog` run — this
feature's coverage strategy (research.md R9) is built on fixture JSON,
local git repositories, and the real shipped `run:` text of both
affected workflows.

## Scenario 1 — A pushed-nothing cycle is caught, even after a rebase (US1; FR-001–FR-003, FR-010, FR-011, SC-001, SC-003)

```
python3 .github/scripts/verify-branch-drift-sha-baseline.py
```

Runs the new gate's scenario 1: a `branch_advance` record with
`before_sha == after_sha`. Confirm the harness reports a
`lost-progress` signal naming the branch, both SHAs, and the recorded
commit count.

**Expected**: SC-001/SC-003 hold — the verdict is read from the two
recorded SHAs alone, so the same fixture, re-inspected with the local
git repository's branch state mutated to simulate an intervening
rebase (differing committer dates, a different current tip), produces
byte-for-byte the same verdict. This is the direct fixture proof for
the case that could previously only be demonstrated on a real run
(34709026525) after the fact.

## Scenario 2 — A cycle that pushed is not flagged, even if a later run has already pushed by inspection time (US2; FR-010, SC-001, SC-003)

```
python3 .github/scripts/verify-branch-drift-sha-baseline.py
```

Scenario 2: `before_sha != after_sha`. Confirm no signal is emitted,
and confirm this holds regardless of what the local git fixture's
*current* branch tip is set to (simulating a second run having already
pushed past both recorded points) — the collector never reads the
branch's current state for this arm at all.

**Expected**: SC-001 holds for the healthy case (zero false detections)
and SC-003 holds independent of inspection timing.

## Scenario 3 — A record with no usable branch evidence falls back visibly (US3; FR-013, FR-017, FR-018)

```
python3 .github/scripts/verify-branch-drift-sha-baseline.py -v
```

Scenario 4 (verbose): a synthetic `metrics-record*` artifact set with no
`branch_advance.available: true` record. Confirm the harness falls back
to the since-created mechanism unchanged, and that the step summary
text names the fallback explicitly.

**Expected**: FR-017/FR-018 hold — detection never regresses below
today's baseline for a record that lacks the new evidence, and the
reader can tell which baseline produced the reported outcome (SC-007).

## Scenario 4 — The record schema round-trips every new-field state (SC-004, SC-005)

```
python .github/scripts/run-local-gates.py gate-39
```

(or `python3 .github/scripts/verify-metrics-record-schema.py
--self-test` directly). Confirm all `branch_advance` fixtures — both
points present+different, both present+equal, before-unavailable,
after-unavailable, commits:0 with differing points, commits-unavailable,
a wrong-typed field, and a record with no `branch_advance` key at all —
validate or reject exactly as data-model.md's fixture table states.

**Expected**: SC-004 holds — every new-field state is proven by a
checked-in fixture, not only by a live run. SC-005 holds via the last
fixture (a pre-feature record with no `branch_advance` key still
validates).

## Scenario 5 — The real composite emits a conforming fourth record (SC-002, SC-005)

```
python .github/scripts/run-local-gates.py gate-43
```

Confirm the extended Gate 43 asserts the real `wing-commander-metrics-
summary` composite, invoked with `implement.yml`'s new fourth call
site's own inputs, produces `record_available: false` (no transcript
was given) alongside `branch_advance.available: true` with the exact
values passed in.

## Scenario 6 — Persistence is unaffected by the new fields (FR-009)

```
python .github/scripts/run-local-gates.py gate-41
```

Confirm the extended Gate 41 still passes with a `branch_advance`-
carrying record mixed into its append/dedup/retry fixtures.

## Scenario 7 — No agent invocation was added (SC-006)

```
python3 .github/scripts/verify-actions-layer-invariants.py
```

(specs/043's existing gate, unchanged — confirms no scanned
`action.yml` under `.github/actions/**`, including the edited
`wing-commander-metrics-summary`, invokes `claude-code-action`.) A
`grep -c "uses: anthropics/claude-code-action" .github/workflows/
implement.yml` before/after this feature's diff should also report the
same count (three) — the fourth `wing-commander-metrics-summary` call
site is not an agent step.

## Full local gate run

```
python .github/scripts/run-local-gates.py
```

Runs the complete PR-time gate suite, matching what CI runs
(`lint-workflows.yml`), including every gate this feature extends or
adds.
