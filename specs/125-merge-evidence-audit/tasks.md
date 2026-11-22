# Tasks: The Merge Evidence Audit

**Input**: Design documents from `/specs/125-merge-evidence-audit/` (plan.md, spec.md, research.md, data-model.md, contracts/merge-evidence-report.md, quickstart.md)

**Tests**: The plan requires one fixture per branch, each failing without the code it tests, driven by the new gate `verify-merge-evidence.py`. Fixture tasks are therefore included.

**Format**: `- [ ] T### [P?] [maintainer?] [Story] Description with file path`. Field constraints are cited to `data-model.md` by `Entity.field` and not restated.

Run `python .github/scripts/run-local-gates.py` before pushing; every task leaves the existing gate suite green. That is guidance, not a task.

## Phase 1: Setup

- [x] T001 Create the fixture directory `.github/scripts/fixtures/merge-evidence/` with a README line saying `sc003/` is filled only by the maintainer capture (T036).
- [x] T002 [P] Add public aliases for reused private names in `.github/scripts/board_merge.py` (fix-PR and bump evidence, snapshot completeness, run confirmation), with no behaviour change.
- [x] T003 [P] Add public aliases for `_checks_green` and `_gate_suite_green` in `.github/scripts/board_readiness.py`, with no behaviour change.
- [x] T004 [P] Add a public alias for the unresolved-human-review test in `.github/scripts/lifecycle_merge_preconditions.py`, with no behaviour change.

## Phase 2: Foundational (blocks all stories)

- [x] T005 Create `.github/scripts/wc_merge_evidence.py` pure half: kind assignment per FR-002 (`VerdictRecord.kind`, `VerdictRecord.kind_facts` in data-model.md), the ordered condition list per kind (`Condition.name`, `Condition.result`, `Condition.reason` in data-model.md), `first_unmet`, `rule_applied` (`VerdictRecord.rule_applied`), and the reported-record classifier (`Reported record.kind`). Condition logic calls the aliases from T002-T004; it copies none of it.
- [x] T006 Add to `.github/scripts/wc_merge_evidence.py` the ledger functions: replace per `(pr, head)` and prune at merge + 31 days / close + 7 days (data-model.md `Ledger.records`), and the unparseable-fails / absent-starts-empty load rule.
- [x] T007 Define `LEDGER_ARTIFACT = "merge-evidence-ledger"` and `SECTION_ARTIFACT = "merge-evidence-section"` as single constants in `.github/scripts/wc_merge_evidence.py`.

**Checkpoint**: pure half importable; existing gates pass unchanged.

## Phase 3: User Story 1 - Verdict for an open PR on the exact head (P1) 🎯 MVP

**Goal**: an hourly run writes a verdict record per open PR head into the ledger artifact.

**Independent Test**: fixtures for each scenario of spec User Story 1 produce the expected `VerdictRecord`; the workflow runs read-only from the default branch.

- [x] T008 [P] [US1] Fixtures under `.github/scripts/fixtures/merge-evidence/verdict-*/` for: all-met board-fix PR; review verdict naming another commit; bump with unconfirmed run; clean final PR round at head; maintainer-account comment listed as reported and not counted (`Reported record`); incomplete snapshot (`VerdictRecord.complete`, `VerdictRecord.not_read`); no checks on head.
- [x] T009 [US1] Implement the runtime `collect` and `verdicts` subcommands in `.github/scripts/wc_merge_evidence.py`: fresh snapshot per head (FR-004), `gh api rate_limit` check failing below 600, incomplete marking (FR-005), ledger download via `gh run download` with 404 told apart by stderr `(HTTP 404)`, ledger write at `ledger.json`.
- [x] T010 [US1] Create `.github/workflows/wing-commander-merge-evidence.yml`: schedules `7 * * * *` and `41 5 * * *`, `workflow_dispatch` input `job`, first step refusing a non-default ref (FR-021), pause step using `WING_COMMANDER_MERGE_EVIDENCE_PAUSED` (FR-022), read-only permissions, `GH_TOKEN: ${{ github.token }}`, `actions/checkout@v5`, concurrency group for one ledger writer, hourly job timeout 10, upload of `merge-evidence-ledger` with `overwrite: true`, no `always()`/`!cancelled()`, no agent step.
- [x] T011 [US1] Create `.github/scripts/verify-merge-evidence.py` with the verdict fixture checks from T008, the single-home checks (a copy of either "checks green" rule or the final-PR rule fails), and error-stub cases built with `wc_shell_harness.gh_error_stub_arm`.
- [x] T012 [US1] Add the unnumbered `verify-merge-evidence.py` step to `.github/workflows/lint-workflows.yml` and confirm `verify-gate-wiring.py` accepts it.

**Checkpoint**: MVP — verdicts recorded hourly and readable via the contract's `gh run download` recipe.

## Phase 4: User Story 2 - Daily audit of everything that reached main (P1)

**Goal**: the daily job rebuilds the 30-day window and the Board status issue shows it.

**Independent Test**: fixture window with a recorded merge, a reconstructed merge and a direct push lists all three correctly.

- [x] T013 [P] [US2] Add `cut_snapshot()` to `.github/scripts/wc_merge_evidence.py` (as-of-merge time cut, FR-012) and the audit-entry builder (`Audit entry.mark`, `Audit entry.prior_record_result`, `Audit entry.decision_record` in data-model.md), plus unpaired-commit detection (`Unpaired commit` in data-model.md) excluding squash commits of merged PRs.
- [x] T014 [P] [US2] Fixtures under `.github/scripts/fixtures/merge-evidence/audit-*/`: recorded merge, reconstructed merge, post-merge runs left out, unpaired commit, session decision record linked and not counted, missed-day rebuild, squash commit not listed as unpaired.
- [x] T015 [US2] Implement the runtime `audit` subcommand in `.github/scripts/wc_merge_evidence.py`; the window start and end are parameters, and the workflow passes none (FR-012). Render the section object (`Section` in data-model.md) and write it for upload.
- [x] T016 [US2] Add the daily audit job to `.github/workflows/wing-commander-merge-evidence.yml` (timeout 15 minutes) that uploads `merge-evidence-section` with `overwrite: true` and 7-day retention.
- [x] T017 [US2] Extend `.github/scripts/verify-merge-evidence.py` with the audit fixture checks from T014 and a check that the artifact names in the workflow equal the constants from T007.
- [x] T018 [P] [US2] Add `merge_evidence_snapshot()`, the `SWITCH_ENV` entry and the collapsed-section renderer with statuses built/paused/failed/never/unreadable and the names-only shortened form over `MAX_BODY_UNITS` to `.github/scripts/wc_board_status.py`.
- [x] T019 [US2] Add the `MERGE_EVIDENCE_PAUSED` env line to `.github/workflows/board-status.yml`; the pause test calls `wc_board_status._switch_on`, not a literal comparison.
- [x] T020 [US2] Extend `.github/scripts/verify-board-status.py` with the writer's merge-evidence paths: each status and the shortened form.

**Checkpoint**: audit visible in Board status.

## Phase 5: User Story 3 - The watcher can never block, merge or be steered (P2)

**Goal**: provable read-only, default-branch-only, switchable, unread by merge jobs.

**Independent Test**: gate checks on the workflow's shape and on the merge jobs' sources all pass; each fails when its subject is broken.

- [x] T021 [P] [US3] Extend `.github/scripts/verify-merge-evidence.py` with workflow-shape checks: read-only `permissions:`, no write verbs to checks/statuses/labels/reviews/merges/pushes/comments, no `always()`/`!cancelled()`, no agent action, non-default-ref refusal as the first step, pause step present (FR-017, FR-020 to FR-023).
- [x] T022 [P] [US3] Extend `.github/scripts/verify-merge-evidence.py` with the FR-019 no-reader check: `board-merge` and `lifecycle-review-gate` sources and workflows reference neither artifact constant nor `wc_merge_evidence`.
- [x] T023 [P] [US3] Add a negative fixture for each T021/T022 check, mutating a copy in memory so each check is shown to fail; `EXEMPT_*` tables are parameters of the checks, never mutated.
- [x] T024 [US3] Add the SC-003 replay check in `.github/scripts/verify-merge-evidence.py` behind an `EXEMPT_SC003_PENDING` entry citing `#1143`, so gate 124 sees a tracker for it.

## Phase 6: Polish and cross-cutting

- [x] T025 [P] Update `docs/reference.md`: the workflow, its schedule, the `WING_COMMANDER_MERGE_EVIDENCE_PAUSED` switch, the "Merge classes" and "Known limits" sections (FR-025).
- [x] T026 [P] Add the `WING_COMMANDER_MERGE_EVIDENCE_PAUSED` row to `docs/setup.md` §3 and list the workflow among the repository-only workflows in `README.md`.
- [x] T027 Run the `review-step-gating` skill over `.github/workflows/wing-commander-merge-evidence.yml` and the `board-status.yml` change, and fix findings.
- [x] T028 Walk `quickstart.md` steps that need no dispatch against the fixtures, then run `python .github/scripts/run-local-gates.py` and fix what it reports.

## Phase 7: Maintainer follow-up

- [ ] T029 [maintainer] Capture the SC-003 corpus under `.github/scripts/fixtures/merge-evidence/sc003/` and its expected file from the saved 2026-11-16 lookup, and delete the `EXEMPT_SC003_PENDING` entry in the same commit; raise any shift whose reason is not one of SC-003's with the owner.
- [ ] T030 [maintainer] After merge, prove it (quickstart step 5): dispatch from the default branch, dispatch off the default branch, and set and clear the switch.

## Dependencies and order

- Phase 1 → Phase 2 → US1 → US2 (the audit reads the ledger format) → US3 (checks the finished workflow and script) → Polish → Maintainer follow-up.
- T002–T004 parallel; T008 parallel with T005–T007 only after T005 fixes the record shape; T013, T014 and T018 parallel; T021–T023 parallel.
- T011, T017, T021–T024 all edit `verify-merge-evidence.py` and must run in sequence.
- T029 deletes T024's exemption entry.

## Implementation strategy

MVP is Phase 1–3 (US1): hourly verdicts in the ledger, gated. Then US2 for the audit and Board status section, then US3 for the proofs of non-interference, then docs. Each phase leaves the gate suite green.

## Summary

- Total tasks: 30 (T001–T030)
- Setup 4, Foundational 3, US1 5, US2 8, US3 4, Polish 4, Maintainer 2

## Review Gate Round 1 Findings

- [x] Review finding: Ledger download can pick a successful run with no ledger artifact and reset history

  download_ledger uses the latest successful run (limit 1); audit or paused runs upload no merge-evidence-ledger, so the next run starts empty and loses all recorded verdicts.

  - .github/scripts/wc_merge_evidence.py

  Detail: Pick the latest successful run that actually has the artifact, and treat 'no valid artifacts' as an error where one is expected.

- [x] Review finding: cut_snapshot leaves counts.comments stale so snapshot_complete fails

  After dropping post-merge comments, counts['comments'] still holds the full count, so board_merge.snapshot_complete is false whenever a post-merge comment existed and entries show INCOMPLETE.

  - .github/scripts/wc_merge_evidence.py

  Detail: Set cut counts to the kept lengths and add a fixture with a post-merge comment.

- [x] Review finding: EXEMPT_SC003_PENDING cites #1143, which the final PR closes

  Gate 124 runs on main and on the daily schedule, so closing #1143 while the waiver remains turns main red. Repoint the waiver to an issue that stays open, such as the Maintenance backlog.

  - .github/scripts/verify-merge-evidence.py

- [x] Review finding: open_verdicts lists every ledger record for open PRs, not the latest head per PR

  Each pushed head adds a record, so superseded heads show as open verdicts, with one API call per record.

  - .github/scripts/wc_merge_evidence.py

  Detail: Group by PR, keep the newest computed_at, and look up each PR's state once.

- [x] Review finding: collect hard-codes base=main and ignores --default-branch

  The open-PR query and assign_kind use main/BASE_BRANCH rather than the default branch the workflow passes, so a repository with a different default branch gets verdicts for the wrong set.

  - .github/scripts/wc_merge_evidence.py

- [x] Review finding: Unpaired-commit detection assumes one commit per PR

  A rebase merge puts several commits on main, but only merge_commit_sha is excluded, so the others are reported as having reached main without a pull request.

  - .github/scripts/wc_merge_evidence.py

- [x] Review finding: Dead guard 'snapshot lists' not in not_read

  not_read holds whole strings, so the membership test is always true and a duplicate near-identical reason can be appended. Use a startswith check or drop the guard.

  - .github/scripts/wc_merge_evidence.py

- [x] Review finding: Schedules table row for 05:41 is out of time order

  The 05:41 merge evidence audit row sits after the 05:43 row in a time-ordered table. Move it above.

  - docs/reference.md

## Review Gate Round 2 Findings

- [x] Review finding: Open final/spec PRs classed maintainer because cross_repository is set after assign_kind

  _extend_with_evidence calls assign_kind before snap["cross_repository"] is set and the snapshot never fetches isCrossRepository, so same-repo spec PRs are classed maintainer and their issue comments/labels are never read, leaving hourly verdicts for open final PRs unmeetable.

  - .github/scripts/wc_merge_evidence.py

  Detail: assign_kind at ~line 1545 runs before cross_repository is set at ~1549; SNAPSHOT_FIELDS lacks isCrossRepository.

- [x] Review finding: download_ledger looks back only 20 workflow runs and can silently restart an empty ledger

  The ledger lookup scans 20 successful runs of the whole workflow, including audit and paused runs that upload no ledger, so a long pause makes the next run start empty and lose recorded history.

  - .github/scripts/wc_merge_evidence.py

  Detail: After about 20 runs with no ledger upload, run_verdicts logs 'starting an empty one' and recorded merges become 'reconstructed'.

- [x] Review finding: run_audit uses capped search/issues to find merged PRs

  The search API returns at most 1000 results and can lag behind new merges, so merged PRs can be missed and then listed as reaching main without a pull request.

  - .github/scripts/wc_merge_evidence.py

  Detail: List closed pulls with pagination and filter on merged_at, or flag the section incomplete when total_count exceeds what was read.

- [x] Review finding: _line crashes when merge_commit_sha is None

  entry["merged_commit"][:12] raises TypeError for a null merge commit, which fails the whole daily audit step.

  - .github/scripts/wc_merge_evidence.py

  Detail: Render (entry["merged_commit"] or "unknown")[:12], or treat a missing merge commit as not-read.

- [x] Review finding: cut_snapshot drops checks and statuses that were updated after the merge

  Checks with no completed_at, and statuses whose latest state postdates the merge, are removed from the rollup, so legitimate merges can read as having missing evidence.

  - .github/scripts/wc_merge_evidence.py

  Detail: Cut checks on started_at or created_at, and treat a context whose only visible state postdates the merge as not-read.

- [x] Review finding: _rest_rollup reads commit statuses without pagination

  commits/{sha}/status is read with the default 30-item page, so a failing status beyond the first 30 is omitted and the verdict can read met.

  - .github/scripts/wc_merge_evidence.py

  Detail: Add per_page=100 and --paginate with a jq that emits the statuses.

## Review Gate Round 4 Findings

- [x] Review finding: Failed PR lookup reports commit as unpaired direct push

  _belongs_to_merged_pr returns False on a read error (5xx, 403, rate limit), so a rebase-merged commit is listed as reaching main without a pull request.

  - .github/scripts/wc_merge_evidence.py

  Detail: Return None on a read error and have run_audit mark the section incomplete, or list the commit as 'could not be checked'.

- [x] Review finding: Audit reads every closed PR in the repository's history

  run_audit pages all closed PRs via gh_items --paginate and never stops once updated_at falls before the window start, so the audit cost grows with repository age.

  - .github/scripts/wc_merge_evidence.py

  Detail: Page manually and stop when a page's oldest updated_at is before window['start']. A rate-limit failure mid-read aborts the whole audit.

- [x] Review finding: cut_rollup drops queued checks with no started_at

  A check run with neither startedAt nor completedAt gets stamp None, and _after(None) is True, so the run is dropped as post-merge. The as-of-merge verdict can then read 'met' while a check was still pending at merge.

  - .github/scripts/wc_merge_evidence.py

  Detail: Use created_at as a fallback stamp (read it in _rest_rollup), or keep unstamped runs as not finished.

- [x] Review finding: Read-error fallback snapshot is recorded under the wrong kind

  When collect hits a read error, its fallback snapshot has no assigned_kind, author or body, so evaluate() derives kind 'maintainer' and the ledger stores the record under that kind.

  - .github/scripts/wc_merge_evidence.py

  Detail: Assign the kind from the PR list item before the failing reads, or record kind 'unknown' for a stub snapshot.

- [x] Review finding: T024 marked done but the SC-003 replay check is absent

  The gate only prints that the SC-003 replay is pending. Nothing fails when the corpus lands or is missing, so EXEMPT_SC003_PENDING guards nothing.

  - .github/scripts/verify-merge-evidence.py

  Detail: Add a check that fixtures/merge-evidence/sc003/ is empty exactly while the exemption entry exists, or reopen T024.

- [x] Review finding: Proof-list keeps its own copy of the pause test

  wing-commander-proof-list.yml still carries a shell copy of the pause test, and PAUSE_SHELL_COPIES_LEFT hard-codes it as an exemption. This breaks the 'shared logic has one home' rule, and no gate fails if the copy drifts.

  - .github/scripts/verify-merge-evidence.py

  Detail: Move proof-list onto the wing-commander-watch-guard composite, or track the follow-up by issue number.
