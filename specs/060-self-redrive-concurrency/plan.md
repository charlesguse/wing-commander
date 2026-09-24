# Implementation Plan: The Proof Run Can Actually Start — Self Re-Drive vs. the Board Loop's Own Concurrency Group

**Branch**: `060-self-redrive-concurrency` | **Date**: 2026-09-24 | **Spec**: [specs/060-self-redrive-concurrency/spec.md](./spec.md)

**Input**: Feature specification from `/specs/060-self-redrive-concurrency/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`board-loop.yml`'s `prove` step re-drives a changed behaviour into the same
workflow-level concurrency group the dispatching run itself already holds,
so the dispatched run can never leave `queued` before the caller gives up
waiting (spec.md "The deadlock"). The fix is not a bigger wait or a bare
separate group (both rejected by the owner's answered questions, spec.md
"What the owner decided") but a **directed proof run**: `board-loop.yml`
gains a `directed-stage` dispatch input that runs exactly one job
(`triage`/`review`/`readiness`/`prove`) against a caller-supplied issue,
selects no board item, opens no fix PR, and — because it takes no board
item — joins a *separate* concurrency group
(`wing-commander-board-loop-directed-proof`) instead of
`wing-commander-board-loop`, so it can start while the dispatching run is
still alive. A new pre-dispatch pair of checks (FR-001 static, FR-001a
dynamic against the Actions API) replaces "dispatch and observe a timeout"
with "know in advance whether this can even start." The existing
three-branch success/failure/uncorrelated outcome recording becomes an
eight-reason taxonomy (contracts/proof-outcome-taxonomy.md) so a maintainer
reading the issue can always tell which of "not proven," "could not
start," "nothing reaches this," "no directed run reaches this," or "the
loop's own dispatch got displaced" actually happened. The reachability
graph `board_prove.py` already builds is extended to resolve
`.github/scripts/board_*.py` Python-import references (FR-014), which is
now safe to route more merges through only because the group split ships
in the same feature. Every new branch is deterministic Python
(`board_prove.py` and one new sibling module), covered by the existing
Gate 89 fixture-and-real-tree-assertion pattern, never an agent's
judgment (Principle IX).

## Technical Context

**Language/Version**: Python 3.11 (`.github/scripts/board_prove.py` and
siblings), Bash (workflow `run:` steps), YAML (`board-loop.yml` and the
`wing-commander-dispatch-and-wait` composite) — the same three languages
spec 057's own plan used; this feature adds no new one.

**Primary Dependencies**: `PyYAML` (already a `board_prove.py` dependency,
`yaml.safe_load` over the checked-out workflow tree), the `gh` CLI (already
the composite's and `board_stand_down.py`'s dependency for `gh run list`/`gh
workflow run`), GitHub Actions' own `concurrency:` and `workflow_dispatch`
primitives. No new external package.

**Storage**: N/A — GitHub Issues/PRs/Actions runs are the only durable
state, exactly as spec 057. This feature adds no database, file, or cache;
`directed_proof_group_busy()`'s occupancy check and
`board_prove_displacement.py`'s detection both read live Actions/Issues
state fresh on every call rather than caching it (constitution: every
durable action re-derives from live state).

**Testing**: This repo's own gate registry
(`.github/scripts/run-local-gates.py`, `.github/workflows/lint-workflows.yml`),
invoked identically locally and in CI (Principle VIII). New/extended gates
follow Gate 89's (`verify-board-prove.py`) existing pattern: inline
fixtures covering each branch in both directions (FR-020), plus a
real-tree assertion against the repository's own checked-out
`board-loop.yml` (FR-021) — not synthetic fixtures alone, which is exactly
what let the original dispatchable-set bug (PR #451's fix) ship silently
green.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), this
repository's own consuming-instrument layer (`board-loop.yml` carries no
`workflow_call` trigger — contracts/board-loop-workflow.md — so nothing
here touches the published stage contract, Principle VII).

**Project Type**: CI-native automation (a GitHub Actions workflow plus its
supporting Python scripts and composite actions) — not an application with
a runtime server or a UI.

**Performance Goals**: SC-005 — a proof run that cannot start must be
recognized in the time the deterministic pre-dispatch checks (FR-001's
tree read, FR-001a's one `gh run list` call) take, not the ~11-minute
correlate-then-wait budget `wing-commander-dispatch-and-wait` currently
burns before reporting `timeout`.

**Constraints**: Principle IX (every branch above is deterministic Python,
never an agent's judgment); Principle VIII (every new gate must be
reachable through the registry, run the same subject locally as in CI, and
fail loudly rather than pass vacuously); the Out of Scope list (no change
to `wing-commander-dispatch-and-wait`'s own correlation mechanism, to
`release.yml`'s dispatchability, or to the round budget/turn ceilings);
CLAUDE.md's single-home rule (the reachability scan, the concurrency-group
decision, and the outcome taxonomy each get exactly one home in
`board_prove.py` or its one new sibling module, never re-pasted into the
workflow's own shell).

**Scale/Scope**: One workflow (`board-loop.yml`, 2811 lines, 9 jobs) gains
3 new `workflow_dispatch` inputs, per-job `concurrency:` blocks replacing
its one workflow-level block, and `if:`/step edits to `select`,
`triage`/`review`/`readiness`, `prove-gate`, and `prove`. One existing
module (`board_prove.py`, 202 lines) gains ~4 new functions. One new
sibling module (`board_prove_displacement.py`, FR-010b). One existing gate
(`verify-board-prove.py`, Gate 89) is extended; 1-2 new gates are added for
the concurrency-guarantee-sentence match (SC-006) and the aimable-jobs
structural assertion (FR-017) unless folded into Gate 89 — left to
`tasks.md` to decide which keeps CLAUDE.md's single-home rule cleanest.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: PASS. This feature is specified, planned, and will be
  implemented through this repository's own pipeline; its lifecycle issue
  is #460.
- **II. Cost-Conscious Model Tiering**: PASS (N/A). No new Claude
  invocation is added — every new branch is deterministic Python/Bash. The
  plan stage itself runs on the sonnet tier per this repository's own
  tiering.
- **III. Simple, GitHub-Native Interaction**: PASS. Every new outcome
  (group-busy, not-started, unfinished, displaced, no-target) is posted to
  the originating issue as a comment; nothing requires a dashboard.
- **IV. Automation-First**: PASS. No new manual step. The directed-stage
  mechanism is dispatched by the existing `prove` job automatically; a
  human never invokes it directly except to reproduce a scenario locally
  (quickstart.md).
- **V. Security**: PASS. `directed-issue`/`directed-pr`/`directed-stage`
  are `workflow_dispatch` inputs, gated the same way `attempt-token`
  already is (a maintainer-trusted trigger); `prove-gate`'s directed path
  re-derives `MERGED`/marker state live from `gh pr view`/issue comments
  rather than trusting the dispatch inputs themselves, exactly as the
  event path already does — no new untrusted-content surface.
- **VI. Portability**: PASS. All changes stay inside this repository's own
  `board-loop.yml` wrapper and its `.github/scripts/` helpers, never a
  published `workflow_call` stage.
- **VII. Two Interfaces**: PASS. `board-loop.yml` carries no
  `workflow_call` trigger today and gains none. `wing-commander-dispatch-and-wait`
  (a composite consumed by both `board-loop.yml` and `auto-release.yml`)
  is not modified — Out of Scope explicitly forbids changing its
  correlation mechanism, and this feature's new inputs pass through its
  existing generic `workflow-inputs` JSON parameter without any schema
  change to the composite itself.
- **VIII. A Green Check Means What It Says**: PASS, and directly on point
  — FR-020/FR-021/SC-006/SC-008 require every new branch be
  gate-registry-reachable, exercised in both directions by a fixture, and
  checked against the repository's own real tree, which is the exact
  discipline that would have caught the dispatchable-set bug this feature
  fixes had it existed before PR #451.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: PASS, and the organizing constraint of this whole plan — the
  directed-stage choice, the concurrency-group choice, the busy-check, the
  outcome-reason taxonomy, and the displacement detection are all pure
  Python functions in `board_prove.py`/`board_prove_displacement.py`,
  never a workflow's own shell `if`/`elif` chain (research.md D6) and
  never left to an agent.
- **X. Bounded Autonomy — The Pipeline Works Its Own Board**: PASS. This
  feature *is* the "prove" step of Principle X's own six-step order
  ("triage, route, fix, review, merge, prove") — it strengthens the
  existing commitment that "a fix to behaviour that only runs in Actions is
  proven after merge by re-driving one run," without changing which merges
  the bot may perform or widening any merge class.

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/060-self-redrive-concurrency/
├── plan.md                                # This file
├── research.md                            # Phase 0: D1-D9 design decisions
├── data-model.md                          # Phase 1: entities (Directed Proof Run, Job-Uses-Graph, etc.)
├── quickstart.md                          # Phase 1: validation scenarios per user story
├── contracts/
│   ├── directed-proof-run.md              # NEW — the dispatch mechanism (FR-002/FR-002a/FR-002b)
│   ├── concurrency-groups.md              # NEW — per-job groups, FR-001/FR-001a, FR-016 guarantee sentence
│   └── proof-outcome-taxonomy.md          # NEW — the 8-reason taxonomy (FR-006/007/008/009/010/010a/010b)
└── spec-meta.json
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── board-loop.yml                     # EDIT — workflow_dispatch inputs (directed-stage/-issue/-pr,
│                                           #   FR-002); per-job concurrency: blocks replacing the workflow-
│                                           #   level one (FR-001/FR-004/FR-016, research.md D3); if: edits
│                                           #   to select/triage/review/readiness/prove-gate/prove; new
│                                           #   busy-check step (FR-001a); widened outcome-recording step
│                                           #   (FR-006/007/010a, research.md D6); new displacement-
│                                           #   detection step inside select (FR-010b, research.md D8)
├── scripts/
│   ├── board_prove.py                     # EDIT — scan_job_uses_graph(), directed_stage(),
│                                           #   joins_directed_group(), directed_proof_group_busy(),
│                                           #   the outcome_reason taxonomy function; script-import
│                                           #   resolution added to the existing uses-graph scan (FR-014)
│   ├── board_prove_displacement.py        # NEW — FR-010b's find_undetected_merges()
│   ├── verify-board-prove.py              # EDIT — Gate 89 extended with fixtures for every new
│                                           #   function, both directions (FR-020), and the widened
│                                           #   real-tree assertion (FR-021, "every board_*.py helper
│                                           #   resolves to at least one stage")
│   ├── verify-board-prove-displacement.py # NEW (or folded into Gate 89 — tasks.md decides) — FR-010b
│   └── verify-concurrency-guarantee-statement.py  # NEW — SC-006's cross-file sentence match
└── actions/
    └── wing-commander-dispatch-and-wait/  # UNCHANGED — Out of Scope forbids touching its mechanism;
                                            #   this feature's new inputs pass through its existing
                                            #   generic workflow-inputs JSON parameter

specs/057-autonomous-board-loop/contracts/
├── prove-step.md                          # EDITED DURING IMPLEMENTATION (FR-019, research.md D9) —
│                                           #   folds in contracts/directed-proof-run.md and
│                                           #   proof-outcome-taxonomy.md from this spec
└── board-loop-workflow.md                 # EDITED DURING IMPLEMENTATION — "Concurrency" section
                                            #   restated per contracts/concurrency-groups.md
```

**Structure Decision**: This feature touches exactly one workflow
(`board-loop.yml`), one existing script module it already owns
(`board_prove.py`), one new sibling module scoped to a single new concern
(`board_prove_displacement.py`), and the gate(s) that check them —
matching this repository's existing convention of one `board_*.py` module
per board-loop concern (`board_eligibility.py`, `board_stand_down.py`,
`board_item_marker.py`, `board_stop_check.py`) rather than introducing a
new package or directory layout. No new top-level directory is needed;
`.github/scripts/tests/` already holds fixture directories for sibling
gates and is available if `tasks.md` chooses external fixtures over Gate
89's inline style for any new gate.

## Complexity Tracking

*No violations — table intentionally empty.*
