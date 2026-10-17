# Implementation Plan: A Not-Ready PR Releases the Board

**Branch**: `spec/093-not-ready-board-release` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/093-not-ready-board-release/spec.md`

## Summary

A not-ready readiness outcome currently posts a comment and writes no
marker at all, leaving the newest marker at `step=readiness` with the PR
still `OPEN` — exactly the shape `in_flight_candidate()` prefers above
every other candidate. This wedges the board on any not-ready outcome a
later run cannot clear on its own.

The fix extends the existing board item marker (never a new store,
`spec.md` Assumptions) with a not-ready record — the PR, the evaluated
head SHA, whether the unmet condition is self-clearing or durable, and a
running count — written on every not-ready outcome. `board_eligibility.py`
(the FR-011 single home for in-flight detection) gains one new hold
predicate, consulted by both `in_flight_candidate()` and `select()`'s
fallback, mirroring the existing `_awaiting_merge_holds()`/
`_unowned_open_pr_holds()` precedent: a **durable** not-ready record whose
PR head is unchanged holds the item out of selection; a **self-clearing**
one never holds. Three not-ready outcomes on the same PR (the count,
carried in the marker across a head-move re-admission the same way
`round`/`base_sha` already are) hand the item to a human through spec 057
FR-030's existing `board:stalled` mechanism — no second handover
mechanism. A re-admission on a moved head resumes at `review`, continuing
rather than resetting the fix→review round budget.

## Technical Context

**Language/Version**: Python 3.11 (`.github/scripts/*.py`, no third-party
dependencies — matches every existing board-loop script); Bash + `jq`
(`.github/workflows/board-loop.yml` `run:` steps, GitHub Actions'
`ubuntu-latest` toolchain).

**Primary Dependencies**: `gh` CLI (issue/PR/comment reads and writes),
`jq` (already-vendored JSON manipulation in workflow `run:` steps). No new
dependency.

**Storage**: None — the not-ready record rides the existing board-item
marker (an HTML-comment-embedded JSON blob on a GitHub issue comment) and
the existing issue-comment convention, per `spec.md` Assumptions ("plan
stage's decision, not this specification's").

**Testing**: `.github/scripts/verify-board-eligibility.py` (Gate 81,
checked-in fixture directories under
`.github/scripts/tests/board-eligibility/`), extended with new fixture
cases (no new gate, FR-013). `.github/scripts/verify-board-loop-resume-gating.py`
(Gate 97, a static `if:`-expression check plus an executed simulation of
the resume step's `step_resolution_json` heredoc against `RESUME_CASES`),
extended with new cases and, per FR-013, a self-test mutation proving the
not-ready site's record write is exercised. `python .github/scripts/run-local-gates.py`
runs the full PR-time gate suite these belong to.

**Target Platform**: GitHub Actions (`ubuntu-latest`), triggered by
`board-loop.yml`'s schedule/`workflow_dispatch`.

**Project Type**: Single project — this is one repository's own CI
automation (`.github/scripts/`, `.github/workflows/`), not an
application with separate frontend/backend trees.

**Performance Goals**: No new API round-trip per item (Assumptions): the
PR head SHA the hold needs is read from the same per-PR `gh api
repos/:owner/:repo/pulls/:number` call the select job's existing PR-state
lookup already makes.

**Constraints**: One board item in flight repository-wide (spec 060,
unchanged). Every new rule provable by a checked-in fixture or gate
self-test mutation with no live run (FR-013, Constitution VIII). No new
gate (FR-013) — the existing eligibility gate (Gate 81) and resume-gating
gate (Gate 97) are extended.

**Scale/Scope**: Three files gain new logic
(`.github/scripts/board_eligibility.py`, `.github/scripts/board_readiness.py`,
`.github/scripts/board_item_marker.py`); one workflow
(`.github/workflows/board-loop.yml`) gains changes across three jobs
(`select`'s PR lookup and resume step, `review`'s three marker-writing
sites, `readiness`'s not-ready-report and handover sites); two gates
extended (Gates 81, 97); three live contracts corrected in place (FR-014:
`specs/057-autonomous-board-loop/contracts/readiness-report.md`,
`specs/061-marker-owned-in-flight/contracts/in-flight-detection.md` and
`contracts/resume-recovery.md`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I (Guide)**: This feature is itself dogfooded through the pipeline —
  spec, plan, tasks, implement, finalize on lifecycle issue #717. PASS.
- **II (Cost-Conscious Model Tiering)**: No new agent invocation; this
  feature changes deterministic selection/readiness code and workflow
  `run:` steps only, all pre-existing job/model assignments (`readiness`,
  `review-fixup` reuse `resolve-model`'s output unchanged; the readiness
  job runs no agent at all, unchanged). PASS.
- **III (Simple, GitHub-Native Interaction)**: The hold, the count, and
  the handover are all visible on the lifecycle issue's own comments and
  the `board:stalled` label — no new surface. PASS.
- **IV (Automation-First)**: The only manual step this feature adds is the
  one FR-008 already requires (removing `board:stalled`), which spec 057
  FR-030 established and this feature reuses rather than duplicates. PASS.
- **V (Security)**: No new trust boundary. The not-ready record is written
  only by the loop's own deterministic code from live GitHub state
  (checks rollup, PR head SHA) — never from issue/comment prose (FR-002,
  Key Entities "Not-Ready Record"). PASS.
- **VI/VII (Portability / Two Interfaces)**: `board-loop.yml` is this
  repository's own consuming-instrument wrapper workflow (not a published
  `workflow_call` stage), so this change is confined to the consuming
  instrument. `.github/scripts/*.py` are read from this repository's own
  checkout already. No published contract surface changes. PASS.
- **VIII (A Green Check Means What It Says)**: FR-013/SC-006 require a
  checked-in fixture or self-test mutation for every new rule, reusing
  Gates 81 and 97 rather than adding an unreachable one. PASS (verified in
  Phase 1 design below; enforced at tasks/implement time).
- **IX (Judgment That Gates a Durable Action Belongs in Deterministic
  Code)**: The hold decision, the self-clearing/durable classification,
  and the threshold check are all pure functions in
  `board_eligibility.py`/`board_readiness.py`, never an agent's reading of
  the rollup or the marker (FR-003, FR-005). PASS.
- **X (Bounded Autonomy)**: This feature does not change what the loop may
  merge (FR-010, Out of Scope: merging). It changes only which item is
  selected and when a not-ready item hands over — squarely the "fix,
  review" shape already in scope for the board loop's own bounded work.
  PASS.

No violations. Complexity Tracking is not filled.

## Project Structure

### Documentation (this feature)

```text
specs/093-not-ready-board-release/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── contracts/
│   └── not-ready-hold.md # Phase 1 output — this feature's own contract
├── quickstart.md         # Phase 1 output
└── spec.md               # Input (not edited by this stage)
```

### Source Code (repository root)

```text
.github/
├── scripts/
│   ├── board_eligibility.py   # + NOT_READY_THRESHOLD, not-ready-record
│   │                           #   parsing, _not_ready_holds(), consulted
│   │                           #   by in_flight_candidate() and select()
│   ├── board_readiness.py     # evaluate_from_snapshot() gains an
│   │                           #   unmet-condition class (self-clearing |
│   │                           #   durable), derived from the rollup's own
│   │                           #   per-entry states
│   ├── board_item_marker.py   # write_marker()/main() gain nr_count/
│   │                           #   nr_head_sha/nr_class fields (only
│   │                           #   meaningful on a `readiness`/`stalled`
│   │                           #   marker); add_stalled_label() call sites
│   │                           #   for THIS feature's handover pass pr +
│   │                           #   nr_head_sha, unlike every other stall
│   │                           #   site
│   └── tests/board-eligibility/
│       └── in-flight/          # + new fixture directories (FR-013)
└── workflows/
    └── board-loop.yml          # select job: PR lookup gains head-sha
                                 #   capture; resume step gains a
                                 #   review-vs-readiness clause for a
                                 #   moved/unmoved head
                                 # review job: three marker-writing sites
                                 #   thread nr_count through unchanged
                                 # readiness job: not-ready-report site
                                 #   writes the not-ready marker/dedups the
                                 #   comment (FR-009)/applies the handover
                                 #   at threshold (FR-008)

specs/057-autonomous-board-loop/contracts/readiness-report.md   # FR-014
specs/061-marker-owned-in-flight/contracts/in-flight-detection.md   # FR-014
specs/061-marker-owned-in-flight/contracts/resume-recovery.md   # FR-014
```

**Structure Decision**: Single project — this feature extends three
existing scripts and one existing workflow in place; it adds no new
top-level component and no new gate (FR-013). The two structural
additions are the fixture directories FR-013 requires (siblings of the
existing ones, same shape) and this spec's own `contracts/not-ready-hold.md`,
which documents the new hold/count/handover logic that spans
`board_eligibility.py`, `board_readiness.py` and `board_item_marker.py`
(no single existing contract owns all three).

## Complexity Tracking

*No entries — Constitution Check reported no violations.*
