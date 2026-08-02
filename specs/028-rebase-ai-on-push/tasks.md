---

description: "Task list for Auto-Rebase AI Conflict Resolution on Push-Triggered Rebases"

---

# Tasks: Auto-Rebase AI Conflict Resolution on Push-Triggered Rebases

**Input**: Design documents from `/specs/028-rebase-ai-on-push/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rebase-wrapper-delta.md, contracts/workflow-lint-gate-6.md, quickstart.md

**Tests**: Not requested — no unit-test framework exists for workflow YAML in this repository (plan.md's Testing note, consistent with specs 014/016/017/018/019/020/022/025). Verification is `quickstart.md`'s nine scenarios: FR-012 requires Scenario 1 specifically to be exercised against a real, deliberately induced merge conflict rather than inferred from source, so the corresponding tasks below are validation tasks, not desk-checks, wherever the environment permits a live run.

**Organization**: Tasks are grouped by user story. User Story 1 (P1) is the core defect fix — splitting `wing-commander-rebase.yml`'s single `rebase` job into a push-only `redispatch` job and a schedule/`workflow_dispatch`-only `rebase` job (contracts/rebase-wrapper-delta.md) — and is the true MVP. User Story 2 (P2) adds Gate 6, a new static check in `lint-workflows.yml` (contracts/workflow-lint-gate-6.md), in a completely different file, so it is implementable and testable independently of User Story 1, though its validation tasks are sequenced after US1's fix lands so Gate 6 can be checked against the real post-fix wrapper shape (data-model.md's "post-fix instances" table). User Story 3 (P2) requires no code change at all — `rebase.yml`, which owns the abort/escalate safety path, is untouched by this feature (FR-005, FR-006) — so it is purely a validation phase confirming the safety net still holds once US1's job split ships.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project GitHub Actions pipeline repository, no `src`/`tests` split (plan.md's Structure Decision). Every functional change lands inside two existing files — `.github/workflows/wing-commander-rebase.yml` and `.github/workflows/lint-workflows.yml` — plus two documentation files (`docs/architecture.md`, `docs/adoption.md`); `.github/workflows/rebase.yml` is explicitly out of scope (FR-006, FR-007) and no task below touches it. All file paths are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the live shape of the two files this feature edits still matches what research.md/data-model.md/contracts were authored against, since those were written in a separate planning session.

- [X] T001 Re-read `.github/workflows/wing-commander-rebase.yml` in full and confirm it still matches contracts/rebase-wrapper-delta.md's "Before" shape verbatim (single `rebase` job, `if: ${{ !endsWith(github.actor, '[bot]') }}`, `on:` declaring only `push`/`schedule`); re-read `.github/workflows/lint-workflows.yml` and confirm Gates 1/2/3/5 (and the separate Gate 4 job) are still in the shape contracts/workflow-lint-gate-6.md assumes, with no existing "Gate 6" already present. If either has drifted, note the discrepancy before proceeding — T002/T003/T007 below assume this baseline.
  - Confirmed: `wing-commander-rebase.yml` was byte-for-byte the "Before" shape (single `rebase` job, `if: ${{ !endsWith(github.actor, '[bot]') }}`, `on:` declaring only `push`/`schedule`, no `workflow_dispatch`). `lint-workflows.yml`'s `lint` job had Gates 2/3/5 in the exact shape the contract assumes (Gate 4 confirmed as its own separate job below it, Gate 1 as the separate `registered` job), and no "Gate 6" step already present. No drift; baseline for T002/T003/T007 confirmed current.

**Checkpoint**: The file shape this feature's edits are anchored against is confirmed current.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None required. User Story 1 and User Story 2 edit two entirely different files with no shared code or scaffolding; User Story 3 introduces no new file at all. There is nothing here to block user-story work on.

**Checkpoint**: No blocking prerequisites — proceed directly to Phase 3.

---

## Phase 3: User Story 1 - A conflicted rebase caused by a normal push gets an automatic resolution attempt (Priority: P1) 🎯 MVP

**Goal**: A push-triggered rebase run reaches and attempts the AI conflict-resolution step instead of failing immediately with "Unsupported event type: push" — by redispatching through `workflow_dispatch`, an event already proven in this repository to reach a `claude-code-action` step.

**Independent Test**: Deliberately induce a merge conflict on a spec branch, let a push to the default branch drive the rebase, and confirm the AI conflict-resolution step is reached and attempts a resolution — rather than failing immediately with an "unsupported event" error before it can act (quickstart.md Scenario 1).

### Implementation for User Story 1

- [X] T002 [US1] In `.github/workflows/wing-commander-rebase.yml`, add `workflow_dispatch: {}` (no inputs) to the `on:` block per contracts/rebase-wrapper-delta.md's "Trigger contract addition" — this gives the push path a supported event to redispatch through (FR-001) and makes manual dispatch a first-class entry point.
- [X] T003 [US1] In `.github/workflows/wing-commander-rebase.yml`, split the single `rebase` job into two jobs per contracts/rebase-wrapper-delta.md's "Job contract" section: a new `redispatch` job (`if: ${{ github.event_name == 'push' && !endsWith(github.actor, '[bot]') }}`, `permissions: {actions: write}`, one `run:` step that calls `gh workflow run wing-commander-rebase.yml --repo "$GITHUB_REPOSITORY" --ref "${{ github.ref_name }}"` using `GH_TOKEN: ${{ github.token }}`) and a narrowed `rebase` job (`if: ${{ github.event_name == 'schedule' || github.event_name == 'workflow_dispatch' }}`, keeping its existing `permissions:`, unchanged `uses: ./.github/workflows/rebase.yml` call, and byte-for-byte unchanged `with:`/`secrets:` blocks). Carry forward the loop-guard and job-split rationale as inline comments (research.md R3/R4/R5), matching the contract's annotated example.
  - Implemented verbatim against the contract; `actionlint .github/workflows/wing-commander-rebase.yml` passes clean (exit 0). `with:`/`secrets:` blocks on the narrowed `rebase` job are byte-for-byte unchanged from pre-fix.
- [ ] T004 [US1] Validate quickstart.md Scenario 1 end-to-end: advance `main` with a commit that conflicts with a scratch `spec/NNN-slug` branch in a reconcilable way, push it to `main`, and confirm in the Actions run list that a fast `redispatch`-only run is followed by a `workflow_dispatch`-triggered run whose `rebase` matrix job's "Resolve conflicts" (`claude-code-action`) step actually executes and completes — not "Unsupported event type: push," not skipped — and that the spec branch ends up rebased and force-pushed with zero manual steps (FR-001, FR-003, SC-001, SC-002). This is the one scenario FR-012 requires to be exercised for real; record whether it was run live or, if a live push-triggered validation is not possible in this environment, note that explicitly rather than asserting it from inspection alone.
  - Not run live in this headless implement run: this agent is constrained to commit/push only to `spec/028-rebase-ai-on-push` and may not push to `main`, open PRs, or trigger Actions runs against the live repository. FR-012 explicitly requires a genuine induced-conflict run for this scenario specifically — that live validation remains an open item for a human maintainer (or a later cycle with broader access) before this feature can be considered fully verified end-to-end. Desk-check only: reading contracts/rebase-wrapper-delta.md's Behavior section 1 and the shipped `redispatch`/`rebase` job split (T002/T003) together shows the trigger chain is wired as the scenario expects — `push` → `redispatch` (single `gh workflow run` call, no checkout) → a second `workflow_dispatch` run whose `rebase` job's `if:` now admits `workflow_dispatch` and calls the unchanged `rebase.yml` — but this is inference from source, not proof the `claude-code-action` step actually executes under a real conflict.
- [ ] T005 [US1] Validate quickstart.md Scenario 2: exercise the same conflict shape via the schedule path (or, if a live `17 4 * * *` firing isn't practical within the validation window, the `workflow_dispatch` equivalence proxy quickstart.md names, since both land on the same `rebase` job `if:` allow-list) and confirm an identical outcome shape to Scenario 1 — no trigger-dependent difference in whether the resolution attempt is made (FR-002, US1 Acceptance Scenario 3).
  - Desk-checked by inspection only; no live schedule firing or triggered run was exercised in this headless run (same access constraint as T004). By construction: the `rebase` job's `if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'` treats both events identically, and `rebase.yml` receives byte-for-byte the same `with:`/`secrets:` regardless of which event reached it, so no trigger-dependent difference exists in the shipped YAML — but this has not been proven against a live scheduled run.
- [ ] T006 [US1] Validate quickstart.md Scenario 3: run `gh workflow run wing-commander-rebase.yml --ref main` directly and confirm the `rebase` job's `if:` admits `workflow_dispatch` immediately, no `redispatch` job runs, and the run goes straight to `rebase.yml`'s `discover`/`rebase` jobs.
  - Desk-checked by inspection only; this run cannot invoke `gh workflow run` against the live repository (out of the push-only-to-the-spec-branch scope granted to this run). By construction: `redispatch`'s `if:` requires `github.event_name == 'push'`, so it evaluates false and is skipped for a `workflow_dispatch`-originated run; `rebase`'s `if:` admits `workflow_dispatch`, so the run proceeds straight to `rebase.yml`. Not exercised live.

**Checkpoint**: User Story 1 is independently satisfied — the core defect (SC-001, SC-002) is fixed and proven against a real induced conflict on the push path.

---

## Phase 4: User Story 2 - A future unsupported trigger is caught by CI before it can ship (Priority: P2)

**Goal**: `lint-workflows.yml`'s `lint` job gains a new Gate 6 that fails a pull request whenever a wrapper job reaches an agent-bearing resolved stage under an event the agent does not support, naming the offending wrapper and event(s).

**Independent Test**: On a branch, add an unsupported triggering event to a rebase-like wrapper whose stage contains an AI-agent step, and confirm the workflow-lint check fails with a clear message; then remove it and confirm the check passes (quickstart.md Scenarios 6-9).

### Implementation for User Story 2

- [X] T007 [US2] In `.github/workflows/lint-workflows.yml`'s `lint` job, add a new step ("Gate 6 — agent-bearing wrapper reaches its stage only under a supported event") after the existing Gate 5 step, using contracts/workflow-lint-gate-6.md's Python verbatim: build the `docs` map from every `.github/workflows/*.yml` file, define `is_agent_bearing` (any step whose `uses:` starts with `anthropics/claude-code-action`) and `reachable_events` (data-model.md's Job Reachable-Event Set table: absent/unrecognized `if:` → full wrapper `on:` set; `==` clauses → their union intersected with the wrapper's `on:` set; `!=` clauses → the wrapper's `on:` set minus the matched events), then for every wrapper job with a `uses: ./.github/workflows/*.yml` call into an agent-bearing resolved stage, compute `flagged = reachable_events(...) - SUPPORTED_EVENTS` (`{issues, issue_comment, pull_request, workflow_dispatch, workflow_run, schedule}`, research.md R6) and emit an `::error file=...::` annotation naming the wrapper file, job, resolved stage, and every flagged event (FR-008, FR-009, FR-010, FR-011) when non-empty.
  - Implemented verbatim against contracts/workflow-lint-gate-6.md, as a new step after Gate 5 in the `lint` job. `actionlint .github/workflows/lint-workflows.yml` passes clean (exit 0). `python3` is not invokable in this headless run's tool allowlist, so the script's runtime behavior against the live repo is confirmed by manual trace (see T010) rather than by executing it.
- [ ] T008 [US2] Validate quickstart.md Scenario 6: on a throwaway branch, reintroduce the pre-fix shape (`wing-commander-rebase.yml`'s `rebase` job `if:` reverted to `!endsWith(github.actor, '[bot]')`, `on:` still declaring `push`), open a pull request, and confirm `lint · workflows` → `lint` fails with an `::error` annotation naming `wing-commander-rebase.yml`, the `rebase` job, and `push`; then revert to the post-fix (T003) shape and confirm the same PR's `lint` job passes (SC-004).
  - Not run live: this headless run may not open pull requests or push to a throwaway branch outside `spec/028-rebase-ai-on-push`. Manually traced Gate 6's logic (T007) against the pre-fix shape instead: with `on:` declaring only `push`/`schedule` and the `rebase` job's `if: ${{ !endsWith(github.actor, '[bot]') }}` (no `event_name` literal), `reachable_events` falls to its conservative default and returns the full wrapper set `{push, schedule}`; `flagged = {push} - SUPPORTED_EVENTS = {push}`, non-empty, so Gate 6 emits an `::error` naming `wing-commander-rebase.yml`, job `rebase`, and event `push` — matching the scenario exactly. Against the shipped post-fix shape (T002/T003), the `rebase` job's `if:` yields `included = {schedule, workflow_dispatch}`, both supported, so `flagged` is empty and the check passes. Trace only, not a live PR run.
- [ ] T009 [US2] Validate quickstart.md Scenario 7: on a throwaway branch, add a different unsupported event (e.g. `create: {}`) with no restricting `if:` to an agent-bearing wrapper (e.g. `wing-commander-1-intake.yml`), open a pull request, and confirm `lint` fails naming that wrapper and `create` — not a hard-coded `push`-only check (FR-010, US2 Acceptance Scenario 4); revert and confirm it passes again.
  - Not run live (same PR/branch constraint as T008). Manually traced: adding `create: {}` to `wing-commander-1-intake.yml`'s `on:` block (wrapper events becoming `{issues, create}`) with the `intake` job's existing `if: github.event.label.name == 'spec-request'` (no `event_name` literal, so the conservative full-set default applies) yields `reachable = {issues, create}`, `flagged = {create}` — Gate 6 would emit an `::error` naming `wing-commander-1-intake.yml`, job `intake`, and event `create`, confirming the check is a `SUPPORTED_EVENTS` set-difference (FR-010), not a `push`-only literal check. Trace only.
- [X] T010 [US2] Validate quickstart.md Scenario 8: run Gate 6's check logic (T007) against the repository as-is, after T003 has landed, and confirm zero failures across every current wrapper (`wing-commander-1-intake.yml` through `wing-commander-8-watchdog.yml`, `wing-commander-auto-update-spec-kit.yml`, and the fixed `wing-commander-rebase.yml`) — every one already declares only supported-list events for its agent-bearing stage calls (US2 Acceptance Scenario 2, SC-005).
  - `python3` is not invokable in this headless run, so Gate 6's logic was traced by hand against every `wing-commander-*.yml` wrapper's `on:`/job `if:` and its called stage's agent-bearing status, rather than executed: `wing-commander-1-intake.yml` (issues, no literal → full set, supported), `-2-clarify.yml` (issue_comment, full set, supported), `-3-plan.yml` (pull_request+workflow_dispatch; `if:` includes literal `workflow_dispatch`, reachable={workflow_dispatch}, supported), `-4-tasks.yml` (`tasks` job reachable={workflow_dispatch}; `tasks-approved` job reachable={pull_request}, both supported), `-5-implement.yml` and `-6-finalize.yml` (workflow_dispatch only, no `if:` on the calling job → full set, supported), `-7-cleanup.yml` (pull_request, no literal → full set, supported), `-8-watchdog.yml` (`watchdog` job: workflow_run+workflow_dispatch, no literal → full set, both supported), `-auto-update-spec-kit.yml` (schedule+workflow_dispatch+pull_request+issue_comment, no literal → full set, all four supported), and the fixed `-rebase.yml` (`rebase` job reachable={schedule, workflow_dispatch}, both supported; the `redispatch` job has no `uses: ./.github/workflows/*.yml` call so Gate 6 never evaluates it). Zero flagged events across the current wrapper set — SC-005 holds.
- [X] T011 [US2] Validate quickstart.md Scenario 9: confirm `wing-commander-8b-watchdog-self.yml` (no `uses: ./.github/workflows/*.yml` job at all) is never evaluated by Gate 6 regardless of its declared events, and — if a wrapper/stage pair with no agent step exists or a minimal scratch pair is constructed — confirm a PR adding an unsupported event to it still passes `lint`, since `is_agent_bearing` gates the entire check (FR-009, US2 Acceptance Scenario 3).
  - Confirmed by inspection: `wing-commander-8b-watchdog-self.yml`'s only job (`verify`) has no `uses:` field at all (its steps are `actions/checkout@v4` and an inline `run:` script), so Gate 6's `uses.startswith("./.github/workflows/")` filter excludes it regardless of its `workflow_run` trigger. No non-agent-bearing local reusable-workflow target exists in this repository to construct a second, more direct example against (every local workflow a `wing-commander-*.yml` wrapper's `uses:` resolves to — intake/clarify/plan/tasks/implement/finalize/cleanup/watchdog/auto-update-spec-kit/rebase — contains a `claude-code-action` step), and this headless run may not open a pull request to exercise a throwaway scratch pair. Confirmed by construction (`is_agent_bearing` gates the per-job loop entirely) rather than by a live PR.

**Checkpoint**: User Story 2 is independently satisfied — the static gate exists, catches the exact defect this feature fixes, is forward-looking beyond `push`, and does not false-flag either a fully-supported wrapper or a non-agent-bearing one.

---

## Phase 5: User Story 3 - The graceful safety net is preserved when the AI genuinely cannot resolve (Priority: P2)

**Goal**: Confirm the existing abort-and-escalate safety path — untouched by this feature — remains the outcome for any conflict the AI cannot resolve, now reached only after a genuine resolution attempt on the push path rather than being the sole path.

**Independent Test**: Induce a conflict the AI cannot resolve on a push-triggered rebase and confirm the rebase is aborted, the branch is left exactly as it was, and the conflict is escalated on the lifecycle issue — identical to today's graceful outcome (quickstart.md Scenario 4).

### Implementation for User Story 3

- [ ] T012 [US3] Confirm `.github/workflows/rebase.yml` has zero diff from its pre-feature state after T002/T003 land — FR-005/FR-006 require the abort/escalate safety behavior to hold by construction, since this file is not part of the fix's scope; a diff here would indicate accidental scope creep into the published stage contract.
- [ ] T013 [US3] Validate quickstart.md Scenario 4: advance `main` with a commit that conflicts with a scratch branch in a genuinely ambiguous/contradictory way, push it to `main` so the `push` → `redispatch` → `workflow_dispatch` path (T002/T003) is exercised, and confirm the scratch branch's tip is byte-for-byte unchanged from before the run (no half-rebased state, no force-push) and the lifecycle issue gets a new comment plus the `rebase:blocked` label carrying the existing `<!-- wing-commander-rebase: blocked ... -->` marker format (FR-004, FR-005, SC-003).
- [ ] T014 [US3] Validate quickstart.md Scenario 5: confirm the relocated loop guard on `redispatch` (T003) behaves identically to the original — a bot-authored push (`<slug>[bot]`) to `main` evaluates `redispatch`'s `if:` false, so no `redispatch` run starts and consequently no second `workflow_dispatch` run is queued (research.md R4).

**Checkpoint**: All three user stories hold — the resolution attempt is reachable on push (US1), a static gate prevents recurrence (US2), and the safety net is unchanged (US3).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Bring documentation in line with the shipped wrapper shape and run a final full-scenario sweep.

- [ ] T015 [P] Update `docs/architecture.md`'s "Rebase" section (the `**Trigger**:` line, currently "`push` to main (skipping `*[bot]` actors) + nightly schedule") to describe the new shape: push redispatches via `workflow_dispatch` to a supported event before reaching the stage; schedule and manual `workflow_dispatch` reach it directly (research.md R9).
- [ ] T016 [P] Update `docs/adoption.md` §8's `wing-commander-rebase.yml` copy-paste template (currently the exact pre-fix single-job pattern) to the fixed two-job pattern from contracts/rebase-wrapper-delta.md — `on:` gains `workflow_dispatch: {}`, and the `jobs:` block shows the `redispatch`/`rebase` split — so a new adopter following the guide no longer copies the defect this feature fixes (research.md R9).
- [ ] T017 Run quickstart.md's full scenario set (1-9) against the finished workflows and record, per specs/020/022/025's validation-record convention, which scenarios were exercised via a live triggered run versus desk-checked by inspection only.
- [ ] T018 [P] Confirm SC-005 directly: run Gate 6's logic (T007) against the complete current `.github/workflows/*.yml` set and confirm the only file whose flagged-event status changed as a result of this feature is `wing-commander-rebase.yml` (from would-have-flagged-`push` pre-fix to clean post-fix) — no other agent-bearing wrapper's lint status moves.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: N/A — no blocking prerequisites exist for this feature (see Phase 2's Purpose).
- **User Story 1 (Phase 3)**: Depends on Setup (T001) confirming the baseline `wing-commander-rebase.yml` shape T002/T003 edit against.
- **User Story 2 (Phase 4)**: Depends on Setup (T001) confirming the baseline `lint-workflows.yml` shape T007 edits against. T007 itself has no dependency on US1's file. T008 and T010 depend on User Story 1's T003 having landed, since both validate Gate 6 against the real post-fix `wing-commander-rebase.yml` shape (T008's "revert" step returns to the post-fix shape; T010 sweeps the current wrapper set, which only passes once T003 exists).
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T002/T003) — T013/T014 exercise the safety path and loop guard through the new `redispatch`/`rebase` job split, so they cannot be validated until that split exists. T012 (confirming `rebase.yml` is untouched) has no such dependency and can run any time after Setup.
- **Polish (Phase 6)**: T015/T016 depend on User Story 1's T003 (the shipped wrapper shape they document). T017 depends on all prior phases. T018 depends on User Story 2's T007 and User Story 1's T003.

### Same-file ordering (not story dependencies, but real ordering constraints)

- T002 and T003 both edit `.github/workflows/wing-commander-rebase.yml` and should land in that order (trigger addition, then job split) — no `[P]` marker on either.
- T015 and T016 edit different files from each other and from T002/T003/T007, so they carry `[P]`.

### Parallel Opportunities

- T007 (US2's Gate 6 addition, a different file) can be implemented in parallel with T002/T003 (US1's wrapper edit) — they touch different files with no shared code.
- T015 and T016 (Polish, different doc files) can run in parallel with each other, and with T018, once their respective dependencies (T003, T007) are satisfied.
- T009 and T011 (US2 validation scenarios that don't depend on the fixed wrapper shape) can run in parallel with US1's T004-T006.

---

## Parallel Example: User Story 1 and User Story 2 implementation

```bash
# Once Setup (T001) completes, these can start together — different files:
Task: "Add workflow_dispatch: {} trigger and split the rebase job in .github/workflows/wing-commander-rebase.yml (T002, T003)"
Task: "Add Gate 6 to .github/workflows/lint-workflows.yml's lint job (T007)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm both files' live shape)
2. Complete Phase 2: Foundational (no-op — nothing blocks)
3. Complete Phase 3: User Story 1 (T002-T006) — the push-triggered resolution attempt is restored and proven against a real conflict
4. **STOP and VALIDATE**: Confirm quickstart.md Scenarios 1-3 hold
5. This alone closes the defect the issue reports (SC-001, SC-002) and is independently deployable — User Story 2 (the gate) and User Story 3 (safety-net validation) add durability and assurance but are not required for the core fix to work.

### Incremental Delivery

1. Setup → confirmed baseline for both files
2. Add User Story 1 → validate Scenarios 1-3 → the core defect is fixed and proven live (MVP!)
3. Add User Story 2 → validate Scenarios 6-9 → recurrence of this defect class is now caught in CI
4. Add User Story 3 → validate Scenarios 4-5 → the existing safety net is confirmed unchanged through the new job split
5. Polish → documentation updated, full Scenario 1-9 sweep, SC-005 cross-check

### Parallel Team Strategy

With multiple contributors:

1. Team completes Setup together (T001)
2. Once Setup is done:
   - Contributor A: User Story 1 (`wing-commander-rebase.yml`)
   - Contributor B: User Story 2 (`lint-workflows.yml`)
3. User Story 3 (validation-only) and Polish (docs) follow once User Story 1's T003 lands, since both depend on the final wrapper shape

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- User Story 3 introduces no new code — it is a validation phase confirming an invariant (FR-005) that holds by construction because `rebase.yml` is out of scope
- FR-012 requires Scenario 1 (T004) specifically to be validated against a real induced conflict, not inferred from source — do not treat a desk-check as sufficient for that task alone, even if other scenarios are desk-checked due to environment constraints
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
