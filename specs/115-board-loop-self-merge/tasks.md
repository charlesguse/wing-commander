# Tasks: Board Loop Merges Its Own Fix-Class and Dependency-Bump PRs

**Input**: Design documents from `/specs/115-board-loop-self-merge/`

**Prerequisites**: plan.md, spec.md, research.md (D1-D9), data-model.md, contracts/board-merge.md, quickstart.md

**Tests**: Required by FR-015: a checked-in fixture per merge-blocking condition and per refusal branch, exercised by the gate `verify-board-merge.py`.

**Organization**: Grouped by user story. Run `python .github/scripts/run-local-gates.py` before pushing. Workflow comments are load-bearing (gates byte-compare them), so re-run the suite after any comment edit.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Read `.github/scripts/board_readiness.py` (`evaluate_from_snapshot`, `_checks_green`), `.github/scripts/board_item_marker.py`, the `readiness` job in `.github/workflows/board-loop.yml`, and the lifecycle `merge` job in `.github/workflows/lifecycle-review-gate.yml`, so the new code mirrors their patterns (no file edits)
- [x] T002 [P] Create the empty fixture directory `.github/scripts/fixtures/board-merge/` with a `README` line in the gate (T006) describing the naming scheme `<class>-<condition>.json` and `refusal-<class>.json`

---

## Phase 2: Foundational (blocking)

**Purpose**: The single home for decision logic. Nothing else may carry a copy (CLAUDE.md "Shared logic has exactly one home").

- [x] T003 Create `.github/scripts/board_merge.py` (stdlib only, runnable as `python3 -I`) with the `MergeDecision` shape from data-model.md `{head_sha, class, may_merge, unmet_reason|null, conditions}`, the tuples `CONDITIONS_FIX = (switch_on, kill_switch_clear, eligible_class, checks_green, gate_suite_green, review_converged, backstop_holds)`, `CONDITIONS_BUMP = (switch_on, kill_switch_clear, attributed_to_auto_update, checks_green, gate_suite_green, verification_passed_at_head)`, `REFUSAL_CLASSES = (workflow-scope, conflict, protection, other)`, and a CLI that reads a snapshot JSON and writes a decision JSON. `unmet_reason` is the first failing condition's name
- [x] T004 Add the `eligible_class` exclusion in `.github/scripts/board_merge.py`: never a candidate if a spec PR, plan PR, lifecycle (final implementation) PR, or a PR touching `.specify/memory/constitution.md` (FR-012)
- [x] T005 [P] Add the new marker steps `merged` (carrying `merge_sha`) and `handed-over` to `.github/scripts/board_item_marker.py`, and make select treat `handed-over` like `awaiting-merge` so a refused item is released and not retried every run (research D6, data-model state transitions)

**Checkpoint**: decision module and marker steps exist; no workflow wiring yet.

---

## Phase 3: User Story 1 - A ready fix PR is merged without the owner (P1) 🎯 MVP

**Goal**: With the switch on and every condition holding on a fresh snapshot of the exact head SHA, the loop squash-merges the fix PR and announces it.

**Independent Test**: quickstart.md fix scenario; fixtures prove each condition blocks.

### Tests for User Story 1

- [x] T006 [US1] Create `.github/scripts/verify-board-merge.py` with: fixture loading from `fixtures/board-merge/`; for each name in `board_merge.CONDITIONS_FIX` and `CONDITIONS_BUMP` require a fixture and assert `may_merge` is false with that `unmet_reason`; fail if any condition name lacks a fixture; one all-pass fixture per class asserting `may_merge` true
- [x] T007 [P] [US1] Add fix-class fixtures in `.github/scripts/fixtures/board-merge/`: `fix-pass.json`, `fix-switch_on.json`, `fix-kill_switch_clear.json`, `fix-eligible_class.json`, `fix-checks_green.json` (red), `fix-checks_pending.json`, `fix-checks_none.json` (empty rollup is not green), `fix-gate_suite_green.json` (gate suite not run on H), `fix-review_converged.json`, `fix-backstop_holds.json`
- [x] T008 [US1] Add static workflow assertions to `.github/scripts/verify-board-merge.py`: `board-loop.yml` contains `--match-head-commit`, contains no `--admin`, no `--auto`, no `gh pr review --approve`, no second merge method, and the `merge` job `if:` carries both `WING_COMMANDER_BOARD_AUTO_MERGE` and `WING_COMMANDER_BOARD_LOOP_PAUSED`
- [x] T009 [US1] Register `verify-board-merge.py` wherever gates are enumerated so `python .github/scripts/run-local-gates.py` and `lint-workflows.yml` both run it (locate the existing registration pattern via Grep for a sibling gate such as `verify-board-readiness.py`)

### Implementation for User Story 1

- [x] T010 [US1] Implement `evaluate_fix(snapshot, review_converged, backstop_holds, paused, switch_on)` in `.github/scripts/board_merge.py`, reusing `board_readiness.evaluate_from_snapshot` / `_checks_green` for `checks_green` and `gate_suite_green` (no reimplementation; an empty rollup is not green, Principle VIII)
- [x] T011 [US1] In `.github/workflows/board-loop.yml`, expose from the `readiness` job the outputs the merge job needs (fix PR number, issue number, review-converged flag) without altering its switch-off report text or marker (SC-006; keep `verify-board-readiness.py` passing)
- [x] T012 [US1] Add the `merge` job to `.github/workflows/board-loop.yml` per contracts/board-merge.md: `needs: [select, readiness]`, `if: !cancelled() && vars.WING_COMMANDER_BOARD_AUTO_MERGE == 'true' && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`, concurrency group `wing-commander-board-loop` with `cancel-in-progress: false`, trusted checkout and pristine `.github/scripts` snapshot like the other jobs, `shell: bash` on every `run:` step
- [x] T013 [US1] In the `merge` job, add steps: fresh `gh pr view --json headRefOid,statusCheckRollup,author,headRefName,commits,files,comments`; recompute the backstop on the final diff; rerun `wing-commander-board-stop-check` as `killswitch-recheck` and re-read `WING_COMMANDER_BOARD_AUTO_MERGE` through the API (research D7); call `board_merge.py` to write the decision JSON. Gate every durable step on `steps.killswitch-recheck.outputs.paused == 'false'` (Gate 97 pattern). Run the `review-step-gating` skill over the result
- [x] T014 [US1] In the `merge` job, add the merge step: only if `may_merge`, `gh pr merge --squash <pr> --match-head-commit <head_sha>` capturing stderr; plus the announcement step posting head SHA, class, every condition result and prove disposition on the PR and the issue; and the "Not merged" post naming the failed condition on the issue (FR-008, FR-009). A head that moved yields a refusal, nothing reaches `main`
- [x] T015 [US1] Write the issue marker `step=merged` with `merge_sha` after a successful merge, via `board_item_marker.py` (single home; no pasted marker logic)
- [x] T016 [US1] Add the merge-switch-off case to `.github/scripts/verify-board-merge.py`: with `vars.WING_COMMANDER_BOARD_AUTO_MERGE` not `'true'` the `merge` job is skipped and the readiness text still reads "Awaiting a human merge"

**Checkpoint**: Fix PRs merge end to end; switch-off behaviour unchanged. This is the MVP.

---

## Phase 4: User Story 2 - A verified Spec Kit upgrade is merged (P2)

**Goal**: The board loop merges an auto-update stage PR once its assigned verification passed on the exact head.

**Independent Test**: quickstart.md bump scenario.

### Tests for User Story 2

- [x] T017 [P] [US2] Add bump fixtures in `.github/scripts/fixtures/board-merge/`: `bump-pass.json` (including a diff far over the fix backstop, which must still merge, scenario 3), `bump-switch_on.json`, `bump-kill_switch_clear.json`, `bump-attributed_to_auto_update.json` (wrong author, wrong branch, human commit on top, missing body marker as separate variants), `bump-checks_green.json`, `bump-gate_suite_green.json`, `bump-verification_passed_at_head.json` (failed, running, stale SHA, record by non-bot login variants)

### Implementation for User Story 2

- [x] T018 [US2] Implement `evaluate_bump(snapshot, records, bot_login, paused, switch_on)` in `.github/scripts/board_merge.py`: attribution requires bot author, head ref `auto-update-spec-kit/v<semver>`, the `auto-update:tracking` body marker, and every commit bot-authored (research D4); the latest `wc-bump-verification` record by the bot login wins and counts only if `result == passed` and `head_sha` equals the fresh head (research D3); no backstop
- [x] T019 [US2] In `.github/workflows/auto-update-spec-kit.yml` act job, post one `wc-bump-verification` hidden-marker comment per verification on the upgrade PR with `head_sha`, `tier`, `result`, `run_id`. Keep the stage never merging its own PR (FR-013). Put the marker formatting in `board_item_marker.py` or `.github/actions/_shared/` rather than inline shell
- [x] T020 [US2] In the `merge` job of `.github/workflows/board-loop.yml`, add candidate discovery: the readiness-ready fix PR of this run, else at most one open PR matching the D4 attribution (research D5); fetch the bump's records and announce on the PR and the `auto-update:tracking` issue with the verification evidence
- [x] T021 [US2] Extend `.github/scripts/verify-board-merge.py` to fail if the auto-update workflow contains any `gh pr merge` (FR-013) and to assert the act job emits the `wc-bump-verification` marker

**Checkpoint**: Both classes merge; US1 unaffected.

---

## Phase 5: User Story 3 - A refused merge is handed to a maintainer (P2)

**Goal**: Any GitHub refusal produces a stated handover, nothing reaches `main` another way, and the item is released.

**Independent Test**: quickstart.md workflow-touching PR scenario.

### Tests for User Story 3

- [x] T022 [P] [US3] Add refusal fixtures `refusal-workflow-scope.json`, `refusal-conflict.json`, `refusal-protection.json`, `refusal-other.json` (stderr text plus expected class) in `.github/scripts/fixtures/board-merge/`; extend the gate to require one per name in `REFUSAL_CLASSES`

### Implementation for User Story 3

- [x] T023 [US3] Implement `classify_refusal(stderr)` in `.github/scripts/board_merge.py` returning one of `workflow-scope`, `conflict`, `protection`, `other`
- [x] T024 [US3] In the `merge` job, on a failed merge classify the stderr, post the handover (head SHA, `refusal_class`, stderr quoted, the sentence "handed to a maintainer") on the PR and the issue, write `step=handed-over`, leave the PR open, and take no other route to `main` (FR-010)

**Checkpoint**: Refusals are visible and not retried.

---

## Phase 6: User Story 4 - The merge is proven and recorded (P3)

**Goal**: An autonomous merge of an Actions-only change feeds the existing prove path.

**Independent Test**: quickstart.md prove scenario.

- [x] T025 [US4] Make the existing `prove-gate`/`prove` jobs in `.github/workflows/board-loop.yml` (spec 096) pick up an item whose marker is `step=merged`, relying on prove-gate's own eligibility classifier and adding no second classifier (research D8)
- [x] T026 [US4] Have the merge announcement state the prove disposition (re-drive pending, or why none is needed for gate-only or doc changes), taken from prove-gate's decision rather than recomputed
- [x] T027 [US4] Add an assertion to `.github/scripts/verify-board-merge.py` that the `merged` marker path reaches prove-gate and that the merge job contains no direct `gh workflow run` dispatch

---

## Phase 7: Polish & Cross-Cutting

- [x] T028 [P] Extend `.github/scripts/verify-constitution-merge-class-parity.py` so `WING_COMMANDER_BOARD_AUTO_MERGE` must appear in both the constitution and `board-loop.yml`
- [x] T029 [P] Add the "single home" check to `verify-board-merge.py`: decision logic (condition names, refusal regexes) appears only in `board_merge.py`, not in any workflow `run:` block
- [x] T030 If any workflow comment was added, ensure repeated prose points at one canonical comment (Gate 47) and run the `container-shell-safety` skill if a `container:` block or `run:` inside one was touched
- [x] T031 Run `python .github/scripts/run-local-gates.py` and fix every failure
- [x] T032 Walk through `specs/115-board-loop-self-merge/quickstart.md` against the changes and fix any drift between the quickstart and the code
- [ ] T033 Post-merge proof reminder: after the implementation PR merges, use the `prove-after-merge` skill to re-drive one board-loop run and record the evidence on the PR

---

## Dependencies & Execution Order

- Phase 1 then Phase 2 (T003 before T004, T010, T018, T023; T005 independent).
- US1 (Phase 3) after Phase 2. US2, US3 and US4 all edit the `merge` job and `board_merge.py`, so start them after US1 lands (T012-T014 define the job) to avoid same-file conflicts.
- US2 T019 (auto-update workflow) is independent of the board-loop edits and can run in parallel with them.
- Polish after all desired stories.

### Parallel Opportunities

- T002, T005, T007 in parallel after T003.
- T017 and T019 in parallel; T022 parallel with T017.
- T028 and T029 in parallel.

## Implementation Strategy

**MVP**: Phases 1-3 (US1, tasks T001-T016): fix PR self-merge behind the switch, with the gate. Then US3 (refusal handover, needed before turning the switch on, since workflow PRs will routinely be refused), then US2, then US4, then Polish. Leave `WING_COMMANDER_BOARD_AUTO_MERGE` unset until US1 and US3 are both merged.

## Maintainer Feedback

- [x] MF001 Make `verify-lifecycle-merge-preconditions.py` (and `--self-test`) pass: in board-loop.yml's `merge` job "Announce the outcome" step, read comments via `gh api "repos/$GITHUB_REPOSITORY/issues/$N/comments" --paginate` (REST `user.type` for `is_loop_marker_author()`) instead of `gh ... view --json comments` (#826).
- [x] MF002 Make `verify-snapshot-integrity-statement.py` (and `--self-test`, Gate 153) pass: the `merge` job's snapshot step must point at the statement (see the fix-agent job's "Snapshot helper scripts" step).
- [x] MF003 Fix `verify-board-loop-resume-gating.py --self-test` (expected 12 non-stalled marker renders, found 14): account for the new merge job's marker renders in the self-test.
- [x] MF004 Fix `.github/scripts/auto-update-spec-kit-tests/run-tests.sh` scenario S5: the version-bump step must exit 0 and the PR must carry the `wc-bump-verification` record bound to its head.
- [x] MF005 Complete T028: extend `verify-constitution-merge-class-parity.py` so `WING_COMMANDER_BOARD_AUTO_MERGE` must appear in both the constitution and `board-loop.yml`.
- [x] MF006 Re-run `python .github/scripts/run-local-gates.py` until green (Gate 62 may be skipped without Docker). T033 (post-merge proof) remains a maintainer step.

## Review Gate Round 1 Findings

- [x] Review finding: Not-merged dedup pipes gh api into grep -q under pipefail

  SIGPIPE from grep -q makes the pipeline return 141, so the already-announced check fails and the same Not merged comment is reposted every hourly run.

  - .github/workflows/board-loop.yml

  Detail: Around line 1300; dedup claimed per head and condition does not hold on issues with many comments.

- [x] Review finding: Refused bump-class merge writes no marker, so it is retried and re-announced every run

  Only the fix class gets a handed-over marker. A refused bump PR (for example, the App lacks the Workflows permission) is picked again each run and gets a new refusal comment on the PR and the tracking issue.

  - .github/workflows/board-loop.yml

  Detail: Around line 1317; the refused path has no dedup.

- [x] Review finding: pick_bump_candidate lets one stuck bump PR hide newer valid ones

  It returns the oldest PR by author and branch shape only. If that PR fails attribution or verification or was refused, newer verified bump PRs are never evaluated.

  - .github/scripts/board_merge.py

  Detail: Around line 411.

- [x] Review finding: Transient merge refusals are classified as other and permanently handed over

  A head-moved race with --match-head-commit, a 502 or mergeability still being computed all become class other. The workflow writes handed-over, which is treated like awaiting-merge, so a recoverable failure is never retried.

  - .github/scripts/board_merge.py

  Detail: Around line 342.

- [x] Review finding: verification_passed_at_head uses only the latest bot record

  A later failed or re-run record voids an earlier valid one. createdAt has one-second resolution, so equal timestamps make the order arbitrary and the decision can flip between runs on the same SHA. Refusal-class patterns can also be fooled by bot-quoted text.

  - .github/scripts/board_merge.py

  Detail: Around line 335.

- [x] Review finding: Verification record posted after PR creation with no retry

  If gh pr view or gh pr comment fails transiently after gh pr create, the PR has no wc-bump-verification record and can never merge until someone re-runs the workflow or pushes a new head.

  - .github/workflows/auto-update-spec-kit.yml

  Detail: Around line 3174.

- [x] Review finding: Merge job requests actions: write that it may not need

  GITHUB_TOKEN is used only for the kill-switch composite's cancel-token, and every API call uses the App token. The extra permission is excess privilege on a privileged job, and verify-board-merge.py does not check the job's permissions.

  - .github/workflows/board-loop.yml
  - .github/scripts/verify-board-merge.py

  Detail: Around line 1079.

- [x] Review finding: Single-merge-call check uses text membership, so a pasted identical line passes

  `line not in merge_job` tests whether the line's text is in the merge job, so an identical gh pr merge line pasted into another job is exempted and the only-one-merge-call invariant does not fail.

  - .github/scripts/verify-board-merge.py

  Detail: Around line 859.

## Review Gate Round 2 Findings

- [x] Review finding: Announce step dedups on the PR comment, so a failed issue comment never gets its marker

  board-loop.yml posts the PR comment before the issue comment, and the PR comment is the dedup source; if the issue-comment post fails, later runs see the PR record, skip, and the merged/handed-over marker is never written.

  - .github/workflows/board-loop.yml

  Detail: Around line 1953. A refused fix item stays eligible and is re-refused hourly; a merged item gets no merged marker.

- [x] Review finding: Merge retry does not check whether the first attempt already merged

  A transient 5xx or timeout after a server-side merge makes the retry fail with 'already merged', which is classed other/refused, so a PR already on main is recorded as handed-over.

  - .github/workflows/board-loop.yml

  Detail: Around line 1866. Check the PR state before retrying and treat MERGED as the merged outcome.

- [x] Review finding: merged/handed-over markers drop branch, base_sha and round

  The markers are rendered with only --step and --pr, so round is 0 and branch/base_sha are null, and they replace the issue's newest marker that resume and prove logic reads.

  - .github/workflows/board-loop.yml

  Detail: Around line 1946. A re-admitted item restarts with its review round budget reset.

- [x] Review finding: Bump-PR attribution check fails when the commit author login is empty

  _attributed_to_auto_update requires every commit author login to be the App bot, but gh reports an empty login when the git email does not map to a GitHub account, so such bump PRs are never merged.

  - .github/scripts/board_merge.py

  Detail: Around line 361. The fixtures use app/wing-commander as the login, so they cannot catch this.

- [x] Review finding: Quoted stderr can escape its code fence

  board_merge.py puts GitHub stderr inside a ``` fence and _defang only handles '<!--', so an embedded ``` line closes the fence and the rest renders as live markdown.

  - .github/scripts/board_merge.py

  Detail: Around line 539.

- [x] Review finding: Verification-record post failure leaves the bump PR permanently without a record

  If three gh pr comment attempts fail, the step exits 1 after the PR is open, and a re-run declines the candidate as already proposed, so the PR never gets wc-bump-verification.

  - .github/workflows/auto-update-spec-kit.yml

  Detail: Around line 1597.

- [x] Review finding: A transient API error in the candidate step fails the whole merge job

  The bump scan runs gh pr list and gh pr view per PR and exits 1 on any failure, so one flaky call turns the job red and the bump candidate is not evaluated.

  - .github/workflows/board-loop.yml

  Detail: Around line 1736.

## Review Gate Round 3 Findings

- [x] Review finding: Bot-author fallback expects an email shape the auto-update stage never produces

  _bot_commit_author's empty-login fallback requires a '<id>+<slug>[bot]@users.noreply.github.com' email, but auto-update-spec-kit.yml commits as '<slug>[bot]@users.noreply.github.com', so a genuine bump PR fails attributed_to_auto_update and is never auto-merged; fixtures only use the id-prefixed form.

  - .github/scripts/board_merge.py
  - .github/workflows/auto-update-spec-kit.yml

  Detail: Unverified by me. Reported by the code-review skill.

- [x] Review finding: Merge step records any post-failure MERGED state as a bot merge

  If gh pr merge fails (e.g. head modified) and the PR is MERGED by another actor, board-loop.yml records outcome=merged with that actor's merge_sha and announces the bot merged the evaluated head.

  - .github/workflows/board-loop.yml

  Detail: Should confirm mergeCommit corresponds to the pinned head, or that the failure was an ambiguous 5xx or timeout.

- [ ] Review finding: Snapshot from gh pr view may be truncated and is treated as complete

  _touches_constitution, actions_only and the marker lookups read files and comments from gh pr view --json with no completeness check, so a large PR could hide a constitution edit or a prior marker.

  - .github/scripts/board_merge.py

  Detail: Whether gh truncates these lists was not confirmed.

- [x] Review finding: verify-board-merge gh pr merge regex ignores backslash-continued lines

  The pattern's [^\n]* consumes the trailing backslash so the continuation group matches zero times; flags on continuation lines (--rebase, --match-head-commit) are never checked.

  - .github/scripts/verify-board-merge.py

- [x] Review finding: Empty merge_sha possible right after gh pr merge

  mergeCommit.oid is read immediately after merging with no re-read or fallback, so the announcement and step=merged marker may carry an empty SHA that the prove path needs.

  - .github/workflows/board-loop.yml

- [ ] Review finding: Merge job refetches the same PR several times

  The candidate step and the snapshot step each run gh pr view for the same PR (snapshot, headRefName, baseRefOid), which wastes API calls and can observe different heads; baseRefOid could go into SNAPSHOT_FIELDS.

  - .github/workflows/board-loop.yml

- [x] Review finding: job_block and job_span duplicate job-boundary logic in the gate

  Both functions in verify-board-merge.py scan for a job header and stop at the next two-space key; job_block should be derived from job_span to keep one home.

  - .github/scripts/verify-board-merge.py

## Review Gate Round 4 Findings

- [ ] Review finding: Unrecognised gh pr merge failures are classed non-retryable

  Rate-limit, expired-token and network errors fall into class `other`, so the outcome is `refused` and the PR is permanently handed over or skipped until its head moves.

  - .github/workflows/board-loop.yml

  Detail: Around line 1991: the `retryable` check exits 1 for class `other`.

- [ ] Review finding: Already-merged PR yields a garbled not-merged announcement

  When the PR is already MERGED by someone else, the step emits outcome=not-merged while may_merge=true, so the announcement says unmet condition `None` and the outcome record stores reason None.

  - .github/workflows/board-loop.yml

  Detail: Around line 1983; affects render_announcement and outcome_record.

- [ ] Review finding: Merged outcome reported even when merge_sha is empty

  If read_merge_sha returns empty after 5 tries, the job still reports outcome=merged and writes the step=merged marker without merge_sha, which prove-gate needs. It neither fails nor warns.

  - .github/workflows/board-loop.yml
  - .github/scripts/board_item_marker.py

  Detail: Around line 1971.

- [ ] Review finding: Fix-class markers drop spec_request and other fields

  --carry-round-from passes through only `round`, so the new merged/handed-over marker replaces the newest marker and loses spec_request and nr_* fields. A newest marker that is missing or unparseable resets the round to 0.

  - .github/workflows/board-loop.yml

  Detail: Around line 2067; contradicts the comment that the marker keeps branch, base and round.

- [ ] Review finding: Auto-update-spec-kit closes and deletes the PR on persistent comment failure

  After three failed `gh pr comment` calls the step runs `gh pr close --delete-branch` and then fails. A lasting cause such as permissions makes this loop on every run, and the comment's claim that the PR is proposed afresh is unverified.

  - .github/workflows/auto-update-spec-kit.yml

  Detail: Around line 3679.

- [ ] Review finding: Bump verification marker trusted from any bot-authored comment

  Any comment posted as the same App that quotes a `wc-bump-verification ... passed` marker creates a trusted pass record. Only the head SHA binds it, and `_defang` protects only render_announcement.

  - .github/scripts/board_merge.py

  Detail: Around line 440, verification_passed_at_head.

- [ ] Review finding: Candidate step makes redundant gh pr view calls

  headRefName and baseRefOid are fetched in separate gh pr view calls, and the snapshot step fetches the PR a third time. This costs API round-trips, and the reads can disagree if the PR moves between them.

  - .github/workflows/board-loop.yml

  Detail: Around line 1851.

- [ ] Review finding: verify-board-merge gate uses a fixed line slice for the if: block

  The gate looks for the switch variables in `merge_job[1:12]` instead of parsing the job's `if:` expression, so it is position-dependent. Adding lines to `if:` breaks it, and a variable moved elsewhere can still pass.

  - .github/scripts/verify-board-merge.py

  Detail: Around line 1344.

- [ ] Review finding: Formatting typo in board_item_marker.py

  The changed line `payload =json.dumps(...)` is missing a space after `=`, which pycodestyle E225 would flag.

  - .github/scripts/board_item_marker.py

  Detail: Line 183.
