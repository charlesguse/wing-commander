---

description: "Task list for One Fold Queue Per PR — Concurrent Stage-9 Runs Stop Cancelling Each Other's Legs and Cycles"
---

# Tasks: One Fold Queue Per PR — Concurrent Stage-9 Runs Stop Cancelling Each Other's Legs and Cycles

**Input**: Design documents from `specs/074-serialized-fold-dispatch/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not explicitly requested as TDD; the composite-level bash fixtures and Gate 99 named in plan.md's Testing section are themselves the test surface for this feature and are included as implementation tasks.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact; line numbers cited as "currently" are against `main` at `91e23d4` (research.md's own baseline) and may drift slightly by implementation time — locate the named job/step by name, not by line number alone.

## Gate number confirmation

Confirmed against `.github/workflows/lint-workflows.yml` at this tasks-stage run: the last registered gate is **Gate 98** (`board-loop's fix, review and readiness run helpers from a pristine snapshot`). **Gate 99** is therefore locked as this feature's gate number for every task below (plan.md's Testing note; research.md D8; contracts/gates.md).

---

## Phase 1: Setup

- [X] T001 Re-confirm immediately before opening the implementation PR that Gate 99 is still the next unclaimed gate number in `.github/workflows/lint-workflows.yml` (locked above as Gate 98 + 1); if another feature has since claimed 99, renumber every task below and every `Gate 99` reference in the new gate script and its registration accordingly

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared CAS ledger and the two composites (`admit`, `release`) every user story's jobs call. No user story can be wired into a workflow before this phase completes.

- [X] T002 Create shared library `.github/actions/_shared/fold-queue-ledger.sh` implementing the fetch-current-tip → parse-JSON (start from `{"specs": {}}` if the `wing-commander-fold-queue` branch or the `spec-dir` key is absent) → apply-one-named-transform → commit → push loop, with retry-on-non-fast-forward-rejection capped at 8 attempts using the 1s/2s/3s/4s/5s/5s/5s backoff `wing-commander-metrics-persist` already uses (`.github/actions/wing-commander-metrics-persist/action.yml:373-509`), creating the `wing-commander-fold-queue` branch via the existing `orphan-branch-reset` idiom on first write, and treating retry-budget exhaustion as a hard `::error::` failure, never a silent no-op (contracts/fold-queue-ledger-schema.md). This file's header comment becomes FR-020's single canonical statement of why the fold/dispatch/implement jobs are gated the way they are (research.md D9) — every other call site this feature touches points at it instead of restating it.

- [X] T003 In `fold-queue-ledger.sh`, implement the `enqueue(spec_dir, kind, run_id)` transform: append `{token: "run-<run_id>-<kind>", kind, run_id, enqueued_at: now, granted_at: null}` to `specs[spec_dir].queue` unless a ticket with that exact token already exists (idempotent no-op on retry); `kind` MUST be one of `act`, `dispatch`, `implement`; increment `specs[spec_dir].round` and initialize a fresh `specs[spec_dir].rounds[<new round>]` record (per data-model.md's shape) only when `queue` was empty immediately before this append (contracts/fold-queue-ledger-schema.md; data-model.md)

- [X] T004 In `fold-queue-ledger.sh`, implement the `release(spec_dir, token, outcome, commit_sha?, leg_id?)` transform: remove the ticket matching `token` from `queue` only when it is at index 0 — a release request for a non-head ticket is a caller error surfaced as `::error::`; append a completion record to the current round's `folded_items` (when `commit_sha` is present) or `not_folded_items` (otherwise); `outcome` MUST be one of `folded`, `not-folded`, `error`; releasing a token already absent from `queue` MUST be a no-op, never an error (contracts/wing-commander-fold-queue-release.md)

- [X] T005 In `fold-queue-ledger.sh`, implement the `claim-dispatch(spec_dir, round, implement_workflow)` transform: valid only when the calling `dispatch`-kind ticket is at the head; returns `should-dispatch: true` only if `queue` contains no other `act`-kind ticket for this `spec_dir` **and** `rounds[round].dispatch_claimed_by` is `null`, and in that same atomic write sets `dispatch_claimed_by` to the calling `run_id`, reads `spec-meta.json`'s `iteration` fresh (never cached), sets `rounds[round].iteration`, and enqueues a new `implement`-kind ticket at the new queue head; every other case returns `should-dispatch: false` and mutates nothing (contracts/fold-queue-ledger-schema.md; research.md D4, D5)

- [X] T006 In `fold-queue-ledger.sh`, implement the `reclaim-stale(spec_dir, stale_token)` transform: valid only when `stale_token` is at index 0, its `granted_at` is older than the caller-supplied `stale-after-minutes`, and the caller has independently confirmed via `gh api` (outside this transform) that the token's owning run is no longer active; removes it from `queue` with no completion record, since a reclaimed ticket's outcome is unknown by construction (research.md D6)

- [X] T007 [P] Create composite action `.github/actions/wing-commander-fold-queue-admit/action.yml` with inputs `spec-dir` (required), `kind` (required, one of `act`/`dispatch`/`implement`), `run-id` (default `${{ github.run_id }}`), `existing-token` (default `''` — when set, skip `enqueue` and only await this token per research.md D5), `max-wait-minutes` (default `30`), `poll-interval-seconds` (default `10`), `stale-after-minutes` (default `10`, must be smaller than `max-wait-minutes`); outputs `token`, `round`, `granted`; each poll iteration does a plain `git fetch` + branch-tip read with no caching across iterations; invokes `reclaim-stale` against the head ticket once a waiter has polled past `stale-after-minutes`; hard-fails the step (non-zero exit) if `max-wait-minutes` elapses without a grant; the composite's own job carries no `concurrency:` block and requests no `pull-requests`/`issues` permission (contracts/wing-commander-fold-queue-admit.md)

- [X] T008 [P] Create composite action `.github/actions/wing-commander-fold-queue-release/action.yml` with inputs `spec-dir`, `token`, `round` (all required), `leg-id` (default `''`, required non-empty when releasing an `act`-kind ticket for one leg — the calling job invokes this composite once per leg it ran), `outcome` (required, one of `folded`/`not-folded`/`error`), `commit-sha` (default `''`), `summary` (default `''`, framed as data never as instructions to a later reader, Principle V); no outputs — calls the ledger's `release` transform (contracts/wing-commander-fold-queue-release.md)

- [X] T009 [P] Add composite-level bash fixtures under `.github/actions/wing-commander-fold-queue-admit/tests/` using an injectable `git`/`gh` shim (no live network): a clean immediate grant, a queued-then-granted sequence, and one stale-ticket reclaim (quickstart.md Drill 2)

- [X] T010 [P] Add composite-level bash fixtures under `.github/actions/wing-commander-fold-queue-release/tests/` using an injectable `git`/`gh` shim: a normal release-with-outcome and an idempotent double-release (quickstart.md Drill 2)

**Checkpoint**: The ledger transforms and the `admit`/`release` composites exist and pass their own fixtures. User story implementation can now begin.

---

## Phase 3: User Story 1 - No review item is lost when two reviews land on one PR (Priority: P1) 🎯 MVP

**Goal**: Every fold-route item classified by any in-flight stage-9 run on a PR reaches a recorded terminal outcome — folded, or named as not folded in a report a maintainer can read — even when a second run's ticket queues behind the first's.

**Independent Test**: Drive two overlapping stage-9 runs on one PR (the second starting while the first's legs are still queued) and confirm the union of the fold-outcome reports accounts for every classified fold-route item of both runs, with no item missing from both, and no pending leg of either run cancelled.

### Implementation for User Story 1

- [X] T011 [US1] Add prerequisite job `fold-turn-act` to `.github/workflows/pr-conversation.yml`: `needs: classify-and-announce`; `if:` mirrors `act`'s own qualifying condition (currently pr-conversation.yml:1485-1491 — `!cancelled()`, `needs.verify-image-prerequisites.result != 'failure'`, `needs.classify-and-announce.result == 'success'`, `needs.classify-and-announce.outputs.qualifies == 'true'`, and non-empty/non-`'[]'` `legs`) so it is skipped exactly when `act` would be skipped (a `stop`-only run, or zero legs); carries no `concurrency:` block; calls `wing-commander-fold-queue-admit` once with `kind: act` and `spec-dir: needs.classify-and-announce.outputs.spec-dir` (contracts/workflow-changes.md)

- [X] T012 [US1] In `.github/workflows/pr-conversation.yml`, add `fold-turn-act` to `act`'s `needs:` list, leaving `act`'s existing `concurrency: group: ${{ needs.classify-and-announce.outputs.concurrency-group }}` block (currently pr-conversation.yml:1521-1523) completely unchanged (contracts/workflow-changes.md)

- [X] T013 [US1] In `.github/workflows/pr-conversation.yml`, add a call to `wing-commander-fold-queue-release` as the final step of each `act` leg, `if: always()`, `kind: act`, one call per leg id that leg actually ran, recording `outcome` (`folded`/`not-folded`/`error`) and `commit-sha` when folded, before the job ends (research.md D3; contracts/wing-commander-fold-queue-release.md)

- [X] T014 [US1] Replace the pasted grouping-rationale comment at `act` (currently pr-conversation.yml:1517-1522) with a one-line pointer to `.github/actions/_shared/fold-queue-ledger.sh`'s header comment, matching Gate 47's canonical-pointer convention (FR-020; research.md D9)

- [X] T015 [US1] In `.github/workflows/pr-conversation.yml`, change `report-fold-outcomes`'s fold-happened signal to read this run's own entries out of the ledger's round record (keyed by this run's own `run_id`) instead of `git log --grep '^fold(' BASE_SHA..TIP_SHA` (currently pr-conversation.yml:2892-2926 / `:2707-2709`), keeping the existing `gh api .../jobs` job-conclusion cross-check unchanged since it independently catches a leg that died before it could call `release` at all (research.md D3; FR-006)

**Checkpoint**: User Story 1 is fully functional and independently testable — drive the two-run scenario and confirm 11/11 items reach a terminal outcome with zero pending-leg cancellations.

---

## Phase 4: User Story 2 - The dispatched implement cycle actually starts (Priority: P2)

**Goal**: After every stage-9 run in flight on a PR finishes folding, exactly one implement cycle is dispatched for the whole overlapping set, and that cycle is never itself cancelled by a later job's queuing.

**Independent Test**: Drive two overlapping stage-9 runs that both fold at least one item, and confirm that exactly one implement run is dispatched for the pair, that it reaches a non-`cancelled` conclusion, and that the lifecycle issue shows one dispatch outcome for the pair rather than one per run.

### Implementation for User Story 2

- [X] T016 [US2] Add prerequisite job `fold-turn-dispatch` to `.github/workflows/pr-conversation.yml`: `needs: [classify-and-announce, act]`, `if: always()` plus the same qualifying condition `dispatch-once` already has (currently pr-conversation.yml:2583-2588); no `concurrency:` block; calls `wing-commander-fold-queue-admit` with `kind: dispatch` (contracts/workflow-changes.md)

- [X] T017 [P] [US2] Create composite action `.github/actions/wing-commander-fold-queue-claim-dispatch/action.yml` with inputs `spec-dir`, `round`, `dispatch-token` (all required); outputs `should-dispatch`, `folded-items`, `not-folded-items`, `iteration`, `implement-token` (the latter four present only when `should-dispatch: true`); calls the ledger's `claim-dispatch` transform once its own `dispatch`-kind ticket is granted, guaranteeing exactly one winner per round (FR-009/SC-003) and never resolving `true` while any `act`-kind ticket for the spec-dir remains queued (FR-007) (contracts/wing-commander-fold-queue-claim-dispatch.md)

- [X] T018 [P] [US2] Add composite-level bash fixtures under `.github/actions/wing-commander-fold-queue-claim-dispatch/tests/` using an injectable `git`/`gh` shim: a losing claim (round not empty), a winning claim (round empty, atomic `implement`-ticket insertion) (quickstart.md Drill 2)

- [X] T019 [US2] In `.github/workflows/pr-conversation.yml`, add `fold-turn-dispatch` to `dispatch-once`'s `needs:` list, leaving its existing `concurrency:` block (currently pr-conversation.yml:2614-2616) unchanged; add a first step calling `wing-commander-fold-queue-claim-dispatch`; when `should-dispatch: false`, release the ticket and end the job with no reply posted; when `true`, drive the existing dispatch/reply logic (currently pr-conversation.yml:2659-2751) from the composite's `folded-items`/`not-folded-items`/`iteration` outputs instead of the job's own `BASE_SHA`/`TIP_SHA`/git-log-range computation, and pass the composite's `implement-token` output as the new `fold-queue-token` input on the `gh workflow run` call (research.md D4; contracts/workflow-changes.md; FR-011)

- [X] T020 [US2] Replace the pasted grouping-rationale comment at `dispatch-once` (currently pr-conversation.yml:2606-2613) with a one-line pointer to `.github/actions/_shared/fold-queue-ledger.sh`'s header comment (FR-020; research.md D9)

- [X] T021 [P] [US2] Add the new optional `workflow_call` input `fold-queue-token` (default `''`) to `.github/workflows/implement.yml`'s `on.workflow_call.inputs`, preserving today's behavior exactly for any caller that omits it — no existing input, secret, or output is removed or renamed (FR-019; contracts/workflow-changes.md)

- [X] T022 [US2] Add prerequisite job `fold-turn-implement` to `.github/workflows/implement.yml`: `needs:` none beyond the workflow's existing prerequisite jobs; no `concurrency:` block; when `inputs.fold-queue-token != ''`, calls `wing-commander-fold-queue-admit` with `existing-token: inputs.fold-queue-token` (await-only, never enqueues, per research.md D5); when `inputs.fold-queue-token == ''`, the job succeeds immediately as a no-op so `implement`'s `needs:` stays uniform whether or not a token was supplied (FR-019)

- [X] T023 [US2] In `.github/workflows/implement.yml`, add `fold-turn-implement` to `implement`'s `needs:` list, leaving its existing `concurrency:` block (currently implement.yml:363-365) unchanged (contracts/workflow-changes.md)

- [X] T024 [US2] Add terminal job `fold-turn-release` to `.github/workflows/implement.yml`: `needs: [implement, stalled]`, `if: always()`; calls `wing-commander-fold-queue-release` with `kind: implement` once both `implement` and `stalled` have concluded, rather than duplicating the release call into both jobs (contracts/workflow-changes.md)

- [X] T025 [US2] Replace the pasted grouping-rationale comment at `implement` (currently implement.yml:360-362) with a one-line pointer to `.github/actions/_shared/fold-queue-ledger.sh`'s header comment (FR-020; research.md D9)

**Checkpoint**: User Stories 1 and 2 are both independently functional — for the two-run scenario, exactly one implement cycle is dispatched and it reaches a non-cancelled conclusion.

---

## Phase 5: User Story 3 - A lost cycle is visible on the lifecycle issue (Priority: P3)

**Goal**: An implement run cancelled because a concurrency group replaced it while pending produces a one-line lifecycle-issue notice naming the spec, iteration, cancelled run, and cause, and the cycle is re-dispatched automatically at most once.

**Independent Test**: Force an implement run to be cancelled while pending in its group and confirm a notice naming it appears on the lifecycle issue and the cycle is re-dispatched exactly once; force the replacement to happen again and confirm the second loss is reported with no third dispatch; confirm a maintainer's own manual cancel of an implement run still produces no notice and no re-dispatch.

### Implementation for User Story 3

- [ ] T026 [US3] Create new published stage `.github/workflows/fold-cycle-guard.yml` (`workflow_call`, no agent step) with inputs `run-id` (required), `conclusion` (required), `spec-dir` (default `''`, resolved via the same `wing-commander-inspected-run-identity` composite `watchdog.yml` already uses when empty), `implement-workflow` (required), `dry-run` (default `false`, skips the real `gh workflow run` re-dispatch for quickstart/fixture use); output `action-taken` (one of `none`/`notice-only`/`notice-and-redispatch`) (contracts/fold-cycle-guard.md)

- [ ] T027 [US3] In `fold-cycle-guard.yml`, implement the never-started detection: read `gh api repos/.../actions/runs/<run-id>/jobs`; if any job's `started_at` is non-null, set `action-taken: none` immediately — this is today's existing manual-cancel silence and must not be touched (FR-013); only proceed to correlation when every job's `started_at` is null (contracts/fold-cycle-guard.md)

- [ ] T028 [US3] In `fold-cycle-guard.yml`, implement the correlation check: look for another run or job sharing the resolved `spec-dir`'s concurrency group whose own `started_at` falls within a short window of this run's `updated_at` (the cancellation timestamp); found → proceed toward a `notice-and-redispatch`/`notice-only` outcome; not found → `action-taken: none`, treating an unexplained pending-cancel with no positive replacement evidence the same as today's silent default rather than guessing a cause (research.md D7; FR-012/FR-013)

- [ ] T029 [US3] In `fold-cycle-guard.yml`, on a positive correlation finding: read the ledger's round record for the resolved `spec-dir` keyed by `implement_run_id == run-id`; post the FR-012 notice (spec, iteration, cancelled run URL, cause = concurrency replacement) unconditionally, reusing `wing-commander-chain-stop-notice`'s posting shape; then check `redispatch_count`, which is bounded to `0` or `1` and MUST never be incremented past `1` (data-model.md): if `0`, call the same claim/enqueue path `dispatch-once` uses to re-dispatch — reusing the existing `iteration` rather than starting a fresh round — increment `redispatch_count` to `1` in that same ledger write, and name the new run in a second notice line; if already `1`, post the FR-016a line instead ("a maintainer's re-drive is the remaining step") and dispatch nothing (research.md D7; FR-016/FR-016a)

- [ ] T030 [US3] Create wrapper `.github/workflows/wing-commander-9b-fold-cycle-guard.yml`: `on: workflow_run: workflows: ["Wing Commander · 5 implement"], types: [completed]`, mirroring the wiring `wing-commander-8-watchdog.yml` already has for the same workflow name (currently wing-commander-8-watchdog.yml:58-70); gated so the published stage is only invoked when `github.event.workflow_run.conclusion == 'cancelled'`; extracts `run-id`/`conclusion` from `github.event.workflow_run` (a stage never reads `github.event.*` itself, Constitution VII) and calls `fold-cycle-guard.yml` (contracts/fold-cycle-guard.md)

**Checkpoint**: All three user stories are independently functional — a concurrency-replaced cancel is reported and recovered once automatically, while a maintainer's manual cancel of an in-progress run stays silent exactly as today.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: The gate that proves the shipped expressions actually implement every guarantee above, and the post-merge live proof FR-023 requires.

- [ ] T031 Write Gate 99 (`.github/scripts/verify-fold-queue-admission.py`) implementing the 8 fixture scenarios of contracts/gates.md (single run no contention; two overlapping runs; three overlapping runs; dispatch claim while a fold is outstanding; dispatch claim after the round empties; a `stop`-only run alongside a mutating run; `fold-cycle-guard` never-started+correlated / never-started+uncorrelated / ran-then-cancelled; the re-dispatch bound), loading the real `concurrency:`/`needs:`/`if:` expressions of `fold-turn-act`, `act`, `fold-turn-dispatch`, `dispatch-once` (`pr-conversation.yml`), `fold-turn-implement`, `implement`, `stalled` (`implement.yml`), and `fold-cycle-guard.yml`'s never-started/correlation expressions via `yaml.safe_load` + the shared `find_job` helper (`wc_shell_harness.py`) and the shared `wc_gha_expr.py` interpreter — never a restated copy (Principle VIII; FR-021)

- [ ] T032 In `verify-fold-queue-admission.py`, implement `MUTATIONS` — `mut_drop_fold_turn_needs` (strips the `fold-turn-*` prerequisite out of the downstream job's `needs:`, must fail scenarios 2/3), `mut_unconditional_dispatch` (removes the round-emptiness check from the claim expression, must fail scenarios 4/5), `mut_collapse_manual_and_replaced` (removes the correlated-entrant check from the guard's detection expression, must fail scenario 7), `mut_unbounded_redispatch` (removes the `redispatch_count` check from the guard's re-dispatch expression, must fail scenario 8) — each proven to make the gate fail against the pre-fix shape and pass against the shipped one (FR-022)

- [ ] T033 Register Gate 99 in `.github/workflows/lint-workflows.yml` immediately after Gate 98, `if: "!cancelled()"`, plus a "Gate 99 self-test" step exercising `--self-test` the way Gate 70's self-test step does (currently lint-workflows.yml:3723-3726); confirm no new `paths:` entry is needed since the existing `.github/workflows/**`/`.github/actions/**`/`.github/scripts/**` globs already cover every file this feature adds or edits (research.md D8)

- [ ] T034 [P] Update `docs/architecture.md` if its concurrency-group description needs the new ticket-admission layer noted (plan.md Project Structure)

- [ ] T035 Run `python .github/scripts/run-local-gates.py "fold-queue"` (quickstart.md Drill 1) and each of the three composites' fixture suites (quickstart.md Drill 2) and confirm all pass, per CLAUDE.md's pre-push gate requirement, before requesting review

- [ ] T036 Post-merge: execute quickstart.md Drill 3 (the reproduced two-run live scenario against the disposable e2e test repository) and Drill 4 (forcing a lost cycle, twice, to exercise the at-most-once re-dispatch bound), recording every run URL on the PR or the lifecycle issue per FR-023/SC-008

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS every user story — no job can call `wing-commander-fold-queue-admit`/`-release` before they exist.
- **User Story 1 (Phase 3)**: Depends on Foundational only. No dependency on US2 or US3.
- **User Story 2 (Phase 4)**: Depends on Foundational. `fold-turn-dispatch` (T016) needs `act` to already carry `fold-turn-act` conceptually (both edit the same run's shape) but not on US1's tasks being merged first — the two stories touch different jobs in the same file and can be sequenced by either job order without breaking each other, since `dispatch-once`'s existing `needs: [..., act]` is unchanged.
- **User Story 3 (Phase 5)**: Depends on Foundational (reads the ledger) and, functionally, on US2 existing in the shipped workflow (it watches `implement.yml` runs dispatched via US2's claim path and re-dispatches through the same path) — implement US2 first in practice, even though the two stories' files (`fold-cycle-guard.yml` and its wrapper) don't overlap with `pr-conversation.yml`/`implement.yml`.
- **Polish (Phase 6)**: Depends on all three user stories being complete — Gate 99 loads the real shipped expressions of every job they add or edit.

### Within Each User Story

- US1: T011 (new job) → T012 (wire `needs:`) → T013 (release calls) → T014 (comment) → T015 (report-fold-outcomes read path). All edit `pr-conversation.yml`; strictly sequential.
- US2: T016 (new job) and T017/T018 (new composite + its tests) can proceed in parallel; T019/T020 (wire `dispatch-once`) need T016 and T017 done first. T021 (new input) can proceed in parallel with the `pr-conversation.yml` chain; T022→T023→T024→T025 (all edit `implement.yml`) are sequential and need T021 done first.
- US3: T026 (new stage skeleton) → T027 → T028 → T029 (detection logic, same file) → T030 (wrapper, needs the stage's input names fixed by T026).

### Parallel Opportunities

- T007 and T008 (the `admit`/`release` composites) — different files, both depend only on T002–T006.
- T009 and T010 (their fixtures) — different files, once T007/T008 exist respectively.
- T017/T018 (`claim-dispatch` composite + fixtures) can run alongside T011–T015 (all of US1) and alongside T021 (`implement.yml`'s new input) — none share a file.
- T034 (docs) can run alongside T031–T033 (gate script) — different files.

---

## Parallel Example: Foundational Phase

```bash
# After T002-T006 (fold-queue-ledger.sh transforms) are complete:
Task: "Create wing-commander-fold-queue-admit/action.yml"
Task: "Create wing-commander-fold-queue-release/action.yml"

# Once each of the above lands:
Task: "Add fixtures under wing-commander-fold-queue-admit/tests/"
Task: "Add fixtures under wing-commander-fold-queue-release/tests/"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1) — this alone fixes the silent item loss, the more severe of the two defects PR #414 exposed, independent of whether the dispatch-side fix (US2) has landed.
3. **STOP and VALIDATE**: drive the two-run scenario and confirm all 11 items reach a terminal outcome with zero pending-leg cancellations (US1's own Independent Test).

### Incremental Delivery

1. Setup + Foundational → ledger and composites exist and pass their own fixtures.
2. Add User Story 1 → validate independently → the silent-loss defect is fixed even before US2/US3 ship.
3. Add User Story 2 → validate independently → the wasted/lost-cycle defect is fixed.
4. Add User Story 3 → validate independently → a lost cycle (the rare residual case research.md D6 and D7 describe) becomes visible and self-heals once.
5. Polish (Gate 99 + docs + live proof) closes out FR-020 through FR-023.

## Notes

- No task in this list removes, renames, or adds a required input to either workflow's published `workflow_call` contract (FR-019) — the only new input is `implement.yml`'s optional `fold-queue-token` (T021).
- Every job this feature adds (`fold-turn-act`, `fold-turn-dispatch`, `fold-turn-implement`, `fold-turn-release`) carries no `concurrency:` block of its own, by design (research.md D1) — do not add one during implementation even for convenience.
- `act`'s, `dispatch-once`'s, `implement`'s, and `stalled`'s existing `concurrency:` blocks are never edited by any task above — only their `needs:` lists change.
