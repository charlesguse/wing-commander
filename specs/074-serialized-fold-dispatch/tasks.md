---

description: "Task list for One Fold Queue Per PR — Concurrent Stage-9 Runs Stop Cancelling Each Other's Legs and Cycles"
---

# Tasks: One Fold Queue Per PR — Concurrent Stage-9 Runs Stop Cancelling Each Other's Legs and Cycles

**Input**: Design documents from `specs/074-serialized-fold-dispatch/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not explicitly requested as TDD; the composite-level bash fixtures and Gate 126 named in plan.md's Testing section are themselves the test surface for this feature and are included as implementation tasks.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact; line numbers cited as "currently" are against `main` at `91e23d4` (research.md's own baseline) and may drift slightly by implementation time — locate the named job/step by name, not by line number alone.

## Gate number confirmation

Confirmed against `.github/workflows/lint-workflows.yml` at this tasks-stage run: the last registered gate is **Gate 98** (`board-loop's fix, review and readiness run helpers from a pristine snapshot`). **Gate 99** was therefore locked at tasks time; main has since claimed Gate 99 (spec 059) and every number through 125, so this feature's gate was renumbered to **Gate 126** at the maintainer's merge with main, and every reference below now reads Gate 126 (plan.md's Testing note; research.md D8; contracts/gates.md).

---

## Phase 1: Setup

- [X] T001 Re-confirm immediately before opening the implementation PR that Gate 126 is still the next unclaimed gate number in `.github/workflows/lint-workflows.yml` (locked above; renumbered from 99 at the merge with main); if another feature has since claimed 126, renumber every task below and every `Gate 126` reference in the new gate script and its registration accordingly

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

- [X] T026 [US3] Create new published stage `.github/workflows/fold-cycle-guard.yml` (`workflow_call`, no agent step) with inputs `run-id` (required), `conclusion` (required), `spec-dir` (default `''`, resolved via the same `wing-commander-inspected-run-identity` composite `watchdog.yml` already uses when empty), `implement-workflow` (required), `dry-run` (default `false`, skips the real `gh workflow run` re-dispatch for quickstart/fixture use); output `action-taken` (one of `none`/`notice-only`/`notice-and-redispatch`) (contracts/fold-cycle-guard.md)

- [X] T027 [US3] In `fold-cycle-guard.yml`, implement the never-started detection: read `gh api repos/.../actions/runs/<run-id>/jobs`; if any job's `started_at` is non-null, set `action-taken: none` immediately — this is today's existing manual-cancel silence and must not be touched (FR-013); only proceed to correlation when every job's `started_at` is null (contracts/fold-cycle-guard.md)

- [X] T028 [US3] In `fold-cycle-guard.yml`, implement the correlation check: look for another run or job sharing the resolved `spec-dir`'s concurrency group whose own `started_at` falls within a short window of this run's `updated_at` (the cancellation timestamp); found → proceed toward a `notice-and-redispatch`/`notice-only` outcome; not found → `action-taken: none`, treating an unexplained pending-cancel with no positive replacement evidence the same as today's silent default rather than guessing a cause (research.md D7; FR-012/FR-013)

- [X] T029 [US3] In `fold-cycle-guard.yml`, on a positive correlation finding: read the ledger's round record for the resolved `spec-dir` keyed by `implement_run_id == run-id`; post the FR-012 notice (spec, iteration, cancelled run URL, cause = concurrency replacement) unconditionally, reusing `wing-commander-chain-stop-notice`'s posting shape; then check `redispatch_count`, which is bounded to `0` or `1` and MUST never be incremented past `1` (data-model.md): if `0`, call the same claim/enqueue path `dispatch-once` uses to re-dispatch — reusing the existing `iteration` rather than starting a fresh round — increment `redispatch_count` to `1` in that same ledger write, and name the new run in a second notice line; if already `1`, post the FR-016a line instead ("a maintainer's re-drive is the remaining step") and dispatch nothing (research.md D7; FR-016/FR-016a)

- [X] T030 [US3] Create wrapper `.github/workflows/wing-commander-9b-fold-cycle-guard.yml`: `on: workflow_run: workflows: ["Wing Commander · 5 implement"], types: [completed]`, mirroring the wiring `wing-commander-8-watchdog.yml` already has for the same workflow name (currently wing-commander-8-watchdog.yml:58-70); gated so the published stage is only invoked when `github.event.workflow_run.conclusion == 'cancelled'`; extracts `run-id`/`conclusion` from `github.event.workflow_run` (a stage never reads `github.event.*` itself, Constitution VII) and calls `fold-cycle-guard.yml` (contracts/fold-cycle-guard.md)

**Checkpoint**: All three user stories are independently functional — a concurrency-replaced cancel is reported and recovered once automatically, while a maintainer's manual cancel of an in-progress run stays silent exactly as today.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: The gate that proves the shipped expressions actually implement every guarantee above, and the post-merge live proof FR-023 requires.

- [X] T031 Write Gate 126 (`.github/scripts/verify-fold-queue-admission.py`) implementing the 8 fixture scenarios of contracts/gates.md (single run no contention; two overlapping runs; three overlapping runs; dispatch claim while a fold is outstanding; dispatch claim after the round empties; a `stop`-only run alongside a mutating run; `fold-cycle-guard` never-started+correlated / never-started+uncorrelated / ran-then-cancelled; the re-dispatch bound), loading the real `concurrency:`/`needs:`/`if:` expressions of `fold-turn-act`, `act`, `fold-turn-dispatch`, `dispatch-once` (`pr-conversation.yml`), `fold-turn-implement`, `implement`, `stalled` (`implement.yml`), and `fold-cycle-guard.yml`'s never-started/correlation expressions via `yaml.safe_load` + the shared `find_job` helper (`wc_shell_harness.py`) and the shared `wc_gha_expr.py` interpreter — never a restated copy (Principle VIII; FR-021)

- [X] T032 In `verify-fold-queue-admission.py`, implement `MUTATIONS` — `mut_drop_fold_turn_needs` (strips the `fold-turn-*` prerequisite out of the downstream job's `needs:`, must fail scenarios 2/3), `mut_unconditional_dispatch` (removes the round-emptiness check from the claim expression, must fail scenarios 4/5), `mut_collapse_manual_and_replaced` (removes the correlated-entrant check from the guard's detection expression, must fail scenario 7), `mut_unbounded_redispatch` (removes the `redispatch_count` check from the guard's re-dispatch expression, must fail scenario 8) — each proven to make the gate fail against the pre-fix shape and pass against the shipped one (FR-022)

- [X] T033 Register Gate 126 in `.github/workflows/lint-workflows.yml` immediately after Gate 98, `if: "!cancelled()"`, plus a "Gate 126 self-test" step exercising `--self-test` the way Gate 70's self-test step does (currently lint-workflows.yml:3723-3726); confirm no new `paths:` entry is needed since the existing `.github/workflows/**`/`.github/actions/**`/`.github/scripts/**` globs already cover every file this feature adds or edits (research.md D8)

- [X] T034 [P] Update `docs/architecture.md` if its concurrency-group description needs the new ticket-admission layer noted (plan.md Project Structure)

- [X] T035 Ran quickstart.md Drill 1 (`python .github/scripts/run-local-gates.py "fold-queue"` — Gate 126 PASS, 1/1) and then the whole PR-time suite CLAUDE.md's "Before pushing" section requires (`python .github/scripts/run-local-gates.py` — **149/149 passed**, 221.7s), so this feature's own gate and every gate its shipped workflow edits could have broken are green together. Drill 2's three composite fixture suites (`bash .github/actions/wing-commander-fold-queue-{admit,release,claim-dispatch}/tests/run.sh`) were **not executed in this implementation run**: this stage's command allowlist does not permit `bash` against a path under `.github/actions/`, and no gate step invokes them either (see the finding recorded with this cycle), so nothing in CI runs them today. They were instead confirmed `shellcheck`-clean alongside `fold-queue-ledger.sh` (exit 0, no findings). Gate 126 independently executes the real `claim-dispatch` transform and the real `fold-cycle-guard.yml` `decide` step under four mutations, which covers Drill 2's claim-side scenarios; the admit-side immediate-grant/queued-then-granted/stale-reclaim cases remain fixture-only and unrun until Drill 2 is executed by a session that can run them.

- [ ] T036 Post-merge: execute quickstart.md Drill 3 (the reproduced two-run live scenario against the disposable e2e test repository) and Drill 4 (forcing a lost cycle, twice, to exercise the at-most-once re-dispatch bound), recording every run URL on the PR or the lifecycle issue per FR-023/SC-008. This is a post-merge action, not a pre-merge blocker — left unchecked pending merge, which this implementation run does not perform (same convention as `specs/052-agent-credential-lifetime`'s T047).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS every user story — no job can call `wing-commander-fold-queue-admit`/`-release` before they exist.
- **User Story 1 (Phase 3)**: Depends on Foundational only. No dependency on US2 or US3.
- **User Story 2 (Phase 4)**: Depends on Foundational. `fold-turn-dispatch` (T016) needs `act` to already carry `fold-turn-act` conceptually (both edit the same run's shape) but not on US1's tasks being merged first — the two stories touch different jobs in the same file and can be sequenced by either job order without breaking each other, since `dispatch-once`'s existing `needs: [..., act]` is unchanged.
- **User Story 3 (Phase 5)**: Depends on Foundational (reads the ledger) and, functionally, on US2 existing in the shipped workflow (it watches `implement.yml` runs dispatched via US2's claim path and re-dispatches through the same path) — implement US2 first in practice, even though the two stories' files (`fold-cycle-guard.yml` and its wrapper) don't overlap with `pr-conversation.yml`/`implement.yml`.
- **Polish (Phase 6)**: Depends on all three user stories being complete — Gate 126 loads the real shipped expressions of every job they add or edit.

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
5. Polish (Gate 126 + docs + live proof) closes out FR-020 through FR-023.

## Notes

- Branch merged with main at `4b8e1fea7e50edb7a2c9503b7a620b282c9de27d` by the maintainer. Renumbered gate: this feature's Gate 99 (and its four fixture steps) is now **Gate 126** (main's Gate 99 is spec 059). In that merge, main's `dispatch-once` and `report-fold-outcomes` steps were taken whole (fold-evidence `folded-json`, `wing-commander-fold-dispatch`, the declined-dispatch notice, the #611 guard). This feature's claim-dispatch step, `record-implement-run` step, round-scoped reply and ledger-backed report read (T015) were dropped until T043 rewires them. The `fold-turn-dispatch` gate and the dispatch-ticket release were kept.
- No task in this list removes, renames, or adds a required input to either workflow's published `workflow_call` contract (FR-019) — the only new input is `implement.yml`'s optional `fold-queue-token` (T021).
- Every job this feature adds (`fold-turn-act`, `fold-turn-dispatch`, `fold-turn-implement`, `fold-turn-release`) carries no `concurrency:` block of its own, by design (research.md D1) — do not add one during implementation even for convenience.
- `act`'s, `dispatch-once`'s, `implement`'s, and `stalled`'s existing `concurrency:` blocks are never edited by any task above — only their `needs:` lists change.

---

## Phase 7: Convergence

- [X] T037 Register the three composite fixture suites this feature shipped (`.github/actions/wing-commander-fold-queue-admit/tests/run.sh`, `.../wing-commander-fold-queue-release/tests/run.sh`, `.../wing-commander-fold-queue-claim-dispatch/tests/run.sh`) as gate steps in `.github/workflows/lint-workflows.yml`, so CI and `run-local-gates.py` actually execute them — today no `run:` step anywhere names any of the three, and `run-local-gates.py` derives its list from `lint-workflows.yml`, so all three are checked in but never run and a regression in the `admit`/`release` composites' shell fails no check. Follow the shape the repository already uses for exactly this kind of suite: `- run: bash .github/scripts/size-path-backstop-tests/run-tests.sh` (`lint-workflows.yml:3923`) and `- run: bash .github/scripts/dispatch-and-wait-tests/run-tests.sh` (`:3978`). Also correct each suite's header comment, which currently cites `size-path-backstop-tests` as precedent for *not* being discovered by `run-local-gates.py` when that suite is in fact a registered gate step — the precedent it names contradicts the conclusion it draws. Per FR-021 (partial). Done for the CI half: all three now have `if: "!cancelled()"` steps directly under Gate 126 in `lint-workflows.yml`, immediately verified clean with `actionlint`, so every PR now runs them. The `run-local-gates.py` half of this task's own premise turned out to be false and was not silently forced through: `wc_gate_registry.gate_scripts()` only globs `.github/scripts/verify-*.{py,sh}` and `.github/scripts/*/run-tests.sh`, never `.github/actions/**/tests/run.sh`, so a plain `run:` step is not sufficient — confirmed by running `python3 .github/scripts/run-local-gates.py "fold-queue"` after wiring, which still executes only `verify-fold-queue-admission.py` (1/1), not the three composite suites. Making the local mirror actually cover them needs a scope change to `wc_gate_registry.py`'s directory convention, which is a design decision (affects `verify-gate-wiring.py`'s forward/reverse checks repo-wide) rather than a mechanical registration step, so it was left undone here and reported as a finding rather than bundled into this task silently. Each suite's header comment was corrected to state this accurately instead of the wrong size-path-backstop-tests precedent.

---

## Phase 8: Convergence

- [X] T038 In `.github/workflows/fold-cycle-guard.yml`'s `react` step, the automatic re-dispatch (`gh workflow run "$IMPLEMENT_WORKFLOW" -f spec_dir=... -f issue=... -f iteration=...`, currently line ~455) omits `-f fold_queue_token=...`, and the `claim-redispatch` transform in `fold-queue-ledger.sh` (currently lines 461-470) only flips `rounds[round].redispatch_count` from 0 to 1 — unlike `claim-dispatch`, it never enqueues a fresh `implement`-kind ticket in that same write. The recovered implement cycle therefore joins `implement.yml`'s concurrency group with no fold-queue ticket at all: `fold-turn-implement` treats an empty `fold-queue-token` as the standalone no-op case (T022), so the very cycle FR-016 exists to recover runs unserialized and is itself exposed to a second, unticketed concurrency eviction — with `redispatch_count` already at 1, FR-016a's bound then silently forecloses any further automatic recovery even though this recovery attempt was never actually admitted through the ledger. Extend `claim-redispatch` (or add a paired enqueue call inside the same atomic write the claim performs) to also enqueue a fresh `implement`-kind ticket for the resolved `spec-dir` when `should-redispatch` is `true`, returning its token as a new `implement-token` output field (mirroring `claim-dispatch`'s shape), and thread that token onto the `react` step's `gh workflow run` call as `-f fold_queue_token="$IMPLEMENT_TOKEN"`, matching `dispatch-once`'s own T019 pattern (`pr-conversation.yml:3001-3002`) exactly. Update Gate 126 and this composite's own fixtures to cover the winning-claim case asserting the enqueue and the token now happen together. Per FR-016; contracts/fold-cycle-guard.md step 5 ("calls the same claim/enqueue path `dispatch-once` uses")

  Done: `claim-redispatch` (`fold-queue-ledger.sh`) now takes a required `RUN_ID` and, in the same atomic write that flips `redispatch_count` 0→1, appends a fresh `{"token": "run-<RUN_ID>-implement", "kind": "implement", ...}` ticket to the queue (granted immediately if it lands alone at head) and returns `implement-token` — idempotent under a retry with the same `RUN_ID` (checked by token existence before the `redispatch_count` gate, so a repeated call returns the same token again rather than losing the race to its own prior effect). The generic `wing-commander-fold-queue-ledger` composite gained a `run-id` input (default `${{ github.run_id }}`, mirroring `wing-commander-fold-queue-admit`'s own convention) wired to `RUN_ID`. `fold-cycle-guard.yml`'s `react` step now reads `implement-token` out of the `claim` step's output and passes `-f fold_queue_token="$implement_token"` on the re-dispatch `gh workflow run` call. Gate 126 gained scenario 9 (`scenario_redispatch_claim_enqueues_ticket`): runs the real `claim-redispatch` transform against a throwaway bare-repo ledger, asserts the returned `implement-token` is actually enqueued and granted (via `peek`), and asserts `react`'s `run:` text contains the `-f fold_queue_token="$implement_token"` thread — plus two new MUTATIONS (`mut_redispatch_no_enqueue`, `mut_drop_redispatch_token_thread`), both proven to fail scenario 9. A new composite-level fixture suite `wing-commander-fold-queue-ledger/tests/run.sh` (winning claim + enqueue-is-granted + same-run_id idempotency + bound-already-spent) was registered as a Gate 126 fixture step in `lint-workflows.yml` alongside the other three, `shellcheck`-clean; per the same command-allowlist limitation T035 recorded, it was not executed directly in this run (only `python .github/scripts/run-local-gates.py "fold-queue"` — Gate 126 PASS, 9 scenarios/6 mutations, 1/1 — and the whole PR-time suite, 149/149, were run). `actionlint`/`shellcheck` on every touched workflow and shell file showed only pre-existing, unrelated warnings.

---

## Phase 9: Convergence

- [ ] T039 Fix `wing-commander-fold-queue-admit`'s stale-reclaim liveness check for an `implement`-kind head ticket, which checks the liveness of the wrong run and can reclaim a ticket still held by an actively-running implement cycle. The check (`action.yml`'s "Enqueue (or resolve existing token) and await this run's turn" step, the `gh api repos/.../actions/runs/${head_run_id}` call guarding `reclaim-stale`) reads `head_run_id` from `peek`'s `head-run-id` output, which is `fold-queue-ledger.sh`'s `queue[0].run_id`. For an `act`- or `dispatch`-kind ticket that field is the ticket's own owning run (correct — research.md D6's stated design: "queries ... for the head ticket's owning run"). For an `implement`-kind ticket it is NOT: both `claim-dispatch` (`fold-queue-ledger.sh:426-429`, `"run_id": $run_id` where `$run_id` is the dispatch ticket's own run — i.e. the DISPATCHING run, `dispatch-once`) and `claim-redispatch` (`:477-484`, `$run_id` is `fold-cycle-guard`'s own run) stamp the new implement-kind ticket with a proxy run's id, never the actual `implement.yml` run that will hold it — documented explicitly as intentional at `fold-queue-ledger.sh:96-100` ("the implement-kind ticket's `run_id` field ... carries the DISPATCHING run's id"). Because the dispatching/guard run completes within seconds of enqueuing the ticket, once a granted implement-kind ticket has sat at queue head for >= `stale-after-minutes` (default 10 — routinely exceeded by a real implement cycle; this very feature's own cycle 4 took well over 10 minutes) while a later round's ticket is polling behind it, that waiter's liveness check sees the long-finished dispatching/guard run reporting `status: completed` and calls `reclaim-stale` on a ticket whose actual holder (the implement job) is still running — reopening the exact multi-pending-contender eviction FR-008 ("A dispatched implement run MUST NOT be cancelled by the later queuing of any job belonging to a stage-9 run on the same PR") and FR-002 exist to remove, since the later ticket can now be granted and attempt entry into the still-occupied `wing-commander-<spec-dir>` GitHub concurrency group. Fix by having the stale-reclaim check, when the head ticket's `kind` is `implement`, resolve and check liveness of the round's own `implement_run_id` (already recorded by `record-implement-run`, called from `pr-conversation.yml`'s "Record this round's dispatched implement run" step) instead of the ticket's `run_id` — e.g. extend a ledger read (`peek-round` or a new peek mode) to expose `implement_run_id` for the ticket's round, and treat an unrecorded (`null`) `implement_run_id` as "not yet confirmed running, do not reclaim" rather than falling back to the wrong id. Add a fixture proving a long-granted implement-kind ticket whose correlated `implement_run_id` run is still `in_progress` is NOT reclaimed, and one proving it IS reclaimed once that run is `completed`/absent. Per FR-008 (contradicts); research.md D6 (the shipped mechanism does not match its own stated design intent for this one ticket kind)

## Maintainer Feedback

- [ ] T040 Amend `specs/074-serialized-fold-dispatch/spec.md` to the maintainer's reconciliation with spec 075 (option 1). Record it under Clarifications as "### Session 2026-09-29 (maintainer, reconciling with spec 075)". Rewrite FR-009 and FR-011, User Story 2 (including acceptance scenario 5) and SC-003 to this rule: (1) a stage-9 run with no folds of its own never claims the round's dispatch; it posts spec 075's declined-dispatch notice (075 FR-015); (2) a run with folds of its own that finds another run's `act` ticket still queued re-queues its dispatch ticket behind it instead of stepping aside; (3) the last run with folds dispatches exactly one implement cycle for the round, and its reply lists every run's folds in the round (its own plus the others'), each attributed to its run through the ledger's `run_id`; (4) spec 075 FR-014 ("no own folds, no dispatch") is preserved unchanged; (5) spec 075's run-only fold list is relaxed to the round's folds only in the dispatching run's own reply. Every other run's reply and every `report-fold-outcomes` report stays run-scoped. Update `data-model.md`'s Round entity and ticket lifecycle and `contracts/fold-queue-ledger-schema.md` to match, including the new re-queue transition.
- [ ] T041 Rework the `claim-dispatch` transform in `.github/actions/_shared/fold-queue-ledger.sh` (and `wing-commander-fold-queue-claim-dispatch`'s inputs and outputs) to T040's rule. Add a caller-supplied `own-folds` count (from `wing-commander-fold-evidence`'s `folded-json`). With zero own folds, return `should-dispatch: false` plus a `declined` outcome and never set `dispatch_claimed_by`. With own folds and another `act`-kind ticket still in the queue, move the calling dispatch ticket behind the last such ticket in the same atomic write (a `requeued` outcome, so the caller keeps awaiting it through `admit`'s `existing-token`) rather than resolving `false`. With own folds and no `act` ticket left, claim as today, return the round's `folded-items` attributed per `run_id`, and enqueue the `implement` ticket. The transform must stay idempotent under retry and must never deadlock (FR-018): the re-queued ticket only ever moves behind tickets that do not wait on it. Update the composite's bash fixtures under `tests/run.sh` accordingly.
- [ ] T042 Rework Gate 126 (`.github/scripts/verify-fold-queue-admission.py`) scenarios 4–5 to the reworked `claim-dispatch`. Add three scenarios, run against the real transform on the local bare-repo fixture: (a) a run with no folds declines while an earlier folding run re-queues behind the no-fold run's `act` ticket and later dispatches; (b) two folding runs produce exactly one dispatch whose `folded-items` list both runs' folds, each with its own `run_id`; (c) a run with no folds never wins the claim, in any queue order. Give each one a `--self-test` mutation that it catches: re-queue replaced by a step-aside, the own-folds check dropped, and the round list narrowed to the claimant's own folds. Update `contracts/gates.md`.
- [ ] T043 In `.github/workflows/pr-conversation.yml`'s `dispatch-once`, wire the reworked claim on top of main's `wing-commander-fold-dispatch` composite without a second copy of the dispatch logic. The claim runs after `Compute this run's fold evidence` and passes the own-fold count. A `declined` result reaches the existing FR-015 notice branch. A `requeued` result awaits the same ticket again through `wing-commander-fold-queue-admit` with `existing-token` and claims again. Only a winning claim calls `wing-commander-fold-dispatch`. If `wing-commander-fold-dispatch` has no such inputs yet, extend it additively (optional inputs whose defaults preserve every other caller's behaviour): it takes the round's attributed fold list for the reply and a `fold-queue-token` to forward as `-f fold_queue_token=`. Restore the `Record this round's dispatched implement run` ledger step keyed on the composite's `run-url`, which `fold-cycle-guard.yml` relies on. Keep the #611 guard, the declined-dispatch notice, the standalone path and the final dispatch-ticket release unchanged. Adjust Gate 34 (`verify-fold-dispatch-once.py`) only where the claim changes a scenario's expected shape, and re-run `python .github/scripts/run-local-gates.py`.
- [ ] T044 Update `specs/074-serialized-fold-dispatch/contracts/wing-commander-fold-queue-claim-dispatch.md`, `contracts/workflow-changes.md`, `contracts/fold-cycle-guard.md` (the re-dispatch reuses the same claim path) and `quickstart.md`. Cover the declined, re-queued and winning claim outcomes, the own-folds input, the round-attributed reply list, and a Drill 3 variant: a folding run, then a no-fold run, ending in one dispatch that lists the first run's folds plus the no-fold run's declined notice.
