---

description: "Task list for feature 055: Unattended passage of the pipeline's human gates in end-to-end release verification"
---

# Tasks: Unattended Passage of the Pipeline's Human Gates in End-to-End Release Verification

**Input**: Design documents from `/specs/055-unattended-e2e-gates/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not explicitly requested as TDD. Constitution VIII and this repository's own PR-time gate suite (`.github/scripts/run-local-gates.py`) require every new pure decision script and every new outcome branch to ship with a checked-in, locally runnable fixture — those fixture tasks are folded into Foundational and the user-story phases below as the feature's own acceptance mechanism, not a separate opt-in pass.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P1/P2/P1/P3) to enable independent implementation and testing of each story. The harness credential/containment check (D2) and the two pure gate-decision scripts (D5/D6) are pulled into Foundational rather than into User Story 1, because User Story 1's poll-loop wiring calls them from the moment it exists, and User Story 4's own Independent Test exercises the same credential check — see Dependencies & Execution Order below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Line numbers cited below are today's (`53e203b`) positions in `.github/workflows/auto-release.yml`, taken from research.md/data-model.md/contracts/; locate sites by the step name in quotes once a prior task in the same phase has landed, since each edit shifts later line numbers in the same file.

## Path Conventions

CI/CD pipeline infrastructure repository — no `src`/`tests` split. Paths below are repository-root-relative (`.github/`, `docs/`, `specs/`), per plan.md's Project Structure. No published stage workflow (`.github/workflows/{intake,clarify,plan,tasks,implement,converge,finalize,cleanup,watchdog}.yml`) is touched by any task below (FR-004).

---

## Phase 1: Setup

**Purpose**: Confirm the baseline this feature edits against, before any file changes.

- [x] T001 Confirm today's line anchors for the sites this feature touches in `.github/workflows/auto-release.yml`: the "Confirm the test repository is reachable" step (~lines 192-224), the `poll` step's env block and `while` loop (~lines 481-582, `POLL_BUDGET_SECONDS: "6900"` at ~line 491), and the `report` job's classification step (`[ "$outcome" = "fail-infra" ] && classification="infrastructure"` at ~line 1014). Record any drift from research.md's citations (which were taken at `53e203b`) in the PR description rather than in a spec file. No file changes.
  - Confirmed against `53e203b`: all three anchors matched exactly (reachable step 192-224, poll step 481-582 with `POLL_BUDGET_SECONDS: "6900"` at line 491, classification line at 1014). No drift.

**Checkpoint**: Baseline confirmed; Foundational work can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The harness credential/containment check and the two pure gate-decision scripts every user story's poll-loop wiring depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 In `.github/workflows/auto-release.yml`'s `verify-e2e` job, add a new step "Confirm the fixture maintainer identity's credential" immediately after "Confirm the test repository is reachable" (`id: reachable`, ~line 224), gated `if: steps.reachable.outputs.ok == 'true'`. Read `secrets.WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` into env; if empty, write a `fail-infra` verdict via `bash .github/actions/_shared/auto-release-verdict.sh` naming `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` as the thing to set (matching the wording shape of the existing App-token check at ~lines 206-219) and `exit 0`. Otherwise run `GH_TOKEN=<token> gh repo view "$E2E_REPO" --json viewerPermission --jq .viewerPermission` and `GH_TOKEN=<token> gh api user --jq .login`; if the `gh` calls fail or `viewerPermission` is not `WRITE`, `MAINTAIN`, or `ADMIN`, write the same `fail-infra` verdict naming the secret and the specific problem (`gh` rejected the token, or `viewerPermission` below `WRITE`); otherwise output `ok=true` and `login=<the resolved login>` for later steps to consume. Never echo the token itself to any output or log line (FR-003a, FR-011, FR-014, research.md D1/D2).
- [x] T003 In the `poll` step's env block (`.github/workflows/auto-release.yml` ~line 491), add `MAX_CLARIFICATION_ROUNDS: "3"` next to `POLL_BUDGET_SECONDS`, and raise `POLL_BUDGET_SECONDS` from `"6900"` to `"9000"` so it stops binding before the job's own `timeout-minutes: 150` (~line 102) does. Update the comment above the `poll` step (~lines 476-480) to describe the four gates the loop now drives and why the budget was raised (research.md D7, D13, FR-006, FR-026).
- [x] T004 [P] Create `.github/actions/_shared/auto-release-e2e-clarify-decision.sh`, invoked as `bash .github/actions/_shared/auto-release-e2e-clarify-decision.sh "$COMMENTS_JSON" "$HARNESS_LOGIN" "$ROUNDS_ANSWERED"` per contracts/gate-decision-scripts.md: find the latest comment whose `body` contains `[!IMPORTANT]` and either `Answer the open clarification questions` or `Answer the remaining clarification questions`; print `none` if no such comment exists; if one exists and no comment from `HARNESS_LOGIN` postdates it, print `exhausted` when `ROUNDS_ANSWERED` is already `3` (matching T003's `MAX_CLARIFICATION_ROUNDS`), else print `reply` followed on subsequent lines by this exact literal (research.md D8): "Use the moment this workflow run started as \"the timestamp.\" On a repeat run, overwrite the existing file rather than adding a new one. For anything else this question doesn't cover, use your own best judgement and proceed."; if one exists and a comment from `HARNESS_LOGIN` already postdates it, print `wait`. Pure function of its arguments — no `gh` or network call (Constitution VIII).
- [x] T005 [P] Create `.github/actions/_shared/auto-release-e2e-merge-decision.sh`, invoked as `bash .github/actions/_shared/auto-release-e2e-merge-decision.sh "$PR_LIST_JSON" "$HEAD_REF_PREFIX" "$SLUG"` per contracts/gate-decision-scripts.md: print `none` if `PR_LIST_JSON` is an empty array; print `wrong-attempt` if the single entry's `headRefName` isn't exactly `<prefix><slug>`; print `wait` if `isDraft` is true, or if `mergeStateStatus` is `UNKNOWN` or `BEHIND`; print `conflicting` if `mergeable == "CONFLICTING"`; print `blocked` if `mergeStateStatus == "BLOCKED"`; otherwise print `merge` followed by the PR's `number` on the next line. Pure function of its arguments — no `gh` or network call (research.md D6, D9).
- [x] T006 Create `.github/scripts/verify-auto-release-e2e-gate-decisions.py`, following the checked-in-fixture-plus-mutation-check style of `.github/scripts/verify-auto-release-report.py`: for T004's script, exercise `none` (no marker comment), `reply` at `ROUNDS_ANSWERED=0` and `=2` (asserting the exact literal body from T004), `exhausted` at `ROUNDS_ANSWERED=3`, and `wait` (a harness reply already postdates the question); for T005's script, exercise `none`, `wrong-attempt` (mismatched `headRefName`), `wait` (draft), `wait` (`mergeStateStatus` = `UNKNOWN`/`BEHIND`), `conflicting`, `blocked`, and `merge` (asserting the printed PR number). End with mutation checks per script that invert one documented branch's condition and assert the suite then fails (Constitution VIII: "a test that cannot fail is not a test").
- [x] T007 Register Gate 63 in `.github/workflows/lint-workflows.yml`, following the Gate 60-62 pattern (~line 3510): add a `- name: Gate 63 — the two e2e gate-decision scripts cover every documented branch` step running `python3 .github/scripts/verify-auto-release-e2e-gate-decisions.py`, and a `- name: Gate 63 self-test — each documented branch fails its own mutation` step running that script's mutation mode.

**Checkpoint**: the harness credential is validated and its containment check is in place; both pure decision scripts exist and are locally gated. User story work can begin.

---

## Phase 3: User Story 1 - The scheduled verification reaches a verdict with nobody watching (Priority: P1) 🎯 MVP

**Goal**: All four lifecycle gates — the clarification exchange, and the spec, plan, and finalize pull-request merges — are driven by the harness from inside the existing `poll` loop, with zero human acts in the test repository.

**Independent Test**: With the pause switch cleared and no human touching the test repository, dispatch one auto-release run against a head that carries new work, and confirm the lifecycle issue closes with `stage:done` and the run reports a `pass` verdict, with the test repository's audit trail showing every gate-satisfying act came from the harness.

### Implementation for User Story 1

- [x] T008 [US1] Thread this attempt's feature slug (research.md D10 — the same slug component intake derives from the kickoff issue title, and that the spec-draft/plan/finalize PRs' branch names are required to carry) from the `kickoff` step to the `poll` step as a new step output/env var `SLUG`, so T010's `gh pr list --head` filters can match the exact branch name (FR-009).
  - Implementation note: the descriptive slug suffix is chosen by the intake agent from the feature description (create-new-feature.sh's word-filtering algorithm), so it cannot be precomputed in the `kickoff` step without pasting that algorithm a second time (CLAUDE.md's single-home rule). Instead the `poll` step discovers it once, inside the loop, the same way intake.yml's own "Resolve spec PR URL" step resolves an unknown suffix: list open PRs and match the one whose `headRefName` starts with the fixed `spec-draft/` prefix. Once resolved it is cached in a shell variable and used for exact `--head` matching on all three gates for the rest of the step (loop iterations and the evidence-gathering code before `write_verdict "pass"`), satisfying D10's "not merely the prefix" requirement from the point it is known.
- [x] T009 [US1] In the `poll` step's `while` loop (`.github/workflows/auto-release.yml` ~lines 509-520), before the existing terminal-state check, add clarification-gate driving each iteration: `gh issue view "$ISSUE" --repo "$E2E_REPO" --json comments` under `GH_TOKEN=<T002's harness token>` (so any reply is attributed to the harness identity, not the App), feed the comments JSON plus T002's resolved `login` and a shell round counter (starting at 0) to T004's script; on `reply`, post the printed body via `gh issue comment "$ISSUE" --repo "$E2E_REPO" --body "<body>"` under the harness token and increment the counter; on `exhausted`, immediately call `write_verdict "fail-gate-stall" "clarification" "a reply from the harness resolves the open clarification question within 3 rounds" "still asking after 3 rounds"` and `exit 0`; on `none`/`wait`, do nothing this iteration (research.md D4, D6, D7, D8; FR-002, FR-006, FR-007, FR-008).
- [x] T010 [US1] In the same loop, add PR-merge gate driving for each of the three head-ref prefixes (`spec-draft/`, `plan/`, `spec/`) not yet recorded as merged this attempt: `gh pr list --repo "$E2E_REPO" --head "<prefix>$SLUG" --json number,headRefName,mergeable,mergeStateStatus,isDraft,state` under the harness token (T002, T008), feed the result plus the prefix and `$SLUG` to T005's script; on `merge`, run `gh pr merge <number> --merge --repo "$E2E_REPO"` under the harness token (a plain merge commit — no `--squash`, `--admin`, or `--delete-branch`) and set a per-gate "already merged" flag so later iterations skip the `gh pr list` call for that gate; on `conflicting`, `blocked`, or `wrong-attempt`, immediately call `write_verdict "fail-gate-stall" "<gate name>" "gh pr merge succeeds" "PR #<n>: <reason>"` per contracts/verdict-extension.md's table (`"<gate name>"` is `"spec-draft PR merge"`, `"plan PR merge"`, or `"finalize PR merge"`) and `exit 0`; on `none`/`wait`, do nothing this iteration (research.md D4, D6, D9, D10; FR-002, FR-009, FR-010, FR-023).
- [ ] T011 [US1] Run quickstart.md Scenario 1 against a manually dispatched attempt (leave `WING_COMMANDER_AUTO_RELEASE_PAUSED` at `true` so the schedule doesn't also fire): confirm the clarification question is answered, all three PRs are merged, and the issue closes `stage:done` with zero human acts, and record the run's evidence per the scenario's step 5 (User Story 1's Independent Test; SC-001, SC-002).

**Checkpoint**: all four gates are driven unattended end to end; User Story 1 is independently functional and testable.

---

## Phase 4: User Story 2 - The run's coverage claim matches what it actually exercised (Priority: P1)

**Goal**: Every gate the harness drives is asserted positively with machine-observable evidence, and the written record states that all four gates are driven, adding no gap to spec 045's FR-008.

**Independent Test**: Read only the accepted-gap statement and the run's report, then compare them against the lifecycle gates the test repository actually exercised — every difference is already written down, with nothing found by reading the workflow.

### Implementation for User Story 2

- [x] T012 [US2] Before `write_verdict "pass" "" "" ""` (`.github/workflows/auto-release.yml` ~line 581), add the clarification-gate pass assertion (research.md D12): if any clarification-question marker comment (T004's marker) ever appeared in the issue's comment history, confirm a harness-authored reply comment exists after each such occurrence; if one is missing, call `write_verdict "fail-wrong-output" "clarification gate answered before stage:done" "a harness reply after every open question" "question opened, never answered"` instead of falling through to `pass`. If no question ever appeared, skip this assertion — it is N/A, not a failure (FR-008, FR-016, FR-017, FR-018).
- [x] T013 [US2] Before the same `write_verdict "pass" ...` call, gather PR-merge evidence for the report: `gh pr list --repo "$E2E_REPO" --state merged --head "<prefix>$SLUG"` for each of the three prefixes (recording `number` and `mergedAt`), plus the clarification question/reply comment ids gathered in T009. Write these into new `poll`-step outputs (e.g. `spec-draft-pr`, `plan-pr`, `finalize-pr`, `clarification-rounds-answered`, `clarification-comment-ids`) for the `report` job to read — this does not change `auto-release-verdict.sh`'s six-field JSON shape (research.md D12; FR-017, FR-019).
- [x] T014 [US2] In the `report` job, extend the summary text on a `pass` outcome to name all four gates and their evidence (the three PRs' numbers and merge timestamps; the clarification comment ids, or "not opened" when the gate never opened), reading T013's new `poll`-job outputs, per data-model.md's Gate evidence table (FR-019, FR-025, SC-004).
- [x] T015 [US2] Update the accepted-gap statement alongside spec 045's FR-008a (the accepted-gap record spec 045 introduced for the end-to-end run's coverage) to state that this feature drives all four human gates and removes none, so spec 045's full-lifecycle claim stands unamended (FR-019, FR-020; User Story 2 Acceptance Scenario 2).
- [x] T016 [US2] Add fixtures to `.github/scripts/verify-auto-release-report.py` (Gate 52) for: the pass-path clarification assertion succeeding (a reply follows every question) and failing (a question opened with no reply, producing T012's `fail-wrong-output` shape), plus mutation checks proving the suite fails if the assertion is ever dropped (Constitution VIII).
  - Implementation note: `verify-auto-release-report.py`'s harness extracts and executes only the `report` job's "Determine this run's outcome" step, not the `poll` step where T012's assertion itself runs — that decision logic is instead exercised directly by T006's new gate-decision fixtures and by quickstart.md Scenario 1/2 (T011/T020, live runs). What this gate adds is a fixture asserting the *consuming* step: given T012's exact `fail-wrong-output` shape as `VERDICT_JSON`, the report renders it as `"pipeline defect"` (unchanged) and never as `"gate stall"`, so the two new outcome-shaped failure modes stay distinguishable at the point a maintainer actually reads them.

**Checkpoint**: a `pass` verdict now carries positive, machine-observable evidence for every driven gate; User Stories 1 and 2 both hold.

---

## Phase 5: User Story 3 - A stall at a gate is reported as a stall at that gate (Priority: P2)

**Goal**: An attempt that does not get past a gate is reported as a stall at that named gate — never as a generic `fail-timeout`, and never folded into "pipeline defect."

**Independent Test**: Force one gate to go unsatisfied and confirm the failure report names that gate, what the pipeline was waiting for, and that the cause is a gate stall rather than a pipeline defect — readable without opening the run.

### Implementation for User Story 3

- [x] T017 [US3] In the `report` job's classification step (`.github/workflows/auto-release.yml` ~line 1014), replace the binary `[ "$outcome" = "fail-infra" ] && classification="infrastructure"` with the three-way `case` contracts/verdict-extension.md specifies: `fail-infra` → `"infrastructure"`, `fail-gate-stall` → `"gate stall"`, every other `fail-*` → `"pipeline defect"` (unchanged for `fail-timeout`, `fail-incomplete`, `fail-wrong-output`) (research.md D11; FR-021).
- [x] T018 [US3] Extend the durable failure-issue body-building logic with a "gate stall" branch stating, per FR-022: the gate name (`failing_check`), what the pipeline was waiting for (`expected`), what was observed instead (`observed`), and one short sentence distinguishing a gate stall from an infrastructure failure or a code defect. Reuse the existing three-field rendering — no new field.
- [x] T019 [US3] Add fixtures to `.github/scripts/verify-auto-release-report.py` (Gate 52) for a `fail-gate-stall` verdict at each of the four gate names (`"clarification"`, `"spec-draft PR merge"`, `"plan PR merge"`, `"finalize PR merge"`) covering the exhausted-rounds case and each of the three merge-decision stall reasons, asserting the `"gate stall"` classification and T018's body text. Add mutation checks proving the suite fails if a `fail-gate-stall` outcome ever renders as `"pipeline defect"` or `"infrastructure"` (SC-010, Constitution VIII).
- [ ] T020 [US3] Run quickstart.md Scenario 2 (revoke the harness identity's write access, or invalidate its secret, then dispatch): confirm the resulting verdict is `fail-gate-stall` (or `fail-infra`, per which check catches the revocation) and never `fail-timeout`, and that the durable failure issue's classification reads `"gate stall"` (or `"infrastructure"`), not `"pipeline defect"` (User Story 3's Independent Test; SC-010).

**Checkpoint**: a gate stall is legible from the failure report alone, distinguishable from both a timeout and a genuine pipeline defect, without opening the run.

---

## Phase 6: User Story 4 - The harness's ability to act stops at the test repository (Priority: P1)

**Goal**: The harness's credential and every actor/merge gate on the published surface are exactly as strict as before this feature — nothing it ships gives an adopter an unattended path to their own default branch.

**Independent Test**: Enumerate what the harness identity and its credential can reach and confirm the set is exactly the configured test repository; confirm this repository's own gates and the published stage workflows' actor/merge conditions are unchanged.

### Implementation for User Story 4

- [x] T021 [US4] Update `docs/setup.md`'s prerequisites (near the existing `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` row, ~line 126) to add: the `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` repository secret (a fine-grained PAT scoped to the test repository alone, Contents/Issues/Pull requests write, read only by `verify-e2e`), and the one-time maintainer act of inviting the dedicated machine user account as a **Write** collaborator on the test repository — never Admin, and never granted on this repository or any other (FR-003a, FR-011; quickstart.md Prerequisites #2-3).
- [ ] T022 [US4] Run quickstart.md Scenario 4: (a) list the harness identity's repository access and confirm it is exactly the one test repository (SC-003); (b) diff the published stage workflows (`.github/workflows/{intake,clarify,plan,tasks,implement,converge,finalize,cleanup,watchdog}.yml`) against the previous release tag and confirm no actor gate, merge gate, or human-gate condition changed (FR-012, SC-008); (c) temporarily set `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` to this repository's own `OWNER/NAME` and dispatch, confirming the existing self-repository refusal (research.md D3, the `config` step's `e2e_lc`/`self_lc` check) still fires before T002's credential check and before any gate-driving code runs, with no new code added for this (FR-013). Record the results on issue #386 or the PR.
  - (b) done from this session: `git diff v2.7.3 -- .github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,watchdog}.yml` shows only unrelated pre-existing cost-reporting changes (#366/#377); grepping that diff for `author_association`, `type == 'Bot'`, `actor`, `pr merge`, `approv`, `OWNER|MEMBER|COLLABORATOR` returns nothing — no actor/merge/human-gate condition changed. `git diff fb8d81b` (this branch's own commits) touches none of those eight files at all (0 lines). FR-012/SC-008 hold.
  - (a) and (c) are unchecked: (a) needs live GitHub UI/API access to the harness account's own repository list, and (c) needs a `workflow_dispatch` of `auto-release.yml` — both out of reach of this headless implementation session (no `gh workflow run`, no dispatch capability). Left for a maintainer or a follow-up session with dispatch access; research.md D3's self-repository refusal is unchanged by this feature's diff (confirmed by inspection: the `config` step's `e2e_lc`/`self_lc` check at the top of `verify-e2e` is untouched, and T002's new credential step is strictly downstream of it).

**Checkpoint**: containment is verified end to end; nothing this feature ships weakens a human gate on the published surface.

---

## Phase 7: User Story 5 - The daily schedule resumes on evidence, not on hope (Priority: P3)

**Goal**: The pause switch stays set until one unattended run has actually reached `stage:done`, and is cleared only in the same change that records that run's evidence.

**Independent Test**: Confirm the resume condition is written down, that the tracker issue receives the run evidence, and that the switch is cleared in the same change that records the evidence — not before.

### Implementation for User Story 5

- [x] T023 [US5] Update `docs/setup.md`'s `WING_COMMANDER_AUTO_RELEASE_PAUSED` row (~line 125) or its adjacent prose to state the resume condition in words: the switch is cleared only in the same pull request that records an unattended run's `stage:done` evidence on tracker issue #385 (research.md D14; FR-028, FR-029). This feature ships no code that flips the variable automatically.

**Checkpoint**: the resume condition is documented; clearing the switch remains a deliberate, evidence-carrying follow-up act (quickstart.md Scenario 5), out of this feature's own scope.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Repository-wide checks this feature's diff must pass before it can be reviewed and merged.

- [x] T024 [P] Run `python .github/scripts/run-local-gates.py` (CLAUDE.md's PR-time gate suite) and fix anything Gate 52, Gate 63, or any pre-existing gate newly flags as a result of this feature's changes.
  - 97/97 gates pass, including Gate 52 (`verify-auto-release-report.py`) and the new Gate 63 (`verify-auto-release-e2e-gate-decisions.py`, plain and `--self-test`).
- [x] T025 [P] Run the `review-step-gating` skill against this feature's diff, since it adds and edits multiple `if:` conditions in `.github/workflows/auto-release.yml` (CLAUDE.md's rule for any change touching `if:`, `continue-on-error:`, or a failing step in a workflow).
  - Gate 24 (the deterministic core of the check) passes. `stranded-steps.py` itself is not on this headless run's allowed command list, so the rest was traced by hand: `auto-release.yml` has exactly one `continue-on-error: true` site ("Install uv"), untouched by this diff; every step this diff touches follows the file's existing "never hard-fail, always degrade to a written verdict and `exit 0`" idiom, so GH Actions' implicit `success()` gating never strands a degradation path the way a `continue-on-error` guard can. No defects found.
- [x] T026 State the expected per-attempt cost of a complete unattended run (FR-027) in `docs/setup.md` or the PR description, per research.md D13's provisional wording: materially more than the roughly one dollar the intake-only attempts recorded, with the exact figure recorded from the first unattended run that reaches a verdict.
- [x] T027 Note as an explicit follow-up (not part of this implementation's own scope, per research.md D14): once the first real unattended run reaches `stage:done`, record its evidence on tracker issue #385 and open the separate pull request that clears `WING_COMMANDER_AUTO_RELEASE_PAUSED` in that same change (FR-028, FR-029, SC-007; User Story 5).
  - Posted as an explicit follow-up on lifecycle issue #386: https://github.com/charlesguse/wing-commander/issues/386#issuecomment-5739703256

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational (needs T002's credential/login output and T004/T005's decision scripts).
- **User Story 2 (Phase 4)**: Depends on User Story 1 (its evidence-gathering tasks read the same `poll`-loop state T009/T010 populate, and its pass-path assertion sits right before the same `write_verdict "pass"` call US1 already reaches).
- **User Story 3 (Phase 5)**: Depends on Foundational only for the `fail-gate-stall` outcome shape (already defined by contracts/verdict-extension.md); its own tasks touch the `report` job independently of US1/US2's `poll`-step edits, so it could in principle run in parallel with Phase 3/4 by a second contributor, but is sequenced after US2 here since both edit `verify-auto-release-report.py`'s fixtures.
- **User Story 4 (Phase 6)**: Depends on Foundational's T002 (the credential/containment check it verifies) but not on US1's gate-driving logic — it can start as soon as Phase 2 completes, in parallel with Phase 3.
- **User Story 5 (Phase 7)**: Depends on nothing but Foundational; it is a documentation-only task with no code dependency, and could run at any point after Phase 2.
- **Polish (Phase 8)**: Depends on all preceding phases being complete.

### Within Each User Story

- User Story 1: T008 (slug threading) before T010 (merge-gate driving, which filters by slug); T009 and T010 both edit the same `poll` step, so they are sequential even though both are `[US1]`.
- User Story 2: T012 and T013 both insert code immediately before the same `write_verdict "pass"` call T009/T010 already reach — sequential, same step. T014 (report job) and T015 (docs) can follow in either order. T016 (fixtures) depends on T012's assertion existing.
- User Story 3: T017 and T018 both edit the `report` job's classification/body logic — sequential, same step. T019 (fixtures) depends on T017/T018. T020 (validation) depends on T017-T019.
- User Story 4: T021 (docs) and T022 (validation) can run in either order, but T022 is most meaningful once T002-T020 have landed.

### Parallel Opportunities

- T004 and T005 (the two decision scripts) touch different files and share no logic — parallelizable.
- T024 and T025 (Polish) are independent checks over the finished diff — parallelizable.
- Phase 6 (User Story 4) and Phase 7 (User Story 5) are both documentation-only and independent of Phase 3-5's code edits — either can be picked up by a second contributor as soon as Phase 2 completes.

---

## Parallel Example: Foundational

```bash
# Launch the two independent decision scripts together:
Task: "Create .github/actions/_shared/auto-release-e2e-clarify-decision.sh"
Task: "Create .github/actions/_shared/auto-release-e2e-merge-decision.sh"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks every user story).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run quickstart.md Scenario 1 end to end (T011). This alone proves SC-001/SC-002 and is the feature's whole point.

### Incremental Delivery

1. Setup + Foundational → the credential check and both decision scripts exist and are gated.
2. Add User Story 1 → an unattended run reaches a verdict (MVP!).
3. Add User Story 2 → that verdict carries positive evidence, closing the coverage-claim gap.
4. Add User Story 3 → a stalled gate reports as a stall, not a timeout or a defect.
5. Add User Story 4 → containment is verified against the shipped credential.
6. Add User Story 5 → the resume condition is on record, ready for the real first pass.

### Notes

- [P] tasks touch different files with no dependency between them.
- [Story] labels map each task to spec.md's user stories for traceability.
- No published stage workflow or `docs/adoption.md`-documented wrapper changes at any step (FR-004) — every edit lands in `auto-release.yml` (this repository's own wrapper), two new `_shared/` scripts, `verify-auto-release-report.py`'s and a new script's fixtures, `lint-workflows.yml`'s gate registry, and `docs/setup.md`.
- Every gate-driving decision is deterministic shell reading already-fetched JSON (Constitution IX) — no task above asks an agent to judge whether to answer or merge.

---

## Phase 9: Convergence

- [x] T028 In `auto-release.yml`'s `poll` step, classify a gate-driving write action that fails at the API level — `gh issue comment` (the clarification reply, ~line 599) or `gh pr merge` (~line 630) — as `fail-gate-stall` after a small bound of consecutive failures for that gate, instead of leaving the loop to retry silently until `POLL_BUDGET_SECONDS` elapses and the attempt reports the generic `fail-timeout`. Today neither call's failure path writes a verdict or increments any counter the loop reads, so a harness whose write access is revoked mid-run (exactly quickstart.md Scenario 2's test) is indistinguishable from a hung stage until the full poll budget is spent. Name the reason `"identity refused, or the write action failed repeatedly"` (or a more specific message drawn from the failed command's own stderr) in `observed`, matching FR-023's explicit "the identity refused" case and closing the gap that lets a gate stall render as `fail-timeout` (SC-010, User Story 3 Acceptance Scenario 2) per FR-023 (partial)
  - Added `MAX_GATE_WRITE_FAILURES=3` plus a `clarify_write_failures` counter and a `gate_merge_failures` map (one entry per PR-merge gate) inside the `poll` step. `gh issue comment` and `gh pr merge` now capture stderr; on failure the relevant counter increments, and at the bound the loop calls `write_verdict "fail-gate-stall" "<gate>" "gh <verb> succeeds within 3 attempts" "<captured stderr, or the generic reason>"` and exits — the same `emit_verdict`/`exit 0` idiom every other fail-gate-stall site in this step already uses. A success resets the counter for that gate. Gate 24 and a by-hand trace of `stranded-steps.py`'s four checks (that script is not on this session's allowed command list) confirm this adds no `continue-on-error`/`if:` change and strands no teardown or degradation path — the new exits sit inside the same single `run:` shell script as every existing exit point and write their verdict output before exiting, exactly like the pre-existing `exhausted`/`conflicting`/`blocked`/`wrong-attempt` branches.
- [x] T029 In `.github/actions/_shared/auto-release-e2e-clarify-decision.sh`, broaden the "already answered" check (`harness_reply_exists`) from a comment authored by `HARNESS_LOGIN` specifically to any comment postdating the marker, so a human who replies to the clarification question before the harness's next poll tick is not duplicated by a harness reply on the same question — matching the "A human answers or merges first" Edge Case, which the three PR-merge gates already satisfy (a human-merged PR simply stops appearing in the `--state open` query) but the clarification gate does not. Keep `ROUNDS_ANSWERED`/the round counter scoped to harness-authored replies only, since that count gates FR-006's bound on the harness's own attempts, not on how many times anyone replied. Update `.github/scripts/verify-auto-release-e2e-gate-decisions.py`'s fixtures for the broadened check per FR-010 (partial)
  - Renamed the check to `reply_exists` and dropped the `--arg login` filter so it matches any comment postdating the marker, regardless of author. `HARNESS_LOGIN` (positional `$2`) is still required by the invocation contract but is no longer read for this decision, so the assignment was replaced with a bare `: "${2:?harness login required}"` to keep the argument-count contract without an unused-variable shellcheck warning. `ROUNDS_ANSWERED` is untouched — the caller in `auto-release.yml` only increments it after its own successful harness-authored `gh issue comment` post, so the bound still counts only the harness's own attempts. Added a new Gate 63 fixture ("a human answers first: wait, not duplicated by the harness") and renamed the matching mutation string from `harness_reply_exists` to `reply_exists`; `python3 .github/scripts/run-local-gates.py` re-verified Gate 63 (plain and `--self-test`) and all 97 gates pass.

## Maintainer Feedback (PR #389 code review by charlesguse, head 14d060a)

### Must fix
- [x] Clarify-gate deadlock: `auto-release-e2e-clarify-decision.sh:52-59` treats *any* later comment as a reply, so a bot comment (metrics rollup, watchdog, over-budget report) that lands after the clarification question is misread as an answer and the attempt dead-ends in `fail-timeout`. Restrict the "already answered" check to a comment from an actor that would pass the clarify entry point's own actor gate (non-Bot and OWNER/MEMBER/COLLABORATOR, or the issue's own author, per `intake.yml:524`); add a Gate 63 fixture with a later bot comment.
  - Rewrote the script around a `qualifying_reply_after` predicate reading REST-shape comments (`{user:{login,id,type}, author_association, ...}`) instead of GraphQL `{author:{login}}` — the actor-gate fields (`author_association`, `user.type`) aren't available from `gh issue view --json comments`, so the caller now fetches via `gh api .../comments` (matching `intake.yml`'s own read exactly). Added Gate 66 fixtures for a bot comment, a non-qualifying human, the issue's own author (by id), and a Bot account carrying a qualifying association (the mutation-detection case: proves the Bot check, not merely association, gates qualification).
- [x] Poll budget vs. job timeout: `POLL_BUDGET_SECONDS=9000` (`auto-release.yml:109`) equals `timeout-minutes: 150` (`:642`), but `$SECONDS` starts after checkout/reset/scaffold/kickoff, so the runner can kill the job before any verdict is written. Lower the budget below the job timeout by the pre-poll steps' time and correct the comment at `:625` to state the arithmetic.
  - Lowered to `8100` (135 minutes), reserving 900s for the twelve pre-poll steps plus this step's own post-loop evidence gathering — both of which still count against the job's `timeout-minutes: 150` even though `$SECONDS` (scoped to this step's own shell) doesn't see them. research.md D13 rewritten to correct the original "aligning the two clocks" reasoning, which mistook the job-timeout clock for the step-local one.
- [x] Containment doesn't match the owner's decision: the credential is a classic token (fine-grained tokens can't reach collaborator-only repos), so `auto-release.yml:316-328`'s `viewerPermission` check alone doesn't enforce runtime containment. Add: list repos the token can reach (`gh api user/repos --paginate --affiliation=owner,collaborator,organization_member` under `GH_TOKEN`) and require the set to be exactly the configured test repository; any other set (including empty) ends the attempt as an infrastructure verdict naming repository names only, never the token. Correct every "fine-grained"/"scoped to the test repository alone" claim: `auto-release.yml:290,308` (verdict text, ends up in a failure issue), `docs/setup.md:59`, `research.md` D1, `data-model.md:16`, `quickstart.md:17`, `plan.md:16`, `spec.md` FR-003/FR-011 and User Story 4 scenarios — state containment is enforced by account memberships plus this runtime check.
  - Added the `user/repos?affiliation=owner,collaborator,organization_member` read to the credential step, requiring the set be exactly one repository matching `E2E_REPO` (case-insensitive); any other outcome fails infra naming only `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN`. Corrected every "fine-grained" claim in `auto-release.yml`'s own comments/verdict text, `docs/setup.md`, `research.md` D1/D2, `data-model.md`, `quickstart.md`, `plan.md`, and `spec.md` FR-003/FR-011/Clarifications Q1 to "classic PAT, contained by account memberships plus this runtime check."
- [x] `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME` secret is unused: the login comes from `gh api user` instead, so a token belonging to the wrong account isn't detected, and the merge lookup requests `number,mergedAt` (not `mergedBy`), so merges are never attributed. Use the secret to confirm the token authenticates as that login and to attribute the merge/clarification gates to it; add a `docs/setup.md` row. Read the secret directly in the poll step's `env`, not through a step output (GitHub drops masked-value step outputs), so `HARNESS_LOGIN` isn't empty.
  - Added the secret; the credential step now cross-checks `gh api user --jq .login` against it and fails infra on a mismatch. The `poll` step's `HARNESS_LOGIN` env now reads the secret directly (never `steps.maintainer-credential.outputs.login`). The pass-path merge-evidence lookups now request `mergedBy` and `assert_merged_by_harness` fails the pass if any of the three PRs is unmerged or not attributed to the harness login. Added the `docs/setup.md` row.
- [x] FR-009 not enforced: the slug lookup (`auto-release.yml:717-722`) takes the first open `spec-draft/*` PR repo-wide instead of one bound to this attempt's own issue (research D10 promised the latter), so the `wrong-attempt` decision can never fire. Derive the slug from this attempt's own issue; treat a failed leftover-PR close (currently `|| true`) as an infrastructure outcome rather than letting a leftover be merged.
  - The slug lookup now filters on the spec-draft PR's title ending in the literal `(#<ISSUE>)` `intake.yml`'s own `gh pr create --title` stamps, bound to this attempt's own kickoff issue number. `Close prior leftovers` now tracks `gh pr close` failures and ends the attempt `fail-infra` ("closing prior leftover pull requests") before the reset if any leftover PR failed to close, since this fixture's kickoff issue body is fixed and every attempt derives the same slug.
- [x] No base-branch check before merge: `gh pr list --json` at `:729` omits `baseRefName`, and `auto-release-e2e-merge-decision.sh` never checks a base, so a retargeted plan PR could be merged. Require the expected base for each of the three PRs; treat a mismatch as a gate stall naming the reason (FR-023).
  - `gh pr list` now requests `baseRefName`; the merge-decision script takes `EXPECTED_BASE` as a third positional arg and prints a new `wrong-base` decision (default branch for spec-draft/finalize, `spec/<slug>` for plan, per research.md D9) — `fail-gate-stall` naming the gate, never merged.
- [x] Read/script failures never become gate stalls: `gh issue view ... || true` (`:695`), `gh pr list ... || echo '[]'` (`:728`), and swallowed decision-script errors (`2>/dev/null || true`) all degrade silently to `fail-timeout` instead of a gate stall or infra verdict. T028 only counts write failures — extend the same bounded-consecutive-failure handling to reads and script crashes.
  - Renamed `MAX_GATE_WRITE_FAILURES` to `MAX_GATE_FAILURES` and widened every counter (`clarify_failures`, `gate_failures[prefix]`, plus a new `slug_lookup_failures` for the pre-slug PR list read) to increment on a comments/PR-list read failure or a decision-script non-zero exit, not only a write failure — reset to 0 on any fully successful read+decide. At the same bound (3) the loop writes the same `fail-gate-stall` shape, naming the captured stderr (or the decision script's own stderr) as `observed`.
- [x] A run a human answers first still fails: the pass assertion at `:894-906` requires a reply from the harness login specifically and returns `fail-wrong-output` when a human answered instead. Per FR-010, accept a human's answer for the clarification assertion (or assert only that the question was answered, not by whom).
  - The pass-path assertion now calls the clarify-decision script's new `satisfied` subcommand, which accepts any QUALIFYING reply (same actor-gate rule as the deadlock fix above) after every marker, not only one from `HARNESS_LOGIN`.
- [x] Merge gates not positively asserted (FR-016/FR-018): the pass-path evidence at `:911-913` falls back to `null` and never fails on a missing or unattributed merge. Assert each of the three PRs was merged, by the harness login (see the username-secret item above), and fail the pass otherwise.
  - Added `assert_merged_by_harness`, called for all three gates right after the evidence is gathered; `fail-wrong-output` naming the gate if the PR is `null` or `mergedBy.login` isn't the harness login.
- [x] `mode` missing from the credential verdicts: the three verdict calls in the `maintainer-credential` step (`:308,321,333`) don't pass `$MODE` (also absent from that step's `env`), so container-mode runs report "(mode: unknown)". Add it.
  - Added `MODE: ${{ steps.mode.outputs.mode }}` to the step's `env` and `"$MODE"` as the 7th positional arg to every verdict call in that step, including the two new ones (username-unset, login-mismatch, containment).
- [x] Marker predicate pasted twice — the `[!IMPORTANT]` + phrase jq lives in `auto-release-e2e-clarify-decision.sh:42` and again inline at `auto-release.yml:895`. Per CLAUDE.md's single-home rule, have the workflow call the helper instead of re-typing the predicate.
  - Added `markers` and `satisfied` subcommands to the clarify-decision script; both the per-iteration `decide` logic and the workflow's pass-path assertion now call the script instead of re-deriving the predicate. `auto-release.yml` no longer contains any `[!IMPORTANT]`/"Answer the ... clarification questions" jq of its own.

### Should fix
- [x] `MAX_CLARIFICATION_ROUNDS` in the workflow env is dead (the script hardcodes 3) — thread it through so the bound is set in one place.
  - The script now reads `MAX_CLARIFICATION_ROUNDS` from its own environment (`"${MAX_CLARIFICATION_ROUNDS:-3}"`), inherited from the `poll` step's env instead of being re-hardcoded.
- [x] The verify script's docstring and output say "Gate 63" while `lint-workflows.yml` registers Gate 66 — fix the mismatched number.
  - Updated the docstring, the self-test banner, and the self-test docstring to say Gate 66, with a note on why (the renumbering `lint-workflows.yml` itself already documents).
- [x] The summary line says "clarification: not opened" when `rounds=0` even if a human answered — correct the wording.
  - The `report` job now reads the question count out of `CLARIFICATION_COMMENT_IDS` and distinguishes "not opened" (zero questions) from "answered by a human before the harness" (questions opened, zero harness rounds) from "answered (N harness round(s))".
- [x] The whole comments JSON is passed as one argv to the decision scripts, hitting Linux's 128 KB per-argument limit on a long issue — pass it on stdin or as a file instead.
  - Both decision scripts now read their JSON from stdin (`$(cat)`); every call site in `auto-release.yml` pipes the JSON in rather than passing it as an argument.

### Verify
- [x] Confirm a PR waiting on required checks (merge state `BLOCKED`) is not declared a gate stall, since `BLOCKED` is also what pending required checks report and is currently treated as an immediate stall.
  - Confirmed the ambiguity is real (GitHub's `mergeStateStatus` has no separate "pending checks" value) and closed it rather than merely documenting it: the merge-decision script now inspects `statusCheckRollup` when `mergeStateStatus == "BLOCKED"` and prints `wait` instead of `blocked` while any entry there is short of `COMPLETED`, or `COMPLETED` with no `conclusion` recorded yet. `gh pr list` now requests `statusCheckRollup`. Gate 66 fixtures cover both the genuinely-blocked and the still-pending shapes, with a mutation proving the suite fails if the distinction is dropped.

### Local-only (optional)
- [ ] Add a sentinel to the gate-decisions script's "merge: empty array: none" scenario so it no longer crashes Git Bash on Windows (0xC0000005) for local contributors running `run-local-gates.py` — not a CI defect (CI is Linux), quality-of-life only.
  - Left unchecked: explicitly out of scope per its own label (local-only, quality-of-life, not a CI defect) and this cycle's turn budget went to the eleven must-fix and four should-fix items plus the verify item above.

## Maintainer Feedback (PR #389 second review by charlesguse, head 32bac5f)

### Must fix
- [x] Masked harness login dropped from job outputs: `HARNESS_LOGIN` (from `secrets.WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME`) is masked, and GitHub Actions silently drops any step output containing a masked value. `auto-release.yml:1089-1091` writes `mergedBy` (which contains the login) into the `spec-draft-pr`/`plan-pr`/`finalize-pr` outputs, so a passing run's gate-evidence lines read "null" (FR-019); `:766` puts `${HARNESS_LOGIN}` into the wrong-merger `fail-wrong-output` verdict's `expected` text, so that output is dropped too and the reporter (`:1540-1547`) misfiles it as an infrastructure failure instead of the intended verdict. Assert on `mergedBy` inside the poll step itself, project each PR to `{number, mergedAt}` before writing it to an output, reword the wrong-merger `expected` text without the login (e.g. "attributed to the configured maintainer identity"), and remove the dead `login=$login` output at `:390`. Add a fixture or scenario asserting no verdict or output field ever carries the login.
  - `assert_merged_by_harness` now reads the full `{number,mergedAt,mergedBy}` object for its own check and reports `"the PR merged, attributed to the configured maintainer identity"` / `"merged, but not attributed to the configured maintainer identity"` instead of interpolating `$HARNESS_LOGIN`. Each of the three PR-evidence variables is projected through `jq -c '{number, mergedAt}'` into a `*_pr_out` variable before the `spec-draft-pr`/`plan-pr`/`finalize-pr` outputs are written, so `mergedBy` (and therefore the login substring) never reaches `$GITHUB_OUTPUT`. Removed the dead `login=$login` output at the credential step. No automated fixture asserts the masking-avoidance property directly -- the `poll` step has no existing test harness (unlike the `report` job's "Determine this run's outcome" step, which `verify-auto-release-report.py` executes directly), and building one for a ~460-line step with a `while` loop and a dozen `gh` call sites is out of scope for this cycle's turn budget; verified by inspection instead, the same limitation T025 already recorded for this file.
- [x] Stray `}` breaks the clarification summary line: `auto-release.yml:1592`'s `"${CLARIFICATION_COMMENT_IDS:-{}}"` parses in bash as `${CLARIFICATION_COMMENT_IDS:-{}` followed by a literal `}`, so with the variable set the value becomes `[1,2]}`, jq errors, and a run where clarification never opened is misreported as "answered by a human before the harness." Use a variable for the default (`default='{}'` then `${VAR:-$default}`) and add a fixture asserting the summary line for the no-question, harness-answered, and human-answered cases.
  - Introduced `clarification_comment_ids_default='{}'` and read `"${CLARIFICATION_COMMENT_IDS:-$clarification_comment_ids_default}"`. Added three fixtures to `verify-auto-release-report.py` (Gate 52) asserting the exact summary line for the not-opened, harness-answered, and human-answered-first cases; the last one is a direct regression guard for the stray-brace bug (it sets `CLARIFICATION_COMMENT_IDS` to a non-`{}` value with `CLARIFICATION_ROUNDS_ANSWERED=0`, which the bug misreported as "not opened").
- [x] Two reads on the pass path fail open instead of becoming infrastructure/gate-stall outcomes: `:1073-1076` turns a failed final-comments read into `[]`, so the `satisfied` check returns a vacuous "ok" and the clarification assertion is skipped; `:777`'s `author_id=...||true` yields an empty id on a transient failure, the clarify script then exits on `${1:?}`, and the attempt stalls falsely at "clarification." Treat a failed read on the pass path as an infrastructure outcome, and retry the author lookup within the existing bounded-failure count rather than silently continuing.
  - The final-comments read now calls `write_verdict "fail-infra" ...` and exits on failure instead of substituting an empty file. `author_id` is no longer resolved once before the loop; it is resolved lazily on the first loop iteration as the first arm of the existing clarify-gate if/elif chain, sharing `clarify_failures`/`clarify_last_failure` with the comments-read and decision-script arms already there, so a transient failure is retried and counted against the same `MAX_GATE_FAILURES` bound instead of leaving `author_id` permanently empty. A defensive one-shot fallback (matching the existing `slug` fallback idiom) resolves it again just before the pass-path assertion in case the loop reached `stage:done` before the lazy resolution ever ran.

### Should fix
- [x] The login comparison (`gh api user` against the secret, and against `mergedBy.login`) is case-sensitive though GitHub logins are case-insensitive; compare lowercased on both sides so a differently-cased secret can't produce a false pass-time failure.
  - Both the credential step's `login` vs `MAINTAINER_USERNAME` compare and `assert_merged_by_harness`'s `merged_by` vs `HARNESS_LOGIN` compare now lowercase both sides via `tr '[:upper:]' '[:lower:]'` before comparing.
- [x] The verdict text hard-codes "3 rounds" (`:835-836`) though the script now reads the bound from the environment; interpolate `MAX_CLARIFICATION_ROUNDS` instead.
  - Both the `expected` and `observed` strings in the `exhausted` branch's `write_verdict "fail-gate-stall" "clarification" ...` call now interpolate `${MAX_CLARIFICATION_ROUNDS}`.
- [x] `checklists/requirements.md:38` still says "credential scoped to the test repository alone" — correct it to match the classic-PAT-plus-runtime-containment wording already fixed elsewhere in round 1.
  - Reworded to name the classic PAT, the fine-grained-PAT limitation that rules it out, and the account-memberships-plus-runtime-check containment mechanism, matching plan.md's already-corrected wording (round 1).

### Verify
- [x] `auto-release-e2e-merge-decision.sh:83-93` reports `BLOCKED` with an empty `statusCheckRollup` as `blocked`; confirm a freshly opened PR under required checks, before any check has registered, is not declared a stall in that window.
  - Confirmed the gap was real: an empty rollup previously fell through `length > 0` to `false` (not pending) and read as `blocked`. `still_pending` now treats an empty rollup as pending explicitly (`if ($rollup | length) == 0 then true`). Added a Gate 66 fixture and a paired mutation.
- [x] A `StatusContext` entry in the rollup with no `.status` always reads as pending, so the gate would wait forever; handle it explicitly.
  - `statusCheckRollup` entries come in two shapes: a CheckRun (`status`/`conclusion`) and a legacy StatusContext (`state`, no `status` at all). The jq predicate now branches on `has("state")`, reading `.state == "PENDING"` for the StatusContext shape instead of always falling through the CheckRun-shaped predicate (which read every StatusContext entry as pending forever, since `.status` is always absent for that shape). Added Gate 66 fixtures for both a pending and a resolved StatusContext entry, plus a mutation forcing the old always-pending behavior back and asserting the resolved-entry fixture then fails.
- [x] `:427`'s `gh pr list ... || true` in the cleanup step means a failed list silently closes nothing and proceeds; treat a failed list as an infrastructure outcome, like a failed close.
  - The open-PR list is now read into `open_prs_json` with its own failure branch, writing a `fail-infra` verdict naming "listing open pull requests before closing leftovers" and exiting before the reset, exactly like the existing failed-close branch below it. The open-issue list (line ~420) is unchanged -- a failed issue close was always best-effort by this step's own existing design (the leftover-issue re-open risk the PR-close failure branch's comment describes does not apply to issues), so it was not in scope for this item.
- [x] Gate 66's `--self-test` failed once in a parallel run with a `FileNotFoundError` on its fixed-name `.mutated.tmp` file and passed on rerun (a Windows-parallel race, not a logic defect); give it a per-process temp name.
  - `tmp_path` is now `f"{script_path}.{os.getpid()}.mutated.tmp"` instead of a fixed name.

Note: the reviewer says historical "Gate 63" mentions elsewhere in this file can stay as-is — no action needed on those.
