# Tasks: The Last Two Agent Stages Join the Credential Sweep — rebase.yml and cleanup.yml

**Input**: Design documents from `/specs/073-rebase-cleanup-credential-refresh/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/gate-68-derived-subjects.md, quickstart.md (all present)

**Tests**: This feature's test suite is Gate 68's own `--self-test` mode (in-memory mutations of the real shipped trees, asserted to fail — no separate fixture files), per plan.md's Technical Context. Every phase below therefore includes the self-test mutations FR-012 requires alongside the workflow/gate edits, not as a separate "tests" subsection.

**Organization**: Tasks are grouped by user story (US1 = rebase.yml full mechanism, US2 = cleanup.yml wall-clock bound, US3 = no agent-bearing workflow invisible to the gate) so each can be implemented and validated independently per its own quickstart.md section.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, or US3 — omitted for Setup/Foundational/Polish tasks
- File paths are exact; line numbers cited from spec.md/research.md are approximate ("~line N") and may have drifted — locate steps by name, not by line number alone.

## Path Conventions

Single project — this repository's own GitHub Actions workflows and gate scripts. No `src/`/`tests/` split; all paths are repository-root-relative.

---

## Phase 1: Setup

**Purpose**: Establish the baseline before any edit lands.

- [X] T001 Run `python .github/scripts/run-local-gates.py` on the current tree and confirm it passes clean, so any later failure is attributable to this feature's own edits, not pre-existing drift (quickstart.md §1; CLAUDE.md "Before pushing").

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Rewrite Gate 68's subject model in `.github/scripts/verify-post-agent-credential-refresh.py` from a hand-typed `SUBJECTS` dict to a derived-set-plus-floor-plus-exemption model (research.md D2–D4, contract §§1–3). This is the shared engine all three user stories' dispositions (`full_subject` for `rebase.yml`, `exempt` for `cleanup.yml`/`watchdog.yml`/`board-loop.yml`/two `auto-update-spec-kit.yml` jobs) are computed against — no story-specific edit can be verified correctly until this lands.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 In `.github/scripts/verify-post-agent-credential-refresh.py`, rewrite `load_all()` to glob every `.github/workflows/*.yml` file (instead of reading the `SUBJECTS` dict's keys) and parse each with `yaml.safe_load`; a file that fails to parse MUST fail the gate, naming the file, rather than silently contributing zero subjects (research.md D2; contract §1).
- [X] T003 In the same file, compute `derived_subjects = {(path, job_name) for ... if any(_is_agent_step(step) for step in job.get("steps", []))}` for every job in every loaded file, reusing the existing `_is_agent_step` helper verbatim (contract §1's pseudocode) — a job qualifies on the presence of at least one agent step alone; no further reading of the job (bot-acting steps present, bound status, matrix-ness) narrows the set (research.md D2, D10).
- [X] T004 Add `SUBJECT_FLOOR: dict[str, set[str]]`, seeded with the nine pre-existing agent-bearing jobs: `intake.yml`/`intake`, `clarify.yml`/`clarify`, `plan.yml`/`plan`, `tasks.yml`/`tasks`, `implement.yml`/`implement`, `finalize.yml`/`finalize`, `pr-conversation.yml`/`classify-and-announce`, `pr-conversation.yml`/`act`, `auto-update-spec-kit.yml`/`e2e-stage` (data-model.md §2 seed content — this feature adds seven more across T021/T029/T036, for sixteen total). Delete the old `SUBJECTS` dict; `AGENTLESS_JOBS`, `STALL_REASON_JOBS`, `FAILED_STEP_REQUIRED_JOBS`, and `NO_REMOTE_REFRESH_JOBS` are unaffected by this deletion and keep their current keys (research.md D3).
- [X] T005 Assert `SUBJECT_FLOOR ⊆ derived_subjects` on every run: a floor member absent from `derived_subjects` fails the gate, naming the missing pair; a `derived_subjects` member absent from the floor MUST NOT fail for that reason alone (contract §2; data-model.md §2 invariant).
- [X] T006 Add `EXEMPT_JOBS: dict[tuple[str, str], ExemptionEntry]` (`reason: str`, `issue: tuple[int, ...]`, `condition: Callable[[dict], bool]`, per contract §3's `ExemptionEntry` shape) and compute, for every `(path, job_name)` in `derived_subjects`, exactly one disposition: `full_subject` (default), `agentless_in_scope` (existing `AGENTLESS_JOBS`, unchanged — checks 1/2 don't apply, checks 3/5 still do), or `exempt` (a key in `EXEMPT_JOBS`). A pair matching none of the three fails the gate, naming the pair (contract §3; data-model.md §1; spec 072 FR-013).
- [X] T007 For every `exempt` disposition, evaluate `condition(job)` on every run; when it returns `False`, fail the gate naming the entry's `(workflow_path, job_name)`, `reason`, and `issue` — an entry with no `condition`, or one that is always `True`, is not a valid entry (contract §3; spec.md FR-007; Constitution IX).
- [X] T008 Rewire `scan()`/`check_job()`'s entry point to iterate `derived_subjects` (dropping the `subjects=` hand-typed parameter) instead of the old `SUBJECTS`-keyed loop: gate the credential-reference check ("check 1"), the fresh-mint-follows-agent-step check ("check 2"), and the per-agent-step `REQUIRED_PER_AGENT_STEP_COMPOSITES`/credential-status-by-reference check ("check 6" in the script's own inline comments, item 7 in its docstring) behind `disposition == "full_subject"` only; keep the over-budget-tolerance check ("check 3"), the single-home-composite check ("check 5"), and the pre-agent shadow-relay check ("check 9") job-agnostic exactly as today (research.md D9; data-model.md §3 "the post-agent composite checks (1, 2, 7 in the gate's own numbering)... do not apply" to exempt jobs). Replace the old `total_agent_steps == 0` guard with "the derived set is empty" failing loudly, never passing vacuously (contract §1).
- [X] T009 [P] Rewrite the module docstring's "WHAT THIS CHECKS" and "Self-test" sections in `.github/scripts/verify-post-agent-credential-refresh.py` to describe the derived-set-plus-floor-plus-exemption model instead of "the 8 sweep-stage jobs (FR-007's list)" (research.md D-Registry; spec 072 FR-017, inherited).
- [X] T010 [P] In `.github/workflows/lint-workflows.yml`, rewrite the comment block above the "Gate 68" step (~lines 3671–3685, currently "Every agent-bearing job in the 8 sweep stages relays its mint into env.WC_BOT_TOKEN...") to describe the derived set rather than naming a fixed count of stages (research.md D-Registry).
- [X] T011 Add a self-test mutation to `.github/scripts/verify-post-agent-credential-refresh.py`: the derived set emptied (e.g. no workflow files loaded) — asserted to fail as misconfigured (contract "Self-test coverage" §1; SIMPLE_MUTATIONS-equivalent list).
- [X] T012 Add a self-test mutation: a workflow file that fails to parse (invalid YAML) — asserted to fail the gate, naming the file, rather than silently contributing zero subjects (contract §1's parse-failure requirement).
- [X] T013 Add a self-test mutation: a `SUBJECT_FLOOR` member's agent step replaced with a non-agent step (adapt the existing `mut_job_loses_agent_step` fixture against a floor job such as `clarify.yml`'s `clarify`) — asserted to fail, naming the missing pair (contract "Self-test coverage" §2; data-model.md §2 invariant).
- [X] T014 Add a self-test mutation: a synthetic agent-bearing job added to a workflow file with no `SUBJECT_FLOOR`/derivation-implied floor membership and no `EXEMPT_JOBS` entry — asserted to fail, naming that job as neither `full_subject`, `agentless_in_scope`, nor `exempt` (contract "Self-test coverage" §3; spec 072 FR-013).
- [X] T015 Run `python3 .github/scripts/verify-post-agent-credential-refresh.py` and `python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test` locally; confirm the clean tree still passes (with the same eight already-covered stages reporting `full_subject`/`agentless_in_scope` as before) and every mutation added in T011–T014 is reported as caught, before any user-story-specific workflow edit lands.

**Checkpoint**: Foundation ready — the derived-subject engine is in place and self-tested; user story implementation can now begin.

---

## Phase 3: User Story 1 - A long rebase still publishes its result (Priority: P1) 🎯 MVP

**Goal**: `rebase.yml`'s `rebase` job adopts spec 052's full post-agent mechanism, so every bot-acting step after the agent step holds a credential established after that step finished.

**Independent Test**: Confirm the publish and escalate arms act on a post-agent credential rather than the pre-agent mint, and that a failed re-establishment surfaces as a named credential failure (quickstart.md §3).

### Implementation for User Story 1

- [X] T016 [US1] In `.github/workflows/rebase.yml`'s `rebase` job, after the `Resolve conflicts` agent step (~line 693), add "Record agent-ran signal" (`wing-commander-agent-ran-signal`), "Re-establish Wing Commander context (post-agent)" (`wing-commander-context`), and "Refresh authenticated spec-branch remote (post-agent)" (`wing-commander-refresh-remote`), each guarded `if: "!cancelled() && steps.agent.outcome != 'skipped'"` matching the eight-stage precedent — `rebase.yml` is NOT added to `NO_REMOTE_REFRESH_JOBS`, since its "Checkout spec branch as wing-commander-bot" step (~line 590) persists the credential into the git remote the publish arm's force-with-lease push rides (spec.md FR-001, FR-002; research.md D5 point 1).
- [X] T017 [US1] In `.github/workflows/rebase.yml`'s `rebase` job, switch `Report over-budget agent run` (~line 833), `Publish rebased branch` (~line 951, including its `git push --force-with-lease` at ~line 955), `Abandon and escalate` (~line 993), and `Announce the rebase escalation on the lifecycle issue` (~line 1056) from `steps.ctx.outputs.token` to `env.WC_BOT_TOKEN` (or the equivalent `GH_TOKEN` env substitution) — preserve each step's existing `if:` condition byte-for-byte (`Publish rebased branch`'s `!cancelled() && (...)`, `Abandon and escalate`'s `!cancelled() && (...)`, `Announce...`'s `always() && steps.escalate.outputs.issue != ''`); do not tighten `Announce...`'s `always()` to `!cancelled()` (spec.md FR-001, FR-014; research.md D5 point 2). Depends on T016.
- [X] T018 [US1] Add `continue-on-error: true` to `rebase.yml`'s `Report over-budget agent run` step — required once Gate 68 (T008) scans every workflow file, not a credential fix in itself (research.md D5 point 3, D9).
- [X] T019 [US1] In `.github/workflows/rebase.yml`'s `rebase` job, immediately before `Abandon and escalate` (~line 993), add "Determine failed post-agent step" (`wing-commander-failed-post-agent-step`), fed the job's own hard-failing candidate steps in order; have `Abandon and escalate`'s own step read `steps.determine-failed-step.outputs.step` directly (job-local consumption — `rebase.yml` has no separate `stalled` job, so it is NOT added to `STALL_REASON_JOBS` or `FAILED_STEP_REQUIRED_JOBS`) so its escalation comment can name an expired or unrefreshed credential as the reason (spec.md FR-004; research.md D5 point 4).
- [X] T020 [US1] In `.github/workflows/rebase.yml`'s `rebase` job, add "Determine post-agent credential status" (`wing-commander-post-agent-credential-status`), positioned per the existing eight-stage call-site convention documented in `specs/052-agent-credential-lifetime/contracts/wing-commander-context-relay.md`; wire `Abandon and escalate`'s own comment to name the credential as the cause when the composite's `ok` output reports not-ok (spec.md FR-003; research.md D5 point 5). Depends on T016.
- [X] T021 [US1] In `.github/scripts/verify-post-agent-credential-refresh.py`, add `(".github/workflows/rebase.yml", "rebase")` to `SUBJECT_FLOOR` (data-model.md §2 seed content) — no `EXEMPT_JOBS` entry, since its disposition is `full_subject` once T016–T020 land.
- [X] T022 [US1] Add self-test mutations to `.github/scripts/verify-post-agent-credential-refresh.py` for `rebase.yml`'s `rebase` job: (a) `Publish rebased branch`'s credential reference reverted to `steps.ctx.outputs.token`, (b) the post-agent `wing-commander-context` call deleted, (c) the `wing-commander-refresh-remote` call deleted — each asserted to fail (spec.md FR-012; research.md D12; contract "Self-test coverage"). Depends on T016, T017, T021.
- [X] T023 [P] [US1] Update `specs/052-agent-credential-lifetime/contracts/wing-commander-context-relay.md`: add a `rebase.yml` section documenting its call-site convention (agent-ran-signal, re-establish, refresh-remote, credential-status, failed-post-agent-step composites and their placement), following the existing per-workflow subsection pattern, and correct the "consumed by all 8 sweep-stage workflows" opening line to name the derived set instead of a fixed count (spec.md FR-016; research.md D11).
- [X] T024 [P] [US1] Update `specs/052-agent-credential-lifetime/contracts/agent-ran-signal.md`'s "Not in scope for consumption" section to add `rebase.yml`: it publishes the signal (T016) but has no `wing-commander-chain-stop-notice`-pattern survivor job to consume it — its own `Abandon and escalate` arm reads `wing-commander-failed-post-agent-step`'s output directly instead (spec.md Edge Cases "rebase.yml has no separate survivor job"; plan.md Project Structure "agent-ran-signal.md gains rebase.yml's rationale if applicable").
- [X] T025 [US1] Run `python3 .github/scripts/verify-post-agent-credential-refresh.py`, `python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test`, and `grep -n "steps.ctx.outputs.token" .github/workflows/rebase.yml`; confirm no match in the `rebase` job at or after `Resolve conflicts` other than the agent step's own `with:` block, and that T022's mutations report as caught (quickstart.md §3).

**Checkpoint**: `rebase.yml`'s `rebase` job is a full Gate 68 subject; a long rebase publishes on a post-agent credential and a failed re-establishment names itself as the cause.

---

## Phase 4: User Story 2 - Teardown finishes even behind a slow summary agent (Priority: P1)

**Goal**: `cleanup.yml`'s `teardown-done` job is protected by a wall-clock bound strictly under the credential's lifetime, recorded as a mechanically-asserted exemption rather than the full post-agent mechanism.

**Independent Test**: Confirm the bound is present and asserted; confirm deleting or raising it fails the gate naming the job (quickstart.md §4).

### Implementation for User Story 2

- [X] T026 [US2] Add `timeout-minutes: 10` to `.github/workflows/cleanup.yml`'s `Completion summary` agent step (~line 691) — `cleanup.yml` MUST NOT receive the post-agent composites (spec.md FR-005; research.md D8).
- [X] T027 [US2] Add `continue-on-error: true` to `cleanup.yml`'s `Report over-budget agent run` step (~line 826) — required once Gate 68 (T008) scans every workflow file (research.md D5 point 3, D9).
- [X] T028 [US2] In `.github/scripts/verify-post-agent-credential-refresh.py`, add a wall-clock-bound condition function (`condition(job) -> bool`: the job's agent step's own `timeout-minutes`, or the job-level `timeout-minutes` if the step has none, is present and `<= 10`) and register `EXEMPT_JOBS[(".github/workflows/cleanup.yml", "teardown-done")]` with `reason` citing `#558` and this `condition` (spec.md FR-005, FR-006, FR-007; data-model.md §3 "Wall-clock bound"; contract "Entries this feature adds"). Depends on T026.
- [X] T029 [US2] Add `(".github/workflows/cleanup.yml", "teardown-done")` to `SUBJECT_FLOOR` (data-model.md §2 seed content).
- [X] T030 [US2] Add self-test mutations for `cleanup.yml`'s `teardown-done` exemption: (a) `timeout-minutes: 10` removed from `Completion summary`, (b) `timeout-minutes` raised past the credential's lifetime (e.g. to `90`) — each asserted to fail, naming `cleanup.yml`'s `teardown-done` job (spec.md FR-012, SC-004; research.md D12). Depends on T028.
- [X] T031 [US2] Run `python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test` and `grep -n -A2 "name: Completion summary" .github/workflows/cleanup.yml`; confirm `timeout-minutes: 10` is present and T030's bound-removed/bound-raised mutations both report as caught, naming `teardown-done` (quickstart.md §4).

**Checkpoint**: `cleanup.yml`'s `teardown-done` job is a recorded, mechanically-checked exemption; its agent step cannot outlive the credential.

---

## Phase 5: User Story 3 - No agent-bearing workflow is invisible to the gate (Priority: P2)

**Goal**: The two further workflows the derivation rule surfaces (`watchdog.yml`, `board-loop.yml`) get recorded exemptions on the same mechanically-checked footing as `cleanup.yml`, `auto-update-spec-kit.yml`'s two prose-only exclusions become mechanically checked, and the documentation matches the checked set.

**Independent Test**: Add an agent step to a workflow that is neither covered nor exempt and confirm the gate fails naming it (proven generically in T014); remove all subjects and confirm the gate fails loudly (proven generically in T011). This phase's own scope is the concrete exemption entries and documentation this derivation surfaces (quickstart.md §5–§6).

### Implementation for User Story 3

- [X] T032 [P] [US3] In `.github/workflows/watchdog.yml`, add an issue citation (`#558`) to the `diagnose` job's agent step's existing `timeout-minutes: 10` explanatory comment (~line 2286) — no behavioural edit; the bound already satisfies the wall-clock condition (spec.md FR-007; research.md D6).
- [X] T033 [US3] In `.github/scripts/verify-post-agent-credential-refresh.py`, register `EXEMPT_JOBS[(".github/workflows/watchdog.yml", "diagnose")]`, reusing T028's wall-clock condition function, citing `#558` (data-model.md §3; contract "Entries this feature adds"; research.md D6). Depends on T028.
- [X] T034 [US3] In `.github/scripts/verify-post-agent-credential-refresh.py`, add a composite-adoption condition function (`condition(job) -> bool`: walks each agent step's post-step window — the same by-position walk the per-agent-step composite check already performs — and asserts a `wing-commander-context` call and a `wing-commander-post-agent-credential-status` call both appear before the next agent step or the job's end, NOT `wing-commander-agent-ran-signal`, which `board-loop.yml` never adopted) and register `EXEMPT_JOBS` entries for `board-loop.yml`'s `triage`, `route`, `fix`, and `review` jobs, citing `#558` and `#410`, with `reason` noting the exemption is provisional ("for now") per spec.md's Assumptions (spec.md FR-007, FR-009; data-model.md §3 "Composite adoption"; research.md D4, D7).
- [X] T035 [US3] In `.github/scripts/verify-post-agent-credential-refresh.py`, register `EXEMPT_JOBS` entries for `auto-update-spec-kit.yml`'s `evaluate-path` and `comment-reply` jobs, reusing T028's wall-clock condition function, mechanizing spec 052's existing prose-only exclusion (spec.md FR-007; data-model.md Disposition Summary Table; contract "Entries this feature adds"). Depends on T028.
- [X] T036 [US3] Add the remaining five `SUBJECT_FLOOR` entries: `(".github/workflows/watchdog.yml", "diagnose")`, `(".github/workflows/board-loop.yml", "triage")`, `(".github/workflows/board-loop.yml", "route")`, `(".github/workflows/board-loop.yml", "fix")`, `(".github/workflows/board-loop.yml", "review")` (data-model.md §2 — the floor holds sixteen entries after T021/T029/T036). Depends on T033, T034.
- [X] T037 [US3] Add self-test mutations: (a) `watchdog.yml`'s `timeout-minutes: 10` removed from `diagnose` — asserted to fail, proving the wall-clock condition function is not hardcoded to `cleanup.yml` alone; (b) `board-loop.yml`'s exemption condition broken (one job's post-agent `wing-commander-context` call deleted) — asserted to fail naming the job, not silently keep treating it as exempt (spec.md FR-012; research.md D12). Depends on T033, T034.
- [X] T038 [US3] Add a self-test mutation: a `SUBJECT_FLOOR` member added by this feature (e.g. `board-loop.yml`'s `review` job) has its agent step replaced with a non-agent step — asserted to fail naming the dropped subject, generalizing T013's fixture to a job this feature itself adds to the floor (spec 072 FR-004/US2 restated; research.md D12).
- [X] T039 [US3] Rewrite `specs/052-agent-credential-lifetime/contracts/post-agent-credential-refresh-gate.md`'s "Subject" section (today: "the 8 workflow files FR-007 names") to describe the derivation rule, the floor, and the full exemption table — `rebase.yml`, `cleanup.yml`, `watchdog.yml`, `board-loop.yml`'s four jobs, and `auto-update-spec-kit.yml`'s two mechanized exclusions — so the documented set and the checked set are the same set (spec.md FR-016; research.md D11).
- [X] T040 [US3] Run `python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test` and `grep -n "rebase.yml\|cleanup.yml\|watchdog.yml\|board-loop.yml" specs/052-agent-credential-lifetime/contracts/post-agent-credential-refresh-gate.md specs/052-agent-credential-lifetime/contracts/wing-commander-context-relay.md`; confirm T037/T038's mutations report as caught and both documents name all four workflows and their dispositions (quickstart.md §5–§6).

**Checkpoint**: Every agent-bearing job in the repository is a Gate 68 full subject or a recorded, mechanically-checked exemption; the documentation matches the checked set.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: The repository-wide acceptance bar and the review pass this class of change requires.

- [X] T041 [P] Run `python .github/scripts/run-local-gates.py` (the full local PR-time gate suite) and confirm every gate, including Gate 68, its self-test, and Gate 69, passes clean (quickstart.md §1; CLAUDE.md "Before pushing").
- [X] T042 Get a pass from the `review-step-gating` skill on this change, since it adds `if:` guards and a `continue-on-error:` step in `rebase.yml` and `cleanup.yml` (research.md D13; CLAUDE.md: "A change that touches any `if:`, `continue-on-error:`, or failing step in a workflow should also get a pass from the `review-step-gating` skill"). Fix any findings in the same PR.
- [ ] T043 After this feature's implementation PR merges, re-drive one real run of `rebase.yml` on a branch with a genuine conflict (so the agent step actually executes) and one real run of `cleanup.yml` to `teardown-done` on a normal teardown, via `gh workflow run` on the wrapper that can dispatch each; record on the PR or lifecycle issue #558 that the publish/escalate arm completed on a post-agent credential and that both runs' outcomes, comments, labels, and artifacts are unchanged from before this feature (quickstart.md §7; SC-007; CLAUDE.md "Working the issue board" prove step).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user stories — every story's disposition (`full_subject`/`exempt`) is computed by the engine T002–T015 build.
- **User Stories (Phase 3–5)**: All depend on Foundational completion.
  - US1 (T016–T025) and US2 (T026–T031) touch disjoint files (`rebase.yml` vs. `cleanup.yml`) and disjoint `EXEMPT_JOBS`/`SUBJECT_FLOOR` entries — they may proceed in parallel once Foundational is done, or sequentially in priority order (both are P1).
  - US3 (T032–T040) reuses T028's wall-clock condition function (T033, T035 depend on it) and therefore should follow US2; it also documents the full derived set (T039), which reads most naturally after US1 and US2 have landed their own entries.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Each User Story

- Workflow edits before the gate script's `EXEMPT_JOBS`/`SUBJECT_FLOOR` entries that assert them.
- Gate script entries before the self-test mutations that exercise them.
- Contract documentation last, once the behaviour it documents has landed.
- Each story's own checkpoint task (T025, T031, T040) runs last within that story.

### Parallel Opportunities

- T009 (gate docstring) and T010 (lint-workflows.yml comment) touch different files and can run in parallel within Foundational.
- Once Foundational (Phase 2) is done, US1 and US2 can proceed in parallel — they touch `rebase.yml`/`cleanup.yml` respectively and disjoint dict entries in the shared gate script (coordinate on that one shared file to avoid conflicting edits, or serialize the two dict-entry tasks T021/T028 relative to each other even while the workflow-file edits run in parallel).
- T023 and T024 (two different contract documents) can run in parallel within US1.
- T032 (watchdog.yml comment) can run in parallel with anything in US1/US2, since it touches neither's files.

---

## Parallel Example: User Story 1

```bash
# T023 and T024 touch different contract documents and can run together
# once T016-T020's workflow edits have landed:
Task: "Add a rebase.yml section to contracts/wing-commander-context-relay.md"
Task: "Add rebase.yml to contracts/agent-ran-signal.md's Not in scope section"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks every story).
3. Complete Phase 3: User Story 1 (`rebase.yml`) — this is the stage with the measured exposure (a 25-minute agent run already observed, no ceiling short of the 360-minute workflow default).
4. **STOP and VALIDATE**: run T025's checkpoint independently.

### Incremental Delivery

1. Setup + Foundational → the derived-subject engine is ready and self-tested.
2. Add User Story 1 (`rebase.yml`) → validate independently (T025) → MVP.
3. Add User Story 2 (`cleanup.yml`) → validate independently (T031).
4. Add User Story 3 (`watchdog.yml`, `board-loop.yml`, `auto-update-spec-kit.yml` exemptions + documentation) → validate independently (T040).
5. Polish: full gate suite, `review-step-gating` skill pass, post-merge live-run proof.

### Notes

- [P] tasks = different files, no dependencies.
- Every gate-script edit is FR-012/SC-005 self-test-first in spirit: each new mechanism (T002–T008) or entry (T021/T028/T033–T035) ships together with the mutation that proves it is enforced, not after.
- FR-013/SC-007 (byte-identical observable behaviour on the clean-rebase and normal-teardown paths) is a static-plus-runtime claim: the static half is verified by T025/T031's grep/self-test checks; the runtime half only T043 (post-merge) can actually prove.
