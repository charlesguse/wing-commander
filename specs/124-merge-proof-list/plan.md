# Implementation Plan: The Proof List

**Branch**: `124-merge-proof-list` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/124-merge-proof-list/spec.md`

**Layer**: consuming instrument (Principle VII). One repository-only scheduled workflow of this repository, its scripts, and the content of one section of the "Board status" issue, which that issue's one writer publishes. Nothing is added to the `workflow_call` published contract.

## Summary

A daily, read-only, agent-free workflow lists every first-parent commit on the default branch in the last 30 days. It puts each in exactly one of five states (needs no run / a comment names a run / no workflow reaches it / reached and no run finished / runs finished and no comment names one), and hands states 4 and 5 plus the counts to `board-status.yml`, whose writer publishes them as a collapsed section of the "Board status" issue. It gives no verdict and starts no run.

Technical approach (the decisions are in [research.md](research.md); round 1 of the plan PR's review is folded in):

1. **Classifier as pure code** (D1). A new `.github/scripts/wc_proof_list.py` holds the pure half: classification, comment qualification (FR-006/007/009), shared-issue detection, set-apart and aged-out counting, and both renderings of the section (FR-020). It takes the window's end as a parameter. It does no I/O, so every branch is drivable from a checked-in fixture (Principle VIII).
2. **Runtime half** (D1, D4-D6, D15). `collect` reads the first-parent commits, each commit's PR (`commits/{sha}/pulls`), changed paths, comment threads, the runs of reaching workflows and every run a comment names (by id). It fails loudly on any incomplete read (FR-013). Its `gh` reads go through a reader that raises on failure. The subcommand the workflow runs, `build`, has no window option. A separate `capture` subcommand writes the SC-001 corpus (D13).
3. **One home for the two rules** (D2, D12; FR-002/003, SC-006). The need-a-run rule stays in `board_prove.actions_only()`. The whole reach computation moves into `board_prove.py`: the closure `reach()`, the literal-mention edge (`mention_edges()`), both combined as `reaching_workflows()`, plus `workflow_triggers()` and `runs_of_its_own()`. The hand procedure's skill script and the proof list both call them. FR-005's nightly edges are a separate `board_prove.nightly_e2e_edges()` that only the proof list merges in, so the hand procedure's output does not change. Gate 89 (`verify-board-prove.py`) gains the single-home check, with one interim exemption for the skill script until a `[maintainer]` commit thins it.
4. **Entry's own tree** (D3; FR-004). For each entry needing a run, extract `.github/` at that commit with `git archive <sha> .github | tar -x` into a fresh temp directory and run the scan, `reaching_workflows()` and `nightly_e2e_edges()` there. Trees are cached per commit within a build.
5. **Runs** (D4, D5). Runs are read per reaching workflow that has runs of its own, completed only, date-bounded and sliced by day when a query passes the 1,000-run cap. A run counts when the merge is an ancestor of its head (`git merge-base --is-ancestor`). Set apart is exactly FR-013's two cases, counted once across the window.
6. **Publication by hand-off** (D7, D8, D17; FR-015, FR-021). The proof-list workflow uploads the section's content as the artifact `proof-list-section` and holds no write permission. `wc_board_status.py` stays the issue's only writer:
   - `snapshot()` gains `proof_list_snapshot()`, which reads the proof-list workflow's finished default-branch runs, decides the status (`built`, `paused`, `failed`, `never` or `unreadable`) and the last good build, and downloads the latest build's artifact;
   - `render()` embeds the full form, else the names-only form, else the failed notice;
   - the new switch joins `SWITCH_ENV`, and `board-status.yml` gains its env line.
7. **Workflow** (D9, D11, D16, D17). `.github/workflows/wing-commander-proof-list.yml`:
   - **Triggers**: `schedule` (`19 6 * * *`, before board-status at 07:17) and `workflow_dispatch` with no inputs.
   - **Job**: own concurrency group `wing-commander-proof-list`, `timeout-minutes: 15`.
   - **Steps**: (1) refuse a dispatch whose ref is not the default branch, before anything else; (2) a pause-check step on `vars.WING_COMMANDER_PROOF_LIST_PAUSED`; (3) checkout with `fetch-depth: 0`, `persist-credentials: false`; (4) build; (5) upload. Steps 3-5 are gated on the pause output under the default `success()`, with no `always()` or `!cancelled()`.
   - **Permissions**: `contents: read`, `actions: read`, `issues: read`, `pull-requests: read`. No agent, no App token, no dispatch, no write.
8. **SC-001** (D13). The replay runs from a checked-in corpus and expected file, with no git or `gh`. Both files come from a `[maintainer]` capture against the saved 2026-11-16 lookup, held by the owner's sessions. Until they land, the check reports "not yet captured" under an exemption citing #1144.
9. **Docs** (D14; FR-022). `docs/reference.md`, `docs/setup.md` §3 and the README list the new loop, its schedule, window, kill switch and report location. reference.md's Known limits and its board-loop prove-step text are checked against what the list shows.

## Technical Context

**Language/Version**: Python 3 (stdlib + PyYAML, as the sibling `board_prove.py` / `wc_board_status.py`); GitHub Actions YAML; bash only for `git`/`gh` glue

**Primary Dependencies**: `gh` CLI (REST through `gh api`; `closingIssuesReferences` through `gh pr view --json`, which is GraphQL; `gh run download`), `git`, PyYAML. Existing homes reused, not copied (research D6 "Reused homes"): `board_prove`, `board_route_backstop.diff_name_list`, `board_backlog_lines.pr_issue`/`pr_line`, `board_triage.run_url_pattern`, `board_item_marker.last_marker_match`, `board_spec_request_body.utf16_len`/`MAX_BODY_UNITS`, `wc_board_status`

**Storage**: none of its own. The section's content is handed to the writer as a 7-day artifact. The only durable output is the section of the "Board status" issue, written by `wc_board_status.py publish`.

**Testing**:
- Checked-in fixtures drive `verify-proof-list.py` (new), `verify-board-status.py` and Gate 89 `verify-board-prove.py` (both extended); quickstart.md step 1 assigns each fixture to its gate.
- `verify-proof-list.py` is wired as an unnumbered `lint-workflows.yml` step, as `verify-board-status.py` is ("gate numbers are allocated by hand and collide", #773). `wc_gate_registry.pr_time_gates()` derives the gate set from those steps, and `verify-gate-wiring.py` fails an unwired `verify-*.py`. There is no separate registry to edit.
- New fixtures under `.github/scripts/fixtures/proof-list/` are already inside the `.github/scripts/**` path that triggers the suite.
- The SC-001 replay runs in the same depth-1 `lint` job.

**Target Platform**: GitHub-hosted `ubuntu-latest`

**Project Type**: repository automation (scripts + one workflow + gates)

**Performance Goals**: complete within a 15-minute job timeout for about 50 merges in 30 days and a few thousand runs

**Constraints**:
- **Writes**: no durable write other than the section content handed over as the artifact; no agents; no dispatches.
- **Reads**: fail loudly on any incomplete read.
- **Size**: the section fits the issue body (`MAX_BODY_UNITS`, counted in UTF-16 units) without dropping entries.
- **API budget** (D15): about 300-450 `GITHUB_TOKEN` calls per build, against a REST pool of 1,000 an hour shared with board-status, the review gates and PR CI. Runs are listed at `per_page=100`; comments are read only for entries that need a run; `gh api rate_limit` is checked first and the build fails below 600 remaining. A primary-limit 403/429 is a failed read with no back-off, and `Retry-After` is honoured only for secondary limits.

**Scale/Scope**: about 50 entries, tens of workflows, a few thousand runs per window (`board-loop.yml` alone had 790 in the 30 days to 2026-11-19)

## Constitution Check

*GATE: passed pre-research; re-checked after design and after round 1 of review — still passes.*

| Principle | Outcome |
|---|---|
| I Guide | Built through the pipeline; PR cites this spec. Pass |
| II Model tiering | No Claude invocation (FR-016). Pass (n/a) |
| III GitHub-native | Report is a section of an existing issue, read with `gh`; the hand-off is an Actions artifact. Pass |
| IV Automation-first | Scheduled. No manual step is needed to run it; pausing uses a variable only the owner creates (FR-018). Pass |
| V Security | No agent; comment bodies are parsed as data only for run links, PR references and the marker, and never reach the report. Default-branch-only, and the writer reads only default-branch runs of its own workflow. No write permission in the proof-list workflow; `persist-credentials: false`. Pass |
| VI Portability | No hardcoded repository or branch name: `github.repository`, and the default branch from the event or the API. Pass |
| VII Two interfaces | Repository-only wrapper, not `workflow_call`; internal shared code in `.github/scripts/`. Pass |
| VIII Green check | Every path has a fixture: refusal, pause, failed, never built, stale, unreadable, each FR-013 failed read, set-apart, shortening, over-size. Single-home checks for the two rules and the reused homes. Both interim exemptions are Gate-124-shaped and cite #1144. Pass |
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
├── workflows/
│   ├── wing-commander-proof-list.yml   # new: schedule + dispatch; refuse, pause step, build, upload artifact
│   ├── board-status.yml                # gains the PROOF_LIST_PAUSED env line
│   └── lint-workflows.yml              # gains the unnumbered verify-proof-list.py step
├── scripts/
│   ├── wc_proof_list.py                # new: pure classifier/renderers + collect + build/capture/render
│   ├── board_prove.py                  # gains reach, mention_edges, reaching_workflows, workflow_triggers,
│   │                                   #   runs_of_its_own, nightly_e2e_edges
│   ├── board_triage.py                 # gains any_run_url_pattern() beside run_url_pattern()
│   ├── wc_board_status.py              # gains SWITCH_ENV entry, proof_list_snapshot(), section render
│   ├── verify-proof-list.py            # new gate: fixtures, reused homes, workflow file, SC-001 replay,
│   │                                   #   EXEMPT_SC001_PENDING
│   ├── verify-board-status.py          # gains the writer's proof-list paths
│   ├── verify-board-prove.py           # Gate 89 gains the single-home check, EXEMPT_REACH_COPIES
│   └── fixtures/proof-list/            # synthetic cases; sc001/ (corpus.json, expected.json) from the
│                                       #   [maintainer] capture only
.claude/skills/prove-after-merge/scripts/redrive_candidates.py   # [maintainer] commit: imports from board_prove
docs/reference.md                       # FR-022
docs/setup.md                           # §3 row for the new variable
README.md                               # repository-only workflow list
```

**Structure Decision**: scripts plus one workflow, following the `board-status` precedent: a pure render and a runtime half, with fixtures driving the pure half. The implement stage cannot write under `.claude/` (its `no-write-paths` input defaults to `.claude/,.git/`), so the skill script edit is always a `[maintainer]` commit on the lifecycle branch before the final PR merges. Until then, Gate 89's `EXEMPT_REACH_COPIES` entry, citing #1144, excuses that one file (research D2).

## For the tasks stage

The tasks stage reads only this directory, so the task shapes the review asked for are stated here. Each line is a requirement on `tasks.md`.

- **Ordinary tasks** (buildable by the implement stage):
  - Move the reach computation into `board_prove.py` (research D2, D12). Add the single-home check to Gate 89 with `EXEMPT_REACH_COPIES` citing #1144. This task names no `.claude/` path.
  - Build `wc_proof_list.py`'s pure half, `collect`, `build`, `capture` and `render`; add `board_triage.any_run_url_pattern()`.
  - Extend `wc_board_status.py` (`SWITCH_ENV`, `proof_list_snapshot()`, section render) and `board-status.yml`'s env line.
  - Write `wing-commander-proof-list.yml` (research D16, D17).
  - Gate tasks: `verify-proof-list.py`, wired as an unnumbered `lint-workflows.yml` step; the `verify-board-status.py` and Gate 89 extensions. One fixture per path, as quickstart.md step 1 lists them, each failing without the code it tests: refuse, paused, failed, never built, stale, unreadable, timeout, each of FR-013's four failed reads, shortening and over-size. The single-home checks cover the reach computation, the mention edge, the FR-005 parser and research D6's reused homes.
  - The SC-001 replay check with `EXEMPT_SC001_PENDING` citing #1144 (research D13). It is the last buildable task. The implement stage must not create, edit or weaken `corpus.json` or `expected.json`, or the check that reads them.
  - A `review-step-gating` pass over `wing-commander-proof-list.yml` and the `board-status.yml` change.
  - **Docs task**:
    - `docs/reference.md`: a row in "Housekeeping and observability"; the Housekeeping line in "At a glance"; "Schedules" (06:19); "Kill switches"; the `board-status.yml` row's description; "Known limits" (the scan's under-reads and the state-3 line from research D14; a session proof form on a shared issue that names no PR, from research D6); and the board loop's prove-step row, checked against what the list shows (FR-022);
    - `docs/setup.md` §3: a row for `WING_COMMANDER_PROOF_LIST_PAUSED`, and the `WING_COMMANDER_BOARD_STATUS_PAUSED` row noting that it also stops the section's rewrite;
    - the README's list of repository-only workflows.
- **Final "Maintainer follow-up" phase**, each line tagged `[maintainer]` (the first two are not on the tasks prompt's list of maintainer kinds, so the tag must be written explicitly):
  - `[maintainer]` Thin `.claude/skills/prove-after-merge/scripts/redrive_candidates.py` to import its reach computation from `board_prove` and delete the interim exemption entry for it, in one commit on the lifecycle branch before the final PR merges. The `[maintainer]` tag alone keeps it out of the implement count (`.github/actions/_shared/count-tasks-checkboxes.sh` classifies the tag before anything else). Its only backticked path is the skill script, so `classify-out-of-boundary-tasks.sh` reads it as out of boundary too. The `board_prove.py` move stays a separate ordinary task, because a line that mixes a `.claude/` path with a buildable one reads as buildable, and implement would keep retrying a write it is denied.
  - `[maintainer]` Capture the SC-001 corpus and build the expected file, as research D13 lists, from a local session with full history and `gh` authentication, once the collector exists on the lifecycle branch, in one commit on that branch before the final PR merges. The answer key comes from the saved 2026-11-16 lookup, held by the owner's sessions. Recheck each merge against FR-007's App and `github-actions[bot]` rule, FR-006's shared-issue condition and FR-013's set-apart runs, and record each shift with its reason. Raise any shift whose reason is not one of SC-001's four with the owner instead of checking it in. Check in only what SC-001 needs, scrub any private project name, and delete `EXEMPT_SC001_PENDING`'s entry in the same commit.
  - `[maintainer]` After-merge proof, as quickstart.md step 4 lists it: dispatch from the default branch, then `board-status.yml`; dispatch from another branch; the owner sets and clears the switch.
