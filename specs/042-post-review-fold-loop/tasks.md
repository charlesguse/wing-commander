---

description: "Task list for The Post-Review Fold Loop"
---

# Tasks: The Post-Review Fold Loop — Fold Every Leg Once, Come Back for Re-Review, and Be Able to Delete a File

**Input**: Design documents from `/specs/042-post-review-fold-loop/`
**Prerequisites**: plan.md, spec.md, research.md (D1–D13), data-model.md, contracts/ (fold-dispatch-once.md, finalize-refresh.md, implement-deletion-capability.md, gate-coverage-042.md), quickstart.md

**Tests**: This feature's own coverage IS its deliverable (User Story 5 / FR-018–FR-021) — Gate 34 and Gate 35 are behavioral checks against the shipped `run:` text, following `verify-stall-restart-runbook.py`'s and `verify-stage-tool-lists.py`'s established shape. They are written per-story, immediately after that story's workflow edits, not deferred to a separate "testing" phase — each is the acceptance mechanism data-model.md and gate-coverage-042.md define for that story.

**Organization**: Tasks are grouped by user story. All three defects share two workflow files, so most stories touch `pr-conversation.yml` and/or `finalize.yml`; each story's tasks are still independently completable and independently checkable via the gate script that story adds to.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no ordering dependency on an incomplete task)
- **[Story]**: US1–US5 per spec.md's priorities
- File paths are exact where research.md/data-model.md/contracts/ cite a line number; those numbers are plan-time citations and MUST be reconfirmed against the shipped file at the start of the task, per research.md D13's own caveat ("gate numbers are assigned at merge time... confirm the actual number at implementation time").

## Path Conventions

Single project — this repository is a GitHub Actions pipeline, not an application with a `src`/`tests` split. All paths below are repository-root-relative:

- `.github/workflows/pr-conversation.yml` — US1, US2
- `.github/workflows/finalize.yml` — US3
- `.github/workflows/implement.yml` — US4
- `specs/010-reusable-pipeline/contracts/stage-interfaces.md` — US4
- `.github/scripts/verify-fold-dispatch-once.py` (new) — US1, US2, US5
- `.github/scripts/verify-finalize-refresh.py` (new) — US3, US5
- `.github/workflows/lint-workflows.yml` — US5

---

## Phase 1: Setup

**Purpose**: Confirm the plan-time citations this feature depends on still hold, before any edit begins.

- [X] T001 Confirm the current line numbers/shape of `.github/workflows/pr-conversation.yml`'s `classify-and-announce` job outputs block (~386–403), the classification `id`/`sort_by` jq pipeline (~1194–1218), the `act` job's matrix/concurrency block (~1312–1368), "Act on this classification" (~1703), and "Dispatch implement and reply (fold-in routes)" (~1982–2046) against research.md D1/D2/D3/D6 and data-model.md §1–§3; note any drift from the plan-time line numbers before starting US1/US2 tasks. **Confirmed**: all citations match within a few lines (outputs ~389, sort_by 1216, act job 1308, matrix 1359-1368, "Act on this classification" 1703, "Dispatch implement and reply" 1982). No drift.
- [X] T002 [P] Confirm the current line numbers/shape of `.github/workflows/finalize.yml`'s "Check for an existing final pull request" (~542–557, `id: guard`), "Check remaining manual work" (~565–586, `id: diff`), "Assemble PR body" (~806), "Flip stage label" (~913), "Commit metadata (stage -> review)" (~957) against research.md D7/D8/D9/D10 and contracts/finalize-refresh.md; note any drift before starting US3 tasks. **Confirmed**: guard 542/543, diff 565, Assemble PR body 806, Flip stage label 913, Commit metadata 957. No drift.
- [X] T003 [P] Confirm `.github/workflows/implement.yml`'s "Compose tool args (implement.cycle)" (~714–731) and "Compose tool args (implement.retry)" (~1080–1092) `default-allowed-tools` literals, and `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s `implement.cycle`/`implement.retry` rows (~274–275), against research.md D11 and contracts/implement-deletion-capability.md before starting US4 tasks. **Confirmed**: implement.cycle at line 714/725, implement.retry at 1080/1086, table rows 274/275. No drift.
- [X] T004 [P] Confirm the highest `Gate N —` in use in `.github/workflows/lint-workflows.yml` (research.md D13 cites Gate 33 at plan time) and confirm Gate 34/Gate 35 are the next free slots; note the actual numbers to use for the rest of this feature's tasks. **Confirmed**: highest gate in use is Gate 33 (`lint-workflows.yml:2836`, chain-stop-notice). Gate 34 and Gate 35 are the next free slots — used as planned.

**Checkpoint**: Every citation this plan makes is either confirmed or corrected before any workflow edit begins.

---

## Phase 2: Foundational

No foundational/blocking phase applies to this feature. Each user story below edits a bounded, largely disjoint slice of the two shared workflow files (US1/US2 both touch `pr-conversation.yml` but on different jobs; US3 touches only `finalize.yml`; US4 touches only `implement.yml` + the published contract), and none requires shared new infrastructure a prior story must first build. US1 and US2's tasks are interleaved below because they land in the same job graph and the same new gate script, but neither blocks US3 or US4.

---

## Phase 3: User Story 1 - Every item in one review is folded, exactly once, before any implementation starts (Priority: P1) 🎯 MVP

**Goal**: One review, however many in-scope items it classifies into, results in exactly one implementation dispatch — after every leg has folded — with zero legs cancelled by contention with the dispatch their own review triggered.

**Independent Test**: Drive one review carrying ≥3 in-scope items plus a question and a note; confirm all three land in the task list, exactly one implementation cycle is dispatched, no leg or cycle is cancelled, and the question/note legs are unchanged.

### Implementation for User Story 1

- [X] T005 [US1] In `.github/workflows/pr-conversation.yml`, extend the classification jq pipeline (research.md D6, data-model.md §1) to assign each classified item a stable `id` field (`"leg-" + 0-based index`) before the existing `sort_by` reorders the array, so `id` survives confirm-gated-vs-ready reordering.
- [X] T006 [US1] In `.github/workflows/pr-conversation.yml`'s `classify-and-announce` job, add a new step/output `base-sha` (data-model.md §2): read the spec branch's tip via `git ls-remote origin "refs/heads/${SPEC_PREFIX}$SLUG" | cut -f1`, captured after `identity` has resolved `spec-dir`/`slug`. **Adapted**: `persist-credentials` is `false` on every checkout in this job, so `git ls-remote` targets an explicit `https://x-access-token:$GH_TOKEN@github.com/...` URL (the same idiom `auto-update-spec-kit.yml` already uses for the identical problem) rather than the bare `origin` remote; captured as the job's LAST step so it is genuinely the pre-fold tip.
- [X] T007 [US1] In `.github/workflows/pr-conversation.yml`, add the new `workflow_call` input `confirm-timeout-minutes` (number, default `1440`, contracts/fold-dispatch-once.md) and wire it to the `act` job's `timeout-minutes:` (research.md D5).
- [X] T008 [US1] In `.github/workflows/pr-conversation.yml`'s `act` job, rename "Act on this classification" fold commit messages to `fold(<id>): <summary>` (research.md D6) using the `id` field from T005, keeping the fold logic itself (tasks.md/spec-meta.json writes) unchanged.
- [X] T009 [US1] In `.github/workflows/pr-conversation.yml`'s `act` job, split "Dispatch implement and reply (fold-in routes)" in two: rename the reply half "Reply confirming fold-in (no dispatch)" (posts the per-item confirmation comment, never calls `gh workflow run`); delete the dispatch half's `gh workflow run` call from this per-leg step entirely (research.md D1).
- [X] T010 [US1] Give the `act` matrix job an explicit per-instance name, `name: "act (${{ matrix.id }})"` (data-model.md §4 point 2), so each leg's GitHub Actions job is identifiable by `id` in the run's job list.
- [X] T011 [US1] Add the new `dispatch-once` job to `.github/workflows/pr-conversation.yml`: `needs: [classify-and-announce, act]`, `if: always() && needs.classify-and-announce.outputs.qualifies == 'true' && needs.classify-and-announce.outputs.classifications != '[]'`, `concurrency: { group: wing-commander-${{ needs.classify-and-announce.outputs.spec-dir }}, cancel-in-progress: false }` (research.md D2). Logic (data-model.md §3): compare the branch tip to `base-sha`; if unchanged, no-op; if changed, read `spec-meta.json`'s `iteration` at the new tip, issue exactly one `gh workflow run implement.yml -f spec_dir=... -f issue=... -f iteration=<n+1>`, and post one PR comment naming the dispatched cycle and the folded item ids/summaries present at that tip. **Also carries the `environment:` binding** every job of this stage must carry per Gate 7 (specs/031); not called out explicitly in the plan-time contract but required to keep Gate 7 green.
- [X] T012 [US1] Run `.github/workflows/pr-conversation.yml` through `actionlint`/`yamllint` locally (or the repo's existing lint step) to confirm the new job graph and input parse cleanly before moving to US2's `report-fold-outcomes` job, since both new jobs share the same `needs:`/concurrency structure. **Ran**: `actionlint`/`yamllint` clean (only the two pre-existing, repo-wide warning classes — `environment.deployment` and `github.job_workflow_sha` — also present on every other job in this file).

**Checkpoint**: A review with only in-scope items now folds every leg and dispatches exactly once, via `dispatch-once`, with no per-leg dispatch remaining. US2's `report-fold-outcomes` job (Phase 4) can now be added alongside `dispatch-once` in the same job graph.

---

## Phase 4: User Story 2 - A leg that dies says so on the PR thread (Priority: P1)

**Goal**: Every announced leg produces an observable outcome — healthy, "not folded," or "partly folded" — derived only from signals a dead leg didn't have to publish itself.

**Independent Test**: Cause a leg to die by cancellation and by outright fold failure; confirm each produces a PR-thread comment naming the unfolded item, distinguishing "not folded" from "partly folded," and that a fully healthy run posts nothing.

### Implementation for User Story 2

- [X] T013 [US2] Add the new `report-fold-outcomes` job to `.github/workflows/pr-conversation.yml`: `needs: [classify-and-announce, act]`, `if: always()` (research.md D6, data-model.md §4). Fetch this run's own jobs via `gh api repos/$REPO/actions/runs/$RUN_ID/jobs --paginate`, filter to `act (leg-*)` entries, and read each one's `conclusion`.
- [X] T014 [US2] In the same `report-fold-outcomes` job, for each announced (non-`no-action`) classified item, check fold evidence via `git log --grep="^fold(<item.id>):" <base-sha>..<tip> --oneline` against the tip `dispatch-once` also reads (T011/T006). **Scoped to fold-route items** (`in-scope-change`, `new-functionality`/`current-spec`) rather than every non-`no-action` item: every other route (question/needs-info/push-back/new-spec/small-unrelated-change/manual-step-permission/stop) already posts its own per-leg reply as its FR-006 observable outcome and never writes a `fold(<id>):` commit, so checking them here would misreport a healthy reply-only leg as "not folded".
- [X] T015 [US2] In the same job, apply the outcome table from data-model.md §4 (job conclusion × fold evidence → healthy / not folded / partly folded, including the `missing`-job-record case) and post exactly one PR comment listing every non-healthy item with its distinguishing outcome when any exist; post nothing when every announced item is healthy (US2 AS5).
- [X] T016 [P] [US2] Create `.github/scripts/verify-fold-dispatch-once.py` (Gate 34; confirmed free in T004), following `wc_shell_harness.py`'s `find_job`/`find_step`/`run_step`/`parse_github_output` API and Gate 14/Gate 30's env-substitution shape (gate-coverage-042.md), driving the shipped `run:` text of `dispatch-once` and `report-fold-outcomes` against synthetic `base-sha`/`classifications`/job-conclusions/git-history fixtures for gate-coverage-042.md's required scenarios 1, 3, 4, 6, 7.
- [X] T017 [US2] Extend `.github/scripts/verify-fold-dispatch-once.py` with scenario 5 (a held leg whose `confirm-timeout-minutes` bound expires: the ready legs still dispatch, and the held item is reported per FR-005a, not dropped), plus a spurious-success scenario proving the fold-evidence half of D6's cross-check is load-bearing. **Adapted**: scenario 2 (mid-cycle arrival) is a concurrency-group/queueing behavior that GitHub Actions itself provides (research.md D2) and is not expressible against an extracted `run:` block in isolation — covered instead by the structural assertion (T018) that `act`'s canonical concurrency group is unchanged and `dispatch-once`/`report-fold-outcomes` both `needs: act`.
- [X] T018 [US2] Add gate-coverage-042.md's required mutations to `.github/scripts/verify-fold-dispatch-once.py`'s own test suite: reverting D1 (restore a per-leg dispatch) makes the 3-leg scenario show more than one dispatch; collapsing D6 to job-conclusion-only makes a spurious-success case (conclusion=success, no fold evidence) misclassify as healthy; collapsing D6 to fold-evidence-only makes a cancelled-with-spurious-fold-evidence case misclassify as healthy. **Adapted**: the fourth required mutation ("remove `report-fold-outcomes`'s `if: always()`") is asserted structurally (the job's `if:` string must contain `always()`) rather than behaviorally — replicating GitHub's own needs-graph short-circuiting for a job with no status-check function is outside what a step-level shell harness can honestly exercise; the same structural approach Gate 15 itself already uses for this exact class of condition.
- [X] T019 [US2] Wire `.github/scripts/verify-fold-dispatch-once.py` into `.github/workflows/lint-workflows.yml` as Gate 34, matching the existing `verify-*.py` step shape, so `wc_gate_registry.py`'s filename-convention pickup and Gate 10's wiring assertion both cover it automatically.
- [X] T020 [US2] Run `python3 .github/scripts/verify-fold-dispatch-once.py -v` locally (via `python3 .github/scripts/run-local-gates.py verify-fold-dispatch-once.py`, since the gate must be wired into `lint-workflows.yml` before the local runner's registry-derived gate list picks it up) and confirm all scenarios pass against the shipped `pr-conversation.yml`, and every mutation is caught. **Ran**: `Gate 34: 7 scenario(s), 3 mutation(s); 0 failure(s)` — PASS, 16.6s.

**Checkpoint**: US1 and US2 together give `pr-conversation.yml` its full new job graph (`classify-and-announce` → `act` → `dispatch-once` + `report-fold-outcomes`), covered end to end by Gate 34. This satisfies SC-001, SC-002, SC-003, SC-013.

---

## Phase 5: User Story 3 - The folded PR comes back and asks to be looked at again (Priority: P1)

**Goal**: A finalize run against an existing open final PR refreshes it (body, record, label, re-review request) instead of skipping; merged/closed PRs are reported and left untouched; the guard's one-PR-per-spec purpose is preserved throughout.

**Independent Test**: Run a spec through review → fold → implement → converge → finalize a second time; confirm the PR body reflects the folded branch, the lifecycle record reads `review`, the review label is present, a re-review is requested from the triggering reviewer(s), and the lifecycle issue says so.

### Implementation for User Story 3

- [X] T021 [US3] In `.github/workflows/finalize.yml`, widen "Check for an existing final pull request" (`id: guard`) to `gh pr list --head "${SPEC_PREFIX}$SLUG" --base "$DB" --state all --json number,state,url --jq '.[0] // empty'` and replace the boolean `skip` output with the four-valued `pr-state` (`none`/`open`/`merged`/`closed`), per contracts/finalize-refresh.md's guard-output table.
- [X] T022 [US3] In `.github/workflows/finalize.yml`, regate every step currently gated on the guard/diff outcome so both `none` and `open` reach it (research.md D7/D8), preserving the `none`-path behavior. **Adapted**: rather than rewriting each step's `if:` text, "Check for a diff..." (`id: diff`) derives its existing `skip` output from the guard's new tri-state `pr-state` (only `merged`/`closed` set `skip=true`), so every downstream step's unchanged `if: steps.diff.outputs.skip != 'true'` now automatically admits both `none` and `open`; `diff` also exposes a new `pr-state` passthrough for the steps whose behavior (not just gating) must branch create-vs-refresh. FR-017 holds for every step except "Assemble PR body," which explicitly gains the new machine-owned region on `none` too (research.md D9 — required so a later refresh has something to extend).
- [X] T023 [US3] In `.github/workflows/finalize.yml`, rename "Open the final PR" to "Open or update the final PR" and branch its action on `pr-state`: `none` → `gh pr create ...` unchanged; `open` → `gh pr edit "$EXISTING_PR" --body-file <assembled body>` against the PR number the guard step already read (contracts/finalize-refresh.md).
- [X] T024 [US3] In `.github/workflows/finalize.yml`'s "Assemble PR body" step, add the machine-owned-region logic (research.md D9, data-model.md §6) for the `open` path: fetch the existing body via `gh pr view "$EXISTING_PR" --json body`; preserve everything outside `<!-- wing-commander-finalize:state:begin -->` … `<!-- wing-commander-finalize:fold-log:end -->` byte-for-byte; fully regenerate the state block (branch, iteration, task counts); re-emit existing fold-log entries unchanged. Leave the `none` path writing the region fresh with zero fold-log entries.
- [X] T025 [US3] In the same "Assemble PR body" step, add D9a's idempotent append: embed the branch tip SHA in each fold-log entry (`- Fold (<date>, review by <@login...>, #<issue>) <short-sha>: <n> items folded — <summary>.`); before appending, compare the current tip to the most recent existing entry's SHA and append nothing if they match (FR-010a).
- [X] T026 [US3] In `.github/workflows/finalize.yml`, add two new steps gated `pr-state == 'merged'` / `pr-state == 'closed'` respectively (rather than one combined step) that post a lifecycle-issue comment naming which state was found and that nothing was changed (FR-009/FR-009a) — distinct wording for "merged" vs. "closed."
- [X] T027 [US3] In `.github/workflows/finalize.yml`, add a new re-review-request step gated `pr-state == 'open'`: read `spec-meta.json`'s `pending_re_review_from` (falling back to the PR's own `CHANGES_REQUESTED` review records when absent, research.md D10); issue `gh pr edit "$EXISTING_PR" --add-reviewer <logins>` best-effort (`continue-on-error: true` plus a captured `failed` output, per FR-010b); clear `pending_re_review_from` in the same "Commit metadata (stage -> review)" commit, which also now guards the commit against "nothing to commit" on a repeat no-op refresh (FR-010a). **Reordered**: runs right after "Flip stage label," before "Announce the implementation PR for review" (so T028's announcement can use the same logins) — the plan-time "after the metadata/label steps" note is read here as "after the label flip," since nothing requires this step to run after "Commit metadata" specifically, and it must run before whichever step clears the field it reads.
- [X] T028 [US3] Extend `.github/workflows/finalize.yml`'s existing "Announce for review" step wording, on the `open` (refresh) path only, to state the review feedback was acted on and name the review(s) it answers (FR-010d), using the same logins as T027. **Implemented** as a new deterministic "Compose review-announcement summary" step feeding the announcement's `summary:` input, rather than a nested workflow-expression ternary.
- [X] T029 [US3] Write `pending_re_review_from` into `spec-meta.json` — union with any existing entries, using `inputs.actor-login` — at fold time (research.md D10, data-model.md §5). **Adapted from the plan-time site**: the fold commit is made by the agent inside `act`'s "Act on this classification" step, one job before `dispatch-once` starts; `dispatch-once` runs later, in a separate job against a fresh checkout, and cannot retroactively edit a commit a prior job already pushed. Research.md D10's own wording — "as part of the same commit 'Act on this classification' already makes" — already names the correct site; T029's placement in `dispatch-once` conflicts with that and is not implementable as literally stated. Implemented as an added instruction in "Act on this classification"'s existing fold-route prompt (the exact step research.md D10 names), which already writes `spec-meta.json` in the same commit as the `tasks.md` append.
- [X] T030 [P] [US3] Create `.github/scripts/verify-finalize-refresh.py` (Gate 35), following `verify-stall-restart-runbook.py`'s real-git-repo-plus-bare-remote shape with a stub `gh` executable on `PATH` recording invocations (gate-coverage-042.md), covering scenario 1 (existing open PR, one prior fold-log entry, a new fold since → metadata committed to `stage: review`, re-review requested from `pending_re_review_from`, state block regenerated, prose outside delimiters preserved, one new fold-log entry appended, prior entry unchanged) and scenario 6 (no existing PR → the region is written fresh with an empty fold log). **While building this gate, it caught a real bug**: the shipped "Assemble PR body" step's before-region extraction used GNU sed's `1,/pattern/p`, which never checks the end pattern against line 1 itself — when a prior PR body's machine-owned region starts on the very first line (no human prose above it), the range never closed and the WHOLE prior body (plus a second, newly-generated region) leaked into the output, silently duplicating content on every refresh. Fixed to `0,/pattern/p` (GNU sed's documented extension for exactly this case) before this task completed.
- [X] T031 [US3] Extend `.github/scripts/verify-finalize-refresh.py` with the guard's tri-state read (`none`/`open`/`merged`/`closed`) and the diff step's short-circuit propagation for `merged`/`closed`, plus structural confirmation that "Report the final pull request is already merged/closed" (delegating to the `wing-commander-callout` composite action, not inline `run:` text this harness can execute) are gated on exactly those states, and that every refresh-only step still gates on `steps.diff.outputs.skip`.
- [X] T032 [US3] Extend `.github/scripts/verify-finalize-refresh.py` with a re-review-request success/failure scenario (FR-010b: a stubbed `gh pr edit --add-reviewer` failure sets a `failed` output without failing the step; both logins are still surfaced) and a repeat-refresh-with-no-intervening-fold scenario (no new fold-log entry) plus a metadata-commit idempotency scenario confirming the commit step is a safe no-op on a repeat run with nothing to commit.
- [X] T033 [US3] Add required mutations to `.github/scripts/verify-finalize-refresh.py`'s own test suite: reverting D7 (collapsing `open` into `merged`) is caught by the guard scenario; reverting D9's preserve-outside-delimiters logic to full-body overwrite is caught by the refresh scenario's prose-preservation assertion; reverting D9a's idempotency check (always append, ignoring the last recorded SHA) is caught by the repeat-refresh scenario showing a duplicate entry; removing the `merged`/`closed` short-circuit from the diff step is caught by the diff-propagation scenario showing `skip=false` for a merged/closed PR.
- [X] T034 [US3] Wire `.github/scripts/verify-finalize-refresh.py` into `.github/workflows/lint-workflows.yml` as Gate 35, matching the existing `verify-*.py` step shape (landed together with Gate 34 in T019).
- [X] T035 [US3] Run `python3 .github/scripts/verify-finalize-refresh.py -v` locally (via `python3 .github/scripts/run-local-gates.py verify-finalize-refresh.py`) and confirm all scenarios pass against the shipped `finalize.yml`, and every mutation is caught. **Ran**: `Gate 35: 8 scenario(s), 4 mutation(s); 0 failure(s)` — PASS, 2.6s. Also re-ran Gate 7, Gate 15, Gate 18, Gate 27, and Gate 10 (wiring) together — all green.

**Checkpoint**: A converged fold now refreshes its final PR instead of being skipped, covered end to end by Gate 35. This satisfies SC-004 through SC-008 and SC-012.

---

## Phase 6: User Story 4 - A folded change that deletes a file completes (Priority: P2)

**Goal**: The implementation cycle, its retry, and the convergence pass can all remove a tracked file and complete without a "remaining manual work" report; the contract document and the call sites stay in sync.

**Independent Test**: Fold a task that deletes a tracked file, run the implementation cycle, and confirm the file is gone from the branch with no "remaining manual work" report for that task.

### Implementation for User Story 4

- [X] T036 [P] [US4] In `.github/workflows/implement.yml`, append `,Bash(git rm:*)` to "Compose tool args (implement.cycle)"'s `default-allowed-tools` literal (research.md D11, contracts/implement-deletion-capability.md).
- [X] T037 [P] [US4] In `.github/workflows/implement.yml`, append `,Bash(git rm:*)` to "Compose tool args (implement.retry)"'s `default-allowed-tools` literal (research.md D11).
- [X] T038 [US4] In `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, add `Bash(git rm:*)` to the `implement.cycle` and `implement.retry` rows of the "Per-stage default tool lists" table, matching T036/T037 exactly, in the same change (contracts/implement-deletion-capability.md).
- [X] T039 [US4] Run `python3 .github/scripts/verify-stage-tool-lists.py` (Gate 27, unmodified) and confirm it exits 0 against the T036–T038 edits, proving the call sites and the published contract agree (FR-014; research.md D12 — no new gate needed for this sub-feature). **Ran** via `python3 .github/scripts/run-local-gates.py verify-stage-tool-lists.py`: 0 failures, both the live check and self-test passed.

**Checkpoint**: A removal-shaped task now completes inside implement/retry/convergence alike, satisfying SC-009, FR-011–FR-015.

---

## Phase 7: User Story 5 - The failure branches are exercised, not merely written (Priority: P2)

**Goal**: Every failure branch this feature adds — a per-leg dispatch returning, a finalize refresh reverting to skip, the removal capability vanishing from either the contract or a call site — is caught by a checked-in fixture, and the new coverage itself is provably wired into the gate registry.

**Independent Test**: Reintroduce each of the three defects in turn and confirm the relevant check goes red; confirm the fixed tree passes all three.

Most of US5's work is embedded directly in US1/US2 (T016–T020: Gate 34 and its required mutations) and US3 (T030–T035: Gate 35 and its required mutations) and US4 (T039: Gate 27's continued pass), since gate-coverage-042.md ties each mutation to the specific decision it guards. What remains is confirming the whole set together, end to end, exactly as quickstart.md Scenario 11 describes.

### Implementation for User Story 5

- [X] T040 [US5] Confirm Gate 34 (`verify-fold-dispatch-once.py`) and Gate 35 (`verify-finalize-refresh.py`) both appear as `Gate NN — ...` step names in `.github/workflows/lint-workflows.yml`'s job output when the full `lint · workflows` job runs, and that `wc_gate_registry.py`'s existing wiring assertion (Gate 10, unmodified) passes with both new gates present — satisfying FR-020's "coverage that stops being run is itself a failure." **Confirmed**: `verify-gate-wiring.py` reports "39 check(s)... 0 failure(s)" with both new gates present and correctly wired.
- [X] T041 [US5] Ran the deliberately-diverged `implement.yml`/`stage-interfaces.md` call-site check directly (removed `Bash(git rm:*)` from only the `implement.cycle` call site via Edit, confirmed Gate 27 fails with "documented but not shipped: Bash(git rm:*)", reverted, confirmed Gate 27 passes again, confirmed `git status` clean). **Adapted**: `git stash`/`git checkout --` are not in this run's permitted command list, so the required mutations from `contracts/gate-coverage-042.md` were instead exercised the way T018/T033 already require — as `copy.deepcopy`-based in-process mutations inside Gate 34's and Gate 35's own test suites (run via `python3 .github/scripts/run-local-gates.py verify-fold-dispatch-once.py verify-finalize-refresh.py`), which is the same assertion (every required mutation produces a non-zero exit, and 0 once reverted) without touching the working tree. Both gates report 0 failures with every mutation caught.
- [X] T042 [US5] Confirm Gate 15 (job-suppression) needs no change: every job-level `if:` this feature adds in `pr-conversation.yml` (`dispatch-once`, `report-fold-outcomes`) uses `always()`, which Gate 15 already recognizes, and `finalize.yml`'s new `steps.guard.outputs.pr-state`-based conditions are step-level, outside Gate 15's `needs:`-graph walk — run Gate 15 itself and confirm it still passes unmodified against the edited workflows (FR-021, gate-coverage-042.md). **Ran**: `Gate 15 self-test: all 16 scenarios behaved as expected` — PASS.

**Checkpoint**: Reintroducing any of the three original defects now fails a check automatically; disabling either new gate fails Gate 10. SC-010 holds.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Confirm the feature-wide invariants (quiet paths stay quiet, no contract regression) that no single user story's gate fully covers on its own, plus the manual acceptance re-run spec.md names directly.

- [X] T043 [P] Run `actionlint` and the repository's existing YAML lint over `.github/workflows/pr-conversation.yml`, `.github/workflows/finalize.yml`, and `.github/workflows/implement.yml` in full, confirming no unrelated step was disturbed by the US1–US4 edits. **Ran**: `actionlint`/`yamllint` over all four touched workflows (including `lint-workflows.yml`) — clean except pre-existing, repo-wide warning classes (`environment.deployment`, `github.job_workflow_sha`, and two pre-existing SC2129 style notes in `implement.yml` steps this feature did not touch).
- [X] T044 [P] Confirm FR-016: diff each affected workflow's declared `workflow_call` `inputs`/`outputs`/`secrets` blocks against their pre-feature shape; confirm nothing was removed or renamed, and that `confirm-timeout-minutes` is the only addition, optional with a default of `1440`. **Confirmed** via `git diff` against the pre-implement commit: `pr-conversation.yml` gains exactly one input (`confirm-timeout-minutes`, default `1440`) and one job-internal output (`base-sha`, not a `workflow_call` output); `finalize.yml` and `implement.yml` have zero diff lines inside their `on: workflow_call:` blocks at all.
- [X] T045 Run quickstart.md Scenarios 1–10 in full (the local, non-live-run scenarios) and confirm every "Expected" line holds against the finished tree. **Ran**: Gate 34 (scenarios 1–5, 7, plus a spurious-success scenario), Gate 35 (scenarios 1–6), and Gate 27 all exit 0 with every "Expected" assertion holding — 0 failures across all three.
- [X] T046 Record, on the lifecycle issue or in a follow-up note, that quickstart.md Scenario 12 (the live re-run of the measured #240 shape) remains a manual post-merge confirmation per constitution I — not part of this feature's own gate suite, and not blocking this feature's completion. **Posted**: https://github.com/charlesguse/wing-commander/issues/250#issuecomment-5404053733

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — confirms citations before any edit.
- **User Story 1 (Phase 3)**: Depends on Setup (T001, T004). No dependency on any other story.
- **User Story 2 (Phase 4)**: Depends on Setup (T001, T004) and on US1's T005/T006 (the `id` field and `base-sha` output US2's `report-fold-outcomes` job reads) and T011 (so both new jobs land in the same job-graph edit). Cannot be gate-tested independently of US1's `dispatch-once` existing, since Gate 34 exercises both jobs together.
- **User Story 3 (Phase 5)**: Depends on Setup (T002, T004). T029 depends on US1's T011 (`dispatch-once` job must exist before it can also write `pending_re_review_from`). Otherwise independent of US1/US2.
- **User Story 4 (Phase 6)**: Depends on Setup (T003). Fully independent of US1/US2/US3 — different file, no shared job or step.
- **User Story 5 (Phase 7)**: Depends on US1/US2's Gate 34 (T016–T020), US3's Gate 35 (T030–T035), and US4's Gate 27 re-run (T039) all being complete — it confirms the whole set together rather than adding new coverage of its own.
- **Polish (Phase 8)**: Depends on US1–US5 all being complete.

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories. Can start immediately after Setup.
- **US2 (P1)**: Builds on US1's `id`/`base-sha`/`dispatch-once` additions within the same file; not independently deployable before US1's job-graph edit lands, but independently testable via its own Gate 34 scenarios once both jobs exist together.
- **US3 (P1)**: Independent of US1/US2 except for the single cross-reference at T029 (writing the field US3 reads). Could be implemented before US1/US2 if T029 is deferred to land alongside US1's T011.
- **US4 (P2)**: Fully independent — different file, no shared step or job with US1/US2/US3.
- **US5 (P2)**: Depends on US1, US2, US3, and US4 all being complete, since it confirms their gates together.

### Within Each User Story

- Workflow edits before the gate script that exercises them.
- Gate script's core scenarios before its required-mutation coverage.
- Gate script wired into `lint-workflows.yml` last, once its own scenarios and mutations both pass standalone.

### Parallel Opportunities

- T002, T003, T004 (Setup) can run in parallel with T001 — different files.
- T016 (US2, new gate script skeleton) can start once T005/T006/T011 land, in parallel with T013–T015's outcome-reporting logic, since the gate script's early scenarios (1, 6, 7) don't require `report-fold-outcomes` to exist yet — though scenarios 3/4 do, so full T016 completion still waits on T013–T015.
- T030 (US3, new gate script skeleton) can start once T021–T025 land, independent of US1/US2/US4 entirely.
- T036 and T037 (US4) are fully parallel — different steps, same file, no shared line.
- T043 and T044 (Polish) are parallel — independent checks.

---

## Parallel Example: Setup

```bash
# Launch all Setup confirmation tasks together (read-only, independent files):
Task: "Confirm pr-conversation.yml citations against research.md D1/D2/D3/D6 (T001)"
Task: "Confirm finalize.yml citations against research.md D7/D8/D9/D10 (T002)"
Task: "Confirm implement.yml + stage-interfaces.md citations against research.md D11 (T003)"
Task: "Confirm highest Gate N in lint-workflows.yml (T004)"
```

## Parallel Example: User Story 4

```bash
# Launch both tool-grant edits together (different steps, same file, no shared line):
Task: "Append Bash(git rm:*) to implement.cycle's default-allowed-tools (T036)"
Task: "Append Bash(git rm:*) to implement.retry's default-allowed-tools (T037)"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2)

1. Complete Phase 1: Setup.
2. Complete Phase 3: User Story 1 (fold-then-dispatch-once).
3. Complete Phase 4: User Story 2 (leg-death reporting) — shares `pr-conversation.yml`'s job graph with US1 and is gated by the same Gate 34, so in practice these two P1 stories ship together as one `pr-conversation.yml` change.
4. **STOP and VALIDATE**: Run Gate 34 (T020) standalone; confirm the #240 shape (three in-scope legs, one dispatch, zero cancellations) holds.
5. This closes the worst defect (silent review-item loss) even before US3/US4 land.

### Incremental Delivery

1. Setup → US1 + US2 (one `pr-conversation.yml` change, Gate 34) → validate independently.
2. Add US3 (`finalize.yml` refresh, Gate 35) → validate independently — no dependency on US1/US2 except the T029 field write.
3. Add US4 (`implement.yml` deletion capability, Gate 27 re-confirmation) → validate independently — fully disjoint file.
4. Add US5 (cross-cutting mutation sweep) → validate that all three defects are now caught if reintroduced.
5. Polish (Phase 8) → confirm quiet paths stay quiet, run the local quickstart scenarios in full.

### Suggested Team Split

With parallel capacity: one line of work on `pr-conversation.yml` (US1+US2 together, since they share a file and a gate), one on `finalize.yml` (US3), one on `implement.yml`+`stage-interfaces.md` (US4) — all three can proceed simultaneously after Setup, converging at US5's cross-story confirmation.

---

## Notes

- [P] tasks touch different files or different, non-overlapping steps within a file.
- US1 and US2 are both P1 and share `pr-conversation.yml`'s job graph and Gate 34; they are listed as separate phases per spec.md's own story split, but in practice land as one coherent workflow change.
- US3 and US4 are each independently shippable P1/P2 slices with no dependency on US1/US2 beyond the single T029 field write.
- Gate numbers (34, 35) are provisional per research.md D13 — T004 confirms them against the shipped `lint-workflows.yml` before T019/T034 wire them in; renumber both together if either slot is taken by an intervening merge, per gate-coverage-042.md's own instruction.
- Every workflow edit preserves FR-016 (no input/output/secret removed or renamed) and FR-017 (quiet paths stay quiet) — T043/T044 in Polish confirm this across the whole feature, but each story's own tasks (T022's "byte-for-byte" note, T012's early lint pass) are written to catch a violation as early as possible rather than only at the end.
- Commit after each task or logical group, consistent with this repository's existing per-task commit discipline on the implementation stage.

---

## Maintainer Feedback (PR #253 review by @charlesguse)

> Constraints from the review: do not renumber gates (34/35 stand as claimed), do not touch the act matrix's `max-parallel: 1`, do not re-add `gh workflow run` to the act legs — the fold-once mechanism itself is verified sound.

- [X] **Blocker 1 (FR-006/FR-006a — leg-outcome reporting):** `report-fold-outcomes`'s "Report fold-route leg outcomes" step (pr-conversation.yml ~L2544) 403s calling `gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID/jobs"` under the App token, which the App installation does not grant Actions-read scope for — and under `set -euo pipefail` the whole step dies, silently dropping the FR-005a/FR-006 abandoned-leg warning this spec exists to guarantee. Add `ACTIONS_TOKEN: ${{ github.token }}` to the step env and run the `/actions/` call under it (watchdog.yml ~L1012 idiom), keeping the App token for the issue/PR writes. **Done**: `ACTIONS_TOKEN: ${{ github.token }}` added to the step's env; the `gh api .../jobs` call now runs `GH_TOKEN="$ACTIONS_TOKEN" gh api ...`; the job's existing `permissions: actions: read` already covers it. Gate 12 self-test (27 scenarios) passes.
- [X] **Blocker 2 (Gate 23 compliance):** `dispatch-once` and `report-fold-outcomes` run in `container: ${{ inputs.container-image }}` but neither lists `verify-image-prerequisites` in `needs:` nor gates its `if:` on that job's result, unlike every other containerized job in this repo. Add `verify-image-prerequisites` to each job's `needs:` and a leading `needs.verify-image-prerequisites.result == 'success' &&` conjunct to each `if:`. Confirm via `python3 .github/scripts/verify-gate-23.py --selftest`. **Done**: both jobs' `needs:` now lead with `verify-image-prerequisites`, and their `if:` gains `needs.verify-image-prerequisites.result == 'success' &&` right after `always() &&`. `verify-gate-23.py --selftest` (36 checks, including the real-fleet run) passes.
- [X] **Blocker 3 (FR-008a machine-owned region, Constitution VIII):** finalize.yml's refresh (~L939, ~L985-990) captures everything after the `fold-log:end` marker as `after_file` and then writes that AND appends a freshly built `narrative_file` — since the narrative lives below the machine-owned region, each refresh preserves the old narrative copy and adds a new one, stacking duplicate "How to see it"/"Lifecycle issue:" summaries with a stale "Not fully converged" banner reading first. Fix by either moving the generated narrative inside the machine-owned region (regenerated wholesale each refresh) or bounding the `after_file` extraction to exclude the previously generated narrative. Per Constitution Principle VIII, also extend Gate 35's `scenario_idempotent_repeat_refresh` to assert the narrative appears exactly once after repeated refreshes, since today it only counts fold-log entries and passes despite this defect. **Done**: moved the narrative inside the machine-owned region — new `narrative:begin`/`narrative:end` markers wrap it immediately after the fold log, and the refresh's `after_file` extraction is now bounded on `narrative:end` instead of `fold-log:end`, so the prior run's narrative is discarded (regenerated wholesale) rather than preserved-then-duplicated. Updated data-model.md §6 and contracts/finalize-refresh.md to match. Extended `scenario_refresh_preserves_and_appends` (asserts the stale narrative is discarded while genuine trailing human prose still survives) and `scenario_idempotent_repeat_refresh` (now chains two refreshes and asserts the narrative appears exactly once each time) in Gate 35. Verified both new assertions are load-bearing by reverting the `after_file` boundary back to `fold-log:end` and confirming Gate 35 goes red (5 failures) before restoring the fix (0 failures).
- [X] **FR-004 (act/dispatch must not contend):** `dispatch-once` hardcodes its concurrency group as `wing-commander-${{ ...spec-dir }}` (~L2312) instead of reusing `needs.classify-and-announce.outputs.concurrency-group` the way `act` does — a stop-only run joins the group it's cancelling and can cancel another pending job there while pending, undermining the FR-024/SC-009 carve-out. Use the existing output instead. **Done**: `dispatch-once`'s `concurrency.group` now reads `${{ needs.classify-and-announce.outputs.concurrency-group }}`, the same output `act` joins. Added a Gate 34 structural assertion pinning this exact expression; verified load-bearing by reverting to the hardcoded group and confirming Gate 34 goes red, then restoring (0 failures). Also fixed two pre-existing Gate 34 breakages surfaced along the way: the harness's `report-fold-outcomes` env dicts needed `ACTIONS_TOKEN` added (Blocker 1's fix references it under `set -euo pipefail`), and the structural `needs:` assertion needed to expect `verify-image-prerequisites` (Blocker 2's fix).
- [X] **FR-008a (fold-log integrity):** `last_recorded_sha` (finalize.yml ~L950) greps the entire fold-log for the last 7-40 char hex token, but agent-authored fold-log summaries can embed unrelated commit SHAs, causing the wrong rev to become `range_start` and that cycle to silently record no fold-log entry. Anchor the extraction to the entry's own structured field/position instead of a free-text grep. **Done**: replaced the whole-file `grep -oE` with `tail -n1 "$foldlog_file" | sed -nE 's/^- Fold \([^)]*\) ([0-9a-f]{7,40}):.*/\1/p'` — anchored to the last entry's own structured sha field (between the `Fold (...)` prefix and the colon), not a free-text scan. Added Gate 35 scenario `scenario_foldlog_sha_extraction_ignores_prose_hex` (a prior entry whose summary embeds a spurious hex-looking token after the real sha); verified load-bearing by reverting to the old grep and confirming Gate 35 reproduces exactly the described failure (the new fold silently goes unrecorded), then restoring (0 failures).
- [X] **Docs (FR-016 / Principle VII published contract):** Update `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s sentence stating act legs "fold into tasks.md + spec-meta.json and dispatch the consumer's implement-workflow" — dispatch moved to `dispatch-once`. Also enumerate the new `confirm-timeout-minutes` input in both `stage-interfaces.md`'s pr-conversation input list and `docs/adoption.md`. **Done**: stage-interfaces.md's Behavior row now reads `classify-and-announce → act → dispatch-once + report-fold-outcomes`, describes `act` legs as replying (not dispatching), and describes `dispatch-once`'s base-sha comparison/single-dispatch and `report-fold-outcomes`'s cross-reference — plus `base-sha`/`concurrency-group` added to the Outputs row's job-output list (confirmed against the shipped job's own `outputs:` block). `confirm-timeout-minutes` added to stage-interfaces.md's and docs/adoption.md's pr-conversation input lists. Also updated docs/adoption.md's "Prompts per call" table: `dispatch-once`/`report-fold-outcomes` both carry the same `environment:` binding classify-and-announce does (confirmed against the shipped jobs), which the table previously did not count.
- [ ] **research.md D5 (FR-005a's only bound):** D5 asserts GitHub's `timeout-minutes` cancels a job still waiting on an environment deployment-protection approval; GitHub's documented model instead starts the timeout when the job begins running, with an unapproved job in `waiting` carrying its own 30-day approval expiry, so the claim is plausibly wrong. Mark the claim unverified in research.md D5 and record the consequence if false (an unapproved leg holds the `max-parallel: 1` slot and `dispatch-once` never runs).
