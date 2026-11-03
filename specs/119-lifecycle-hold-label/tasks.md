# Tasks: Lifecycle Hold Label and Fold-Time Analyze

**Input**: `specs/119-lifecycle-hold-label/` (plan.md, spec.md, research.md D1–D10, data-model.md, contracts/hold-interfaces.md, quickstart.md)

**Tests**: Required by the spec (FR-014, FR-023, SC-006: a checked-in fixture per failure branch, constitution VIII). Fixture and unit tasks sit beside the code they cover.

**Organization**: Grouped by user story. All paths are relative to the repository root. Run `python .github/scripts/run-local-gates.py` before pushing; workflow comments are load-bearing, so re-run the suite after any comment edit. Changes touching `if:` / `continue-on-error:` also get a `review-step-gating` pass; changes adding `container:`/`run:` steps get `container-shell-safety`. Do not reference private downstream consumers anywhere.

## Phase 1: Setup

- [ ] T001 Read `.github/scripts/board_stop_check.py`, `wc_convergence.py`, `wc_lifecycle_review_marker.py`, `.github/actions/wing-commander-fold-dispatch/action.yml`, `.github/actions/wing-commander-implement-outcome/`, and the `disposition` job of `.github/workflows/lifecycle-review-gate.yml` (~lines 1232–1315) and record in a scratch note (not committed) the marker shape for title→fingerprints (research D7 risk)
- [ ] T002 [P] Create empty fixture directories and test module stubs: `.github/scripts/fixtures/lifecycle-hold/`, `.github/scripts/fixtures/fold-analyze/`, `.github/scripts/fixtures/fold-drop/`, `.github/scripts/fixtures/dismissals/` following the layout of existing `*_tests/` and `fixtures/` siblings

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: the shared homes of FR-019 that every story consumes.

- [x] T003 Implement `.github/scripts/wc_lifecycle_hold.py` with pure functions + CLI subcommands `check` (fresh `gh issue view` labels → `state` = `clear|held|unreadable`; unreadable on any read failure, never `clear`), `set` (idempotent label add, always posts reason; `set` output `true|already`), default label `lifecycle:held`
- [x] T004 [P] Unit tests for `wc_lifecycle_hold.py` check/set (clear, held, unreadable, set-twice idempotent, custom label name) in `.github/scripts/wc_lifecycle_hold_tests/` with fixtures under `.github/scripts/fixtures/lifecycle-hold/`
- [x] T005 Create composite `.github/actions/wing-commander-lifecycle-hold/action.yml` with inputs `mode` (check|set), `issue` (declared), `hold-label` (default `lifecycle:held`), `token`, `reason`; outputs `state`, `set`; `shell: bash` on every `run:`; calls only `wc_lifecycle_hold.py`
- [x] T006 Add the unreadable-labels message text ("labels could not be read; dispatch implement by hand once readable", distinct from a hold) as a single canonical string in `wc_lifecycle_hold.py`, consumed by all callers (FR-004)
- [x] T007 [P] Write gate `.github/scripts/verify-lifecycle-hold-single-home.py`: fails when implement.yml or fold-dispatch stop calling the check composite, when any setter (issue-comment job, pr-conversation strict-stop, analyze decide) stops calling `mode: set`, or when a second inline copy of the label read/add (`gh issue view … labels` against the hold label, `gh issue edit --add-label` of the hold label) appears in a workflow; register it in `.github/scripts/run-local-gates.py`; add fixtures proving it fails per branch

**Checkpoint**: shared check/set homes exist and are gated.

---

## Phase 3: User Story 1 — Hold a lifecycle; implement stops until released (P1) 🎯 MVP

**Goal**: label (or strict `stop`/`/stop`) holds a lifecycle; implement, fold-dispatch and the merge honour it; removing the label resumes.

**Independent Test**: quickstart.md scenario — add label, trigger implement cycle and fold dispatch, confirm nothing built and a status line posted; remove label, confirm implement dispatched.

- [x] T008 [US1] Add the start-of-cycle hold check to `.github/workflows/implement.yml` as the first step of the `implement` job (before any agent/write step) calling the lifecycle-hold composite `mode: check`; on `held`/`unreadable` set job output `held=true` and skip all later steps via `if:` (FR-002, FR-004)
- [x] T009 [US1] In `.github/workflows/implement.yml` add the short status-line job/step posting one line on the lifecycle issue (hold vs. unreadable wording from T006), and make the held path end `final-ok` success with `outcome=held`: no `stage:stalled`, no next-iteration or finalize dispatch, fold-queue ticket still released by `fold-turn-release` (FR-002, FR-003, FR-021)
- [ ] T010 [P] [US1] Teach `.github/actions/wing-commander-implement-outcome/` the `held` outcome value, and fixture-test it
- [ ] T011 [P] [US1] Make the watchdog's lost-progress classifier treat `outcome=held` as expected (locate in `.github/workflows/watchdog.yml` / its scripts under `.github/scripts/`); add a checked-in fixture showing a held cycle's run is not classified as lost progress, stall or defect (FR-021)
- [x] T012 [US1] Add `hold-label` input and `withheld` output (`held|unreadable|""`) to `.github/actions/wing-commander-fold-dispatch/action.yml`; first step calls the lifecycle-hold composite `mode: check`; when withheld, skip `gh workflow run`, set `dispatched=false` and `ticket-unused=true` (FR-003)
- [ ] T013 [US1] Make fold-dispatch callers post the "withheld because of hold / labels unreadable" line on the issue and release the carried ticket: `disposition`/dispatch job in `.github/workflows/lifecycle-review-gate.yml` and `dispatch-once` in `.github/workflows/pr-conversation.yml`
- [x] T014 [P] [US1] Add `release-plan` subcommand to `wc_lifecycle_hold.py`: `{due, reason, spec_dir, issue, iteration}`; due iff issue open, not `parked`, not `stage:stalled`, spec branch exists, spec-meta stage in `tasks|implement`; `iteration = recorded + 1`; unit tests with a fixture for each not-due reason (FR-007)
- [ ] T015 [US1] Add `issues: types: [unlabeled]` trigger and a first job to `.github/workflows/wing-commander-5-implement.yml` that exits unless `github.event.label.name` equals the hold label (`vars.WING_COMMANDER_HOLD_LABEL || 'lifecycle:held'`), runs `release-plan`, dispatches the wrapper itself via `workflow_dispatch` when due, and posts the release note naming `github.event.sender.login`; ensure the added run skips at once for any other label (FR-007)
- [ ] T016 [US1] Find every `gh run list` consumer that looks up a just-dispatched implement run (`grep -rn "gh run list" .github/`) and add `--event workflow_dispatch`; write gate `.github/scripts/verify-lifecycle-hold-dispatch-filter.py` failing when one lacks it; register in `run-local-gates.py` (FR-007)
- [ ] T017 [P] [US1] Add `strict-stop` handling to `.github/workflows/wing-commander-9-pr-conversation.yml`: new `lifecycle-stop` job on issue comments for non-PR issues — skip bots, require OWNER/MEMBER/COLLABORATOR, resolve lifecycle issue, strict check via the existing `wing-commander-board-stop-check` composite (no regex copy, FR-020), then lifecycle-hold composite `mode: set` with an acknowledgement that names the release path and that a maintainer with triage access releases it
- [ ] T018 [US1] Add the strict-stop path for lifecycle PR comments to `.github/workflows/pr-conversation.yml` (deterministic pre-classify step, same checks, `mode: set`); for a classified non-strict `stop` on a lifecycle PR, extend the reply text with "post exactly `stop` or `/stop`, or add the label" and do not set the hold (FR-005)
- [ ] T019 [P] [US1] Make `.github/workflows/clarify.yml` skip (no run, not an answer) a comment that is a strict stop on a lifecycle issue in `stage:spec`/`stage:clarify` using the same parser (FR-024); add a fixture/gate case
- [ ] T020 [P] [US1] Fixture tests for the stop grammar acceptance matrix against `board_stop_check.is_stop_command`: maintainer `stop`, `/stop`, `stop: reason`; non-maintainer, bot, prose containing "stop", `@alice stop` (accepted per Assumptions); under `.github/scripts/fixtures/lifecycle-hold/`
- [ ] T021 [P] [US1] Exclude the hold label from label copying in intake, plan, tasks and finalize (`.github/workflows/{intake,plan,tasks,finalize}.yml`) through one shared jq filter in an existing `.github/actions/_shared/` helper (not four copies); gate `.github/scripts/verify-lifecycle-hold-label-copy.py` fails when a copy step lacks the exclusion; register in `run-local-gates.py` (FR-001)
- [ ] T022 [US1] Add merge precondition 9 "lifecycle issue does not carry the hold label" (fresh read, fail closed, readiness report names the hold) to `.github/workflows/lifecycle-review-gate.yml` `readiness`/`merge` and the fixtures of `verify-lifecycle-merge-preconditions.py` (FR-022)
- [ ] T023 [US1] Add `constitution-names-hold` subcommand to `wc_lifecycle_hold.py` (reads constitution X from the default branch via `git show origin/<default>:.specify/memory/constitution.md`, requires the literal "no hold label"; unreadable → refuse) and call it from the `merge` job; fixtures for unamended (refuse), amended (allow) and unreadable (refuse) text (FR-022, research D9)
- [ ] T024 [P] [US1] Update `specs/062-*/contracts/readiness-and-merge.md` so `may_merge` lists condition 9 (live contract)
- [ ] T025 [P] [US1] Update `docs/adoption.md` with the wrapper `issues: unlabeled` trigger note and the by-hand release for older wrappers (FR-007)

**Checkpoint**: a maintainer can hold in one action and release in one; MVP complete.

---

## Phase 4: User Story 2 — Constitution-conflicting folded task is held (P2)

**Goal**: read-only Sonnet analyze after each tasks-changing fold, deterministic decide, hold only on valid constitution conflicts.

**Independent Test**: fold a task contradicting a NON-NEGOTIABLE principle → held, question posted, no dispatch; ordinary task → dispatch.

- [x] T026 [US2] Implement `.github/scripts/wc_fold_analyze.py prepare`: build `fold-input.json` (`fold_base_sha`, `fold_head_sha`, `added_tasks[]` as `{id, line}` where `id` is the fold title line from the tasks.md diff of the fold's own commits only, `spec_md`, `constitution` from the default branch, `principles[]` headings) per data-model.md
- [x] T027 [US2] Implement `wc_fold_analyze.py decide`: validate schema `{objections:[{task, constitution_conflict, principle|null, reasoning}]}`; `hold` only when well-formed, `constitution_conflict` true, principle in `principles[]`, task in `added_tasks[]`; result `{hold, held_items[], recorded_items[], status: ok|agent-failed|malformed}`; missing/invalid artifact → `agent-failed`; also compute `first-attempt` output (FR-011, FR-013, FR-016)
- [ ] T028 [P] [US2] Fixtures + unit tests, one per FR-014 branch, in `.github/scripts/fixtures/fold-analyze/`: hold, record-only objection, malformed verdict, unknown principle, task not in fold, agent failure, no tasks.md diff, multi-commit fold union only, earlier-fold tasks excluded
- [ ] T029 [US2] Split `.github/workflows/lifecycle-review-gate.yml` `disposition` at the fold commit: new outputs `fold-base-sha`, `fold-head-sha`, `tasks-changed`; add job `fold-analyze` (`permissions: contents: read` only, `claude-sonnet-5-5`, `--max-turns 8`, no write tools, JSON schema output uploaded as artifact, agent step `continue-on-error`, `if: tasks-changed`, behind the existing `kill-switch`) with `shell: bash` where a container applies (FR-008–FR-010)
- [ ] T030 [US2] Add job `fold-decide` (`issues: write`, no agent) running `wc_fold_analyze.py decide`; on `hold=true` call lifecycle-hold composite `mode: set` and post task, principle, reasoning and the four release paths; post record-only objections and agent failures on the lifecycle issue; dispatch (through fold-dispatch composite) proceeds unless held or withheld (FR-012, FR-013)
- [ ] T031 [US2] Ensure a fold on an already-held lifecycle still runs analyze and posts its verdict while dispatch is withheld by the fold-dispatch hold check; fixture/gate case (US2 scenario 6)
- [ ] T032 [P] [US2] Extend gate `.github/scripts/verify-lifecycle-hold-single-home.py` (or a sibling `verify-lifecycle-hold-analyze-permissions.py` registered in `run-local-gates.py`) to fail if the analyze job gains any permission other than `contents: read`, drops the explicit model, or drops `--max-turns`

**Checkpoint**: an analyze verdict can hold a lifecycle; ordinary folds are unaffected.

---

## Phase 5: User Story 3 — Release paths: drop, amend, retry, dismissals (P2)

**Goal**: the four documented answers work; drop removes the task deterministically and findings become dismissed by derivation.

**Independent Test**: from a held lifecycle created by US2, each of proceed/drop/amend/retry leaves the lifecycle unheld with the expected task list.

- [ ] T033 [US3] Write the hold question text (four answers, adopter-neutral, only the hold label named) as a single canonical template in `wc_fold_analyze.py` (or the lifecycle-hold script) used by `fold-decide`; unit test that it names proceed/drop/amend/retry and no repository-specific wrappers (FR-015)
- [x] T034 [US3] Implement `.github/scripts/wc_fold_drop.py parse` per research D8 grammar: first non-quoted line `drop`/`drop:` (case-insensitive), then lines `- Review finding: <title>` / `- Recurring review finding: <title>` with optional `- [ ] ` prefix; disjoint from the stop grammar
- [x] T035 [US3] Implement `wc_fold_drop.py apply`: for each title outcome `removed|unknown|not-fold-task|already-checked|already-absent`; `non-maintainer` for the whole comment; remove only unchecked fold-task lines; build the single-commit message with trailers `Wing-Commander-Drop: <comment-id>` and removed titles; produce reply text naming what was removed and refused
- [ ] T036 [P] [US3] Fixtures + unit tests per FR-023 branch (removed, unknown task, not a fold task, already checked off, already absent, non-maintainer, same-titled tasks) in `.github/scripts/fixtures/fold-drop/`
- [ ] T037 [US3] Add the deterministic `drop` job to `.github/workflows/pr-conversation.yml` (and pass-through in `wing-commander-9-pr-conversation.yml`), running before classification on lifecycle PR comments, through the existing fold-queue admit/push path (spec 074), committing the removal alone, posting the reply, never dispatching implement on a held lifecycle, and setting an output that makes classify/agent skip the handled comment (FR-023)
- [ ] T038 [US3] Implement `.github/scripts/wc_dismissals.py derive` per research D7/D8: input drop-trailer commits on the lifecycle branch, their removed unchecked fold lines, the review marker's title→fingerprints records (all rounds), current tasks.md; verify each trailer'd commit against the API comment (maintainer association, non-bot, comment parses as drop naming exactly the removed lines); a fingerprint is dismissed only when every unchecked fold task carrying its title is dropped; ignore checked-off, reworded, rebase-removed tasks; attribution survives rebase replay (FR-017)
- [ ] T039 [P] [US3] Fixtures + unit tests in `.github/scripts/fixtures/dismissals/`: all-dropped, partial drop, earlier fold already checked off (Recurring finding), same title two fingerprints, forged trailer without maintainer comment, reworded task, task removed by rebase conflict resolution, drop commit replayed by rebase
- [ ] T040 [US3] Wire the derived dismissed list into `lifecycle-review-gate.yml` as `evaluate(dismissed=...)` (`wc_convergence.py` caller), and exclude dismissed fingerprints from folding and from the open in-scope count of the round (FR-017, SC-005); fixture showing zero recurrences and no re-fold after a drop
- [ ] T041 [P] [US3] Update `specs/116-*/contracts/convergence-signals.md` so it states the dismissed list is fed by the derivation of `wc_dismissals.py` (live contract)
- [ ] T042 [US3] Implement the retry semantics (FR-016) in `lifecycle-review-gate.yml`: on `run_attempt > 1`, analyze/decide read constitution from the default branch and spec/tasks at branch tip, task set = fold additions still present; `decide` posts a fresh verdict, may set but never removes the label; dispatch, review post, round record and merge jobs are guarded by the `first-attempt` output; fixture for retry after amendment and retry that still finds a conflict
- [ ] T043 [P] [US3] Gate `.github/scripts/verify-lifecycle-hold-no-new-surface.py` asserting FR-018: no `/fold-hold`, no `fold-hold.yml`, no hold-state/resolved marker, no second hold label, no per-lifecycle lock; register in `run-local-gates.py`

**Checkpoint**: all four answers work and a drop is not undone by the next round.

---

## Phase 6: Polish and cross-cutting

- [ ] T044 Run `python .github/scripts/run-local-gates.py` and fix every failure; apply `review-step-gating` to the changed `if:`/`continue-on-error:` steps and `container-shell-safety` to any new `container:`/`run:` steps
- [ ] T045 [P] Verify `.github/scripts/verify-comment-canonical-pointers.py` and other comment gates pass after any workflow comment edits; point repeated prose at one canonical comment (CLAUDE.md "single home")
- [ ] T046 [P] Walk `specs/119-lifecycle-hold-label/quickstart.md` against the fixtures and confirm each scenario is covered by a checked-in fixture

---

## Phase 7: Maintainer follow-up

- [ ] T047 [maintainer] Open and merge the separate human-merged constitution X amendment PR changing "all eight of its gates" to name the hold condition ("no hold label"), moving the Sync Impact Report to the top of `.specify/memory/constitution-history.md` in the same commit; merge it before the final implementation PR (the merge check refuses otherwise)
- [ ] T048 [maintainer] After merge, re-drive one implement run on a held lifecycle (`gh workflow run` on the implement wrapper) and one label-removal release, and record the evidence on the PR or issue #1066 (`prove-after-merge`)
- [ ] T049 [maintainer] Add the `issues: unlabeled` trigger to any adopting repository's implement wrapper copy that predates it (settings/wrapper change in that repository)

---

## Dependencies and execution order

- Phase 1 → Phase 2 (blocks all) → US1 (MVP) → US2 → US3 → Polish → Maintainer follow-up.
- US2 depends on US1's hold (it sets the label and relies on the dispatch withhold); US3 depends on US2 for the hold question and on the fold record for dismissals.
- Within US1: T008→T009; T012→T013; T014→T015; T022→T023. T010, T011, T017, T019–T021, T024, T025 are independent.
- T047 must merge before the final PR; T048 only after the code PR merges.

## Parallel examples

- Foundational: T004 and T007 together after T003/T005.
- US1: T010, T011, T017, T019, T020, T021, T024, T025 together once T008 is in.
- US3: T036, T039, T041, T043 beside their implementation tasks.

## Implementation strategy

MVP is Phase 1–3 (US1): the label, implement/fold-dispatch/merge honouring it, stop-comment setters, and the label-removed release trigger. Then US2 (analyze + decide), then US3 (drop, dismissals, retry). Each phase ends with the gate suite green. Task count: 49 (US1 18, US2 7, US3 11, Setup 2, Foundational 5, Polish 3, Maintainer 3).
