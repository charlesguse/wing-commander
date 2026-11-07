# Implementation Plan: Board Loop Works Maintenance Backlog Lines

**Branch**: `spec/121-board-backlog-line-items` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/121-board-backlog-line-items/spec.md` (lifecycle issue #1080)

## Summary

When no eligible issue is waiting, the board loop takes one unchecked top-level line from the Maintenance backlog issue (#889) as its work item. Line behaviour is concentrated in two new deterministic Python modules: `board_backlog_lines.py` (parse, select, id, annotation, branch/title derivation, closing-keyword check, selection gate) and `board_backlog_edit.py` (the single read-modify-write helper every backlog edit goes through). `board-loop.yml` gains an `item_kind` of `line` carried through its existing jobs, with each site that holds, routes, closes or ticks an item calling the line module instead of editing labels or closing the issue. State lives in a loop-authored marker comment keyed by a loop-minted line id. A new repository variable, `WING_COMMANDER_BOARD_BACKLOG_LINES` (default off), and a constitution phrase check gate new claims. See [research.md](research.md) for the decisions.

## Technical Context

**Language/Version**: Python 3 (stdlib only) for scripts; bash and `jq` in GitHub Actions YAML; no new dependencies.

**Primary Dependencies**: `gh` CLI, existing `board_item_marker.py`, `board_eligibility.py`, `board_merge.py` (`FIX_BRANCH_RE`), `board_triage.py`, `board_duplicate_disposition.py`, `board_prove*.py`.

**Storage**: GitHub issue body (line annotations) and loop-authored issue comments (markers). No files persisted.

**Testing**: Checked-in fixtures under `.github/scripts/tests/board-backlog-lines/` and `.../board-backlog-edit/`, exercised by new `verify-*.py` gates registered in the gate registry and run by `python .github/scripts/run-local-gates.py` and `lint-workflows.yml`.

**Target Platform**: GitHub Actions runners (Linux), local sessions for the edit helper CLI.

**Project Type**: CI/pipeline tooling in a workflow repository (scripts + workflows + gates).

**Performance Goals**: One line per run; one claim costs one read-modify-write plus read-back.

**Constraints**: Closing keyword never reaches a title, body or commit of a line PR (FR-017); body edits never lose a concurrent writer's change that landed before the re-read (FR-015); branch matches `fix/\d+-[a-z0-9-]{1,40}`; titles ≤256 chars; no other behaviour change when no line is claimed (FR-020).

**Scale/Scope**: ~140 open lines on #889; roughly the 9 board-loop jobs touched at their hold/route/close/prove sites; two new modules, two gates, one variable, one CLAUDE.md rule.

## Constitution Check

*GATE: passes before Phase 0; re-checked after Phase 1.*

| Principle | Assessment |
|---|---|
| IX Deterministic judgment for durable actions | Selection, claim, hold, tick, keyword refusal, constitution check are all code; the agent only proposes triage/route/fix as today. PASS |
| VIII Green check means what it says | New gates have fixtures for every failure branch (FR-019); registered in the gate registry and triggered by changes to their subjects. PASS |
| X Bounded autonomy | The feature extends X's entry to lines; spec FR-022/FR-025 make the merge conditional on the separate, human-merged amendment (#1115), checked in code at selection. This PR does not edit `constitution.md`. PASS, conditional on that amendment merging first |
| Spec-proposals never self-promoted | `route-proposal` files `spec-proposal` only, never `spec-request`. PASS |
| CLAUDE.md single home | Edit logic only in `board_backlog_edit.py`; gate scans for a second writer. PASS |

No violations; Complexity Tracking not needed.

**Post-design re-check**: unchanged. The only new surface is the annotation token and marker `line` field, both single-homed and fixture-covered.

## Project Structure

### Documentation (this feature)

```text
specs/121-board-backlog-line-items/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── backlog-lines.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
.github/
├── scripts/
│   ├── board_backlog_lines.py            # new: parse/select/id/annotate/title/keywords/gate
│   ├── board_backlog_edit.py             # new: FR-024 shared read-modify-write helper
│   ├── board_item_marker.py              # edit: optional `line` key on read/write
│   ├── board_eligibility.py              # edit: issue-path readers ignore line-keyed markers
│   ├── verify-board-backlog-lines.py     # new gate
│   ├── verify-board-backlog-edit.py      # new gate (incl. single-home scan)
│   └── tests/
│       ├── board-backlog-lines/          # new fixtures
│       └── board-backlog-edit/           # new fixtures
├── workflows/
│   ├── board-loop.yml                    # edit: item_kind, line sites, PR reference, keyword checks
│   └── board-status.yml                  # edit: show the new switch
CLAUDE.md                                 # edit: "Working the issue board" backlog-edit rule
```

**Structure Decision**: Follow the existing `board_*.py` module-per-concern layout with `verify-*.py` gates and fixture directories; no new directory conventions. The workflow changes are limited to calling the new modules at the existing hold/route/close/prove sites rather than forking jobs.

## Complexity Tracking

No constitution violations to justify.
