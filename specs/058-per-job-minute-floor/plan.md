# Implementation Plan: The Per-Job Minute Floor — No-Op and Healthy Paths Cost What They Run

**Branch**: `spec/058-per-job-minute-floor` | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/058-per-job-minute-floor/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

GitHub bills every Actions job a whole minute however briefly it runs,
and this repository's three biggest consumers are all shapes where the
*job count*, not the work, sets the bill on the no-op and healthy paths
that dominate real traffic. This plan lands the three sub-problems in
sequence, in the order spec.md's own priorities and file-overlap
argument require:

**A (P1, all 13 published stages)**: the `verify-image-prerequisites`
job gains a job-level `if: inputs.container-image != ''`, so it reports
`skipped` and bills nothing when no image is configured. The historical
reason this job never skipped today (comment `#224`: a bare job-level
skip silently no-ops the whole dependent closure via GitHub's default
skip-propagation) is addressed head-on: every one of the ~40 jobs that
name the check in `needs:` gains an explicit `if:` that tolerates a
`skipped` result for that one dependency while still requiring
`success` from every other — never widened to "run unless cancelled."
Gates 22 and 23 are amended to assert the new shape and to fail when a
dependent job reverts to bare skip-propagation; Gate 15 needs no code
change, since its existing walk automatically covers the newly-rewritten
jobs.

**B (P2, `watchdog.yml` + its wrapper + self-verifier)**: `diagnose`'s
agent-skip condition widens from "every collector failed" to "the
aggregate signal set is empty," regardless of collector failures short
of all of them — the all-failed case keeps today's "could not inspect"
path untouched. A new deterministic step inside `collect`, beside the
`aggregate` step that decided it, posts the full- or partial-pass
passed-inspection comment on this newly-widened no-agent path, reusing
the two wording strings the agent-driven version already has rather than
inventing new ones. The wrapper's `resolve` job is removed by making
`run-name` optional and resolving it inside the stage itself when
empty — the wrapper becomes a single `uses:` job that allocates no
runner. The self-verifier accepts the new healthy shape (`diagnose`
skipped, no artifact, no record, a duration that can fall under today's
floor) by lowering its absolute floor constant while its
median-based term self-adjusts as new-shape runs accumulate.

**C (P3, `metrics-persist.yml` + its composite + its wrapper)**: the
stage gains an additive `since` input for sweep mode, reusing the
existing discover→retrieve→validate→append-with-retry pipeline per
discovered run and batching every run's records into one commit. A
durable high-water mark (`sweep-state.json`) and an explicit
expired-artifact ledger (`unpersisted.jsonl`) live beside `records.jsonl`
on the same destination branch, both written in the same
retry-safe commit as any records append. The wrapper's completion
trigger drops watchdog (a healthy inspection now emits no record after
B; a signal-bearing one is reached only by the new daily
`schedule:`-triggered sweep) while keeping its nine-stage completion
trigger, its hand-driven single-run re-drive, and — deliberately — no
`concurrency`-based coalescing.

Every new/amended check is a deterministic gate with a checked-in
fixture per failure branch (constitution VIII); no piece adds an agent
invocation anywhere (SC-013, constitution IX) — the passed-inspection
record and the persistence high-water mark are both written by
deterministic code, exactly as spec.md's constitution-dependency
paragraph requires.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps and composite
`action.yml` files), YAML (workflow/job condition definitions), `jq` for
JSON, `git`/`gh` for the metrics store and cross-run job/artifact
discovery — identical toolchain to every existing workflow, composite,
and gate in this repository; no new language. Gate scripts follow the
existing split (Python for structural/YAML-aware checks — the Gate
22/23 amendments — bash for behavioral/fixture-driven ones — the
watchdog and sweep gates), matching the closest existing gate each new
one most resembles.

**Primary Dependencies**: GitHub Actions (`workflow_call` stages, job
`needs:`/`if:` semantics, and GitHub's own skip-propagation rules — the
mechanism this feature works both with and around), the GitHub CLI
(`gh`) and REST API for cross-run job/artifact/run-listing discovery
(the sweep's own run-listing is the same `gh api ... --paginate`
idiom `watchdog.yml`'s existing collectors already use, including the
per-page-not-whole-result caution Gate 18 already documents), `git` for
the append-with-retry store writes (unchanged from spec 043), and this
repository's own `wing-commander-metrics-persist` composite (extended
for sweep mode, research.md R-C1) and `wc_published_stages.py`
(unmodified — this feature changes existing published stages' job
graphs and inputs, adding none).

**Storage**: The existing `metrics` orphan branch (spec 043) gains two
small files, `sweep-state.json` and `unpersisted.jsonl`, beside its
existing `records.jsonl` — see research.md R-C2/R-C4 and data-model.md.
No database, no external service, no new branch.

**Testing**: This repository's existing gate-registry convention —
`.github/scripts/verify-*.py`/`.sh` scripts wired into `lint-workflows.yml`
and runnable identically via `run-local-gates.py`. Two existing gates
(22, 23) are amended in place; one existing self-test (Gate 15) gains a
fixture with no code change; the watchdog self-verifier's own fixture
harness (Gate 36) gains a passing case; a handful of new gates are added
for the watchdog clean-path and sweep behaviors, each with checked-in
fixtures (contracts/gate-coverage-058.md, no manual-only demonstration —
constitution VIII).

**Target Platform**: GitHub Actions runners (`ubuntu-latest` class, this
repository's existing default), any repository that adopts the 13
published stage workflows and the watchdog/metrics-persist composite
actions (constitution VI/VII).

**Project Type**: GitHub Actions reusable-workflow pipeline (not an
application with a conventional `src/`/`tests/` split) — this feature
edits existing workflow, composite-action, and gate-script files under
`.github/`, plus its own `specs/058-per-job-minute-floor/` planning
artifacts. It adds no new stage workflow and no new composite action.

**Performance Goals**: Per spec.md's own "not a cost-target spec"
framing, outcomes are per-run job counts and skip/execute states, not
usage-page totals. Concretely: SC-001/SC-004 (one fewer billed job per
no-op stage run, all 13 stages), SC-006 (at most two billed jobs for a
clean watchdog inspection, down from five), SC-009/SC-011 (persistence
run count bounded by completions plus sweeps, records still landing
within minutes on the nine-stage completion path and within one sweep
interval otherwise).

**Constraints**: No agent invocation added anywhere (SC-013,
constitution IX) — every new/changed step is deterministic. FR-004's
"no dependent job may be widened to run merely because the workflow was
not cancelled" — `!cancelled()` is necessary but never sufficient;
every other dependency keeps its own explicit `== 'success'` check.
FR-025/FR-026 — persistence stays isolated and stays a separate
workflow from the watchdog run it may collect from; sweep mode changes
*how many runs* one persistence run processes, never *where* persistence
runs. FR-030(d) — no `concurrency:` group is added to coalesce
overlapping persistence runs; idempotence is the only safety mechanism
(explicit non-decision, research.md R-C7).

**Scale/Scope**: All 13 published stage workflows gain one job-level
`if:` line each; roughly 40 dependent jobs across those 13 files gain an
amended `if:` (data-model.md's dependent-job condition table). One
workflow (`watchdog.yml`) gains one new step and one amended job
condition; one wrapper (`wing-commander-8-watchdog.yml`) loses a job;
one self-verifier script gains a new passing case and a re-scaled
constant. One workflow (`metrics-persist.yml`) gains one optional
input and extends its composite's existing pipeline for batch/sweep
mode; one wrapper (`wing-commander-metrics-persist.yml`) gains a
`schedule:` trigger and a `sweep` job, and loses one `workflow_run`
list entry. Two existing gates are amended, one existing self-test
gains a fixture, and several new gates are added — final count and
numbering assigned at implementation time (research.md, following spec
043's own precedent).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | This feature is itself built through intake → plan → tasks → implement, the same pipeline it makes cheaper to run. | Pass |
| II. Cost-Conscious Model Tiering | This plan was produced at the planning tier (`claude-sonnet-5`). The feature itself removes one agent invocation from the watchdog's common path (sub-problem B) and adds none anywhere (SC-013) — nothing here is subject to tiering because nothing new here is a model call. | Pass |
| III. Simple, GitHub-Native Interaction | No new surface — every outcome is read from the jobs API of a run, the records file, or the lifecycle issue's existing comment conventions; no dashboard, CLI, or external tool is introduced. | Pass |
| IV. Automation-First | Sub-problems A-C are all shape changes to fully-automated paths; no new manual step is introduced. The maintainer-triggered single-run re-drive (FR-024) and the maintainer-driven hand closure of #404/#405/#406 (spec.md's Assumptions) are both pre-existing/explicitly out-of-scope manual actions, not new ones. | Pass |
| V. Security — untrusted content is never instructions | No sub-problem reads issue/comment bodies as instructions. Sub-problem B's new deterministic step reads only the aggregate's own structured outputs (already-trusted, deterministically computed collector data); sub-problem C's sweep lists runs via `gh api`/`git`, never parsing untrusted content. No stage gains a new secret or a `secrets: inherit`. | Pass |
| VI. Portability — consuming repo owns its artifacts | The sweep's destination remains wrapper-supplied (`destination-branch`/`destination-path`, unchanged from spec 043); an adopter who never includes the metrics-persist wrapper gets zero persistence and zero sweep activity, exactly as today. | Pass |
| VII. Two Interfaces | Every changed input (`run-name` optional, `since` new) is a declared, typed, versioned addition to a published `workflow_call` stage — never an ambient read. The wrapper changes (resolve-job removal, sweep trigger, dropped watchdog trigger entry) are entirely consuming-instrument changes, exactly where constitution VII says a repository-specific trigger decision belongs. | Pass |
| VIII. A Green Check Means What It Says | Gates 22/23 are amended (never bypassed) to assert the new shape and to fail on FR-007's reversion case; new gates for the watchdog clean path and the sweep each ship with a checked-in fixture per failure branch (contracts/gate-coverage-058.md); Gate 15 and the self-verifier's own fixture harness are extended rather than narrowed. | Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | The passed-inspection record's full-vs-partial choice, the FR-007 reversion check, the sweep's high-water-mark advancement, and the expired-artifact ledger entry are all deterministic code paths reading structured data — none is a prompt instruction, and sub-problem B's whole point is *removing* an agent call from a path where its judgment was never actually needed (an empty signal set leaves nothing to weigh). | Pass |
| X. Bounded Autonomy — The Pipeline Works Its Own Board | Not implicated — this feature is worked through the ordinary feature lifecycle (intake already ran; this is the plan stage), not the board loop. | N/A |

No violations. Complexity Tracking below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/058-per-job-minute-floor/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src`/`tests` split — it is a GitHub Actions
pipeline. This feature's concrete changes, grouped by sub-problem:

```text
.github/
├── workflows/
│   ├── intake.yml, clarify.yml, plan.yml, tasks.yml, implement.yml,
│   │   finalize.yml, cleanup.yml, rebase.yml, watchdog.yml,
│   │   pr-conversation.yml, metrics-persist.yml,
│   │   auto-update-spec-kit.yml, private-image-dogfood.yml
│   │                                    # A: verify-image-prerequisites gains
│   │                                    # job-level `if:`; ~40 dependent jobs
│   │                                    # across these 13 files gain the
│   │                                    # amended `if:` shape
│   │                                    # (contracts/image-check-shape-delta.md)
│   ├── watchdog.yml                    # B: diagnose `if:` widened; new
│   │                                    # deterministic passed-inspection step
│   │                                    # in `collect`; run-name resolution
│   │                                    # moved in from the wrapper
│   │                                    # (contracts/watchdog-clean-path-delta.md)
│   ├── wing-commander-8-watchdog.yml   # B: resolve job removed — single
│   │                                    # `uses:` job
│   ├── wing-commander-8b-watchdog-self.yml
│   │                                    # B: no workflow change — its script
│   │                                    # dependency changes (see scripts/)
│   ├── metrics-persist.yml             # C: new optional `since` input, sweep
│   │                                    # batching (contracts/metrics-persist-
│   │                                    # sweep-delta.md)
│   ├── wing-commander-metrics-persist.yml
│   │                                    # C: `schedule:` trigger + `sweep` job
│   │                                    # added; watchdog removed from
│   │                                    # `workflow_run.workflows`
│   └── lint-workflows.yml              # A/B/C: Gate 22/23 amendments, Gate
│   │                                    # 15 self-test fixture, new gate
│   │                                    # `run:` lines
├── actions/
│   └── wing-commander-metrics-persist/
│       └── action.yml                  # C: extends discover→retrieve→
│                                        # validate→append-with-retry for
│                                        # batched/sweep-mode runs; writes
│                                        # sweep-state.json/unpersisted.jsonl
│                                        # in the same commit
└── scripts/
    ├── verify-gate-22.py                        # amended (A)
    ├── verify-gate-23.py                        # amended (A)
    ├── verify-gate-15.py                        # self-test fixture only (A)
    ├── verify-watchdog-run.sh                    # amended floor/ceiling (B)
    ├── verify-watchdog-run-failure-paths.sh      # new healthy-shape fixture (B)
    ├── verify-watchdog-clean-path.{py,sh}        # new (B)
    ├── verify-watchdog-no-record-on-clean-path.{py,sh}  # new (B)
    ├── verify-watchdog-wrapper-resolve-fold.{py,sh}     # new (B)
    ├── verify-metrics-sweep-idempotence.sh       # new (C)
    ├── verify-metrics-sweep-high-water-mark.sh   # new (C)
    ├── verify-metrics-expired-artifact-outcome.sh # new (C)
    ├── verify-metrics-wrapper-trigger-drops-watchdog.py  # new (C)
    └── fixtures/
        └── job-minute-floor-*/          # new: checked-in fixtures per
                                          # data-model.md's "Gate fixtures" table

specs/058-per-job-minute-floor/
├── plan.md, research.md, data-model.md, quickstart.md   # this plan
├── contracts/
│   ├── image-check-shape-delta.md
│   ├── watchdog-clean-path-delta.md
│   ├── metrics-persist-sweep-delta.md
│   └── gate-coverage-058.md
└── tasks.md                            # /speckit-tasks output — not produced here
```

**Structure Decision**: Three sub-problems, three delta contracts, one
shared gate-coverage document — mirroring spec.md's own A/B/C split so
each can be implemented (and, per spec.md's Assumptions, potentially
shipped) as an independently-reviewable unit while still landing in one
sequence: **A first** (it edits all 13 stages, including the two files B
and C also touch, and carries the highest regression risk per spec.md's
own priority ordering), **B second** (edits `watchdog.yml`, which A
already touched, and is a prerequisite for C's watchdog-trigger removal
— C's FR-030(b) is stated in terms of "after FR-031"), **C last** (its
sweep design is new mechanism, not a shape change to an existing job, so
it carries the least risk to land after the other two have settled the
files it also edits). No new stage workflow, no new composite action,
and no new documentation-artifact type is introduced — every change is
an amendment to an existing published contract, recorded as a delta
against the base contract it amends (the same pattern specs 020/024 used
for `watchdog.yml`'s own base contract), rather than a rewritten
from-scratch document.

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
