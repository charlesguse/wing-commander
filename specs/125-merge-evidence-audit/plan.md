# Implementation Plan: The Merge Evidence Audit

**Branch**: `125-merge-evidence-audit` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/125-merge-evidence-audit/spec.md`

**Layer**: consuming instrument (Principle VII). One repository-only scheduled workflow of this repository, its script, its gate, one artifact-backed store, and the content of one section of the "Board status" issue, which that issue's one writer publishes. Nothing is added to the `workflow_call` published contract.

## Summary

An hourly, read-only, agent-free job computes a verdict for every open pull request into `main` and records it in a cumulative ledger artifact. A daily job rebuilds the whole 30-day window: each merged PR with its verdict as of the merge (marked recorded or reconstructed), and each commit that reached `main` without a PR. `board-status.yml`'s writer displays the audit as a collapsed section. The workflow never merges, labels, comments, pushes or writes a check or status, and no existing merge job reads it.

Technical approach (decisions in [research.md](research.md)):

1. **One script, pure half and runtime half** (D4). `.github/scripts/wc_merge_evidence.py`: kind assignment, the condition list per kind, `cut_snapshot()` for as-of-merge, ledger replace/prune, audit and section renderers (pure, fixture-driven); `collect`, `verdicts`, `audit` subcommands (runtime). It takes the window's start and end as parameters; the workflow passes none, so the window is always now-30-days (FR-012).
2. **Calls the existing conditions** (D4; FR-008). Fix-PR and bump evidence come from `board_merge`; the "every status counts" rule from `board_readiness`; the final-PR rule from `lifecycle_merge_preconditions`. Private names those homes expose are given public aliases; no behaviour changes. A single-home check in the new gate fails a copy.
3. **Ledger artifact as the store** (D1, D2). `merge-evidence-ledger`, keyed `<pr>@<head>`, replaced per head, pruned at merge + 31 days; one writer at a time via a concurrency group; each hourly run starts from the last successful run's ledger.
4. **As of the merge** (D5). A pure time-cut of the snapshot is fed to the same evaluators.
5. **Workflow** (D3, D12). `wing-commander-merge-evidence.yml`: schedules `7 * * * *` and `41 5 * * *`, dispatch with a `job` selector; first step refuses a non-default ref; a pause step on `WING_COMMANDER_MERGE_EVIDENCE_PAUSED`; no `always()`/`!cancelled()`; read-only permissions.
6. **Publication by hand-off** (D10, D11). The audit job uploads `merge-evidence-section`; `wc_board_status.py` renders it (statuses built/paused/failed/never/unreadable, shortened form when over size) as spec 124's proof list does. Sessions read the latest verdict with `gh run download` (contract).
7. **One gate** (D9). `verify-merge-evidence.py`, an unnumbered `lint-workflows.yml` step: fixtures for every branch, single-home checks, workflow-shape checks, the FR-019 no-reader check, and the SC-003 replay behind an `EXEMPT_SC003_PENDING` entry citing #1143.
8. **Docs** (D13; FR-025). `docs/reference.md`, `docs/setup.md` §3, README.

## Technical Context

**Language/Version**: Python 3 (stdlib + PyYAML, as `board_merge.py`, `wc_proof_list.py`); GitHub Actions YAML; bash only for `git`/`gh` glue

**Primary Dependencies**: `gh` CLI (REST via `gh api`, `gh run download`), `git`, PyYAML; reused homes `board_merge`, `board_readiness`, `lifecycle_merge_preconditions`, `wc_board_status`, `board_item_marker`

**Storage**: the `merge-evidence-ledger` artifact (90-day retention, re-uploaded hourly); the daily section is a 7-day artifact. No issue, file, branch or variable is written.

**Testing**: checked-in fixtures under `.github/scripts/fixtures/merge-evidence/` drive `verify-merge-evidence.py` (new), `verify-board-status.py` (extended); error stubs built with `wc_shell_harness.gh_error_stub_arm`; the unnumbered gate step is derived by `wc_gate_registry.pr_time_gates()` and checked by `verify-gate-wiring.py`.

**Target Platform**: GitHub-hosted `ubuntu-latest`

**Project Type**: repository automation (script + one workflow + gate)

**Performance Goals**: hourly job under 5 minutes (timeout 10); daily audit under 15 minutes for about 50 merges

**Constraints**:
- No write beyond artifacts; no agents; no dispatches; no comment, label, review, status or check (FR-017, FR-020).
- Any incomplete read makes the verdict incomplete (FR-005) or fails the audit loudly; never a silent pass.
- API budget: verdicts about 8-10 REST calls per open PR plus one list; audit about 4 per merged PR; `gh api rate_limit` checked first, failing below 600 remaining.
- Section fits `MAX_BODY_UNITS` (UTF-16 units) with a names-only shortened form.

**Scale/Scope**: about 5-15 open PRs; about 50 merges and a ledger of under 1 MB per 30-day window

## Constitution Check

*GATE: passed pre-research; re-checked after design — still passes.*

| Principle | Outcome |
|---|---|
| I Guide | Built through the pipeline; PR cites this spec. Pass |
| II Model tiering | No Claude invocation (FR-020). Pass (n/a) |
| III GitHub-native | Verdict read with `gh`; report is a section of an existing issue. Pass |
| IV Automation-first | Scheduled; pause uses a variable only the owner creates (FR-022). Pass |
| V Security | No agent; comment bodies are data, never instructions; default-branch-only; fork heads never checked out; read-only token; no merge, approval or label. Pass |
| VI Portability | Repository and branch prefixes from `github.repository` and the configured prefix variables; none hard-coded. Pass |
| VII Two interfaces | Repository-only wrapper, not `workflow_call`; internal code in `.github/scripts/`. Pass |
| VIII Green check | Fixture per failure branch; verdict is never a check or status, so it cannot read as green; no checks is unmet (FR-006). Pass |
| IX Deterministic judgment | Every kind and condition is code. Pass |
| X Bounded autonomy | Watches only; merge jobs and rules unchanged and read nothing of this (FR-019, gate-checked). Pass |

No violations; Complexity Tracking not needed.

## Project Structure

### Documentation (this feature)

```text
specs/125-merge-evidence-audit/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── merge-evidence-report.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── wing-commander-merge-evidence.yml   # new: hourly verdicts + daily audit + dispatch
│   ├── board-status.yml                    # gains the MERGE_EVIDENCE_PAUSED env line
│   └── lint-workflows.yml                  # gains the unnumbered verify-merge-evidence.py step
├── scripts/
│   ├── wc_merge_evidence.py                # new: pure kinds/conditions/cut/ledger/renderers + collect/verdicts/audit
│   ├── board_merge.py                      # public aliases for reused names (no behaviour change)
│   ├── board_readiness.py                  # public aliases for _checks_green/_gate_suite_green
│   ├── lifecycle_merge_preconditions.py    # public alias for the unresolved-human-review test
│   ├── wc_board_status.py                  # SWITCH_ENV entry, merge_evidence_snapshot(), section render
│   ├── verify-merge-evidence.py            # new gate
│   ├── verify-board-status.py              # gains the writer's merge-evidence paths
│   └── fixtures/merge-evidence/            # synthetic cases; sc003/ from the [maintainer] capture only
docs/reference.md                           # FR-025
docs/setup.md                               # §3 row for the new variable
README.md                                   # repository-only workflow list
```

**Structure Decision**: script plus one workflow, following the proof-list and board-status precedents. No `.claude/` path is touched, so every task is buildable by the implement stage except the SC-003 corpus capture.

## For the tasks stage

- **Ordinary tasks**: public aliases in the three reused homes (existing gates must pass unchanged); `wc_merge_evidence.py` pure half, then runtime half; the workflow; `wc_board_status.py` and `board-status.yml` extension; `verify-merge-evidence.py` with one fixture per branch (each failing without the code it tests) wired unnumbered; the `review-step-gating` pass over the new workflow and the `board-status.yml` change; the docs task (D13).
- **Build details**:
  - Build steps set `GH_TOKEN: ${{ github.token }}`; `actions/checkout@v5`; upload `overwrite: true` (a re-run keeps the run id).
  - Download the ledger with `gh run download` in the script; a 404 is told apart by `gh`'s stderr `(HTTP 404)`; stubs via `wc_shell_harness.gh_error_stub_arm`.
  - Pause test calls `wc_board_status._switch_on`, not a literal comparison.
  - Gate 124: `EXEMPT_*` tables are parameters of the checks, never mutated.
  - `merge-evidence-section` and `merge-evidence-ledger` are single constants checked against the upload steps.
- **Final "Maintainer follow-up" phase**, tagged `[maintainer]`:
  - `[maintainer]` Capture the SC-003 corpus and expected file from the saved 2026-11-16 lookup and delete `EXEMPT_SC003_PENDING`'s entry in the same commit; raise any shift whose reason is not one of SC-003's with the owner.
  - `[maintainer]` After-merge proof (quickstart step 5): dispatch from default; dispatch off-default; set and clear the switch.
