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
- [ ] T027 Note as an explicit follow-up (not part of this implementation's own scope, per research.md D14): once the first real unattended run reaches `stage:done`, record its evidence on tracker issue #385 and open the separate pull request that clears `WING_COMMANDER_AUTO_RELEASE_PAUSED` in that same change (FR-028, FR-029, SC-007; User Story 5).

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
