# Implementation Plan: Lifecycle Hold Label and Fold-Time Analyze

**Branch**: `spec/119-lifecycle-hold-label` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/119-lifecycle-hold-label/spec.md`

## Summary

One label (`lifecycle:held`) on the lifecycle issue stops all implement
work. It is read by implement at cycle start, by `wing-commander-fold-dispatch`
and by the review gate's merge; set by a strict `stop`/`/stop`, by hand, or
by a deterministic decide step after a read-only Sonnet fold-time analyze
job; released by removing the label, which a new `issues: unlabeled`
trigger on the implement wrapper turns into the next implement dispatch.
Drop is a deterministic pr-conversation action whose tasks.md removal
(verified by a maintainer-comment-backed commit trailer) is the only source
of "dismissed" fingerprints, derived rather than stored. See
[research.md](research.md) D1–D10.

## Technical Context

**Language/Version**: Python 3 (stdlib, `.github/scripts/`), Bash and jq in composite actions, GitHub Actions YAML

**Primary Dependencies**: `gh` CLI, `claude-code-action` (analyze job only), existing composites (fold-queue, spec-meta, board-stop-check), `board_stop_check.py`, `wc_convergence.py`, `wc_lifecycle_review_marker.py`

**Storage**: N/A — the label is the only state; dismissals derived from tasks.md git history and PR comments

**Testing**: checked-in fixtures + unit tests beside each script; new `verify-*.py` gates registered in `run-local-gates.py`

**Target Platform**: GitHub Actions (ubuntu runners; adopter repos via wrappers)

**Project Type**: CI pipeline / workflow library

**Performance Goals**: hold check adds one API call per cycle/dispatch; analyze adds one bounded (8-turn) Sonnet call per tasks-changing fold

**Constraints**: no new command/stage/marker/label/lock (FR-018); agent job `contents: read`; fail closed on unreadable labels; public repo (no private references)

**Scale/Scope**: touches implement.yml, lifecycle-review-gate.yml, pr-conversation.yml and wrapper, implement wrapper, clarify, label-copying steps, fold-dispatch, ~4 new scripts, 1 composite, constitution X amendment (separate PR)

## Constitution Check

Gate evaluated against `.specify/memory/constitution.md` (I–X).

| Principle | Result |
|---|---|
| I Guide | Pass — built through this lifecycle |
| II Model tiering | Pass — analyze declares `claude-sonnet-5-5` and `--max-turns 8`; no other agent added |
| III GitHub-native | Pass — label, comment, label removal |
| IV Automation-first | Pass — release is one action; trigger restarts implement |
| V Security | Pass — maintainer association checks, bots ignored, agent job read-only; drop attribution verified against the maintainer's comment; bot never merges anything new. Constitution X amendment stays human-merged |
| VI Portability | Pass — all text adopter-neutral; wrapper trigger documented |
| VII Two interfaces | Pass — published inputs/outputs declared (`issue`, `hold-label`, `withheld`); wrapper additions are consuming-instrument |
| VIII Green means green | Pass — fixture per failure branch; gates fail if a consumer stops calling the shared home |
| IX Deterministic gating | Pass — hold, decide, drop, release-plan, merge condition are code; agent only produces a verdict |
| X Bounded autonomy | **Pending dependency** — adds merge condition 9; constitution X wording must be amended first (separate human-merged PR), enforced by the merge check (FR-022). Not a violation of this plan |

Post-design re-check: unchanged; no Complexity Tracking entries.

## Project Structure

### Documentation

```text
specs/119-lifecycle-hold-label/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/hold-interfaces.md
└── tasks.md          # tasks stage
```

### Source Code

```text
.github/actions/wing-commander-lifecycle-hold/action.yml   # new: check | set
.github/actions/wing-commander-fold-dispatch/action.yml    # hold-label input, withheld output
.github/actions/wing-commander-implement-outcome/          # `held` outcome
.github/scripts/wc_lifecycle_hold.py                       # new: check/set/release-plan/constitution-names-hold
.github/scripts/wc_fold_analyze.py                         # new: prepare + decide
.github/scripts/wc_fold_drop.py                            # new: parse + apply drop
.github/scripts/wc_dismissals.py                           # new: derive dismissed fingerprints
.github/scripts/verify-lifecycle-hold-*.py                 # new gates (single home, dispatch filter, label copy, fixtures)
.github/scripts/*_tests/ + fixtures/                       # per-branch fixtures
.github/workflows/implement.yml                            # start check, held outcome
.github/workflows/lifecycle-review-gate.yml                # split disposition; analyze/decide jobs; merge condition 9; dismissed list
.github/workflows/pr-conversation.yml                      # drop job, strict-stop path, reply text
.github/workflows/clarify.yml                              # skip strict-stop comment
.github/workflows/{intake,plan,tasks,finalize}.yml        # exclude hold from label copy
.github/workflows/wing-commander-5-implement.yml           # issues: unlabeled trigger
.github/workflows/wing-commander-9-pr-conversation.yml     # lifecycle-stop job
docs/adoption.md                                           # wrapper trigger note
specs/062-*/contracts/readiness-and-merge.md               # condition 9
specs/116-*/contracts/convergence-signals.md               # dismissed fed by derivation
.specify/memory/constitution.md                            # X amendment (separate PR)
```

**Structure Decision**: Extend the existing composite/script/gate layout;
no new published stage workflow.

## Complexity Tracking

None.
