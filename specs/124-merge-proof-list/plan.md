# Implementation Plan: The Proof List

**Branch**: `124-merge-proof-list` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/124-merge-proof-list/spec.md`

**Layer**: consuming instrument (Principle VII). One repository-only wrapper workflow, its scripts and one section of the "Board status" issue. Nothing is added to the `workflow_call` published contract.

## Summary

A daily, read-only, agent-free workflow lists every first-parent commit on `main` in the last 30 days, puts each in exactly one of five states (needs no run / a comment names a run / no workflow reaches it / reached and no run finished / runs finished and no comment names one), and publishes states 4 and 5 plus counts as a collapsed section of the "Board status" issue. It gives no verdict and starts no run.

Technical approach:

1. **Classifier as pure code.** A new `.github/scripts/wc_proof_list.py` holds the pure half: `classify(entry_inputs) -> state`, comment qualification (FR-006/007/009), shared-issue detection, aged-out counting, and report rendering with graded shortening (FR-020). It does no I/O, so every branch is drivable from a checked-in fixture (Principle VIII).
2. **Runtime half.** The same module's `collect` side reads `git log --first-parent`, per-commit changed paths, PR/issue/comment threads and workflow runs through `gh api`, failing loudly on any incomplete read (FR-013).
3. **One home for the two rules (FR-002/003, SC-006).** The need-a-run rule stays in `board_prove.actions_only()`. The reach computation (transitive closure over `scan_dispatchable_and_uses_graph()`'s `uses_graph`, plus the FR-005 nightly rule) moves out of `.claude/skills/prove-after-merge/scripts/redrive_candidates.py` (`reach()`) into `board_prove.py`; the hand procedure and the proof list both import it. A new gate fails if a copy of either rule reappears.
4. **Entry's own tree (FR-004).** For each entry needing a run, extract `.github/` at that commit with `git archive <sha> .github | tar -x` into a fresh temp directory and run the existing scan with that directory as the working directory (the scan resolves repo-relative paths from cwd, so no change to its signature is needed). Trees are cached per commit within a build.
5. **Runs.** List runs by `created>=<oldest merge>` date-bounded and by workflow, paged; fail if any date slice hits the 1,000-run cap (FR-013). Contains-merge test is `git merge-base --is-ancestor <merge> <run head_sha>`; an unresolvable head SHA while `main` history is complete is "set apart" and counted.
6. **Publication (FR-021).** `wc_board_status.py` stays the issue's only writer. It gains a `--proof-section FILE` / `--proof-status {built,failed,paused}` option on `publish`, and `render()` embeds a `<details>` section between stable markers. `board-status.yml`'s daily rewrite carries the existing section forward (read from the current issue body), so a rewrite never drops or ages the list silently; on a failed/paused build the section is replaced by a notice plus the last-good build date (held in a marker comment), and the stale list is dropped. The proof-list workflow shares concurrency group `wing-commander-board-status` so the two writers serialize.
7. **Workflow.** `.github/workflows/wing-commander-proof-list.yml`: `schedule` (daily, offset from board-status) + `workflow_dispatch`; first step refuses if `github.ref != refs/heads/main` (before reading anything); job `if:` stands down on `vars.WING_COMMANDER_PROOF_LIST_PAUSED == 'true'` and a following always-gated step publishes the "paused" notice via `!cancelled()` reasoning reviewed with `review-step-gating`. Permissions: `contents: read`, `actions: read`, `pull-requests: read`, `issues: write` (only for the board-status issue edit by the shared writer). `fetch-depth: 0`. No agent, no App token, no dispatch.
8. **Docs.** `docs/reference.md` gains the loop (schedule, window, kill switch, report location) and its "Known limits" / board-loop prove-step text are checked (FR-022).

## Technical Context

**Language/Version**: Python 3 (stdlib + PyYAML, as the sibling `board_prove.py` / `wc_board_status.py`); GitHub Actions YAML; bash only for `git`/`gh` glue

**Primary Dependencies**: `gh` CLI (REST), `git`, PyYAML; existing `board_prove`, `board_item_marker`, `wc_board_status`

**Storage**: none; the only durable output is the section of the "Board status" issue body

**Testing**: checked-in fixture-driven `verify-proof-list.py` registered in the gate registry and `run-local-gates.py`, following `verify-board-status.py`; includes the SC-001 corpus replay with a checked-in expected-differences list

**Target Platform**: GitHub-hosted `ubuntu-latest`

**Project Type**: repository automation (scripts + one workflow + gates)

**Performance Goals**: complete within a 15-minute job timeout for ~50 merges/30 days and ~1,000+ runs

**Constraints**: zero writes other than the issue section; zero agents/dispatches; fail loudly on incomplete reads; report must fit one issue body (65,536 chars) without dropping entries

**Scale/Scope**: ~50 entries, tens of workflows, a few thousand runs per window

## Constitution Check

*GATE: passed pre-research; re-checked after design — still passes.*

| Principle | Outcome |
|---|---|
| I Guide | Built through the pipeline; PR cites this spec. Pass |
| II Model tiering | No Claude invocation (FR-016). Pass (n/a) |
| III GitHub-native | Report is a section of an existing issue read with `gh`. Pass |
| IV Automation-first | Scheduled; no manual step except the owner creating the kill-switch variable (FR-018), reported in the PR. Pass |
| V Security | No agent, no untrusted content as instructions; comment bodies are parsed as data only for run URLs / PR numbers / marker; default-branch-only; `permissions` least-privilege; `persist-credentials: false`. Pass |
| VI Portability | No hardcoded repo name; uses `github.repository`. Pass |
| VII Two interfaces | Repository-only wrapper, not `workflow_call`; internal shared code in `.github/scripts/`. Pass |
| VIII Green check | Every failure branch (refusal, pause, incomplete read, set-apart, shortening, over-size) has a fixture; new single-home gate for the two rules; gate registered and triggered by its subject paths. Pass |
| IX Deterministic judgment | All classification is code. Pass |
| X Bounded autonomy | Does not act on the board; changes no way a change is proven. Pass |

No violations; Complexity Tracking not needed.

## Project Structure

### Documentation (this feature)

```text
specs/124-merge-proof-list/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── proof-list-report.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
.github/
├── workflows/wing-commander-proof-list.yml      # new: schedule + dispatch wrapper
├── scripts/
│   ├── wc_proof_list.py                          # new: pure classifier/renderer + collect
│   ├── board_prove.py                            # gains reach() (moved from the skill script)
│   ├── wc_board_status.py                        # gains proof-section embed/carry-forward
│   ├── verify-proof-list.py                      # new gate: fixtures, SC-001 replay, no-write/no-dispatch assertions
│   ├── verify-proof-list-single-home.py          # new gate: SC-006 (or a check inside the above)
│   └── fixtures/proof-list/                      # checked-in corpus + expected differences
.claude/skills/prove-after-merge/scripts/redrive_candidates.py  # now imports reach()
.github/workflows/board-status.yml                # carries the section forward
docs/reference.md                                 # FR-022
```

**Structure Decision**: scripts-plus-one-workflow following the `board-status` precedent (pure render + runtime half, fixtures driving the pure half). The edit to files under `.claude/skills/` (skill script) is made at implement time by a human-reviewed PR, since stage agents may not write under `.claude/`; if the implement stage cannot, the move of `reach()` is handed to a maintainer and the gate allows the skill script to import it only (see research D2).
