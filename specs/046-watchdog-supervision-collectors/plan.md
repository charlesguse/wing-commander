# Implementation Plan: Deterministic Watchdog Collectors for the Supervision Gap

**Branch**: `spec/046-watchdog-supervision-collectors` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/046-watchdog-supervision-collectors/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Four new deterministic `collect-*` steps join the five that already run
inside `watchdog.yml`'s `collect` job — `collect-turn-budget`,
`collect-cost-report`, `collect-final-pr-claims`, `collect-spec-collision`
— each a bash/jq step matching the existing collectors' shape exactly
(own `collector-outcomes.json` entry, own attribution guard, own
false-positive suppression), adding zero agent invocations. Three design
problems drive most of this plan's decisions, none answered directly by
spec.md: (1) the turn-budget trend's "accumulate at one band, only
reopen-or-refile on escalation" behavior (FR-012/FR-015) must be built
entirely from signal-identity and a collector-side pre-check against
already-closed issues, because FR-032 forbids touching the shared
dedup/fingerprint code that would otherwise need a bespoke "don't reopen"
branch; (2) the final-PR-claims check's three signals must be reportable
without opening a `pipeline-defect` issue (FR-025), which needs one new,
narrowly-scoped deterministic routing step in `triage`/`act` rather than
a change to the evidence-validity gate itself; (3) every Finding's
`normalizedFacts` is schema-constrained today to ten fixed keys (`tool,
branch, spec, file, job, step, workflow, stage, expected, actual`) and
FR-032 forbids widening that schema, so all four new classes are designed
to express their comparison as `stage`/`expected`/`actual` (plus `spec`
or `file` where an artifact identity is needed) rather than inventing new
keys. No workflow outside `watchdog.yml` changes; `specs/
015-pipeline-watchdog/contracts/watchdog-workflow.md`'s "five deterministic
collector steps" line becomes stale by this feature and is flagged in
this plan as a task for the implementation stage to update — plan-stage
edits are scoped to `specs/046-watchdog-supervision-collectors/` only.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML, `jq`, and
Python only where the repository's existing convention already uses it
for structural/hash logic (the `Stamp signal ids` step's sha256 heredoc) —
identical toolchain to the five existing collectors; no new language.

**Primary Dependencies**: `gh` CLI, `jq`, `git` — all already used inside
`watchdog.yml`'s `collect` job. `collect-turn-budget` additionally reads
the durable metrics store `metrics-persist.yml` maintains (a `records.jsonl`
file on an orphan branch, spec 043) via `git show
origin/<branch>:<path>`, the same read shape `verify-metrics-rollup-idempotent.py`
already exercises. No new external service, no new composite action, no
new `claude-code-action` invocation (FR-001, SC-003).

**Storage**: No new storage location. `collect-turn-budget` reads (never
writes) the spec-043 metrics branch. The turn-budget suppression check
(research.md R4) reads (never writes) `pipeline-defect`-labeled issues via
`gh issue list`, the same read shape the existing dedup-search step
already performs — this is an additional read at collect time, not a
second store.

**Testing**: This repository's existing gate-registry convention — one
`verify-<collector>.{sh,py}` script per new collector (plus one for the
turn-budget fingerprint-suppression logic and one for the narrative-drift
issue-exemption routing), each wired into `lint-workflows.yml` and
runnable locally via `run-local-gates.py`, each with checked-in fixtures
covering every failure branch (SC-002, constitution VIII). Diagnose
itself (the one agent step) is not fixture-tested by this convention
today and stays that way — these gates validate the deterministic
collector/routing code this feature adds, not the model's judgment over
class-hint-null signals, exactly the boundary the five existing
collectors' gates already draw.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), unchanged
triggers — the existing `wing-commander-8-watchdog.yml` wrapper already
listens for intake and finalize completions (among others), so the
finalize- and intake-scoped collectors need no new trigger wiring.

**Project Type**: Single project — CI/CD automation under
`.github/workflows/`, unchanged.

**Performance Goals**: Not a latency-sensitive feature — four more bash/jq
steps inside a job that already runs nine (soon thirteen) sequential
`gh`/`jq` steps add seconds, not minutes, to `collect`. SC-003 restates
this as the actual constraint: marginal cost is runner-seconds, not agent
turns, and is satisfied by construction (zero new agent steps).

**Constraints**: FR-030–FR-033 (scope boundaries) is the binding
constraint on this entire plan: no new agent invocation; no change to the
five existing collectors' behavior; no change to diagnose's model,
prompt, tool allowlist, or output schema; no change to the
evidence-validity gate's rule, the dedup rules, the self-dispatch cap, or
the pause switch. Every design choice below that looks like it should
touch one of those pieces is redesigned instead to be an additive
registration (a new row in an existing per-class table, a new collector
step, a new narrowly-scoped routing step that runs alongside — not
inside — the protected steps) rather than a modification of them.

**Scale/Scope**: One file changes at implementation time —
`.github/workflows/watchdog.yml` (four new `collect-*` steps; the `Stamp
signal ids` step's source→kind map gains four rows; a new
`Determine issue-filing eligibility` step in `triage`, additive alongside
the existing coexistence-suppression step; five labels
(`🐕 · turn-budget-trend`, `🐕 · cost-line-missing`, `🐕 · cost-line-malformed`,
`🐕 · narrative-drift`, `🐕 · spec-number-collision`) that self-register via
the existing `__new__` escape hatch the first time each fires, needing no
repository setup step). New: four-to-six `.github/scripts/verify-*.{sh,py}`
gate scripts with fixtures, wired into `lint-workflows.yml`.
`specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`'s collector
count is noted as needing a follow-up edit outside this plan's scope
(constraint: plan-stage edits are confined to
`specs/046-watchdog-supervision-collectors/`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | This feature is built through intake (#274) → this spec → this plan → tasks → implement, the same pipeline it instruments, and its subject is that same pipeline's own watchdog. | Pass |
| II. Cost-Conscious Model Tiering | No model tier changes; no new agent step at any tier (FR-001, SC-003). `diagnose` stays `claude-opus-5`, untouched. | Pass |
| III. Simple, GitHub-Native Interaction | New findings surface exactly where the five existing ones already do — a `pipeline-defect` issue (four classes) or the lifecycle issue's own report comment (the narrative-drift exemption, FR-025) — no new dashboard, no new interaction surface. | Pass |
| IV. Automation-First | Nothing here introduces a manual step; the new labels self-register the same automated way every prior watchdog class has. | Pass |
| V. Security (NON-NEGOTIABLE) | FR-006 restates the untrusted-content framing for every new artifact a collector reads (PR bodies, issue comments, task files) — the final-PR-claims check in particular parses agent-authored PR-body prose, which research.md R6 frames identically to how `diagnose`'s own prompt already frames `signals.json`: data to compare against ground truth, never instructions. No new write surface — the four new collectors only read; the one new routing step in `triage`/`act` only decides which existing write path a Finding takes. | Pass |
| VI. Portability | The turn-budget check's cross-run read degrades to "could not inspect" for any adopter that has not wired `metrics-persist.yml` (spec.md Assumptions, research.md R3) — this feature adds no new required adoption step. Config knobs are `vars.*` with the same wrapper-owned-default pattern every existing knob uses. | Pass |
| VII. Two Interfaces | `watchdog.yml` remains `workflow_call`-only. The three new threshold vars follow the one documented exception this workflow already carries (Gate 1b's watchdog carve-out, watchdog.yml's own comment at the branch-prefix reads) rather than opening a second exception — see research.md R2. | Pass |
| VIII. A Green Check Means What It Says | Every failure branch each new collector ships gets a checked-in fixture (SC-002), gate-registered the standard single-registration way; the turn-budget collector's copied fingerprint/signal-id formula is gate-diffed against the live `Stamp signal ids`/`Compute fingerprint` steps, mirroring gate 5's existing drift guard for the denied-tool collector's copied jq filter (research.md R4). | Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | This is the organizing constraint of the whole design (Summary above): the trend's accumulate/escalate decision, the narrative-drift issue-exemption, and the class-hint-null-vs-set split for the per-run turn-budget signal are all deterministic code or pre-existing deterministic convention — none is a new prompt instruction asking the model to decide whether to file or reopen. | Pass |

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/046-watchdog-supervision-collectors/
├── plan.md               # This file (/speckit-plan command output)
├── research.md           # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── collector-signals.md
│   ├── turn-budget-trend.md
│   └── gate-coverage-046.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src`/`tests` split — it is a GitHub Actions
pipeline. This feature's concrete changes (all at implementation time,
none made by this plan):

```text
.github/
├── workflows/
│   └── watchdog.yml                 # AMENDED — four new collect-* steps in
│                                     # the `collect` job; four new rows in
│                                     # `Stamp signal ids`' source→kind map;
│                                     # one new `Determine issue-filing
│                                     # eligibility` step in `triage`,
│                                     # additive alongside the existing
│                                     # coexistence-suppression step
└── scripts/
    ├── verify-turn-budget-collector.sh        # new
    ├── verify-turn-budget-suppression.sh      # new — the closed-fingerprint
    │                                           # pre-check (contracts/
    │                                           # turn-budget-trend.md)
    ├── verify-cost-report-collector.sh        # new
    ├── verify-final-pr-claims-collector.sh    # new
    ├── verify-spec-collision-collector.sh     # new
    ├── verify-narrative-drift-routing.sh      # new — the issue-exemption
    │                                           # routing step
    └── fixtures/
        └── watchdog-collectors-046/           # new — checked-in fixtures,
                                                # one per failure branch
                                                # (data-model.md's table)

specs/015-pipeline-watchdog/contracts/watchdog-workflow.md
    # NOT edited by this plan (out of scope per this run's constraints) —
    # flagged here as a task for /speckit-tasks: its "five deterministic
    # collector steps" line needs updating to nine once implementation lands.
```

**Structure Decision**: Every new collector is one more step inside the
`collect` job `watchdog.yml` already has — no new job, no new workflow
file, matching spec.md's own framing ("no new agent surface... flowing
through the existing... path unchanged"). Gate scripts follow the
existing `.github/scripts/verify-*.{py,sh}` naming convention so
`lint-workflows.yml`'s registry picks each up with one `run:` line, the
same single-registration point every prior gate uses.

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
