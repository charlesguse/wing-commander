# Tasks: Review a Spec PR Automatically Once Clarification Has Settled It

**Input**: Design documents from `/specs/122-settled-spec-pr-review/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/decision-module.md, contracts/spec-pr-review-workflow.md, quickstart.md

**Tests**: FR-025 requires every deterministic decision to be exercised by a checked-in fixture reachable through the gate registry, so fixture tasks are included. Each fixture task is written before the decision code it covers, and is expected to fail until that code lands.

**Organization**: Tasks are grouped by user story. The decision logic is one module (`.github/scripts/spec_pr_review.py`) and one workflow (`.github/workflows/spec-pr-review.yml`), so tasks that edit the same file are sequential (no `[P]`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: the user story the task serves

## Path Conventions

- Decision module: `.github/scripts/spec_pr_review.py`
- Fixtures: `.github/scripts/spec-pr-review-fixtures/`
- Verifiers: `.github/scripts/verify-spec-pr-review.py`, `.github/scripts/verify-spec-pr-review-wiring.py`
- Workflow: `.github/workflows/spec-pr-review.yml`
- Docs: `docs/setup.md`

Before pushing, run `python .github/scripts/run-local-gates.py` (CLAUDE.md "Before pushing"). Because this change adds a workflow with `if:` guards and a `container:`-adjacent `run:` step, it also gets a pass from the `review-step-gating` and `container-shell-safety` skills. Workflow comments are load-bearing; treat comment edits as code edits and re-run the suite. Reuse existing single homes (FR-023); do not paste shared shell or jq into the new workflow.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Skeletons the stories fill in.

- [x] T001 Read `.github/workflows/lifecycle-review-gate.yml`, `.github/scripts/wc_convergence.py`, `.github/scripts/wc_review_finding_fingerprint.py`, `.github/scripts/wc_lifecycle_review_marker.py`, `.github/scripts/wc_gate_registry.py`, `.github/scripts/git_read.py` and `.github/actions/wing-commander-clarification-marker` to record the exact import names and composite inputs to reuse; note them in the module docstring of `.github/scripts/spec_pr_review.py`
- [x] T002 Create `.github/scripts/spec_pr_review.py` as a stdin-JSON / stdout-JSON CLI with subcommands `select`, `eligible`, `verdict`, `check-fixes`, `plan-actions`, `failed-cap` per `contracts/decision-module.md`; non-zero exit on unreadable input (VIII); all subcommands stubbed
- [x] T003 [P] Create `.github/scripts/spec-pr-review-fixtures/` with a README-free layout: one JSON file per case, named `<subcommand>-<case>.json` holding `input` and `expect`
- [x] T004 [P] Create `.github/scripts/verify-spec-pr-review.py`, a runner that loads every fixture in `.github/scripts/spec-pr-review-fixtures/`, invokes `spec_pr_review.py`, and fails on any mismatch or on a subcommand with no fixture
- [x] T005 Register `verify-spec-pr-review.py` in the gate registry (`.github/scripts/wc_gate_registry.py`) so `run-local-gates.py` and CI run the same subject (FR-025)

**Checkpoint**: `python .github/scripts/run-local-gates.py` runs the new gate (red until fixtures are satisfied).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared data shapes and the stand-down every story depends on.

**CRITICAL**: No story work starts until this phase is complete.

- [x] T006 Implement `SpecPrSnapshot`, `EligibilityDecision` and `Finding` parsing/validation in `.github/scripts/spec_pr_review.py` per `data-model.md` (reason enum: `ok`, `paused`, `not-spec-pr`, `fork`, `no-issue`, `multiple-issues`, `unsettled:<why>`, `already-reviewed`, `budget-exhausted`, `convergence-stop`, `failed-cap`); reuse the finding shape and fingerprint helper from `wc_review_finding_fingerprint.py`
- [x] T007 [P] Add fixtures `eligible-paused.json`, `eligible-fork.json`, `eligible-not-spec-pr.json`, `eligible-no-issue.json`, `eligible-multiple-issues.json` in `.github/scripts/spec-pr-review-fixtures/`
- [x] T008 Implement the `eligible` pre-checks (kill switch FR-020, `spec-draft/` same-repo head FR-001, exactly one lifecycle issue, final and plan PRs excluded) in `.github/scripts/spec_pr_review.py`
- [x] T009 Create `.github/workflows/spec-pr-review.yml` skeleton: `schedule` plus `workflow_dispatch` with one input `pr`, concurrency group `spec-pr-review` with no cancel of an in-progress round, default `permissions` minimal, three jobs `select`, `review`, `act` (job-level `statuses: write` on the status-posting job only), no `workflow_call` input, secret or output (FR-022)
- [x] T010 In `.github/workflows/spec-pr-review.yml` job `select`, add the stand-down step on `vars.WING_COMMANDER_SPEC_REVIEW_PAUSED` that records the stand-down in the run summary and stops (FR-020)

**Checkpoint**: Pre-checks and workflow skeleton exist; the gate passes for the foundational fixtures.

---

## Phase 3: User Story 1 - A settled spec PR is reviewed and the result is on the PR (Priority: P1) MVP

**Goal**: A settled spec PR gets one `COMMENT` review naming round, head SHA, a deterministic verdict and structured findings; nothing approves, requests changes or merges.

**Independent Test**: With a settled spec PR, run the review once; a single review appears on the PR with the reviewed SHA, a verdict of exactly "ready for the owner" or "not ready", and findings (quickstart.md).

### Fixtures for User Story 1

- [x] T011 [P] [US1] Add `verdict-empty.json` (empty findings ⇒ `ready for the owner`) and `verdict-nonempty.json` (any finding, including one the round fixed ⇒ `not ready`) in `.github/scripts/spec-pr-review-fixtures/` (FR-013)
- [x] T012 [P] [US1] Add SC-004 replay fixtures `replay-spec119-fr022.json` (ninth merge condition vs constitution X) and `replay-spec120-fr002.json` (`Actions: write` vs the permissions `docs/setup.md` lists) in `.github/scripts/spec-pr-review-fixtures/`, each expecting `not ready` with a finding naming that requirement; the 119 fixture is checked against `main` as it stood at that review (the constitution has since changed)
- [x] T013 [P] [US1] Add `plan-actions-never-approve.json` asserting the plan carries only a `COMMENT` event and a commit-status result of `success` for ready, `failure` otherwise, in `.github/scripts/spec-pr-review-fixtures/`

### Implementation for User Story 1

- [x] T014 [US1] Implement the `verdict` subcommand in `.github/scripts/spec_pr_review.py` (verdict is `not ready` iff findings is non-empty; never taken from agent prose, IX)
- [x] T015 [US1] In `.github/workflows/spec-pr-review.yml` job `review`, check out the PR head only after confirming a same-repo `spec-draft/` ref, re-check eligibility on a fresh snapshot with `spec_pr_review.py eligible`, and fail loud if the PR or spec is unreadable (FR-021)
- [x] T016 [US1] In `.github/workflows/spec-pr-review.yml` job `review`, add the reviewer step using `anthropics/claude-code-action` as `lifecycle-review-gate.yml` does: model `vars.WING_COMMANDER_SPEC_REVIEW_MODEL` defaulting to `claude-opus-5-5`, effort `vars.WING_COMMANDER_SPEC_REVIEW_EFFORT` defaulting to `high`, bounded `--max-turns` via the turn-ceiling composite, tool args via `wing-commander-tool-args`; frame spec, PR title/body, diffs and comments as untrusted data (FR-008, FR-009); a prompt that covers FR-007 (a) buildability against the documented permissions/secrets/variables surface on `main` (without trying to list secrets or variables), (b) conflicts with the constitution and merged specs' live contracts, (c) contradictory, untestable or undecided requirements, and asks for findings in the existing structured shape with class, precedent, fix and question fields
- [x] T017 [US1] In `.github/workflows/spec-pr-review.yml`, extract and validate the reviewer's findings (malformed output ⇒ failure, never "ready", FR-021) using the `wing-commander-agent-verdict` and `wing-commander-stage-findings` composites; compute the verdict with `spec_pr_review.py verdict`
- [x] T018 [US1] In `.github/workflows/spec-pr-review.yml`, post the one `COMMENT` review with the `wing-commander-post-review-comment` composite: round number, reviewed head SHA, verdict, rendered findings, spec 116 round record appended last, cost line from the `wing-commander-metrics-summary` `cost-line` output (FR-011, FR-012, FR-024); never `APPROVE` or `REQUEST_CHANGES`
- [x] T019 [US1] In `.github/workflows/spec-pr-review.yml` job `act`, post the commit status under a context distinct from spec 062's using the workflow token (success for "ready for the owner"; failure for "not ready" and for every failed or stopped outcome), and the one-line outcome on the lifecycle issue (FR-016, FR-017); do not make the status a required check
- [x] T020 [US1] Add `.github/scripts/verify-spec-pr-review-wiring.py` asserting, modelled on `verify-lifecycle-review-gate-composite-provenance.py`: the workflow consumes the composites above rather than inlining the cost-line formatter, no `APPROVE`/`REQUEST_CHANGES`/merge call exists, model and effort come from the variables with the stated defaults, the status context differs from spec 062's, and no `workflow_call` surface is added (FR-010, FR-016, FR-022, FR-023, FR-024); register it in `.github/scripts/wc_gate_registry.py`

**Checkpoint**: A settled PR gets one review with a deterministic verdict; the SC-004 replays pass. This is the MVP.

---

## Phase 4: User Story 2 - Unsettled PRs are never reviewed (Priority: P1)

**Goal**: Selection skips any PR that is not settled and records the reason.

**Independent Test**: For each of the four unsettled conditions run selection once and confirm the PR is skipped with the reason in the run log.

### Fixtures for User Story 2

- [x] T021 [P] [US2] Add `eligible-unsettled-stage-clarify.json`, `eligible-unsettled-marker.json`, `eligible-unsettled-head-newer.json`, `eligible-unsettled-no-announcement.json`, `eligible-settled.json` in `.github/scripts/spec-pr-review-fixtures/`
- [x] T022 [P] [US2] Add `eligible-lookalike-announcement.json` (non-App author ignored) and `eligible-bare-phrase-not-marker.json` (the bare phrase in prose is not a marker) in `.github/scripts/spec-pr-review-fixtures/` (FR-002)
- [x] T023 [P] [US2] Add `select-multiple.json` and `select-none.json` in `.github/scripts/spec-pr-review-fixtures/` (at most one PR selected; skip reason recorded per PR)

### Implementation for User Story 2

- [x] T024 [US2] Implement settledness in `.github/scripts/spec_pr_review.py`: `stage:spec` and not `stage:clarify`; no open colon-form marker (consume the result of the `wing-commander-clarification-marker` scan, do not re-implement it); a ready announcement authored by the pipeline's App; head commit not newer than it (FR-002)
- [x] T025 [US2] Implement the `select` subcommand in `.github/scripts/spec_pr_review.py` (choose at most one PR and head SHA, with a skip reason for every other PR)
- [x] T026 [US2] In `.github/workflows/spec-pr-review.yml` job `select`, list open PRs, build a `SpecPrSnapshot` per `spec-draft/` candidate (head, issue labels, marker-scan result via the clarification-marker composite, App-authored announcements, the App's own prior reviews, failed-attempt notes), call `spec_pr_review.py select`, and emit at most one PR and head SHA; write each skip reason to the run summary

**Checkpoint**: Unsettled PRs are skipped with reasons; US1 still passes.

---

## Phase 5: User Story 3 - One review per head, re-eligible on a new head (Priority: P1)

**Goal**: A head with a completed round is not reviewed again; a new settled head is.

**Independent Test**: Review a head, rerun selection and see it skipped as already reviewed; push a commit, settle it, and see it selected.

### Fixtures for User Story 3

- [x] T027 [P] [US3] Add `eligible-already-reviewed.json`, `eligible-new-head-reselected.json`, and `eligible-failed-round-not-reviewed.json` (a failed round does not mark the head reviewed, FR-005) in `.github/scripts/spec-pr-review-fixtures/`

### Implementation for User Story 3

- [x] T028 [US3] Implement one-review-per-head in `.github/scripts/spec_pr_review.py` using the head-SHA bookkeeping read from the App's own PR reviews (spec 062's convention, consumed through `wc_lifecycle_review_marker.py`), counting only completed rounds (FR-004, FR-005)
- [x] T029 [US3] In `.github/workflows/spec-pr-review.yml` job `review`, re-fetch the PR head just before posting and, if it moved, post against the SHA actually reviewed and state that the result is stale (edge cases)

**Checkpoint**: No head is reviewed twice by a completed round; a new settled head is selected.

---

## Phase 6: User Story 4 - Decisions come back as questions, with precedent cited (Priority: P2)

**Goal**: Unambiguous errors are fixed on the branch under the path/size/citation backstop; owner decisions become clarification markers plus issue questions and move the issue to `stage:clarify`.

**Independent Test**: Seed one precedent-settled finding and one trade-off finding; the first is pushed with its precedent cited and its fixing SHA listed, the second carries options and a recommendation, is written as a marker and posted on the issue, and the issue moves to `stage:clarify` only after the marker push.

### Fixtures for User Story 4

- [x] T030 [P] [US4] Add `check-fixes-ok.json`, `check-fixes-path-outside-spec-dir.json`, `check-fixes-over-size-cap.json`, `check-fixes-precedent-missing.json`, `check-fixes-precedent-unresolvable.json` (default-branch line, head line and issue-comment kinds each resolved or not) in `.github/scripts/spec-pr-review-fixtures/` (FR-026)
- [x] T031 [P] [US4] Add `check-fixes-markers-exempt-from-citation.json` (marker lines pass without a citation) and `check-fixes-markers-path-size-checked.json` (marker lines still blocked by path and size) in `.github/scripts/spec-pr-review-fixtures/`
- [x] T032 [P] [US4] Add `plan-actions-label-after-markers.json`, `plan-actions-no-label-when-marker-push-blocked.json`, `plan-actions-announce-all-fixes-pushed.json`, `plan-actions-no-announce-when-fix-blocked.json`, `plan-actions-no-announce-with-decisions.json`, `plan-actions-stale-head-no-writes.json`, `plan-actions-closed-pr-no-writes.json`, `plan-actions-ambiguous-is-owner-decision.json` in `.github/scripts/spec-pr-review-fixtures/` (FR-015a–FR-015d)

### Implementation for User Story 4

- [x] T033 [US4] Implement the `check-fixes` subcommand in `.github/scripts/spec_pr_review.py`: fix diff touches only `[<P>/]specs/NNN-*/` of the lifecycle, stays under a fixed size cap constant, and each fix's precedent resolves (`default-branch` file:line on main, `head` file:line in the spec's own files, `issue-comment` confirmed through the API result passed in); marker lines checked for path and size only; blocked fixes become report-only findings (FR-015b, FR-026)
- [x] T034 [US4] Implement the `plan-actions` subcommand in `.github/scripts/spec_pr_review.py` producing the `ActionPlan` with the invariants from `data-model.md`: `move_label` only if markers pushed; `post_announcement` only if every finding was an unambiguous error and every fix pushed; no writes on a stale or closed PR; doubtful classification is an owner decision (FR-015a, FR-015c, FR-015d)
- [x] T035 [US4] In `.github/workflows/spec-pr-review.yml` job `review`, run `check-fixes` and `plan-actions` after finding validation, passing the diff stat, per-fix precedent resolutions (issue-comment citations checked with `gh` against this repository) and snapshot freshness; reflect blocked fixes and the decisions list in the posted review body
- [x] T036 [US4] In `.github/workflows/spec-pr-review.yml` job `act`, re-fetch PR state and head, then push fixes and colon-form clarification marker lines in one path-bounded push through the `wing-commander-hardened-push` and `wing-commander-refresh-remote` composites, writing markers with the `wing-commander-clarification-marker` format; list each fixing commit SHA and its precedent in the result (FR-015b, FR-015c)
- [x] T037 [US4] In `.github/workflows/spec-pr-review.yml` job `act`, post each owner-decision question (at least two options and a recommendation, precedent if any) on the lifecycle issue, move the issue from `stage:spec` to `stage:clarify` only when the marker push succeeded, and otherwise post the hand-off stating that a reply on the issue will not be folded and that the owner answers by editing the spec on the branch, settled by a maintainer's dispatch (FR-015c, FR-017)
- [x] T038 [US4] In `.github/workflows/spec-pr-review.yml` job `act`, post the App-authored ready announcement naming the pushed head when `ActionPlan.post_announcement` is true, using the same announcement format intake and clarify use so FR-002(c) recognizes it (FR-015d)
- [x] T039 [US4] Extend `.github/scripts/verify-spec-pr-review-wiring.py` to assert that every `git push` in the workflow goes through the hardened-push composite scoped to the spec directory, that the label move step is gated on the marker-push step's success, and that nothing the workflow posts can start pr-conversation or clarify (bot-actor content only, FR-010)

**Checkpoint**: Fixes and decisions are routed correctly; US1–US3 unaffected.

---

## Phase 7: User Story 5 - The loop is bounded and can be stopped (Priority: P2)

**Goal**: Round budget, spec 116 convergence, failed-attempt cap and the kill switch stop the loop with a stated hand-off.

**Independent Test**: Drive a PR to budget and see the next selection decline it with a hand-off; set the kill switch and see no round run and the stand-down recorded.

### Fixtures for User Story 5

- [x] T040 [P] [US5] Add `eligible-budget-exhausted.json` (5 rounds), `eligible-convergence-stop.json`, `eligible-convergence-rearm-on-diff-change.json` (spec 116 FR-008) in `.github/scripts/spec-pr-review-fixtures/`
- [x] T041 [P] [US5] Add `failed-cap-below.json` (1 failure ⇒ stop false), `failed-cap-at.json` (2 ⇒ stop true), `failed-cap-new-head-resets.json`, `eligible-failed-cap-dispatch-resumes.json` in `.github/scripts/spec-pr-review-fixtures/` (FR-028)

### Implementation for User Story 5

- [x] T042 [US5] Implement the round budget (default 5, one-line constant) and the convergence check in `.github/scripts/spec_pr_review.py` by calling `wc_convergence.py`, not re-implementing its arithmetic (FR-018, FR-019, FR-023)
- [x] T043 [US5] Implement the `failed-cap` subcommand and its use in `eligible` in `.github/scripts/spec_pr_review.py` (stop at 2 failed attempts per head, separate from the round budget; resumes on a new head or a dispatch) (FR-028)
- [x] T044 [US5] In `.github/workflows/spec-pr-review.yml`, on budget exhaustion, convergence stop or failed-cap stop post the hand-off line on the lifecycle issue and PR stating the reason and that the PR is with the owner, and set the failure status; on a failed review step record a failed-attempt note on the issue and report failure (FR-005, FR-018, FR-019, FR-021, FR-028)
- [x] T045 [US5] Extend `.github/scripts/verify-spec-pr-review-wiring.py` to assert the kill-switch variable is read in `select` and that every outcome that is not "ready for the owner" yields a failure status

**Checkpoint**: All stories work; loops are bounded.

---

## Phase 8: Dispatch (FR-027, supports US2/US3)

**Purpose**: Maintainer dispatch as the settling act for human-pushed heads.

- [x] T046 [P] [US2] Add `eligible-dispatch-ok.json`, `eligible-dispatch-bot-actor.json`, `eligible-dispatch-wrong-stage.json`, `eligible-dispatch-open-marker.json`, `eligible-dispatch-skips-announcement.json`, `eligible-dispatch-closed-pr.json` in `.github/scripts/spec-pr-review-fixtures/`
- [x] T047 [US2] Implement the dispatch branch of settledness in `.github/scripts/spec_pr_review.py`: PR open on this repository's `spec-draft/` branch, `stage:spec`, no open colon-form marker; announcement and unchanged-head conditions skipped; bot actor and non-maintainer rejected; eligibility checks FR-001, FR-004, FR-018–FR-020 still apply (FR-003, FR-027)
- [x] T048 [US2] In `.github/workflows/spec-pr-review.yml` job `select`, handle `workflow_dispatch` with input `pr`: pass the triggering actor type and association into the snapshot's `dispatch` field and select exactly that PR

---

## Phase 9: Polish & Cross-Cutting Concerns

- [x] T049 [P] Document `WING_COMMANDER_SPEC_REVIEW_PAUSED`, `WING_COMMANDER_SPEC_REVIEW_MODEL` and `WING_COMMANDER_SPEC_REVIEW_EFFORT`, the new commit-status context, and that the status is not a required check, in `docs/setup.md` (Gate 12 reads this file)
- [x] T050 [P] Confirm `specs/122-settled-spec-pr-review/quickstart.md` steps match the final workflow and fixture names; correct the live docs or code rather than the spec if they differ (the spec's own files are corrected only in this spec's open PR)
- [x] T051 Run `python .github/scripts/run-local-gates.py` and fix any red gate (comment pointers, composite provenance, waiver and registry gates) until the suite passes
- [x] T052 Review the workflow against the `review-step-gating` skill (guards on `if:`, `always()` versus `!cancelled()`, outputs read by always-gated reporters) and the `container-shell-safety` skill (effective `shell: bash` on any `run:` step in a container job); fix findings in the same change

---

## Phase 10: Maintainer follow-up

- [ ] T053 [maintainer] Set the repository variables from `docs/setup.md` if non-default values are wanted (`WING_COMMANDER_SPEC_REVIEW_MODEL`, `WING_COMMANDER_SPEC_REVIEW_EFFORT`); leave `WING_COMMANDER_SPEC_REVIEW_PAUSED` unset to enable the review
- [ ] T054 [maintainer] After merge, prove the change per the `prove-after-merge` skill: dispatch `spec-pr-review.yml` for one settled spec PR with `gh workflow run`, check the run took the select, review and act path on the merged code, and record the evidence on the PR or lifecycle issue #1094
- [ ] T055 [maintainer] After merge, set `WING_COMMANDER_SPEC_REVIEW_PAUSED` to `true` on a test run, confirm the next scheduled selection records the stand-down and runs no round (SC-006), then unset it

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup; blocks all stories.
- **US1 (Phase 3)**: after Foundational. MVP.
- **US2 (Phase 4)**, **US3 (Phase 5)**: after Foundational; both use the `eligible` function from Phase 2 and edit the same module and workflow as US1, so do them after US1 in practice.
- **US4 (Phase 6)**: after US1 (needs the review job and validated findings).
- **US5 (Phase 7)**: after US2 and US3 (extends `eligible`).
- **Dispatch (Phase 8)**: after US2.
- **Polish (Phase 9)**: after all stories.
- **Maintainer follow-up (Phase 10)**: after the change merges.

### Within Each Story

Fixture tasks first (they fail until the code lands), then the decision-module task, then the workflow task, then the wiring-verifier extension.

### Parallel Opportunities

- T003 and T004 touch different files.
- Fixture tasks within a phase (all marked [P]) touch separate JSON files and can be written together.
- T049 and T050 are independent of each other.
- Tasks that edit `spec_pr_review.py` or `spec-pr-review.yml` are not parallel with each other.

### Parallel Example: User Story 1 fixtures

```text
Task: "Add verdict-empty.json and verdict-nonempty.json in .github/scripts/spec-pr-review-fixtures/"
Task: "Add replay-spec119-fr022.json and replay-spec120-fr002.json in .github/scripts/spec-pr-review-fixtures/"
Task: "Add plan-actions-never-approve.json in .github/scripts/spec-pr-review-fixtures/"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup, Phase 2 Foundational.
2. Phase 3 (US1): reviewer, deterministic verdict, `COMMENT` review, status.
3. Stop and validate with quickstart.md and the SC-004 replays.

### Incremental Delivery

1. Add US2 and US3 (selection correctness) and the dispatch path before enabling the schedule broadly, so unsettled or already-reviewed heads are never reviewed.
2. Add US4 (fixes, markers, label move).
3. Add US5 (budget, convergence, caps), then Polish.

---

## Notes

- Never push a fix outside the spec directory, never approve, request changes or merge (FR-010, FR-015b).
- Commit after each task or logical group; keep the gate suite green before pushing.
- Tasks T053–T055 need the repository owner (variables, workflow run, post-merge proof) and are the only `[maintainer]` tasks.

## Phase 11: Convergence

- [x] T056 In `.github/workflows/spec-pr-review.yml` job `select`, persist a convergence or budget stop (a durable App-authored note on the lifecycle issue naming the stopped head) when `review` reports `stop-reason`, and feed it into each snapshot's `convergence_history` / stop state so a rebase-moved head does not re-arm the loop unless the diff against `main` changed (`wc_convergence.py rearmed`); add the matching `eligible-*` fixture if the snapshot shape changes per FR-018, FR-019 (partial)
- [x] T057 Add the wiring assertions to `.github/scripts/verify-spec-pr-review-wiring.py` that `select` reads the stop note and that a stopped PR is skipped before any billable step, with a mutation in its `--self-test` per FR-025 (missing)

## Review Gate Round 1 Findings

- [ ] Review finding: Review job eligibility re-check never runs the eligible subcommand

  The 'Re-check eligibility on a fresh snapshot' step only checks head SHA, fork flag, ref prefix, spec.md and round count, so a PR that became unsettled (stage:clarify, open marker, kill switch) still gets a billable review round.

  - .github/workflows/spec-pr-review.yml

  Detail: FR-021/T015 require the eligible subcommand on a fresh snapshot; the step comment claims it does.

- [x] Review finding: Open-marker scan fails open on git fetch/show failure

  If fetching or showing spec.md fails, open_marker stays false and a PR with unresolved clarification markers is treated as settled.

  - .github/workflows/spec-pr-review.yml

  Detail: Select checks out with persist-credentials false, so the fetch can fail; only the scan script's exit codes are treated as errors.

- [x] Review finding: Fixes are joined to findings by title, so duplicate titles bypass the blocked-fix backstop

  With two findings sharing a title, a fix blocked by the precedent check is pushed because the other fix with the same title passed.

  - .github/scripts/spec_pr_review_actions.py

  Detail: pushable and ok are keyed on title; use a unique key such as the finding index. This defeats FR-026.

- [x] Review finding: prepare and apply validate fix uniqueness differently, so apply can skip a fix silently

  prepare checks old-text uniqueness against a normalized copy of the file and apply checks the raw text, then skips silently on failure, so the PR can be announced as ready with an unfixed error.

  - .github/scripts/spec_pr_review_actions.py

  Detail: CRLF or multi-line old text; the apply count is never reconciled with the number of pushable fixes.

- [x] Review finding: Blocked-only fix outcomes leave the PR stuck with no hand-off

  When all findings are errors but every fix is blocked, the plan has no announcement, marker or label move, so the PR is skipped forever and the owner is never told.

  - .github/scripts/spec_pr_review.py

  Detail: handoff is only set when decisions exist.

- [x] Review finding: Precedent citation check is trivially satisfiable

  A cited file:line only has to exist and an issue-comment ID only has to exist, with no check on author, issue or content, so the FR-026 backstop does not actually constrain fixes.

  - .github/scripts/spec_pr_review_actions.py

  Detail: issue-comment accepts untrusted authors.

- [x] Review finding: Owner-decision questions can be posted with no options or recommendation

  A downgraded fix with no agent-supplied question or options produces a marker and a comment with empty options and an empty Recommendation line, then moves the issue to stage:clarify.

  - .github/scripts/spec_pr_review_actions.py

  Detail: The contract requires at least two options and a recommendation.

- [x] Review finding: Label moves to stage:clarify even when the questions comment fails

  The step has no set -e, so gh issue edit runs after a failed gh issue comment and clarify starts with no questions.

  - .github/workflows/spec-pr-review.yml

  Detail: FR-015c ties the label move to the questions and markers being written.

- [x] Review finding: Dispatch settledness path does not reject stage:clarify

  Under maintainer dispatch an issue labelled both stage:spec and stage:clarify counts as settled, while the scheduled path skips it.

  - .github/scripts/spec_pr_review.py

- [ ] Review finding: Snapshot/trusted-copy block and round-record reader are pasted across workflows

  The helper-script snapshot and write-protect block exists in about nine copies across workflows, and the round-record reader is duplicated, against the repo's single-home rule.

  - .github/workflows/spec-pr-review.yml

  Detail: CLAUDE.md requires moving shared shell into a composite action and adding a single-home check to a gate.

- [ ] Review finding: SC-004 replay fixtures are tautological

  The replay fixtures feed one hard-coded finding to the verdict subcommand and assert not-ready, so SC-004 detection of the spec 119 and 120 conflicts is never exercised.

  - .github/scripts/spec-pr-review-fixtures/replay-spec119-fr022.json

## Review Gate Round 2 Findings

- [ ] Review finding: Review job's fresh-snapshot eligibility re-check skips spec_pr_review.py eligible

  The re-check step hand-rolls a partial check (head SHA, fork, ref prefix, labels, marker, round count) and omits stop-note, failed-cap, already-reviewed, convergence and dispatch actor rules, so a billable duplicate round can run.

  - .github/workflows/spec-pr-review.yml

  Detail: Comment and FR-021/T015 say the module is run; it is not.

- [ ] Review finding: Precedent trust check never restricted to lifecycle issue because SPEC_LIFECYCLE_ISSUE is never set

  _trusted_comment only scopes issue-comment precedents when SPEC_LIFECYCLE_ISSUE is set, and no workflow step sets it, so any repo comment by an OWNER/MEMBER/COLLABORATOR counts as precedent; the unit test sets the variable itself and masks this.

  - .github/scripts/spec_pr_review_actions.py
  - .github/workflows/spec-pr-review.yml

  Detail: The prepare step env has only FAILED, SPEC_DIR and GH_TOKEN.

- [ ] Review finding: plan_actions ignores the stop decision

  A round that ends in convergence-stop or budget-exhausted can still move the label to stage:clarify or post the ready announcement, while the stop note says no further review.

  - .github/scripts/spec_pr_review.py

- [x] Review finding: Writing steps use always() instead of !cancelled()

  Post-review, questions, status, outcome and stop-note steps run on cancellation and can leave stop notes or failed-attempt markers that count toward the failed-cap.

  - .github/workflows/spec-pr-review.yml

- [ ] Review finding: Lifecycle issue derived by scanning every #N in PR body

  Requiring exactly one distinct #N means any extra reference skips the PR forever as multiple-issues, and closingIssuesReferences is fetched but unused.

  - .github/workflows/spec-pr-review.yml

- [ ] Review finding: Pasted snapshot/protect and round-record reader blocks violate single-home rule

  The pristine-script snapshot block is repeated across three jobs and the read_round_records heredoc is duplicated with differing sys.path logic, contrary to CLAUDE.md.

  - .github/workflows/spec-pr-review.yml

- [ ] Review finding: Round budget hard-coded in several places and rounds counted two ways

  Budget 5 appears three times in the workflow plus ROUND_BUDGET in the module, and the workflow uses max record number+1 while the module counts completed rounds, so they can disagree.

  - .github/workflows/spec-pr-review.yml
  - .github/scripts/spec_pr_review.py

- [ ] Review finding: Blocked-fix list prints b.get('finding') but fixes are keyed by id

  The posted review lists blocked fixes as bare integer ids such as '- 0 (precedent-unresolvable)' without naming the finding.

  - .github/workflows/spec-pr-review.yml

- [ ] Review finding: Stale notice appended after the round-record marker

  The Detect-a-head-that-moved step appends text after the hidden round-record marker that the compose step put last deliberately, which may break marker-last parsing.

  - .github/workflows/spec-pr-review.yml

- [ ] Review finding: SC-004 replay fixtures cannot detect the spec 119/120 conflicts

  The fixtures feed a hand-written non-empty finding to the verdict subcommand, which returns 'not ready' for any non-empty list, so a reviewer regression would leave gate 157 green.

  - .github/scripts/spec-pr-review-fixtures/replay-spec119-fr022.json
