# Quickstart: Validating the Proof Run Can Actually Start

This feature ships no user-facing command — it changes `board-loop.yml`'s
own behaviour. Validation is: run the gate suite locally (it is the same
set CI runs, CLAUDE.md "Before pushing"), then exercise the real workflow
in Actions per Story 1's independent test.

## Prerequisites

- A checkout of this repository with `.github/scripts/board_prove.py`,
  `.github/scripts/board_eligibility.py`, `.github/scripts/board_stand_down.py`,
  and `.github/workflows/board-loop.yml` at the versions this feature ships.
- `python3`, `gh` (authenticated, for the live-run scenarios only), and
  this repo's usual local gate dependencies (`pyyaml`, etc., already
  required by `board_prove.py`/`verify-board-prove.py`).

## 1. Local gate suite (every user story, fixture-level)

```
python .github/scripts/run-local-gates.py
```

Expect green, including:

- Gate 89 (`verify-board-prove.py`), extended by this feature with
  `directed_stage()`, `joins_directed_group()`, and
  `directed_proof_group_busy()` fixtures per outcome_reason
  (contracts/proof-outcome-taxonomy.md), each with a passing and a failing
  direction (FR-020), plus the existing real-tree assertion widened to
  cover job-level reachability (FR-021, research.md D5).
- The new gate covering FR-016/SC-006's concurrency-guarantee sentence
  match across `board-loop.yml`'s comments,
  `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`, and
  `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`.
- The new gate (or Gate 89 extension) covering D7's structural assertion
  that `aimable_jobs` excludes `select`/`route`/`fix`.
- `board_prove_displacement.py`'s own fixture gate (FR-010b).

Each of these MUST also be run with the mutation each gate exists to
catch (Principle VIII, FR-020) — e.g. temporarily widen `aimable_jobs` to
include `"fix"` and confirm D7's gate fails; temporarily point
`prove-gate`'s directed branch at `wing-commander-board-loop` instead of
the `-directed-proof` group and confirm the concurrency-guarantee gate
fails.

## 2. Story 1 — an Actions-only fix gets a proof run that starts (Independent Test)

1. Merge a fix PR that changes only Actions-only behaviour reachable from
   the loop and whose changed path resolves (research.md D1) to the
   `prove` job specifically — e.g. a change to
   `board-loop.yml`'s own "Record the proof outcome" step, or to
   `board_prove.py` itself.
2. Watch `prove-gate`/`prove` run on the `pull_request: closed` trigger.
   Confirm the `decide` step's `redrive-workflow` output is `board-loop.yml`
   and a new `directed-stage` output is `prove`.
3. Confirm the busy-check step reports `group-busy: false`, then the
   `redrive` step dispatches successfully.
4. In the Actions tab (or `gh run list --workflow=board-loop.yml`), confirm
   the dispatched run's `status` moves out of `queued` **while the
   dispatching run is still in progress** — this is the deadlock's actual
   regression test; today's tree cannot pass this step at all (spec.md
   "The deadlock").
5. Confirm the dispatched run reaches a terminal `conclusion` inside the
   dispatching run's wait budget, and that the issue records the run URL
   and conclusion (success → closes; failure → stays open, per
   contracts/proof-outcome-taxonomy.md).

## 3. Story 2 — distinct no-proof reasons (Independent Test)

Force each condition and read the resulting issue comment; each must name
its own distinct reason from contracts/proof-outcome-taxonomy.md's table,
never collapse into another:

- **group-busy**: dispatch a directed proof run manually
  (`gh workflow run board-loop.yml -f directed-stage=triage -f
  directed-issue=<N>`) and, before it completes, trigger a second merge's
  prove step against a different issue whose changed path also resolves to
  a directed stage. The second's issue comment must say `group-busy`, not
  time out silently.
- **not-started** / **unfinished**: not independently forceable without a
  runner-capacity artifice; covered at the fixture level (step 1) by
  feeding `board_prove.py`'s outcome function synthetic `gh run view`
  payloads for each case.
- **displaced**: same fixture-level coverage — a `gh run list` payload with
  no matching row after a successful `gh workflow run` call.
- **no-target**: merge a PR touching only a `.github/scripts/board_*.py`
  helper whose only executor (per the job-uses-graph) is `select`
  (excluded from the aimable set, research.md D2) — confirm the issue
  records `no-target`, not `nothing-reaches`.
- **nothing-reaches**: merge a PR touching a path no workflow references at
  all (a scratch file under a directory nothing scans) — confirm
  `nothing-reaches` is recorded, unchanged from today.

## 4. Story 4 — a board helper merge is reachable (Independent Test)

Merge a PR changing only `.github/scripts/board_item_marker.py`. Confirm
the `decide` step's `reason` output cites a real executing job (via the
job-uses-graph, research.md D5) rather than "no changed paths"/"nothing
reaches this change," and that the same target is chosen on a second,
independent run over the identical merge (FR-015's determinism).

## 5. Story 5 — the concurrency guarantee still holds (Independent Test)

While a directed proof run (from step 2) is in flight, trigger the hourly
schedule tick manually (`gh workflow run board-loop.yml`, no
`directed-stage`). Confirm:

- the schedule-triggered run's `select` job either runs and picks an
  eligible issue *other than* the one the directed run is proving, or
  queues in `wing-commander-board-loop` if another ordinary run already
  holds it — never races the directed run for the same issue;
- the directed run's own progress is unaffected (different group);
- neither run closes an issue the other is acting on.
