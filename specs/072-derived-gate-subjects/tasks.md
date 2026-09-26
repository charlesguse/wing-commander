---

description: "Task list template for feature implementation"
---

# Tasks: Gate 68 Derives Its Own Subjects

**Input**: Design documents from `/specs/072-derived-gate-subjects/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/gate-68-subject-derivation.md, quickstart.md (all present)

**Tests**: Not requested. This gate's own `--self-test` mode (mutation-based, over the real shipped trees) is this feature's test mechanism, and it is itself part of the required implementation — every self-test task below is load-bearing, not optional coverage.

**Organization**: Tasks are grouped by user story (spec.md's US1/US2/US3) for traceability. **They are not independently deployable in this repository's current state** — see "Implementation Strategy" at the end before starting: the moment T006 wires structural derivation into `scan()`, the gate begins deriving `board-loop.yml`/`cleanup.yml`/`rebase.yml`/`watchdog.yml` as subjects and will fail against them until US3's exclusion record and workflow adoptions land. All phases must reach the working tree together, in one PR, before `run-local-gates.py` is green again. "Independent test" below means a scratch/local verification (quickstart.md steps 4-6), never a partial merge.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact; line numbers are approximate anchors (2026-09-26 shipped tree) to speed navigation, not a guarantee against drift — locate the named step by its `name:`/`id:` when a line number has moved.

## Path Conventions

Every task in this feature touches one of exactly four files:
- `.github/scripts/verify-post-agent-credential-refresh.py` — Gate 68 itself
- `.github/workflows/board-loop.yml`, `.github/workflows/cleanup.yml`, `.github/workflows/rebase.yml` — the three workflows that gain real contract steps
- `.github/workflows/lint-workflows.yml` — one comment-block update

No new directory, no new dependency, no test framework beyond the gate's own `--self-test`.

---

## Phase 1: Setup

**Purpose**: Establish the pre-change baseline this feature's SC-006 is measured against.

- [X] T001 Run `python .github/scripts/run-local-gates.py` from the repository root on the current shipped tree and confirm it passes. Record the result — this is the "before" half of SC-006, paired with T032's "after" run.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The glob-based, structural derivation primitives every later phase dispatches through. No user story is testable until this phase is done.

**⚠️ CRITICAL**: No US1/US2/US3 work can begin until this phase is complete.

- [X] T002 In `.github/scripts/verify-post-agent-credential-refresh.py`, add `import glob` and rewrite `load_all(root=".")` to glob `os.path.join(root, ".github/workflows/*.yml")` (34 files today, not just the 8 keyed by the old `SUBJECTS` dict) into `{repo_relative_path: parsed_yaml_or_sentinel}`. Wrap each file's `yaml.safe_load` call in a `try/except yaml.YAMLError` (and a missing-file check, as today) so an unreadable or unparseable file is recorded with a distinct sentinel value (e.g. the string `"PARSE_ERROR"`, distinguishable from `None` for "missing") rather than raising or silently contributing nothing (FR-006, D1).

- [X] T003 In the same file, add a pure function `derive_subjects(loaded)` that, given `load_all()`'s output (no re-globbing, no disk I/O of its own — this is what lets `self_test()` mutate `loaded` in memory), returns `(derived_subjects: set[(path, job_name)], parse_failures: list[str])`: for every `(path, wf)` in `loaded` where `wf` is not the missing/parse-error sentinel, for every `(job_name, job)` in `(wf.get("jobs") or {}).items()`, add `(path, job_name)` to `derived_subjects` when `job.get("steps")` contains at least one step matching the existing `_is_agent_step` check, unchanged (FR-002, FR-008, D1, D2 — reuse `AGENT_ACTION_RE`/`_is_agent_step` as-is; a job whose `jobs.<name>` has no `steps` key at all, e.g. every `wing-commander-*.yml` wrapper's `workflow_call` jobs, contributes nothing and raises nothing). For every `path` whose value is the missing/parse-error sentinel, append a message naming that file to `parse_failures` (FR-006).

- [X] T004 Rename the `SUBJECTS` module constant to `SUBJECT_FLOOR` throughout `.github/scripts/verify-post-agent-credential-refresh.py` (the constant itself, its own comment, and every reference in `load_all`, `scan`, and the self-test scaffolding) — pure rename, same 9-entry content, no behavior change yet (D3). New entries land in T026.

- [X] T005 In the same file, add a new module-level constant directly below `SUBJECT_FLOOR`: `EXCLUSIONS: Dict[Tuple[str, str], str] = {}`, with a comment stating its purpose — an explicit, checked-in record of derived subjects deliberately not held to the post-agent credential contract, keyed by `(path, job_name)`, mapping to the one-line reason (FR-012, FR-013, D4). Left empty here; populated in T017.

---

## Phase 3: User Story 1 - A new agent-bearing job is checked the day it ships (Priority: P1)

**Goal**: Subject selection comes from structural derivation over every workflow file, never from a hand-typed list — so a job added later is inspected with zero edits to the gate.

**Independent Test**: quickstart.md step 4 (scratch copy, duplicate a covered job, strip its post-agent re-mint, confirm the gate fails naming it with no gate-script edit; restore and confirm it passes) — deferred to T033 once the whole feature has landed, since before US3 lands the gate also fails on the real, not-yet-adopted `board-loop.yml`/`cleanup.yml`/`rebase.yml`/`watchdog.yml` jobs (expected, interim state).

- [X] T006 [US1] Rewrite `scan()` in `.github/scripts/verify-post-agent-credential-refresh.py` to call `derived_subjects, parse_failures = derive_subjects(loaded)` instead of iterating a hand-typed `subjects` dict; append a failure naming each file in `parse_failures`; for every `(path, job_name)` in `derived_subjects`, resolve `loaded[path]["jobs"][job_name]` and dispatch to `check_job(path, job_name, job)` exactly as today. Keep the existing `stall_reason_jobs` parameter and its loop untouched (FR-015/D7 — out of scope for this feature). Drop the old hand-typed `subjects` parameter's role as a selector entirely (FR-001, FR-003).

- [X] T007 [US1] Add a new self-test mutation `mut_agent_step_reference_respelled(loaded)` to `SIMPLE_MUTATIONS`: respell one real agent step's `uses:` to a reference `AGENT_ACTION_RE`'s prefix match does not match (e.g. `anthropics/claude-code-action-v2@v1`), on a job distinct from the one `mut_job_loses_agent_step` already targets (that one uses `clarify.yml`'s `clarify` job — use e.g. `plan.yml`'s `plan` job or `intake.yml`'s `intake` job instead, so the two mutations don't exercise the identical fixture). Assert (via `self_test()`'s existing pattern) that `scan()` then fails via T009's floor-coverage branch, since the respelled job silently drops out of `derived_subjects` (FR-009's third named minimum, D8).

---

## Phase 4: User Story 2 - A subject that disappears fails loudly (Priority: P1)

**Goal**: A checked-in floor (`SUBJECT_FLOOR`) that the derived set must cover; losing a floor member, or deriving nothing at all, fails the gate loudly instead of passing over a shrunk world.

**Independent Test**: quickstart.md step 5 (scratch copy, strip a floored job's agent step, confirm the gate fails naming it as no longer reachable; restore and confirm it passes) — deferred to T033 for the same reason as US1's.

- [X] T008 [US2] Give `scan()` (from T006) a `floor` parameter (default `SUBJECT_FLOOR`); flatten it to `set[(path, job_name)]` and implement FR-004: any floor member absent from `derived_subjects` appends a failure naming that `(path, job_name)` as no longer reachable by derivation; a `derived_subjects` member absent from the floor is inspected exactly like any other subject and never fails for that reason alone (FR-004's second bullet — this is what makes an un-updated floor fail *safe*, not shrink-and-pass).

- [X] T009 [US2] In the same `scan()`, replace the existing `if total_agent_steps == 0` check with the FR-005 empty-derivation check: if `derived_subjects` is empty — whichever reason (empty `loaded`, every file parsing to zero agent steps, or T003's derivation step itself unreachable) — append a failure that the gate is misconfigured/cannot reach its subject, never a vacuous pass.

- [X] T010 [US2] In `self_test()`, rewire the loop currently keyed to `SUBJECT_MUTATIONS`/`copy.deepcopy(SUBJECTS)` to operate on `(mutated_loaded, mutated_floor)` where `mutated_floor = copy.deepcopy(SUBJECT_FLOOR)`, asserting via `scan(mutated_loaded, floor=mutated_floor)` (T008's new parameter). Keep the `SUBJECT_MUTATIONS` list name (its *entries* change in T011-T013, not its shape as "a list of (label, mutation-fn) pairs").

- [X] T011 [US2] Replace `mut_nonexistent_ninth_file` with `mut_floor_names_nonexistent_file(loaded_and_floor)`: add a `(path, job)` pair naming a nonexistent workflow file to the mutated floor; assert `scan()` fails naming that pair via T008's floor-coverage check (D8's first retired-mutation row — same assertion, the map being mutated is now `SUBJECT_FLOOR`, not a selection dict).

- [X] T012 [US2] Replace `mut_nonexistent_job_in_existing_file` with `mut_floor_names_nonexistent_job(loaded_and_floor)`: add `(existing path, nonexistent job)` to the mutated floor; assert the same floor-coverage failure (D8's third retired-mutation row).

- [X] T013 [US2] Replace `mut_zero_files` with `mut_derivation_yields_zero_subjects(loaded_and_floor)`: empty the mutated `loaded` dict entirely (simulating the glob step finding nothing); assert `scan()` reports T009's "misconfigured, zero subjects" failure (D8's second retired-mutation row — this mutation also satisfies FR-009's "derived set emptied" minimum directly, so it is not a fourth, separate mutation).

- [X] T014 [US2] Update `mut_job_loses_agent_step`'s docstring/comment only (no code change — same fixture, same failing outcome): note that under derivation this mutation now fails via T008's floor-comparison branch (the job silently drops out of `derived_subjects` while `SUBJECT_FLOOR` still names it), not the old per-job "expected an agent step, found none" branch (FR-010, D8's closing paragraph).

**Checkpoint**: Foundational + US1 + US2 give the gate a fully self-defending selection mechanism. It will currently fail on the shipped tree (board-loop.yml/cleanup.yml/rebase.yml/watchdog.yml are now derived subjects with no contract or exclusion) — expected until US3 lands.

---

## Phase 5: User Story 3 - Every agent-bearing job is covered or recorded with a reason (Priority: P2)

**Goal**: The four workflows derivation newly surfaces each end this feature either passing the full checks or excluded with a checked-in reason — never a third, silent state.

**Independent Test**: quickstart.md step 6 (for each of the four workflows, confirm every derived job prints as either `excluded: <reason>` or `excluded: no (inspected)`, and the clean run passes) — deferred to T033.

- [X] T015 [US3] Give `check_job()` a new `excluded: Optional[str] = None` parameter in `.github/scripts/verify-post-agent-credential-refresh.py`: when set, skip checks 1 (stale reference), 2 (re-mint), 6 (per-agent-step composites), and 9 (pre-agent shadow relay); still run checks 3 (tolerance) and 7 (failed-post-agent-step, only when `(path, job_name)` is also present in `FAILED_STEP_REQUIRED_JOBS`) unconditionally — mirror `AGENTLESS_JOBS`'s existing treatment of `tasks-approved` (D4, contract's "Exclusion completeness").

- [X] T016 [US3] In `scan()` (from T006/T008/T009), for every `(path, job_name)` in `derived_subjects`: when it's a key of `EXCLUSIONS`, call `check_job(path, job_name, job, excluded=EXCLUSIONS[(path, job_name)])`; otherwise call it as before. A derived subject that is neither excluded nor passing its (non-excluded) checks fails under its ordinary failure messages — no new failure class (FR-012, FR-013).

- [X] T017 [US3] Populate `EXCLUSIONS` (from T005) with its one ship-time entry: `(".github/workflows/watchdog.yml", "diagnose"): "agent step carries timeout-minutes: 10, an order of magnitude under the credential's one-hour lifetime (same basis as spec 052's auto-update-spec-kit.yml exclusions)"` (FR-014, D5/D6). `watchdog.yml` itself needs no file change — the `Diagnose` step's `timeout-minutes: 10` (`.github/workflows/watchdog.yml:2290`) is the basis, recorded here only.

- [X] T018 [P] [US3] In `.github/workflows/board-loop.yml`, add a `wing-commander-agent-ran-signal` call to the `triage` job's `Triage-propose` agent-step window (after its existing `Re-establish Wing Commander context (post-agent, triage-propose)` / `Determine post-agent credential status (triage-propose)` pair, ~line 1043-1055) and the `route` job's `Route-propose` window (~line 1375-1387, same relative position). Name them `Record agent-ran signal (triage-propose)` / `Record agent-ran signal (route-propose)`, `uses: ./.github/actions/wing-commander-agent-ran-signal`, `with: agent-outcome: ${{ steps.<agent-step-id>.outcome }}` (the agent steps are `id: ` — check each job's `Triage-propose`/`Route-propose` step for its exact id), gated `if: "!cancelled() && steps.<agent-step-id>.outcome != 'skipped'"` — matching this file's own existing per-agent-step-suffix naming convention (D5).

- [X] T019 [US3] In the same file, add the equivalent `wing-commander-agent-ran-signal` call to the `fix` job's `Fixer` window (~line 1895-1915, alongside its existing `Refresh authenticated remote (post-agent, fixer)` / `Determine post-agent credential status (fixer)` pair): `Record agent-ran signal (fixer)`.

- [X] T020 [US3] In the same file, add the equivalent `wing-commander-agent-ran-signal` call to BOTH of the `review` job's agent-step windows: `Reviewer`'s (~line 2433-2445, `Record agent-ran signal (reviewer)`) and `Review-fixup`'s (~line 3029-3045, `Record agent-ran signal (review-fixup)`). While doing this, run the gate's self-test (T031) and check whether `Reviewer`'s own window also needs its own `wing-commander-refresh-remote` call: as read on the shipped tree (2026-09-26), only `Review-fixup`'s window calls `wing-commander-refresh-remote` (`.github/workflows/board-loop.yml:3038`) — `Reviewer`'s window has none. This contradicts research.md D5's claim that refresh-remote already "follows each" agent step in this job (see the reported finding in this run's `wing-commander-findings` block). Since `Review-fixup` genuinely pushes a branch, `review` should NOT be added to `NO_REMOTE_REFRESH_JOBS` wholesale — if check 6 (position-based, per-agent-step-window) then requires `Reviewer`'s own window to carry a `wing-commander-refresh-remote` call too, add one there (`with: token: ${{ env.WC_BOT_TOKEN }}`, matching the `fix` job's own call shape) rather than suppressing the check.

- [X] T021 [US3] In `.github/scripts/verify-post-agent-credential-refresh.py`, add two entries to `NO_REMOTE_REFRESH_JOBS`: `(".github/workflows/board-loop.yml", "triage")` and `(".github/workflows/board-loop.yml", "route")` (neither job ever pushes a branch — D5/D7), each with this map's existing one-line reason-comment convention.

- [X] T022 [P] [US3] In `.github/workflows/cleanup.yml`'s `teardown-done` job, add the full post-agent credential contract immediately after the existing `Completion summary` agent step (`id: summarize`, `continue-on-error: true`, ~line 687-733): a re-mint (`uses: ./.wing-commander-pipeline/.github/actions/wing-commander-context`, `continue-on-error: true`, gated `if: "!cancelled() && steps.summarize.outcome != 'skipped'"`, same `app-id`/`private-key` inputs the job's existing `Wing Commander context` step, `id: ctx`, already uses); `wing-commander-refresh-remote` (`with: token: ${{ env.WC_BOT_TOKEN }}`, `continue-on-error: true`, named `Refresh authenticated spec-branch remote (post-agent)` to match `SINGLE_HOME_STEPS`'s recognized name); `wing-commander-agent-ran-signal` (`with: agent-outcome: ${{ steps.summarize.outcome }}`); and `wing-commander-post-agent-credential-status` (`with: mint-outcome:` the re-mint step's outcome, `refresh-outcome:` the refresh-remote step's outcome) — gate each the same way this job's existing post-agent steps already are.

- [X] T023 [US3] In the same job, switch every post-agent credential reference currently reading `steps.ctx.outputs.token` to `env.WC_BOT_TOKEN`: the `Report over-budget agent run` step's `token:` (~line 826), `Close lifecycle issue and flip label`'s `GH_TOKEN:` (~line 863), and `Report incomplete teardown on the lifecycle issue`'s `GH_TOKEN: ${{ steps.ctx.outputs.token || github.token }}` (~line 941 — keep the `github.token` fallback, switch only the first alternative). Leave every PRE-agent reference (`Resolve spec identity`, `Require the merge commit`, `Verify spec artifacts and resolve lifecycle issue`, `Idempotency check`, the pre-summary checkouts) unchanged — check 1 only inspects steps after the job's first agent step.

- [X] T024 [P] [US3] In `.github/workflows/rebase.yml`'s `rebase` job, add the same full post-agent contract immediately after the existing `Resolve conflicts` agent step (`id: agent`, `continue-on-error: true`, ~line 693-747): re-mint (`./.wing-commander-pipeline/.github/actions/wing-commander-context`), `wing-commander-refresh-remote` (this job persists a git-remote credential via `Checkout spec branch as wing-commander-bot`'s `token: ${{ steps.ctx.outputs.token }}` and later force-pushes in `Publish rebased branch`), `wing-commander-agent-ran-signal` (`agent-outcome: ${{ steps.agent.outcome }}`), and `wing-commander-post-agent-credential-status` — gated `if: "!cancelled() && steps.agent.outcome != 'skipped'"`, matching this job's existing `Compute agent run verdict` step's own guard (~line 754-756).

- [X] T025 [US3] In the same job, switch every post-agent credential reference reading `steps.ctx.outputs.token` to `env.WC_BOT_TOKEN`: `Report over-budget agent run`'s `token:` (~line 833), `Publish rebased branch`'s `GH_TOKEN:` (~line 951), `Abandon and escalate`'s `GH_TOKEN:` (~line 993), and `Announce the rebase escalation on the lifecycle issue`'s `token:` (~line 1056). Leave `Wing Commander context` itself and `Checkout spec branch as wing-commander-bot` unchanged (pre-agent).

- [X] T026 [US3] In `.github/scripts/verify-post-agent-credential-refresh.py`, add three entries to `SUBJECT_FLOOR` (from T004; D3/D5): `".github/workflows/board-loop.yml": ["triage", "route", "fix", "review"]`, `".github/workflows/cleanup.yml": ["teardown-done"]`, `".github/workflows/rebase.yml": ["rebase"]`. Do NOT add `watchdog.yml`'s `diagnose` — its exclusion (T017) is sufficient; the floor tracks only jobs whose disappearance would be a coverage regression (D6).

- [X] T027 [US3] Add a new self-test mutation `mut_excluded_job_removed_from_exclusions(loaded)` to `SIMPLE_MUTATIONS`: delete `EXCLUSIONS[(".github/workflows/watchdog.yml", "diagnose")]` from a mutated copy and assert `scan()` then fails — `diagnose` is now inspected under the full checks and fails immediately (no relay/refresh/signal/credential-status machinery exists in that job). Proves the exclusion record is load-bearing, not decorative (FR-013, D8).

- [X] T028 [US3] Add the FR-015 reason comments D7 specifies: a one-line comment on `STALL_REASON_JOBS` and on `FAILED_STEP_REQUIRED_JOBS` in `.github/scripts/verify-post-agent-credential-refresh.py` stating that each is "keyed to a different job than the agent-step subject derivation selects; deriving this would need its own structural rule, out of scope for this feature (spec 072 item 1)." No entries change in either map — none of `board-loop.yml`/`cleanup.yml`/`rebase.yml` has a stall/survivor job structure in this feature's scope.

- [X] T029 [US3] Add the FR-007/D9 subject report: give `scan()` a `report_subjects: bool = False` parameter that, when true, prints the sorted `derived_subjects` set (one `path [job_name]` per line, marking excluded ones per T016) to stdout alongside the existing failure lines. Update `main()`'s non-`--self-test` branch to call `scan(..., report_subjects=True)` so a plain invocation always prints the full subject set, on both a passing and a failing run — sourced from the same `scan()` call that decides pass/fail, never a second derivation pass.

- [X] T030 [US3] Rewrite the module docstring's "WHAT THIS CHECKS" preamble in `.github/scripts/verify-post-agent-credential-refresh.py` (currently "For each of the 8 sweep-stage jobs...") and `.github/workflows/lint-workflows.yml`'s Gate 68 comment block (currently naming "the 8 sweep stages") to describe the derived rule and the floor/exclusion split instead of a fixed count (FR-017).

**Checkpoint**: All three user stories complete. The gate now passes on the shipped tree with every agent-bearing job either inspected-and-passing or excluded-with-a-reason.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Confirm the success criteria against the finished tree.

- [X] T031 Run `python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test` and confirm every mutation (the pre-existing set plus T007, T011-T013, T027) reports `Mutation OK`, the total mutation count is strictly greater than the pre-feature shipped count (SC-005), and the clean tree still passes.

- [X] T032 Run `python .github/scripts/run-local-gates.py` from the repository root and confirm it passes on the post-feature tree — the "after" half of SC-006, paired with T001.

- [ ] T033 Follow quickstart.md steps 4-6 by hand (scratch/discarded edits — never committed) to confirm: SC-001 (a new stale-credential job fails with zero `verify-post-agent-credential-refresh.py` lines changed), SC-002 (removing an agent step from a floored job fails naming it), SC-003 (every job in `board-loop.yml`/`cleanup.yml`/`rebase.yml`/`watchdog.yml` prints as either excluded-with-a-reason or inspected-and-passing, never a third state), and SC-007 (the subject report from T029 names every inspected file/job without opening the script's source).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. Blocks every later phase — `derive_subjects()` (T003) is what US1/US2/US3 all dispatch through.
- **US1 (Phase 3)**: Depends on Foundational. T006 (scan rewrite) is a prerequisite for T008/T009 (US2) and T016 (US3), since they all extend the same `scan()`.
- **US2 (Phase 4)**: Depends on T006. T008 (floor parameter) is a prerequisite for T010-T013 (self-test) and is read again by nothing in US3.
- **US3 (Phase 5)**: Depends on T006, T008, T009 (scan must already dispatch derived subjects and know about the floor/empty checks before exclusion-awareness is layered on in T015/T016). The three workflow-file task groups (T018-T021 board-loop.yml, T022-T023 cleanup.yml, T024-T025 rebase.yml) are mutually independent of each other but must all land before T026 (SUBJECT_FLOOR additions) and T031/T032 (which require every derived subject to be either compliant or excluded).
- **Polish (Phase 6)**: Depends on every prior phase.

### Within This Feature

Because scan()/check_job() in `.github/scripts/verify-post-agent-credential-refresh.py` is edited incrementally across T002-T017 and T021/T026-T030, those tasks are not parallelizable against each other (same file, overlapping functions) — do them in ID order. The three workflow-file streams (T018-T020, T022-T023, T024-T025) touch different files from the script and from each other, so they can proceed in parallel with each other and with the script edits, but T026 (SUBJECT_FLOOR) should not land until the workflow files it names are actually compliant, or the gate will fail mid-implementation on its own floor check.

### Parallel Opportunities

- T018 (board-loop.yml), T022 (cleanup.yml), and T024 (rebase.yml) start three independent-file work streams and can run in parallel with each other and with the script-side Foundational/US1/US2 tasks (T002-T014).
- Within each workflow-file stream, later tasks (T019/T020 after T018; T023 after T022; T025 after T024) touch the same file and should not run concurrently with their own stream's earlier task.

## Parallel Example: Starting the three workflow-file streams

```bash
Task: "Add agent-ran-signal to board-loop.yml's triage/route windows (T018)"
Task: "Add the full post-agent contract to cleanup.yml's teardown-done job (T022)"
Task: "Add the full post-agent contract to rebase.yml's rebase job (T024)"
```

## Implementation Strategy

### Not independently shippable, despite the per-story organization

Spec.md's own Assumptions note "the derived set is expected to be a superset of today's list, never a different one" — true only once the WHOLE feature has landed. `derive_subjects()` (T003) is structural and unconditional: the instant T006 wires it into `scan()` as the selector, `board-loop.yml`, `cleanup.yml`, `rebase.yml`, and `watchdog.yml`'s agent-bearing jobs are ALL derived subjects, checked under the full credential-freshness checks, and ALL currently fail them (none has adopted the contract yet, and `EXCLUSIONS` is still empty at that point). This is expected, interim, in-progress-PR state — it is not a regression to fix mid-sequence, and `run-local-gates.py` is not expected to be green again until Phase 5 (US3) and Phase 6 are both done. Land every phase in one PR; use quickstart.md's scratch-copy method (never a partial merge) to validate each user story's acceptance scenarios along the way.

### Suggested order

1. Foundational (T002-T005) — derivation and floor/exclusion scaffolding exist but nothing yet uses them for selection.
2. US1 (T006-T007) — derivation becomes the selector. Expect `run-local-gates.py` to go red here (see above) until step 4 below.
3. US2 (T008-T014) — floor-coverage and empty-derivation failures wired in; self-test rewired to match.
4. US3 (T015-T030) — exclusion record, the three workflow files' real contract adoption, and the docstring/registry rewrite. `run-local-gates.py` returns to green only once this phase's workflow-file tasks (T018-T025) and `SUBJECT_FLOOR`/`EXCLUSIONS` content (T017, T026) are all in place.
5. Polish (T031-T033) — confirm every success criterion against the finished tree.
