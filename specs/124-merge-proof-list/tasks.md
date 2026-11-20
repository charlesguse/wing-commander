# Tasks: The Proof List

**Input**: Design documents from `specs/124-merge-proof-list/` (plan.md, spec.md, research.md, data-model.md, contracts/proof-list-report.md, quickstart.md)

**Tests**: Gates and fixtures are part of this feature (Principle VIII, plan "Testing"): every path has a checked-in fixture that fails without the code it tests. Fixtures live under `.github/scripts/fixtures/proof-list/`. Gates are wired as unnumbered `lint-workflows.yml` steps.

**Format**: `- [ ] T### [P?] [Story?] Description with file path`. `[P]` means a different file with no dependency on an incomplete task. `[maintainer]` tasks are only for the repository owner.

**Guidance (prose, not tasks)**: run `python .github/scripts/run-local-gates.py` before pushing and keep it green. Do not create, edit or weaken `corpus.json`, `expected.json` or the check that reads them beyond what T033 says. A deleted exemption entry belongs to its `[maintainer]` task. Gate 124's `verify-waiver-citations.py` forbids writing to an `EXEMPT_*` name, so checks take their table as a parameter and fixtures pass their own dict. Error stubs are built with `wc_shell_harness.gh_error_stub_arm` (Gate 127).

## Phase 1: Setup

- [x] T001 Create the fixture directory `.github/scripts/fixtures/proof-list/` with a short README stating which gate reads which fixture (per quickstart.md step 1); do not create `sc001/`.
- [x] T002 [P] Add `any_run_url_pattern()` beside `run_url_pattern()` in `.github/scripts/board_triage.py` (matches any Actions run URL, job links included, captures repository and run id), with a case in `.github/scripts/verify-board-triage.py` or the gate that already covers that module.

## Phase 2: Foundational (blocks all stories)

**Single home for the two rules (FR-002, FR-003, SC-006; research D2, D12)**

- [x] T003 Move the reach computation into `.github/scripts/board_prove.py`: `reach()`, `mention_edges()`, `reaching_workflows()`, `workflow_triggers()`, `runs_of_its_own()`. Keep the scan's inline `on:` read unchanged (plan "Build details"). Behaviour of the existing hand-procedure output must not change.
- [x] T004 Add `nightly_e2e_edges()` to `.github/scripts/board_prove.py` (FR-005: nightly end-to-end run reaches the stage workflows whose copies its wrappers run, each copied wrapper file, and what those reach). Move `STAGE_MAP_RE` from `.github/scripts/verify-e2e-provisioning-single-home.py` into `board_prove.py` and have that gate import it.
- [x] T005 Extend Gate 89 `.github/scripts/verify-board-prove.py` with the single-home check for the reach computation, the mention edge and the FR-005 parser, plus the reused homes of research D6. Take the exemption table (`EXEMPT_REACH_COPIES`, citing #1144, covering only the skill script until the maintainer commit) as a parameter; add fixtures for a reappearing copy and for a stale exemption.

**Checkpoint**: the rules have one home; the gate fails if a copy reappears.

## Phase 3: User Story 2 - Every entry is in exactly one state, decided by code (P1)

**Goal**: pure, deterministic classification and qualification.
**Independent test**: feed fixtures built to land in each of the five states, plus entries satisfying two at once; each lands in the first fitting state only.

- [x] T006 [US2] Create `.github/scripts/wc_proof_list.py` pure half (no I/O): `classify()` over Entry/FinishedRun/RecordComment per data-model.md "State" (first that fits; states 1-5), taking `start`/`end` as parameters (FR-008, FR-011). Cite data-model.md `Entry.needs_run`, `Entry.reaching`, `Entry.state`; use `board_prove.actions_only()` as the pair `(needs_run, needs_reason)`, never as a condition on the pair.
- [x] T007 [US2] In `.github/scripts/wc_proof_list.py` add comment qualification per data-model.md "RecordComment" steps 1-5 (FR-006, FR-007, FR-009): after-merge test, marker step `proven` only, unmarked bot account (`User`/`Bot`) never counts, shared-issue detection requiring the entry's PR to be named (`#N` with boundaries or PR URL), named-run qualification (started after merge, merge is ancestor of head). Cite data-model.md `RecordComment.marker_step` (`none` only when no opener is found; opener with no match or bad JSON is `other`) and `NamedRun.kind`.
- [x] T008 [US2] In `.github/scripts/wc_proof_list.py` add set-apart and aged-out counting per data-model.md "SetApartRun" (exactly FR-013's two cases, de-duplicated by run id or URL, unresolvable runs only when started after a relevant merge) and the aged-out count (FR-012: state 4 or 5 commits in the 24 hours before the window start, classified as if the window began a day earlier).
- [x] T009 [P] [US2] Add synthetic fixtures under `.github/scripts/fixtures/proof-list/` for each state, a two-states-at-once entry (state 2 beats 3), mixed docs/gate-script paths (not state 1), empty paths (state 1), the `prove`-step marker, unmarked App and `github-actions[bot]` notices, shared-issue comment with and without the PR named, pre-merge comment, run started before the merge, set-apart cases, and a fixed-window determinism pair (US2 scenario 4).
- [x] T010 [US2] Create the gate `.github/scripts/verify-proof-list.py` driving T009's fixtures through the pure half (each fixture fails without the code it tests); wire it as an unnumbered step in `.github/workflows/lint-workflows.yml` beside `verify-board-status.py`, so `verify-gate-wiring.py` passes. Assert the window is `end − 30 days` for `build` and that no report input can change it (US2 scenario 5).

**Checkpoint**: classification is fully fixture-tested.

## Phase 4: User Story 1 - See which entries have a run that could show them working and nothing on record (P1)

**Goal**: the report lists state-4 and state-5 entries with reaching workflows and per-workflow run counts.
**Independent test**: an entry reached by a workflow with a later finished run on a containing commit and no record comment is listed in state 5 with that run as earliest and latest.

- [x] T011 [US1] In `.github/scripts/wc_proof_list.py` add the per-workflow run summary for state-5 entries (count by event and conclusion, earliest and latest run link; FR-020) and the two renderings of the section: `full` and `names_only` (with the "shortened" line), per contracts/proof-list-report.md "Content when built": per-state counts, aged-out count, set-apart count, the standing State 3 line, a table of every state-4 and state-5 entry, "no runs of its own" marking, and no wording of verdict (FR-010). Cite data-model.md `Report.full`, `Report.names_only`, `Report.counts`, `Report.aged_out`, `Report.set_apart`.
- [x] T012 [US1] In `.github/scripts/wc_proof_list.py` add report assembly (`proof-list-section.json`, schema 1, per data-model.md "Report"): `built_at`, `window`, `head_sha`, and size handling using `board_spec_request_body.utf16_len`/`MAX_BODY_UNITS`: the full form if it fits, the names-only form otherwise, failing the build if even that does not fit (FR-020). Never drop an entry.
- [x] T013 [P] [US1] Add fixtures: hundreds of runs for one workflow collapse to counts plus earliest/latest (US1 scenario 5), state-4 entry, state-5 entry, a run of a reaching workflow whose commit cannot be resolved plus a comment naming a foreign run (US1 scenario 9), names-only form asserting the "shortened" line and every state-4/5 entry present, over-size failure. Extend `.github/scripts/verify-proof-list.py` to drive them.
- [x] T014 [US1] In `.github/scripts/wc_proof_list.py` add the runtime reader `collect`: reads first-parent commits of the default branch in the window (and the aged-out day), each commit's PR from `commits/{sha}/pulls` (the one whose `merge_commit_sha` equals the sha), changed paths via `board_route_backstop.diff_name_list`, named issues (`closingIssuesReferences` via `gh pr view --json`, `board_backlog_lines.pr_issue`/`pr_line`, lifecycle issue from the merge tree's `spec-meta.json`), and comment threads on the PR, its named issues and the lifecycle issue. All `gh` reads go through a reader that raises on failure. Cite data-model.md `Entry.named_issues`, `Entry.lifecycle_issue`.
- [x] T015 [US1] In `.github/scripts/wc_proof_list.py` extend `collect` with runs: per reaching workflow that has runs of its own, completed runs only, date-bounded and sliced by day when a query passes the 1,000-run cap, `per_page=100`; `event` filtered client-side (the runs API takes one value); ancestry via `git merge-base --is-ancestor`; each run a comment names read by id (`actions/runs/{id}`) with 404 told apart by `gh` stderr `(HTTP 404)`. Read comment namings with `board_triage.any_run_url_pattern()`.
- [x] T016 [US1] In `.github/scripts/wc_proof_list.py` make every FR-013 incomplete read fail loudly: runs past the cap, incomplete `main` history, unreadable comment thread, unresolvable tree, and any non-404 API error; check `gh api rate_limit` first and fail below 600 remaining; treat primary-limit 403/429 as a failed read without back-off, honouring `Retry-After` only for secondary limits (research D15). Add fixtures (via `wc_shell_harness.gh_error_stub_arm`) for each failed read and extend `verify-proof-list.py`.
- [x] T017 [US1] In `.github/scripts/wc_proof_list.py` add the `build` subcommand (no window option; `end` = now, `start = end − 30 days`) that runs `collect`, classifies, assembles and writes `proof-list-section.json`; and the `render` subcommand. Add a `capture` subcommand that writes the SC-001 corpus (data-model.md "SC-001 corpus"), so the maintainer capture can run it; do not run it.

**Checkpoint**: a full report is produced from fixtures and from live reads.

## Phase 5: User Story 3 - The list reads each entry's own tree (P2)

**Goal**: reach is decided from the tree at the entry's merge.
**Independent test**: an entry that added a reaching workflow lists it; a workflow deleted later is still credited.

- [x] T018 [US3] In `.github/scripts/wc_proof_list.py` add per-entry tree extraction (`git archive <sha> .github | tar -x` into a fresh temp directory, cached per commit within a build), run `board_prove.reaching_workflows()` and `board_prove.nightly_e2e_edges()` there, and merge the nightly edges only in the proof list (the hand-procedure output must not change). Read runs of a later-deleted reaching workflow like any other (FR-013). Cite data-model.md `ReachingWorkflow.reached_via`, `ReachingWorkflow.runs_of_its_own`; drop a `workflow_call`-only workflow when an in-repository caller reaches the same path.
- [x] T019 [P] [US3] Add fixtures (a small synthetic repository history or recorded tree listings) for an entry adding a workflow (listed), an entry whose reaching workflow a later commit deleted (still listed), and a stage-workflow change reached by the nightly run (FR-005, US1 scenario 4); extend `verify-proof-list.py` to cover them.

## Phase 6: User Story 4 - It is safe to leave running (P2)

**Goal**: scheduled, read-only, agent-free, default-branch-only, paused by a switch, published as a section of "Board status".
**Independent test**: dispatch off the default branch refuses; a set switch stands down; a normal run's only output is the section content.

- [x] T020 [US4] Write `.github/workflows/wing-commander-proof-list.yml` (research D9, D11, D16, D17): triggers `schedule` (`19 6 * * *`) and `workflow_dispatch` with no inputs; one job, concurrency group `wing-commander-proof-list`, `timeout-minutes: 15`; permissions `contents: read`, `actions: read`, `issues: read`, `pull-requests: read` only. Steps in order: (1) a first step that exits 1 on a ref that is not the default branch; (2) pause-check on `vars.WING_COMMANDER_PROOF_LIST_PAUSED` through `wc_board_status._switch_on`'s test; (3) `actions/checkout@v5` with `fetch-depth: 0`, `persist-credentials: false`; (4) build with `GH_TOKEN: ${{ github.token }}`; (5) upload artifact `proof-list-section` (7 days). Steps 3-5 are gated on the pause output under default `success()`, with no `always()` or `!cancelled()`. No agent, App token, dispatch or write.
- [x] T021 [US4] Extend `.github/scripts/wc_board_status.py`: add the switch to `SWITCH_ENV`, `proof_list_snapshot()` (reads the proof-list workflow's finished default-branch runs, decides `built`/`paused`/`failed`/`never`/`unreadable`, last good build, downloads artifact with `gh run download`), and the section render in `render()` reading `snap.get("proof_list")` (full form if the body fits `MAX_BODY_UNITS`, else names-only, else the failed notice; the contract's markers). `proof-list-section` is one constant shared with the check in T023. Add the env line to `.github/workflows/board-status.yml`.
- [x] T022 [P] [US4] Add fixtures for the section statuses per research D17 and contracts/proof-list-report.md "Content otherwise": built, paused, failed (failed build, no build in 48 hours, over-size), never, unreadable (last good known and unknown), stale; a refused run changes nothing the section shows.
- [x] T023 [US4] Extend `.github/scripts/verify-board-status.py` (`SNAP` gains a `proof_list` entry; check the artifact constant against the upload step and the new env line) with T022's fixtures, and extend `.github/scripts/verify-proof-list.py` with the workflow-file assertions: refusal first, pause step, permissions list, no `dispatch`/comment/label/close/edit call, no agent step, upload name, schedule, no dispatch inputs (FR-014 to FR-019, SC-004, SC-007). Fixtures for refuse, paused, failed, never, unreadable and timeout.

**Checkpoint**: the loop is runnable and safe; the owner creates the repository variable.

## Phase 7: Polish and cross-cutting

- [x] T024 Docs (FR-022; research D14): `docs/reference.md` (row in "Housekeeping and observability", the Housekeeping line in "At a glance", "Schedules" 06:19, "Kill switches", the `board-status.yml` row's description, "Known limits" for the scan's under-reads, the state-3 line and a session proof on a shared issue naming no PR, and the board loop's prove-step row checked against what the list shows); `docs/setup.md` §3 (a row for `WING_COMMANDER_PROOF_LIST_PAUSED`; note on the `WING_COMMANDER_BOARD_STATUS_PAUSED` row that it also stops the section's rewrite); the README's list of repository-only workflows.
- [x] T025 Run the `review-step-gating` skill over `.github/workflows/wing-commander-proof-list.yml` and the `.github/workflows/board-status.yml` change; apply findings in those files.
- [x] T026 Add the SC-001 replay check and `EXEMPT_SC001_PENDING` (citing #1144, reports "not yet captured" while `sc001/corpus.json` and `expected.json` are absent; a stale entry fails) to `.github/scripts/verify-proof-list.py`, passing the table as a parameter; the replay needs no git or `gh`, applies the expected-differences rules of data-model.md, and fails on an expected difference that no longer differs. Include a synthetic corpus fixture that proves the check fails on each mismatch. This is the last buildable task; never create the real corpus or expected files.
- [x] T027 Run `python .github/scripts/run-local-gates.py` and fix every failure inside this feature's files (including Gate 124 and `verify-gate-wiring.py`).

## Phase 8: Maintainer follow-up

- [ ] T028 [maintainer] Thin `.claude/skills/prove-after-merge/scripts/redrive_candidates.py` to import its reach computation from `board_prove` and delete the `EXEMPT_REACH_COPIES` entry for it, in one commit on the lifecycle branch before the final PR merges.
- [ ] T029 [maintainer] Capture the SC-001 corpus with `wc_proof_list.py capture` and build `expected.json` from the saved 2026-11-16 lookup (research D13), from a local session with full history and `gh`; recheck each merge against FR-007, FR-006's shared-issue condition and FR-013 set-apart runs, record each shift with a reason, raise any shift outside SC-001's four reasons, scrub private names, and delete the `EXEMPT_SC001_PENDING` entry in the same commit, before the final PR merges.
- [ ] T030 [maintainer] Create and later clear the repository variable `WING_COMMANDER_PROOF_LIST_PAUSED` when exercising the switch (FR-018).
- [ ] T031 [maintainer] After-merge proof (quickstart.md step 4): dispatch the workflow from the default branch, then `board-status.yml`; dispatch from another branch and confirm refusal; set and clear the switch.

## Dependencies and order

- Phase 1 → Phase 2 (T003 → T004 → T005) blocks everything.
- US2 (T006-T010) first: the classifier and gate. US1 (T011-T017) depends on US2. US3 (T018-T019) depends on T014-T015 and T003-T004. US4 (T020-T023) depends on T012 and T017.
- T024-T027 after the stories; T026 last of the buildable tasks. Phase 8 after merge of the ordinary tasks; T028 and T029 before the final PR merges.

## Parallel opportunities

T002 with T003; T009 with T006-T008; T013, T019, T022 are fixture-only and can run beside their code tasks; T024 beside T025.

## Implementation strategy

MVP is US2 + US1 (T001-T017): a classifier and report produced from fixtures and live reads. Then US3 (own-tree accuracy), then US4 (workflow and publication), then docs and the SC-001 replay; the maintainer captures last.

## Review Gate Round 1 Findings

- [x] Review finding: Missing spec-meta.json aborts whole proof-list build

  lifecycle_issue() only treats NotFound (HTTP 404) as skippable, but git show for a missing path exits 128 with 'does not exist', so it raises ReadError and main() exits 1.

  - .github/scripts/wc_proof_list.py

  Detail: A Finalize PR touching a spec dir with no spec-meta.json at that commit fails the daily build until it ages out of the window.

- [x] Review finding: Waiver cites issue 1144 that will close on merge

  EXEMPT_REACH_COPIES cites issue 1144 (the lifecycle item), so closing it turns Gate 124 red on main while PRs stay green.

  - .github/scripts/verify-board-prove.py

  Detail: Repoint the waiver at the open Maintenance backlog issue or another tracker that stays open.

- [x] Review finding: O(runs x entries) git subprocesses may exceed job timeout

  run_record() spawns one git merge-base --is-ancestor per (run, entry) plus per-run commit_present calls, which can reach tens of thousands of subprocesses against a 15-minute timeout.

  - .github/scripts/wc_proof_list.py

  Detail: Cache is_ancestor by (sha, head) or compute containment once per distinct head_sha.

- [x] Review finding: counting_runs counts cancelled/skipped runs

  Every completed run whose head contains the merge counts regardless of conclusion, so cancelled or skipped runs move an entry from state 4 to state 5 and lose the re-drive nudge.

  - .github/scripts/wc_proof_list.py

  Detail: Decide explicitly which conclusions count and add a fixture.

- [x] Review finding: Run-URL repository comparison is case-sensitive

  key[0] == repository fails for differently capitalised owner/repo in a proof comment's run URL, so a genuine own-repo run is treated as set apart.

  - .github/scripts/wc_proof_list.py

  Detail: Compare lower-cased; the same applies in set_apart() and named_runs().

- [x] Review finding: NotFound fallback in workflow_runs silently truncates at the cap

  The fallback lists the whole repo run stream with no RUN_CAP or day-splitting check, so a truncated list shrinks the counting runs without failing loudly.

  - .github/scripts/wc_proof_list.py

  Detail: Apply the same total_count > RUN_CAP check or raise ReadError.

- [x] Review finding: proof_list_snapshot can crash the Board status rewrite

  It catches only CalledProcessError, ValueError, KeyError and OSError, so a malformed API shape raising AttributeError or TypeError aborts the whole daily publish.

  - .github/scripts/wc_board_status.py

  Detail: Add TypeError/AttributeError or wrap the call so failure becomes status unreadable.

- [x] Review finding: Daily-times table row out of time order

  The 06:19 proof list row is placed after 06:37 (and 05:43) in the time-ordered table; it belongs between 05:43 and 06:37.

  - docs/reference.md

## Review Gate Round 2 Findings

- [x] Review finding: capture subcommand cannot build the SC-001 corpus window

  capture builds a 30-day window ending at --end via Collector window_for(built_at), not the 33-day corpus window, and --as-of is only stored, never used to drop later comments/runs.

  - .github/scripts/wc_proof_list.py

  Detail: capture(collect(repo, args.end), as_of); corpus needs 2026-10-15..2026-11-17 and filtering at as_of per D13.

- [x] Review finding: Per-day run slicing double-counts runs on slice boundaries

  workflow_runs slices use inclusive created=A..B and the next slice starts at B, so a run created exactly at midnight appears twice and inflates workflow_summary counts.

  - .github/scripts/wc_proof_list.py

  Detail: De-duplicate by run id or end each slice one second early.

- [x] Review finding: Secondary-rate-limit back-off likely never triggers

  _run only waits when gh stderr matches retry-after, which gh api normally does not print, so secondary limits become immediate ReadError; the stub in the verify gate hides this.

  - .github/scripts/wc_proof_list.py
  - .github/scripts/verify-proof-list.py

  Detail: Add a fixed bounded wait when secondary-limit text matches without Retry-After.

- [x] Review finding: Exemption namedtuple duplicated across two verify scripts

  Exemption with identical fields is defined in both verify-board-prove.py and verify-proof-list.py, violating the single-home rule.

  - .github/scripts/verify-board-prove.py
  - .github/scripts/verify-proof-list.py

  Detail: Define once and import.

## Maintainer Feedback

- [ ] R1-a Take `<slug>` from `headRefName` (`spec/<slug>`) in `Collector.lifecycle_issue()` in `wc_proof_list.py`, using the `gh pr view` call the collector already makes.
- [ ] R1-b Read only `specs/<slug>/spec-meta.json` in the merge commit's tree and cross-check `.issue` against the title's `(#N)`.
- [ ] R1-c Add a fixture where a final PR touches two spec directories and only its own spec's issue is used.
- [ ] R1-d Add a fixture where its own spec's issue really disagrees with the title, which must fail.

## Maintainer Feedback

- [ ] R2-a Convert to UTC (`astimezone(datetime.timezone.utc)`) before formatting in `Collector.entries` and every other place a time is serialised.
- [ ] R2-b Normalise to UTC in `parse_time` and `window_for`.
- [ ] R2-c Add a fixture with a `-05:00` commit and a comment posted between the local and the UTC merge time, which must not count.

## Maintainer Feedback

- [ ] R3-a In `verify-board-prove.py` `single_home_fixture_cases`, give the three `EXEMPT_REACH_COPIES` cases (unthinned consumer, stale entry, missing file) each a local dict with its own `Exemption(...)` row.
- [ ] R3-b In `verify-proof-list.py` `check_sc001_fixtures`, give the two `EXEMPT_SC001_PENDING` cases a local dict with its own `Exemption(...)` row.
- [ ] R3-c Do not touch the module-level `EXEMPT_*` tables or their entries.
- [ ] R3-d Show that emptying either live table no longer fails these fixtures.
