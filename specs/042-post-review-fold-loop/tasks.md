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

- [ ] T001 Confirm the current line numbers/shape of `.github/workflows/pr-conversation.yml`'s `classify-and-announce` job outputs block (~386–403), the classification `id`/`sort_by` jq pipeline (~1194–1218), the `act` job's matrix/concurrency block (~1312–1368), "Act on this classification" (~1703), and "Dispatch implement and reply (fold-in routes)" (~1982–2046) against research.md D1/D2/D3/D6 and data-model.md §1–§3; note any drift from the plan-time line numbers before starting US1/US2 tasks.
- [ ] T002 [P] Confirm the current line numbers/shape of `.github/workflows/finalize.yml`'s "Check for an existing final pull request" (~542–557, `id: guard`), "Check remaining manual work" (~565–586, `id: diff`), "Assemble PR body" (~806), "Flip stage label" (~913), "Commit metadata (stage -> review)" (~957) against research.md D7/D8/D9/D10 and contracts/finalize-refresh.md; note any drift before starting US3 tasks.
- [ ] T003 [P] Confirm `.github/workflows/implement.yml`'s "Compose tool args (implement.cycle)" (~714–731) and "Compose tool args (implement.retry)" (~1080–1092) `default-allowed-tools` literals, and `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s `implement.cycle`/`implement.retry` rows (~274–275), against research.md D11 and contracts/implement-deletion-capability.md before starting US4 tasks.
- [ ] T004 [P] Confirm the highest `Gate N —` in use in `.github/workflows/lint-workflows.yml` (research.md D13 cites Gate 33 at plan time) and confirm Gate 34/Gate 35 are the next free slots; note the actual numbers to use for the rest of this feature's tasks.

**Checkpoint**: Every citation this plan makes is either confirmed or corrected before any workflow edit begins.

---

## Phase 2: Foundational

No foundational/blocking phase applies to this feature. Each user story below edits a bounded, largely disjoint slice of the two shared workflow files (US1/US2 both touch `pr-conversation.yml` but on different jobs; US3 touches only `finalize.yml`; US4 touches only `implement.yml` + the published contract), and none requires shared new infrastructure a prior story must first build. US1 and US2's tasks are interleaved below because they land in the same job graph and the same new gate script, but neither blocks US3 or US4.

---

## Phase 3: User Story 1 - Every item in one review is folded, exactly once, before any implementation starts (Priority: P1) 🎯 MVP

**Goal**: One review, however many in-scope items it classifies into, results in exactly one implementation dispatch — after every leg has folded — with zero legs cancelled by contention with the dispatch their own review triggered.

**Independent Test**: Drive one review carrying ≥3 in-scope items plus a question and a note; confirm all three land in the task list, exactly one implementation cycle is dispatched, no leg or cycle is cancelled, and the question/note legs are unchanged.

### Implementation for User Story 1

- [ ] T005 [US1] In `.github/workflows/pr-conversation.yml`, extend the classification jq pipeline (research.md D6, data-model.md §1) to assign each classified item a stable `id` field (`"leg-" + 0-based index`) before the existing `sort_by` reorders the array, so `id` survives confirm-gated-vs-ready reordering.
- [ ] T006 [US1] In `.github/workflows/pr-conversation.yml`'s `classify-and-announce` job, add a new step/output `base-sha` (data-model.md §2): read the spec branch's tip via `git ls-remote origin "refs/heads/${SPEC_PREFIX}$SLUG" | cut -f1`, captured after `identity` has resolved `spec-dir`/`slug`.
- [ ] T007 [US1] In `.github/workflows/pr-conversation.yml`, add the new `workflow_call` input `confirm-timeout-minutes` (number, default `1440`, contracts/fold-dispatch-once.md) and wire it to the `act` job's `timeout-minutes:` (research.md D5).
- [ ] T008 [US1] In `.github/workflows/pr-conversation.yml`'s `act` job, rename "Act on this classification" fold commit messages to `fold(<id>): <summary>` (research.md D6) using the `id` field from T005, keeping the fold logic itself (tasks.md/spec-meta.json writes) unchanged.
- [ ] T009 [US1] In `.github/workflows/pr-conversation.yml`'s `act` job, split "Dispatch implement and reply (fold-in routes)" in two: rename the reply half "Reply confirming fold-in (no dispatch)" (posts the per-item confirmation comment, never calls `gh workflow run`); delete the dispatch half's `gh workflow run` call from this per-leg step entirely (research.md D1).
- [ ] T010 [US1] Give the `act` matrix job an explicit per-instance name, `name: "act (${{ matrix.id }})"` (data-model.md §4 point 2), so each leg's GitHub Actions job is identifiable by `id` in the run's job list.
- [ ] T011 [US1] Add the new `dispatch-once` job to `.github/workflows/pr-conversation.yml`: `needs: [classify-and-announce, act]`, `if: always() && needs.classify-and-announce.outputs.qualifies == 'true' && needs.classify-and-announce.outputs.classifications != '[]'`, `concurrency: { group: wing-commander-${{ needs.classify-and-announce.outputs.spec-dir }}, cancel-in-progress: false }` (research.md D2). Logic (data-model.md §3): compare the branch tip to `base-sha`; if unchanged, no-op; if changed, read `spec-meta.json`'s `iteration` at the new tip, issue exactly one `gh workflow run implement.yml -f spec_dir=... -f issue=... -f iteration=<n+1>`, and post one PR comment naming the dispatched cycle and the folded item ids/summaries present at that tip.
- [ ] T012 [US1] Run `.github/workflows/pr-conversation.yml` through `actionlint`/`yamllint` locally (or the repo's existing lint step) to confirm the new job graph and input parse cleanly before moving to US2's `report-fold-outcomes` job, since both new jobs share the same `needs:`/concurrency structure.

**Checkpoint**: A review with only in-scope items now folds every leg and dispatches exactly once, via `dispatch-once`, with no per-leg dispatch remaining. US2's `report-fold-outcomes` job (Phase 4) can now be added alongside `dispatch-once` in the same job graph.

---

## Phase 4: User Story 2 - A leg that dies says so on the PR thread (Priority: P1)

**Goal**: Every announced leg produces an observable outcome — healthy, "not folded," or "partly folded" — derived only from signals a dead leg didn't have to publish itself.

**Independent Test**: Cause a leg to die by cancellation and by outright fold failure; confirm each produces a PR-thread comment naming the unfolded item, distinguishing "not folded" from "partly folded," and that a fully healthy run posts nothing.

### Implementation for User Story 2

- [ ] T013 [US2] Add the new `report-fold-outcomes` job to `.github/workflows/pr-conversation.yml`: `needs: [classify-and-announce, act]`, `if: always()` (research.md D6, data-model.md §4). Fetch this run's own jobs via `gh api repos/$REPO/actions/runs/$RUN_ID/jobs --paginate`, filter to `act (leg-*)` entries, and read each one's `conclusion`.
- [ ] T014 [US2] In the same `report-fold-outcomes` job, for each announced (non-`no-action`) classified item, check fold evidence via `git log --grep="^fold(<item.id>):" <base-sha>..<tip> --oneline` against the tip `dispatch-once` also reads (T011/T006).
- [ ] T015 [US2] In the same job, apply the outcome table from data-model.md §4 (job conclusion × fold evidence → healthy / not folded / partly folded, including the `missing`-job-record case) and post exactly one PR comment listing every non-healthy item with its distinguishing outcome when any exist; post nothing when every announced item is healthy (US2 AS5).
- [ ] T016 [P] [US2] Create `.github/scripts/verify-fold-dispatch-once.py` (Gate 34; confirm number from T004), following `wc_shell_harness.py`'s `find_job`/`find_step`/`run_step`/`parse_github_output` API and Gate 14/Gate 30's env-substitution shape (gate-coverage-042.md), driving the shipped `run:` text of `dispatch-once` and `report-fold-outcomes` against synthetic `base-sha`/`classifications`/job-conclusions/git-history fixtures for gate-coverage-042.md's required scenarios 1, 3, 4, 6, 7 (three clean legs → one dispatch and no report; a cancelled leg with no fold evidence → "not folded"; a fold-landed-but-non-success-conclusion leg → "partly folded"; an all-question/no-action review → zero dispatches and zero reports; an all-healthy review → no report at all).
- [ ] T017 [US2] Extend `.github/scripts/verify-fold-dispatch-once.py` with gate-coverage-042.md's scenario 2 (a review arriving mid-cycle, modelled as `act`'s `environment:` wait, produces no fold/no dispatch until the modelled cycle finishes, and the wait is never misreported as a terminated leg) and scenario 5 (a held leg whose `confirm-timeout-minutes` bound expires: the ready legs still dispatch, and the held item is reported per FR-005a, not dropped).
- [ ] T018 [US2] Add gate-coverage-042.md's required mutations to `.github/scripts/verify-fold-dispatch-once.py`'s own test suite (or a sibling check the gate script runs): reverting D1 (restore a per-leg dispatch) must make scenario 1 show more than one dispatch; reverting D6 to job-conclusion-only must make scenario 4 misclassify as healthy; reverting D6 to fold-evidence-only must make scenario 3 misclassify as healthy given spurious fold evidence; removing `report-fold-outcomes`'s `if: always()` must make scenario 3 produce no report when `act` itself fails.
- [ ] T019 [US2] Wire `.github/scripts/verify-fold-dispatch-once.py` into `.github/workflows/lint-workflows.yml` as Gate 34 (number confirmed in T004), matching the existing `verify-*.py` step shape (a `name: Gate NN — ...` step immediately invoking `python3 .github/scripts/verify-fold-dispatch-once.py`), so `wc_gate_registry.py`'s filename-convention pickup and Gate 10's wiring assertion both cover it automatically.
- [ ] T020 [US2] Run `python3 .github/scripts/verify-fold-dispatch-once.py -v` locally and confirm all of gate-coverage-042.md's scenarios 1–7 pass against the shipped `pr-conversation.yml`, and that each required mutation (T018) produces a non-zero exit when applied and exit 0 when reverted (quickstart.md Scenario 11, restricted to this gate).

**Checkpoint**: US1 and US2 together give `pr-conversation.yml` its full new job graph (`classify-and-announce` → `act` → `dispatch-once` + `report-fold-outcomes`), covered end to end by Gate 34. This satisfies SC-001, SC-002, SC-003, SC-013.

---

## Phase 5: User Story 3 - The folded PR comes back and asks to be looked at again (Priority: P1)

**Goal**: A finalize run against an existing open final PR refreshes it (body, record, label, re-review request) instead of skipping; merged/closed PRs are reported and left untouched; the guard's one-PR-per-spec purpose is preserved throughout.

**Independent Test**: Run a spec through review → fold → implement → converge → finalize a second time; confirm the PR body reflects the folded branch, the lifecycle record reads `review`, the review label is present, a re-review is requested from the triggering reviewer(s), and the lifecycle issue says so.

### Implementation for User Story 3

- [ ] T021 [US3] In `.github/workflows/finalize.yml`, widen "Check for an existing final pull request" (`id: guard`) to `gh pr list --head "${SPEC_PREFIX}$SLUG" --base "$DB" --state all --json number,state,url --jq '.[0] // empty'` and replace the boolean `skip` output with the four-valued `pr-state` (`none`/`open`/`merged`/`closed`), per contracts/finalize-refresh.md's guard-output table.
- [ ] T022 [US3] In `.github/workflows/finalize.yml`, regate every step currently gated `steps.diff.outputs.skip != 'true'` — "Assemble PR body," "Open the final PR," "Flip stage label," "Commit metadata (stage -> review)," "Announce for review," "Check remaining manual work" — to `steps.diff.outputs.pr-state == 'none' || steps.diff.outputs.pr-state == 'open'` (research.md D7/D8), preserving each step's `none`-path body byte-for-byte (FR-017).
- [ ] T023 [US3] In `.github/workflows/finalize.yml`, rename "Open the final PR" to "Open or update the final PR" and branch its action on `pr-state`: `none` → `gh pr create ...` unchanged; `open` → `gh pr edit "$EXISTING_PR" --body-file <assembled body>` against the PR number the guard step already read (contracts/finalize-refresh.md).
- [ ] T024 [US3] In `.github/workflows/finalize.yml`'s "Assemble PR body" step, add the machine-owned-region logic (research.md D9, data-model.md §6) for the `open` path: fetch the existing body via `gh pr view "$EXISTING_PR" --json body`; preserve everything outside `<!-- wing-commander-finalize:state:begin -->` … `<!-- wing-commander-finalize:fold-log:end -->` byte-for-byte; fully regenerate the state block (branch, iteration, task counts); re-emit existing fold-log entries unchanged. Leave the `none` path writing the region fresh with zero fold-log entries.
- [ ] T025 [US3] In the same "Assemble PR body" step, add D9a's idempotent append: embed the branch tip SHA in each fold-log entry (`- Fold (<date>, review by <@login...>, #<issue>) <short-sha>: <n> items folded — <summary>.`); before appending, compare the current tip to the most recent existing entry's SHA and append nothing if they match (FR-010a).
- [ ] T026 [US3] In `.github/workflows/finalize.yml`, add a new step gated `pr-state == 'merged' || pr-state == 'closed'` that posts a lifecycle-issue comment naming which state was found and that nothing was changed (FR-009/FR-009a) — distinct wording for "merged" vs. "closed."
- [ ] T027 [US3] In `.github/workflows/finalize.yml`, add a new re-review-request step gated `pr-state == 'open'`, running after the metadata/label steps: read `spec-meta.json`'s `pending_re_review_from` (falling back to `gh pr view "$EXISTING_PR" --json reviews --jq '[.reviews[] | select(.state=="CHANGES_REQUESTED") | .author.login] | unique'` when absent, research.md D10); issue `gh pr edit "$EXISTING_PR" --add-reviewer <logins>` best-effort (continue-on-error or inline `|| true` with an explicit captured-failure report per FR-010b); clear `pending_re_review_from` in the same "Commit metadata (stage -> review)" commit.
- [ ] T028 [US3] Extend `.github/workflows/finalize.yml`'s existing "Announce for review" step wording, on the `open` (refresh) path only, to state the review feedback was acted on and name the review(s) it answers (FR-010d), using the same logins as T027.
- [ ] T029 [US3] In `.github/workflows/pr-conversation.yml`'s `dispatch-once` job (T011), write `pending_re_review_from` into `spec-meta.json` at fold time — union with any existing entries, using `inputs.actor-login` — in the same commit the fold already makes (research.md D10, data-model.md §5). *(Cross-references US1's `dispatch-once` job; the write side of the field US3's finalize reads.)*
- [ ] T030 [P] [US3] Create `.github/scripts/verify-finalize-refresh.py` (Gate 35; confirm number from T004), following `verify-stall-restart-runbook.py`'s real-git-repo-plus-bare-remote shape with a stub `gh` executable on `PATH` recording invocations (gate-coverage-042.md), covering scenario 1 (existing open PR, one prior fold-log entry, a new fold since → metadata committed to `stage: review`, label restored, re-review requested from `pending_re_review_from`, state block regenerated, prose outside delimiters preserved, one new fold-log entry appended, prior entry unchanged) and scenario 6 (no existing PR → today's create path byte-for-byte unchanged, fresh machine-owned region with an empty fold log).
- [ ] T031 [US3] Extend `.github/scripts/verify-finalize-refresh.py` with gate-coverage-042.md's scenarios 2 and 3 (merged PR and closed-not-merged PR → no PR edit, no metadata commit, no label change, no re-review request, and a lifecycle-issue comment naming the correct state with FR-009a's distinct wording).
- [ ] T032 [US3] Extend `.github/scripts/verify-finalize-refresh.py` with scenario 4 (a stubbed `gh pr edit --add-reviewer` failure → metadata/labels/body still occur, failure stated on the lifecycle issue, job exit 0) and scenario 5 (repeat refresh, tip SHA unchanged from the fold log's most recent entry → no new fold-log entry, no duplicate re-review request, no duplicate lifecycle-issue comment).
- [ ] T033 [US3] Add gate-coverage-042.md's required mutations to `.github/scripts/verify-finalize-refresh.py`'s own test suite: reverting D7 (restore boolean `skip`) must make scenario 1 show no refresh; reverting D9's preserve-outside-delimiters logic to full-body overwrite must fail scenario 1's prose-preservation assertion; reverting D9a's idempotency check (always append) must make scenario 5 show a duplicate entry; removing the `merged`/`closed` guard on refresh-only steps must make scenario 2 or 3 show a metadata commit or label change against a merged/closed PR.
- [ ] T034 [US3] Wire `.github/scripts/verify-finalize-refresh.py` into `.github/workflows/lint-workflows.yml` as Gate 35 (number confirmed in T004), matching the existing `verify-*.py` step shape.
- [ ] T035 [US3] Run `python3 .github/scripts/verify-finalize-refresh.py -v` locally and confirm all of gate-coverage-042.md's scenarios 1–6 pass against the shipped `finalize.yml`, and that each required mutation (T033) produces a non-zero exit when applied and exit 0 when reverted (quickstart.md Scenario 11, restricted to this gate).

**Checkpoint**: A converged fold now refreshes its final PR instead of being skipped, covered end to end by Gate 35. This satisfies SC-004 through SC-008 and SC-012.

---

## Phase 6: User Story 4 - A folded change that deletes a file completes (Priority: P2)

**Goal**: The implementation cycle, its retry, and the convergence pass can all remove a tracked file and complete without a "remaining manual work" report; the contract document and the call sites stay in sync.

**Independent Test**: Fold a task that deletes a tracked file, run the implementation cycle, and confirm the file is gone from the branch with no "remaining manual work" report for that task.

### Implementation for User Story 4

- [ ] T036 [P] [US4] In `.github/workflows/implement.yml`, append `,Bash(git rm:*)` to "Compose tool args (implement.cycle)"'s `default-allowed-tools` literal (research.md D11, contracts/implement-deletion-capability.md).
- [ ] T037 [P] [US4] In `.github/workflows/implement.yml`, append `,Bash(git rm:*)` to "Compose tool args (implement.retry)"'s `default-allowed-tools` literal (research.md D11).
- [ ] T038 [US4] In `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, add `Bash(git rm:*)` to the `implement.cycle` and `implement.retry` rows of the "Per-stage default tool lists" table, matching T036/T037 exactly, in the same change (contracts/implement-deletion-capability.md).
- [ ] T039 [US4] Run `python3 .github/scripts/verify-stage-tool-lists.py` (Gate 27, unmodified) and confirm it exits 0 against the T036–T038 edits, proving the call sites and the published contract agree (FR-014; research.md D12 — no new gate needed for this sub-feature).

**Checkpoint**: A removal-shaped task now completes inside implement/retry/convergence alike, satisfying SC-009, FR-011–FR-015.

---

## Phase 7: User Story 5 - The failure branches are exercised, not merely written (Priority: P2)

**Goal**: Every failure branch this feature adds — a per-leg dispatch returning, a finalize refresh reverting to skip, the removal capability vanishing from either the contract or a call site — is caught by a checked-in fixture, and the new coverage itself is provably wired into the gate registry.

**Independent Test**: Reintroduce each of the three defects in turn and confirm the relevant check goes red; confirm the fixed tree passes all three.

Most of US5's work is embedded directly in US1/US2 (T016–T020: Gate 34 and its required mutations) and US3 (T030–T035: Gate 35 and its required mutations) and US4 (T039: Gate 27's continued pass), since gate-coverage-042.md ties each mutation to the specific decision it guards. What remains is confirming the whole set together, end to end, exactly as quickstart.md Scenario 11 describes.

### Implementation for User Story 5

- [ ] T040 [US5] Confirm Gate 34 (`verify-fold-dispatch-once.py`) and Gate 35 (`verify-finalize-refresh.py`) both appear as `Gate NN — ...` step names in `.github/workflows/lint-workflows.yml`'s job output when the full `lint · workflows` job runs, and that `wc_gate_registry.py`'s existing wiring assertion (Gate 10, unmodified) passes with both new gates present — satisfying FR-020's "coverage that stops being run is itself a failure."
- [ ] T041 [US5] Run quickstart.md Scenario 11 in full: apply each of gate-coverage-042.md's required mutations one at a time (git stash first), plus a deliberately-diverged `implement.yml`/`stage-interfaces.md` call-site edit (removing `Bash(git rm:*)` from only one call site without touching the table); confirm every mutation produces a non-zero exit from the relevant gate script (Gate 34, Gate 35, or Gate 27) and exit 0 once reverted; restore the tree (`git checkout -- .github/workflows .specify specs/010-reusable-pipeline`, `git stash pop`).
- [ ] T042 [US5] Confirm Gate 15 (job-suppression) needs no change: every job-level `if:` this feature adds in `pr-conversation.yml` (`dispatch-once`, `report-fold-outcomes`) uses `always()`, which Gate 15 already recognizes, and `finalize.yml`'s new `steps.guard.outputs.pr-state`-based conditions are step-level, outside Gate 15's `needs:`-graph walk — run Gate 15 itself and confirm it still passes unmodified against the edited workflows (FR-021, gate-coverage-042.md).

**Checkpoint**: Reintroducing any of the three original defects now fails a check automatically; disabling either new gate fails Gate 10. SC-010 holds.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Confirm the feature-wide invariants (quiet paths stay quiet, no contract regression) that no single user story's gate fully covers on its own, plus the manual acceptance re-run spec.md names directly.

- [ ] T043 [P] Run `actionlint` and the repository's existing YAML lint over `.github/workflows/pr-conversation.yml`, `.github/workflows/finalize.yml`, and `.github/workflows/implement.yml` in full, confirming no unrelated step was disturbed by the US1–US4 edits.
- [ ] T044 [P] Confirm FR-016: diff each affected workflow's declared `workflow_call` `inputs`/`outputs`/`secrets` blocks against their pre-feature shape; confirm nothing was removed or renamed, and that `confirm-timeout-minutes` is the only addition, optional with a default of `1440`.
- [ ] T045 Run quickstart.md Scenarios 1–10 in full (the local, non-live-run scenarios) and confirm every "Expected" line holds against the finished tree.
- [ ] T046 Record, on the lifecycle issue or in a follow-up note, that quickstart.md Scenario 12 (the live re-run of the measured #240 shape) remains a manual post-merge confirmation per constitution I — not part of this feature's own gate suite, and not blocking this feature's completion.

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
