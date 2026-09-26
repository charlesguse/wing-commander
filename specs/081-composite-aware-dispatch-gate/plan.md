# Implementation Plan: Gate 59 resolves the dispatch idiom wherever it lives

**Branch**: `081-composite-aware-dispatch-gate` (spec branch:
`spec/081-composite-aware-dispatch-gate`) | **Date**: 2026-09-26 | **Spec**:
[spec.md](./spec.md)

**Input**: Feature specification from
`/specs/081-composite-aware-dispatch-gate/spec.md`

## Summary

Gate 59 (`verify-correlated-release-dispatch.py`) pins three of spec
048's release-dispatch invariants to `auto-release.yml`'s own raw text,
so a pure relocation of the correlation search or the wait-before-tag-read
shell into a called composite reads as a deletion and fails by
construction — the defect blocking spec 057's T054. This plan makes the
gate resolve the `dispatch-release` job's effective shell (its own steps
plus any local composite those steps call, one level deep) for checks 3
and 5, while keeping check 4 (tag-state) enforced against the job's own
text only, per the clarified FR-027 scope boundary. It widens the
`wing-commander-dispatch-and-wait` composite's outputs contract
additively to carry the six facts `auto-release.yml`'s `report` job
reads today, adds a new runtime harness proving the tag-state invariant
by execution (the correlation/wait invariants' runtime proof already
exists in Gate 88 and is widened, not replaced), repoints
`dispatch-release` at the composite, and retires the `dispatch-and-wait`
entry in `single-home-waivers.json` — completing spec 057's T054 and the
withheld half of T056.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflow/composite-action
syntax), Bash (`set -uo pipefail` convention already used throughout this
repository's workflow shell), Python 3 (gate scripts, matching every
other `verify-*.py` in `.github/scripts/`).

**Primary Dependencies**: GitHub Actions, `gh` CLI, `jq`, `git`,
PyYAML (already a transitive dependency of every gate that parses
workflow/composite YAML, e.g. `wc_shell_harness.find_step`). No new
external dependency.

**Storage**: N/A — no runtime data store. Persistent artifacts are the
repository's own files (a gate script, a composite action, a workflow,
a JSON waiver file, two other specs' task lists and contracts).

**Testing**: Gate self-tests (`--self-test` flags and mutation-kill
fixtures) plus two shell-execution harnesses (`dispatch-and-wait-tests/run-tests.sh`,
widened; a new tag-state harness following Gate 67's `find_step`/`run_step`
pattern), all run through `.github/scripts/run-local-gates.py`, mirrored
in `.github/workflows/lint-workflows.yml`'s PR-time gate job
(Constitution VIII). FR-025's runtime-proof bar is met by these
execution harnesses, not by Gate 59 itself, which stays a textual,
line-based check matching Gate 50/51's established shape (research.md
D8). The one live-Actions proof this feature needs (FR-022) is a
post-merge re-drive of `auto-release.yml`, out of this feature's local
test plan by construction.

**Target Platform**: GitHub Actions runners (`ubuntu-latest`).

**Project Type**: Single repository, CI/CD pipeline infrastructure (no
`src`/`tests` application tree — see Project Structure below).

**Performance Goals**: N/A — CI configuration, not a service with a
throughput target. The measurable cost property is the one CLAUDE.md
already states (a pasted copy costs N future divergent fixes); this
feature's point is removing the *gate-level* obstacle that currently
forces that copy to exist, per spec 057 T054.

**Constraints**: FR-027 — the tag-state verification MUST stay in
`auto-release.yml`'s own job; the composite gains no release-specific
input. FR-004/SC-004 — an unresolvable composite reference MUST fail
loudly, never pass and never read as "invariant deleted." FR-013/FR-016 —
the composite's existing two outputs keep their name and meaning; every
new fact is additive. Constitution VIII — Gate 59 (amended) and the new
Gate 99 must each satisfy every clause of "a green check means what it
says." Constitution VII — widening the composite's published,
adopter-pinned surface is a deliberate, recorded act (FR-016), not a
convenience.

**Scale/Scope**: 1 gate script amended (Gate 59: resolution logic +
3-fixture self-test matrix), 1 composite action widened (4 new outputs,
1 new input, header-comment update), 1 existing behavioral harness
widened (Gate 88: 2 new scenarios), 1 new gate script + harness (Gate 99,
tentative number), 1 workflow edited (`auto-release.yml`'s
`dispatch-release` job split into two steps + its `outputs:` block), 1
waiver entry removed (`single-home-waivers.json`), 2 tasks checked off
with pointers (`specs/057-autonomous-board-loop/tasks.md` T054, T056),
1 contract note added (`specs/048-correlated-release-dispatch/contracts/regression-gate.md`),
1 post-merge re-drive recorded on the PR or issue #595.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1
design.*

- **I. Guide — the repo is its own first example**: PASS. This feature
  flows through the same intake → clarify → plan → tasks → implement →
  converge → finalize pipeline as any other spec here, tracked against
  lifecycle issue #595.
- **II. Cost-conscious model tiering**: N/A — no new Claude agent
  invocation is introduced.
- **III. Simple, GitHub-native interaction**: PASS — no new interaction
  surface; the feature is invisible to a spec requester and legible from
  issue #595 alone.
- **IV. Automation-first**: PASS — every code and configuration change
  is an ordinary commit. The one step that is not a git commit — the
  post-merge re-drive of `auto-release.yml` (FR-022) — is itself
  automatable through `gh workflow run` and is reported to the lifecycle
  issue like any other automated action, matching CLAUDE.md's "prove"
  step.
- **V. Security — untrusted content is never instructions**: PASS — no
  change to token scoping (the composite's `token` input keeps its
  `actions:write` scope; `auto-release.yml`'s own `github.token` use is
  unchanged) and no change to which content is treated as instructions.
  The gate reads only repository files, never issue/comment bodies.
- **VI. Portability**: PASS — nothing this feature adds hardcodes a
  repository name/owner; the composite and gate already operate purely
  on the checked-out tree.
- **VII. Two Interfaces**: DIRECTLY ENGAGED, not violated — widening
  `wing-commander-dispatch-and-wait`'s outputs (a non-underscore,
  published composite) is exactly the kind of deliberate surface growth
  this principle requires be recorded rather than snuck in; FR-016
  states the widening explicitly and additively (no existing input/output
  removed or renamed), and `contracts/dispatch-and-wait-outputs.md`
  records it. No amendment to this principle's text is needed — unlike
  spec 049, this feature performs a widening the principle already
  describes, rather than closing a gap in what the principle says.
- **VIII. A Green Check Means What It Says**: DIRECTLY ENGAGED — this
  feature's entire point is fixing a gate that today reports a pass it
  did not earn (a relocation reads as a deletion, and vice versa is
  guarded against by SC-004). See the Constitution Check re-check below
  and `contracts/resolving-gate.md`'s "Wiring" section for how each
  clause is satisfied post-change.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: PASS, and reinforced — the resolution algorithm (which
  composite is credited, whether a reference is unresolvable, which
  clause a failure names) is deterministic Python over parsed YAML and
  string search, never a model's judgment call.
- **X. Bounded Autonomy**: N/A — this feature does not touch the board
  loop; it is being planned under the ordinary feature lifecycle (Gate 3
  disabled for this run per the operator prompt).

No violations requiring Complexity Tracking.

### Re-check after Phase 1 design

Design artifacts (data-model.md, contracts/, quickstart.md) introduce
nothing outside what the initial Constitution Check already covers — no
new agent invocation, no new interaction surface, no widened token
scope, no repository name hardcoded. Gate 59 (amended) and Gate 99 (new)
each satisfy Principle VIII's clauses:

- **Reachable through the gate registry**: unchanged script path for
  Gate 59; Gate 99 follows the standard `verify-*.py` naming
  `wc_gate_registry.py` globs for. Neither needs a manual registration
  step to forget.
- **Same subject, same arguments, locally and in CI**: `run-local-gates.py`
  derives both from `lint-workflows.yml`'s own steps — no separate local
  invocation exists to drift from CI's.
- **Triggered by what it checks**: `lint-workflows.yml`'s existing
  PR-time gate job already triggers on both `.github/workflows/**` and
  `.github/actions/**` (`lint-workflows.yml:19-23`) — Gate 59's widened
  subject (a resolved composite) is already covered without a new
  trigger path (`contracts/resolving-gate.md` "Wiring").
- **Fails loudly when it can't reach its subject**: strengthened — the
  new unresolvable-reference cases (missing file, two-levels-deep) are
  additional loud-failure branches beyond today's guard.
- **Not suppressible by an unrelated gate**: unchanged/new steps both
  use the same `if: "!cancelled()"` sequential-job convention every
  other gate in `lint-workflows.yml` uses, not `continue-on-error`.
- **Every failure branch fixture-covered**: strengthened — Gate 59's
  self-test grows from 4 to 10 cases (research.md D5); Gate 88 grows by
  2 scenarios; Gate 99 ships with its own mutation-kill fixture, matching
  Gate 67's precedent.

Constitution Check: PASS. Proceeding to Phase 2 (tasks) is authorized by
the pipeline's own stage gate — Gate 3 (plan review) is disabled for this
run per the operator prompt, so `/speckit-tasks` dispatches automatically.

## Project Structure

### Documentation (this feature)

```text
specs/081-composite-aware-dispatch-gate/
├── plan.md              # This file
├── research.md          # Phase 0 output — 12 design decisions (D1-D12)
├── data-model.md        # Phase 1 output — gate/composite/job shapes
├── quickstart.md        # Phase 1 output — validation guide
├── contracts/            # Phase 1 output
│   ├── resolving-gate.md            # Gate 59's amended contract
│   └── dispatch-and-wait-outputs.md # The widened composite contract
└── tasks.md              # Phase 2 output (/speckit-tasks — not this stage)
```

### Source Code (repository root)

This is CI/CD pipeline infrastructure, not an application with a
src/tests split. The real "source" this feature touches:

```text
.github/
├── actions/
│   └── wing-commander-dispatch-and-wait/
│       └── action.yml                      # EDITED — 4 new outputs, 1 new input, header note (US2)
├── scripts/
│   ├── verify-correlated-release-dispatch.py   # EDITED — Gate 59: resolution + 10-case self-test (US1)
│   ├── verify-auto-release-tag-state-runtime.py # NEW — Gate 99 (US3)
│   ├── dispatch-and-wait-tests/
│   │   └── run-tests.sh                    # EDITED — Gate 88: 2 new scenarios (US2)
│   ├── single-home-waivers.json            # EDITED — dispatch-and-wait/auto-release.yml entry removed (US3)
│   ├── wc_shell_harness.py                 # existing, unchanged — find_step/run_step reused by Gate 99
│   └── run-local-gates.py                  # existing, unchanged — auto-derives Gate 59/88/99
└── workflows/
    ├── auto-release.yml                    # EDITED — dispatch-release job repointed + split (US3)
    └── lint-workflows.yml                  # EDITED — Gate 99 wiring (US3); Gate 59/88 steps unchanged

specs/057-autonomous-board-loop/
└── tasks.md                                # EDITED — T054, T056 checked off with pointers (FR-023)

specs/048-correlated-release-dispatch/
└── contracts/regression-gate.md            # EDITED — note that checks 3/5 now resolve through composites (FR-023)
```

**Structure Decision**: No new top-level directory and no new gate
*category* — this feature extends two existing conventions in place
(`.github/scripts/verify-*.py`, registry-derived; the existing
`wing-commander-dispatch-and-wait` composite's own contract) rather than
introducing a new one. The one new file, Gate 99's script, follows the
same `verify-*.py` + `find_step`/`run_step` shape Gate 67 already
established for "extract one job step's shell and run it against a
stub," so a future maintainer reading Gate 99 already knows the pattern
from Gate 67.

## Complexity Tracking

*No entries — Constitution Check recorded no violations.*
