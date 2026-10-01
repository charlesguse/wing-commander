# Implementation Plan: The Worked Example Outlives Its Code — Keeping spec-cross-reference's Structural Claim True

**Branch**: `089-skill-example-drift` | **Date**: 2026-09-29 | **Spec**: [specs/089-skill-example-drift/spec.md](./spec.md)

**Input**: Feature specification from `/specs/089-skill-example-drift/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`spec-cross-reference`'s Over-rated worked example quotes a concrete
structural fact about `board-loop.yml` — that every job able to select a
board item or open a fix PR (`select` through `readiness`) joins
`wing-commander-board-loop`, with the only permitted overlap being a
directed proof run in a separate group. Nothing in the repository fails
when that quote and the workflow's actual per-job `concurrency:` blocks
diverge, even though the example exists specifically to teach a reviewer
when a structural guarantee can refute a plausible race. The remedy fixed
by the spec's own clarifications is a **gate over the concrete quote**, not
a rewrite into something generic: a new script,
`.github/scripts/verify-skill-board-loop-concurrency-claim.py` (**Gate
125**), extracts the skill's claim (the job range and the two group names,
tolerant of wording per FR-009), reads
`specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`'s
per-job table as the authoritative classification of which jobs can select
or open a fix PR, and compares both against `board-loop.yml`'s actual
`concurrency:` blocks (group membership *and* `cancel-in-progress`, per
FR-012's explicit property list). A divergence blocks the PR
(FR-010) unless covered by an entry in a new
`skill-example-drift-waivers.json`, itself stale-checked in both directions
(FR-014) the way `single-home-waivers.json` and `stage-invariant-waivers.json`
already are. The skill gains one wording clause (the queuing property,
research.md D6) and one pointer sentence naming Gate 125 by path, so a
triager settles "is this stale?" in one command with no history of spec 060
(FR-008, SC-004).

## Technical Context

**Language/Version**: Python 3.11 (the new gate script, following
`verify-concurrency-guarantee-statement.py`/`verify-single-home-idioms.py`'s
existing style), Markdown (`SKILL.md`'s wording addition), JSON (the new
waiver file) — no new language for this repository.

**Primary Dependencies**: None new. Regex/string parsing over
`board-loop.yml`, `SKILL.md`, and `concurrency-groups.md` (the same
lightweight approach `verify-concurrency-guarantee-statement.py` already
uses for the sibling comment-text check); `json` (standard library) for the
waiver file, matching every other `*-waivers.json` reader.

**Storage**: N/A. `skill-example-drift-waivers.json` is the one new
tracked file, and it is a register (like its siblings), not a data store —
see data-model.md.

**Testing**: This repo's own gate registry
(`.github/scripts/run-local-gates.py`, `.github/workflows/lint-workflows.yml`),
invoked identically locally and in CI (Principle VIII). Gate 125 follows
the `verify-*.py --self-test` convention (Gate 24, Gate 60, Gate 101's
siblings): synthetic fixtures for every `DriftFinding` property in both
directions, plus the waiver stale-check in both directions (research.md D9,
contracts/skill-drift-gate.md's Self-test section), separate from a
real-tree run against the actual `SKILL.md`/`board-loop.yml`
(quickstart.md §1's manual mutation step) — mirroring why
`verify-board-prove.py` keeps a real-tree assertion distinct from its
fixtures (spec 060's own plan.md **Testing** note: fixtures alone let the
original dispatchable-set bug ship silently green).

**Target Platform**: GitHub Actions (`lint-workflows.yml`'s existing
PR-time lint job) and any maintainer's local checkout via
`run-local-gates.py` — not a new workflow, not a runtime service.

**Project Type**: CI-native automation (one gate script plus a documentation
edit) — not an application with a runtime server or a UI.

**Performance Goals**: N/A beyond "fast enough for a PR-time gate" — the
script reads three small-to-medium text files once and does no network
call, comparable to Gate 101's sibling check, which is not among the
suite's slow gates.

**Constraints**: Principle VIII (the gate must be reachable through the
registry, fail loudly on a missing subject, and be exercised by a checked-in
fixture per failure branch); Principle IX (the comparison is deterministic
code — job classification comes from a maintained table, never an agent's
judgment about which jobs "look like" they select an item); FR-004 (follow
`main`'s actual shape — the per-job split #490 already shipped — never
anticipate a design not yet merged); FR-011 (bind only this one claim, no
registry of skill-quoted facts); CLAUDE.md's single-home rule (job
classification lives once, in `concurrency-groups.md`'s table, per
research.md D4 — not re-copied into the new gate script).

**Scale/Scope**: One new gate script (~200-300 lines, in line with
`verify-concurrency-guarantee-statement.py`'s 140 lines plus a waiver-aware
comparison layer). One new waiver JSON file, shipping empty. Two wiring
lines added to `lint-workflows.yml` (gate + self-test step, following the
existing per-gate block convention). A handful of lines added to
`spec-cross-reference/SKILL.md`'s existing Over-rated paragraph (one
clause) plus one new pointer sentence — no other file in the skill changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: PASS. Specified, planned, and implemented through this
  repository's own pipeline; lifecycle issue #658.
- **II. Cost-Conscious Model Tiering**: PASS (N/A). No new Claude
  invocation — the comparison is deterministic Python, never a prompt.
- **III. Simple, GitHub-Native Interaction**: PASS. The gate's failure
  surfaces as an ordinary PR check; no dashboard, no new interaction
  surface. Waivers are reviewed the same way any tracked JSON file is, in
  the PR diff.
- **IV. Automation-First**: PASS. No new manual step for an ordinary PR;
  the one manual step this feature explicitly preserves (a human session
  updating the skill after an implement-stage PR lands a waived divergence,
  FR-013) is already reported via the waiver entry's own `reason`/`issue`
  fields, never silently assumed.
- **V. Security**: PASS (N/A). No new trigger, no new secret, no new
  untrusted-content surface — the gate reads tracked repository files only.
- **VI. Portability**: PASS (N/A). This entire feature lives in Wing
  Commander's own consuming-instrument layer (a skill under `.claude/skills/`
  and a gate under `.github/scripts/`, both already excluded from the
  published `workflow_call` contract) — Principle VII's boundary, not
  Principle VI's, is the relevant one and is addressed below.
- **VII. Two Interfaces**: PASS. Neither `spec-cross-reference/SKILL.md`
  nor any `.github/scripts/verify-*.py` gate is part of the published
  `workflow_call` stage surface; both are consuming-instrument artifacts
  this repository is free to change. `lint-workflows.yml` itself is also
  not a published stage.
- **VIII. A Green Check Means What It Says**: PASS, and the organizing
  principle of this whole feature — the entire point is that the skill's
  claim currently has NO check behind it (a violation of this principle
  today, named as such in the spec's own framing) and this feature installs
  one that is registry-reachable (`verify-*.py` convention), fails loudly on
  a missing subject, and is exercised by a checked-in fixture per failure
  branch (research.md D9).
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: PASS, and directly on point — job classification is read from a
  maintained table (`concurrency-groups.md`), never inferred by the gate's
  own heuristic judgment about workflow shape (research.md D4's Alternatives
  considered explicitly rejects that).
- **X. Bounded Autonomy — The Pipeline Works Its Own Board**: PASS (N/A).
  This feature does not change the board loop's own behavior or merge
  classes; `board-loop.yml` is read-only input to the new gate, never
  edited by this feature (Scope, spec.md).

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/089-skill-example-drift/
├── plan.md                      # This file
├── research.md                  # Phase 0: D1-D9 design decisions
├── data-model.md                # Phase 1: SkillClaim, JobClassification,
│                                 #   WorkflowConcurrencyFact, DriftFinding, WaiverEntry
├── quickstart.md                # Phase 1: validation scenarios per user story
├── contracts/
│   ├── skill-example-claim.md   # NEW — the gate-readable shape the Over-rated
│   │                             #   example's prose must keep (FR-003/005/008/009)
│   └── skill-drift-gate.md      # NEW — Gate 125's algorithm, failure message
│                                 #   shape, waiver semantics, self-test, wiring
├── checklists/
│   └── requirements.md          # From intake; unchanged by plan
└── spec-meta.json
```

### Source Code (repository root)

```text
.claude/skills/spec-cross-reference/
└── SKILL.md                     # EDIT — Over-rated example gains the queuing/
                                  #   cancel-in-progress clause (research.md D6)
                                  #   and a pointer sentence naming Gate 125
                                  #   (research.md D8, contracts/skill-example-claim.md)

.github/
├── scripts/
│   ├── verify-skill-board-loop-concurrency-claim.py  # NEW — Gate 125
│   │                                                   #   (contracts/skill-drift-gate.md)
│   └── skill-example-drift-waivers.json               # NEW — ships with an
│                                                        #   empty `waivers` array
│                                                        #   (research.md D2)
└── workflows/
    └── lint-workflows.yml       # EDIT — two new steps (gate + self-test),
                                  #   following the existing per-gate block
                                  #   convention (contracts/skill-drift-gate.md
                                  #   "Wiring")

specs/060-self-redrive-concurrency/contracts/
└── concurrency-groups.md        # READ-ONLY — this feature's authoritative
                                  #   source for job classification
                                  #   (research.md D4); not edited
```

**Structure Decision**: This feature touches exactly one skill document, one
new gate script plus its companion waiver register, and one workflow's
wiring block — matching the repository's existing one-gate-per-concern
convention (`verify-concurrency-guarantee-statement.py`,
`verify-single-home-idioms.py`, `verify-stage-invariants.py` each own one
script plus, where relevant, one waiver register). No new directory, no new
package, and — per FR-011 and the spec's own Scope — no registry spanning
`.claude/skills/**`.

## Complexity Tracking

*No violations — table intentionally empty.*
