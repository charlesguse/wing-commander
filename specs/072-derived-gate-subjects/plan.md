# Implementation Plan: Gate 68 Derives Its Own Subjects

**Branch**: `spec/072-derived-gate-subjects` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/072-derived-gate-subjects/spec.md`

## Summary

Gate 68 (`.github/scripts/verify-post-agent-credential-refresh.py`)
currently decides which workflow jobs it inspects from `SUBJECTS`, a
hand-typed `{path: [job names]}` map covering 8 workflow files. Four
agent-bearing workflows exist on `main` today that `SUBJECTS` never named:
`board-loop.yml` (5 agent steps across 4 jobs), `cleanup.yml`, `rebase.yml`,
and `watchdog.yml` — none of them checked, and nothing reporting that they
are not checked. This feature (item 1 of the four the originating issue
#410 listed; items 2–4 already shipped in commit `2a1cf1b`) replaces
`SUBJECTS`-as-selector with structural derivation: every job, in every
`.github/workflows/*.yml` file, containing a step whose `uses:` matches the
agent action is a subject, full stop. `SUBJECTS` is renamed to
`SUBJECT_FLOOR` and repurposed as a drop-detector (a floor member the
derived set no longer yields fails loudly), a new `EXCLUSIONS` map records
which derived subjects are deliberately not held to the contract and why,
and the four newly-surfaced workflows are each assessed against FR-014's
rule and land in whichever of the two states it yields: `board-loop.yml`'s
four jobs, `cleanup.yml`'s `teardown-done`, and `rebase.yml`'s `rebase`
adopt the post-agent credential contract (real workflow-file changes, not
only a gate change); `watchdog.yml`'s `diagnose` is excluded on its
`timeout-minutes: 10` bound. The self-test gains fixtures for the
regressions derivation newly makes possible and loses none of its existing
coverage (research.md D8).

## Technical Context

**Language/Version**: Python 3 (matching every existing `.github/scripts/
verify-*.py` gate; no version bump — the shipped gate already runs under
whatever interpreter `run-local-gates.py` and `lint-workflows.yml`'s
`actions/setup-python` step provide)

**Primary Dependencies**: `PyYAML` (`yaml.safe_load`) — already a
dependency of this exact script and of every other structural workflow
gate; no new dependency

**Storage**: N/A — every shape this feature introduces is a Python module
constant (`SUBJECT_FLOOR`, `EXCLUSIONS`) or a value computed fresh per run
(the derived subject set); see data-model.md

**Testing**: The gate's own `--self-test` mode (loads the real shipped
trees, applies `copy.deepcopy` mutations, asserts each fails) — the same
convention `verify-plan-tasks-cost-line.py` and every other mutation-based
gate in this repository already uses. `python .github/scripts/
run-local-gates.py` is the one command that runs this gate (plain and
`--self-test`) the same way CI does.

**Target Platform**: Whatever runs `lint-workflows.yml`'s PR-time job in
GitHub Actions, and whatever local machine (Linux/macOS/Windows) a
maintainer runs `run-local-gates.py` on before pushing — unchanged from the
shipped gate, which already has to be cross-platform-safe (no shell-outs,
pure `yaml.safe_load` plus `re`).

**Project Type**: Single script within this repository's existing
`.github/scripts/` gate-suite tooling — not a new project, app, or service.

**Performance Goals**: N/A beyond "does not visibly slow the PR-time gate
job" — parsing 34 workflow YAML files (up from 8) with `yaml.safe_load` is
well under the gate suite's existing per-step budget; the self-test's
`copy.deepcopy`-per-mutation cost scales with mutation count, not with the
34-file glob, so the two new mutations add a constant, small cost.

**Constraints**: Must remain a pure static-structure check — no
`wc_shell_harness.py` execution pass, no network access, no change to what
any check *means* (Assumptions: "Deriving subjects is a change to how it
chooses what to read, not a change to what the checks mean"). Must not
weaken any check that fails today under a given mutation (FR-018).

**Scale/Scope**: 34 `.github/workflows/*.yml` files scanned (up from 8
read); derived subject count grows from 9 job entries to 15 non-excluded
plus 1 excluded; `SUBJECT_FLOOR` gains 6 entries; `EXCLUSIONS` gains 1;
self-test mutation count grows by 2 net (3 retired, 3 replacements, 2 pure
additions — research.md D8).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **Principle VIII (A Green Check Means What It Says)** — this feature's
  entire purpose is closing exactly the gap VIII names: a gate whose subject
  selection cannot fail when a subject disappears is "coverage that proves
  nothing." FR-004/FR-005/FR-009 make the derived-and-floored design fail
  loudly on every way VIII's failure modes could recur (wrong subject set,
  empty result set, an unreachable file). **PASS** — this feature
  strengthens, not weakens, VIII's guarantee for Gate 68. Re-checked after
  Phase 1: the floor/exclusion split (D3/D4) and the subject report (D9)
  both trace directly to VIII's "every failure branch a gate ships MUST be
  exercised by a checked-in fixture" and "a gate that cannot reach its
  subject... MUST fail loudly" clauses. Still **PASS**.
- **Principle IX (Judgment That Gates a Durable Action Belongs in
  Deterministic Code)** — no model judgment is introduced anywhere in this
  feature; subject derivation, floor comparison, and exclusion lookup are
  all deterministic YAML/set operations, and the four-workflow disposition
  decision (FR-014) is itself a deterministic rule applied by this plan
  during research (D5), not deferred to a runtime judgment call. **PASS**.
- **Principle VII (Two Interfaces)** — `board-loop.yml`, `cleanup.yml`, and
  `rebase.yml` are published-contract stage workflows (workflow_call-only,
  resolving composites through self-checkout); the post-agent credential
  contract additions this feature makes to them (D5) add internal steps
  only — no new `workflow_call` input, secret, or output, so the published
  surface is unchanged. **PASS**.
- **Principle VI (Portability)** — no change touches anything outside this
  repository's own `.github/scripts/` and `.github/workflows/`; nothing
  about consumer-repository artifacts is introduced. **PASS**.
- No other principle bears on a gate-subject-selection change. No violation
  to record in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/072-derived-gate-subjects/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── gate-68-subject-derivation.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature touches no application source tree — it is entirely within
this repository's own CI tooling and workflow definitions. No `src/`,
`tests/`, `backend/`, or `frontend/` directories apply; the structure below
names the actual files this feature changes or reads.

```text
.github/
├── scripts/
│   └── verify-post-agent-credential-refresh.py   # Gate 68 — subject
│       derivation (SUBJECT_FLOOR, EXCLUSIONS), self-test mutations,
│       docstring (FR-017)
├── workflows/
│   ├── lint-workflows.yml       # Gate 68's registration comment block
│   │   (FR-017) — wiring itself (`run:` step, self-test step) unchanged
│   ├── board-loop.yml           # 4 jobs (triage, route, fix, review) gain
│   │   the missing wing-commander-agent-ran-signal call
│   ├── cleanup.yml               # teardown-done job gains the full
│   │   post-agent contract (re-mint, refresh-remote, agent-ran-signal,
│   │   credential-status; every post-agent token read switched to
│   │   env.WC_BOT_TOKEN)
│   ├── rebase.yml                # rebase job gains the same full
│   │   treatment as cleanup.yml's teardown-done
│   └── watchdog.yml               # no code change — diagnose is excluded,
│       recorded in EXCLUSIONS only
└── scripts/run-local-gates.py     # read, not changed — already derives
    Gate 68's invocation from lint-workflows.yml (FR-016)
```

**Structure Decision**: No new directories. All changes land in the three
existing locations above: the gate script itself, its one-comment-block
registration in `lint-workflows.yml`, and the three workflow files whose
jobs adopt the contract this feature's derivation newly holds them to.
`watchdog.yml` needs no file change — its exclusion is recorded entirely
inside the gate script's `EXCLUSIONS` constant.

## Complexity Tracking

*No entries — Constitution Check recorded no violation requiring
justification.*
