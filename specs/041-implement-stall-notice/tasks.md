---

description: "Task list template for feature implementation"
---

# Tasks: An Implement Run That Dies at Entry Still Marks the Record and Says So on the Issue

**Input**: Design documents from `/specs/041-implement-stall-notice/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: This feature's "tests" ARE part of its deliverables — the repository's `verify-*.py` gate scripts and `wc_shell_harness.py`-based harnesses are how every composite/condition in this fleet is checked (no separate test framework). They are called out explicitly by FR-012–FR-015 and User Story 4, and are included below as first-class tasks, not an optional add-on.

**Organization**: Tasks are grouped by user story. Because this feature is one shared mechanism (FR-017a) reused at seven call sites, User Story 1 delivers the mechanism itself at all six stages (its own Acceptance Scenario 6 requires that); User Stories 2–4 layer verification of, respectively, the notice's content, its silence on every currently-quiet path, and its executable reachability — each independently testable per spec.md's own "Independent Test" for that story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1/US2/US3/US4, mapping to spec.md's priorities (US1/US2 = P1, US3/US4 = P2)

## Path Conventions

This repository is a GitHub Actions pipeline component — no `src`/`tests` split. All paths are relative to the repository root: `.github/actions/**`, `.github/workflows/**`, `.github/scripts/**`.

---

## Phase 1: Setup

**Purpose**: Scaffold the one new file every downstream task references.

- [X] T001 Create `.github/actions/wing-commander-chain-stop-notice/action.yml` with the full `inputs:`/`outputs:` declaration from contracts/wing-commander-chain-stop-notice.md (`token`, `issue-number` required; `spec-dir`, `spec-branch`, `stage-label`, `run-url`, `restart-command` optional with the documented defaults; `reason` required; no `outputs:` block — best-effort by design) and a `runs: using: composite` block with an empty `steps: []` placeholder. Follow the self-checkout-snippet convention documented at `.github/actions/wing-commander-context/action.yml:1-23` in the composite's own header comment (this composite is itself checked out via that snippet by every caller, so it needs no internal re-checkout of itself — only of the *spec* branch it marks).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The refusal-signal convention and the notice composite's real behavior — both are load-bearing for every user story below.

**⚠️ CRITICAL**: No user story task can be verified end-to-end until this phase is complete.

- [X] T002 [P] Add the refusal signal to `.github/actions/wing-commander-preflight/action.yml`: add `id: check` to the single "Preflight (credentials, spec-kit, prerequisites)" step (currently unnamed, `:106`); in the `fail()` helper (`:126-130`), write `echo "reason=$1" >> "$GITHUB_OUTPUT"` and `echo "refused=true" >> "$GITHUB_OUTPUT"` immediately before the existing `exit 1`, reusing the message already passed to `fail()` verbatim (research.md D2, contracts/refusal-signal-contract.md); add a new `outputs:` block (the file has none today) mapping `refused`/`reason` through to `steps.check.outputs.refused`/`.reason` per contracts/refusal-signal-contract.md's composite-output pattern.
- [X] T003 Implement `.github/actions/wing-commander-chain-stop-notice/action.yml`'s internal steps (scaffolded in T001), mirroring `implement.yml`'s existing `stalled` job (`:1580-1701`) generalized per data-model.md and contracts/wing-commander-chain-stop-notice.md:
  1. **Checkout spec branch** (`if: inputs.spec-dir != ''`) — on failure, set an internal `record-status=unwritable` output/env rather than failing the composite.
  2. **Mark `spec-meta.json` stalled** (`if: inputs.spec-dir != '' && <checkout succeeded>`) — `jq '.stage = "stalled"'`, commit, push; treat "nothing to commit" (already-stalled record) as success like today's step (`:1580-1613`); treat a rejected push as `record-status=unwritable`, not a composite failure.
  3. **Flip labels** (`if: always()`) — `gh label create`/`gh issue edit --add-label "stage:stalled"` (always, `|| true`-guarded); remove `inputs.stage-label` only when non-empty and the mark succeeded.
  4. **Post the notice** (`if: always()`) — render one of the two bodies in data-model.md's "Notice content" section (`marked` vs `unwritable` wording) using `inputs.reason`, `inputs.run-url` (default to `${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}` when empty), and `inputs.restart-command`; post via `gh issue comment "$ISSUE" --body-file <path>` (never `--body "$(...)"`, matching `wing-commander-callout`'s discipline at `.github/actions/wing-commander-callout/action.yml:123`). Every step from #2 onward runs under `set -uo pipefail` (no `-e`), matching `wing-commander-callout`'s and `wing-commander-preflight`'s existing shell discipline, so no internal step can fail the calling job (FR-011).

**Checkpoint**: The composite and the refusal signal exist and can be called; per-stage wiring can now begin.

---

## Phase 3: User Story 1 - The chain stops out loud (Priority: P1) 🎯 MVP

**Goal**: Every one of the six gated stages (seven entry jobs, since tasks.yml has two) marks the lifecycle record stalled, flips the label, and posts a notice when it dies at entry — reusing the one shared composite from Phase 2.

**Independent Test**: Drive an implement run whose first step fails; confirm the three effects. Drive the same failure through a stage with no chain state (e.g. clarify) and confirm the notice arrives there too.

### Implementation for User Story 1

- [X] T004 [US1] In `.github/workflows/implement.yml`, add the refusal signal to the `implement` job's three refusal-shaped steps: add `id: preflight` to the "Preflight" step (`:462`, currently unnamed); in "Resolve and validate spec identity" (`id: spec`, `:495-516`), write `refused=true`/`reason=<msg>` to `$GITHUB_OUTPUT` immediately before each of the three existing `exit 1`s (`:503-514`); in "Verify spec artifacts match the dispatch" (`id: meta`, `:532-556`), do the same before each of its two existing `exit 1`s (`:539-554`) — reusing each existing `::error::`/`msg=` text verbatim (contracts/refusal-signal-contract.md).
- [X] T005 [US1] In `.github/workflows/implement.yml`'s `implement` job: add `refusal-reason: ${{ steps.preflight.outputs.reason || steps.spec.outputs.reason || steps.meta.outputs.reason }}` to the job's `outputs:` block (`:393-400`); add three new `if: always()`-gated steps — one immediately after "Preflight" (`:462-474`), one after "Resolve and validate spec identity" (`:495-516`), one after "Verify spec artifacts match the dispatch" (`:532-556`) — each calling `./.wing-commander-pipeline/.github/actions/wing-commander-callout` with `kind: action`, gated on that step's own `outputs.refused == 'true'`, `summary: "This stage could not start — ${{ steps.<id>.outputs.reason }}"` (data-model.md "Could not start" refusal note; research.md D1 — in-job, not the survivor job).
- [X] T006 [US1] In `.github/workflows/implement.yml`, widen the `stalled` job (`:1492-1494`): change `needs: implement` to `needs: [verify-image-prerequisites, implement]` and replace the `if:` with data-model.md's condition table row for implement (`!cancelled() && (needs.verify-image-prerequisites.result == 'failure' || needs.implement.result == 'failure' || needs.implement.result == 'skipped' || needs.implement.outputs.final-ok == 'false')`); guard the three existing steps (`Mark lifecycle record stalled` `:1580`, `Report stalled on lifecycle issue` `:1615`, `Announce the stall on the lifecycle issue` `:1694`) each with an added `needs.implement.outputs.final-ok == 'false'` clause (research.md D7 — makes today's implicit case explicit, wording of these steps stays byte-for-byte unchanged, Out of Scope); add new steps calling `wing-commander-chain-stop-notice` (built in T003), guarded by `needs.implement.outputs.final-ok != 'false' && needs.implement.outputs.refusal-reason == ''` (the complementary, mutually-exclusive arm — D3, D7), passing `spec-dir`/`spec-branch` from `inputs.spec-dir`/the already-resolved branch, `issue-number: inputs.issue-number`, `reason` naming which dependency failed, and `restart-command` reusing the existing `recorded_iteration + 1` formula from the current "Report stalled..." step (`:1615-1693`).

- [X] T007 [P] [US1] In `.github/workflows/clarify.yml`: add the refusal signal to the `wing-commander-preflight` call (`:392`, add `id: preflight` if absent) and to "Verify spec identity" (`:432`, its `exit 1` for the empty-`spec:NNN-slug`-label case near `:440-447`); add a `refusal-reason` output to the `clarify` job's `outputs:` block (create the block if none exists) folding in both steps' `.reason` via `||`; add `if: always()`-gated in-job `wing-commander-callout` (`kind: action`) steps immediately after each, per T005's pattern.
- [X] T008 [US1] In `.github/workflows/clarify.yml`, add a new `stalled` job: `needs: [verify-image-prerequisites, clarify]`, `if:` per data-model.md's clarify row (`!cancelled() && (needs.verify-image-prerequisites.result == 'failure' || needs.clarify.result == 'failure' || needs.clarify.result == 'skipped')`), further split on `needs.clarify.outputs.refusal-reason == ''` before calling the composite (T007's mutual-exclusion arm). Resolve `spec-dir` independently via `gh issue view --json labels` and parsing the `spec:*` label — the same lookup `wing-commander-context`'s `resolve` step already performs (`.github/actions/wing-commander-context/action.yml:69-81`) — per research.md D6's clarify row (never trust `needs.clarify.outputs.*` for identity, only for `refusal-reason`). `stage-label: "stage:clarify"`.

- [ ] T009 [P] [US1] In `.github/workflows/finalize.yml`: add the refusal signal to the `wing-commander-preflight` call (`:399`), "Resolve and validate spec identity" (`id: spec`, `:438-454`, refuse-and-exit blocks at `:445-452`), and "Verify spec artifacts match the dispatch" (`id: meta`, `:470-492`, blocks at `:477-492`) — same shape as implement.yml's identical steps (T004); add a `refusal-reason` output to the `finalize` job's `outputs:` block; add three in-job refusal-callout steps per T005's pattern.
- [ ] T010 [US1] In `.github/workflows/finalize.yml`, add a new `stalled` job: `needs: [verify-image-prerequisites, finalize]`, data-model.md's finalize row for `if:`, split on `refusal-reason == ''`. `spec-dir`/`issue-number` are directly declared `workflow_call` inputs (research.md D6 — no re-derivation needed). `stage-label: "stage:finalize"`.

- [ ] T011 [P] [US1] In `.github/workflows/intake.yml`: add the refusal signal to the `wing-commander-preflight` call (`:437`); grep the file for any other inline refusal-shaped `exit 1` block guarding the `intake` job's entry (research.md D10's rule — not a fixed list; `Allocate feature number` `:495` and `Resolve created spec` `:810` run well after entry and are out of this task's scope, per spec's framing that intake's failure mode is "no record exists yet," not a mid-run refusal). Add a `refusal-reason` output to the `intake` job's `outputs:` block (`:370-372`, alongside existing `spec-dir`/`feature-num`); add in-job refusal-callout step(s) per T005's pattern.
- [ ] T012 [US1] In `.github/workflows/intake.yml`, add a new `stalled` job: `needs: [verify-image-prerequisites, intake]`, data-model.md's intake row for `if:`, split on `refusal-reason == ''`. Always call the composite with `spec-dir: ""` (research.md D5 — intake dying at entry means no `spec-meta.json` was ever written; this is the *same* "record could not be updated" branch every other stage takes only on a rarer failure, not a bespoke wording). `issue-number: inputs.issue-number` (intake's issue exists before any spec record does). No `stage-label` (intake has no predecessor stage label to remove).

- [ ] T013 [P] [US1] In `.github/workflows/pr-conversation.yml`: add the refusal signal to both `wing-commander-preflight` calls (`:509` in `classify-and-announce`, `:1378` in `act`) and to "Resolve PR identity and check qualification" (`id: identity`, `:444-505`, refusal block at `:476-481` — note: the non-qualifying-PR early exit at `:503-505` is a deliberate silent stop per FR-018/US3, NOT a refusal — do not add `refused`/`reason` there) and "Read lifecycle issue number from spec-meta.json" (`id: meta`, `:540-553`, refusal block at `:548-552`); add a `refusal-reason` output to `classify-and-announce`'s `outputs:` block folding in `identity`/`meta`/`preflight`'s `.reason`; add in-job refusal-callout steps per T005's pattern (posting to `inputs.pr-number` — a PR is a valid `gh issue comment` target).
- [ ] T014 [US1] In `.github/workflows/pr-conversation.yml`, add a new `stalled` job: `needs: [verify-image-prerequisites, classify-and-announce]`, data-model.md's pr-conversation row for `if:`, split on `refusal-reason == ''`. Resolve `spec-dir`/`issue-number` independently — `gh pr view` on the head ref to recover the `spec/NNN-slug` branch name, then the same `spec-meta.json` API read `meta` (`:540-553`) already performs, run again here (research.md D6). When *this* re-derivation itself fails, post the notice to `inputs.pr-number` directly instead of an unresolvable lifecycle issue (research.md D6, D10 — the PR is the one identifier FR-003 guarantees survives every failure shape on this stage). No `stage-label`.

- [ ] T015 [P] [US1] In `.github/workflows/tasks.yml`: add the refusal signal to `resolve-spec`'s "Resolve spec identity" step (`id: spec`, `:405-425`, refuse-and-exit at `:420-423`) and to both `wing-commander-preflight` calls (`:510` in `tasks`, `:1155` in `tasks-approved`, the latter with `require-credential: "false"`); add a `refusal-reason` output to `resolve-spec`'s `outputs:` block (`:397-399`, alongside `slug`/`spec-dir`) and to both the `tasks` and `tasks-approved` jobs' outputs (folding in their own preflight step plus `needs.resolve-spec.outputs.refusal-reason`, since a `resolve-spec` refusal skips both downstream jobs before either can run its own steps); add in-job refusal-callout steps at each of the three refusing steps per T005's pattern.
- [ ] T016 [US1] In `.github/workflows/tasks.yml`, add two new survivor jobs (or one job with two arms, if the shared shape's `if:` cleanly OR's both): one for `mode: generate` (`needs: [verify-image-prerequisites, resolve-spec, tasks]`, firing when `resolve-spec` failed/was skipped-with-a-non-refusal, or `tasks` failed/was skipped, and no `refusal-reason` anywhere in the chain) and one for `mode: approved` (same shape against `tasks-approved`). `spec-dir` needs no lookup (`slug` parses directly from `head-ref` when `slug` is empty — string derivation only, `specs/<slug>`); `issue-number` via `gh api .../contents/$SPEC_DIR/spec-meta.json -f ref=<branch>` (the same call `pr-conversation`'s `meta` step makes, research.md D6). No `stage-label` per data-model.md.

**Checkpoint**: All seven entry points mark the record, flip the label, and post a notice on abnormal termination; refusals post the shorter note in-job instead. User Story 1's independent test is now runnable end-to-end. This is the MVP — deployable/demoable on its own.

---

## Phase 4: User Story 2 - The notice describes the stop that actually happened (Priority: P1)

**Goal**: A maintainer reading the notice can tell whether the implementation agent ever ran, and the restart instructions are correct for whichever stop occurred.

**Independent Test**: Produce both stops — an exhausted retry and a death at entry — and confirm each notice names its own case, with correct restart instructions.

### Implementation for User Story 2

- [ ] T017 [US2] Using `wc_shell_harness.py`'s `run_step`/stubbed-`gh` pattern (the same convention `.github/scripts/verify-stall-restart-runbook.py` established for today's `stalled` job), write `.github/scripts/verify-chain-stop-notice-body.py` (or extend an existing harness script) driving `wing-commander-chain-stop-notice`'s steps (T003) against a synthetic repo with `spec-meta.json` reading `{"stage": "implement", "iteration": 2}`. Assert: the branch's `spec-meta.json` now reads `"stage": "stalled"`; exactly one `gh issue comment` call whose body matches the "stage did not start" template (data-model.md) — names where the run stopped, links `run-url`, contains no model-tier or escalation language (FR-007); exactly one `stage:stalled` label add and (when `stage-label` was non-empty) one label removal (quickstart.md §3 steps 1-3).
- [ ] T018 [US2] Extend T017's harness: repeat with the synthetic repo's remote unreachable (no bare remote configured) — assert the composite still posts exactly one comment, now using the "record could not be updated" wording (data-model.md), and raises nothing (FR-011). Repeat with `spec-dir` empty (the intake case, T012) — assert the record-mark step is skipped entirely and the same "record could not be updated" comment is posted (quickstart.md §3 steps 4-5).
- [ ] T019 [US2] Extend T017/T018's harness with one fixture per non-implement stage (T008/T010/T012/T014/T016) asserting `restart-command` renders that stage's own plain re-dispatch line (no `recorded_iteration + 1` arithmetic — data-model.md's composite input table), and one fixture confirming implement's `restart-command` still computes `recorded_iteration + 1` (T006) — satisfies FR-008/SC-004 for both stop causes.
- [ ] T020 [US2] Add a byte-for-byte regression assertion (in `verify-stall-restart-runbook.py` or a new small script) that `implement.yml`'s existing exhausted-retry notice text (`:1615-1693`) is unchanged after T006's edit — confirms Out of Scope / User Story 2 Acceptance Scenario 3 ("reads exactly as it does today").

**Checkpoint**: Both stall causes render distinct, individually-correct notices; restart instructions are provably right for each stage.

---

## Phase 5: User Story 3 - A refusal is still a refusal, and a healthy run is untouched (Priority: P2)

**Goal**: Nothing quiet today becomes noisy except the declared refusal note; a refusal never touches the record or labels.

**Independent Test**: Exercise each currently-quiet path (duplicate dispatch, closed lifecycle, successful cycle, exhausted retry) and confirm no change; exercise a declared refusal and confirm the record/labels are untouched while the could-not-start note appears.

### Implementation for User Story 3

- [ ] T021 [US3] Write `.github/scripts/verify-chain-stop-refusal-exclusion.py` (or extend `wc_shell_harness.py` usage in an existing script): drive `wing-commander-preflight` (T002) with `require-credential: "true"` and both credential inputs empty, forcing its refusal branch; assert `steps.check.outputs.refused == 'true'` and `.reason` non-empty (quickstart.md §4 step 1). Then, using Gate 28's fixture table (built in T025), assert that with `needs.<job>.outputs.refusal-reason` set from this value, every one of the seven survivor-job conditions (T006/T008/T010/T012/T014/T016) evaluates `false` — the refusal and abnormal-termination paths cannot both fire for the same run (quickstart.md §4 step 2, FR-006).
- [ ] T022 [US3] Add fixtures asserting FR-004's currently-quiet paths stay byte-for-byte quiet after T006-T016's widening: a duplicate dispatch the idempotency guard skips, a run against a closed lifecycle issue (`Note closed lifecycle and stop`, e.g. `implement.yml:452` equivalent per stage), and a successful cycle — confirm none of the seven survivor-job conditions evaluates `true` for these `needs.*` shapes (extend Gate 28's fixture table, T025, or a standalone script — SC-005).
- [ ] T023 [US3] Add a fixture asserting a cancelled run (`needs.*.result` irrelevant, run-level `cancelled`) produces `false` on every one of the seven survivor-job conditions and leaves every in-job refusal-callout step unrun (`!cancelled()`, T006/T008/T010/T012/T014/T016 — FR-009, Edge Cases "The run is cancelled").
- [ ] T024 [US3] Add a fixture asserting that on a refusal path, across all six stages, the composite is never invoked (only the in-job `wing-commander-callout` is) — so `spec-meta.json`'s `stage` field and every `stage:*` label are provably untouched (SC-010; combine with T021's harness or keep standalone).

**Checkpoint**: Every path that posts nothing today still posts nothing except the one declared refusal note; refusal and stall are provably mutually exclusive.

---

## Phase 6: User Story 4 - The failure branch is executed, not merely written (Priority: P2)

**Goal**: A check drives an implement run whose dependency actually fails and asserts the notice happened; removing or narrowing the guard fails a check.

**Independent Test**: Make the modelled dependency fail and confirm coverage observes the mark and the notice; make the notice path unreachable and confirm a check goes red.

### Implementation for User Story 4

- [ ] T025 [US4] Extend `.github/scripts/wc_shell_harness.py` with a job-aware YAML lookup (a `find_job(path, name)`-style function alongside the existing `find_step`, `:210`) that returns a job's `needs:`/`if:` dict by job id — the "job-aware extension of `wc_shell_harness.py`'s existing `find_step`-style YAML access" research.md D8 and contracts/chain-stop-gate-coverage.md call for. This is shared plumbing (`wc_*.py` naming convention, exempt from the gate-wiring check per `wc_gate_registry.py:19-31`), used by T026.
- [ ] T026 [US4] Implement `.github/scripts/verify-chain-stop-notice.py` (Gate 28): a minimal evaluator for `!cancelled()`, `&&`, `||`, `==`, `!=`, and `needs.<job>.result`/`needs.<job>.outputs.<name>` substitution (research.md D8); using T025's job lookup, extract each of the seven survivor-job `if:` strings (T006/T008/T010/T012/T014/T016) from the shipped workflow files; evaluate each against every row of contracts/chain-stop-gate-coverage.md's fixture table (healthy run → false; refusal with job success/failure → false; job failure/skip → true; upstream-dependency failure → true; cancelled → false; implement's exhausted-retry arm → true); assert every row's actual evaluation matches expected, for all seven call sites.
- [ ] T027 [US4] Extend T026 with the four required mutations from data-model.md's mutation table, applied to a copy of each extracted condition string, re-running T026's row assertions and confirming at least one row disagrees for every mutation (FR-013): (1) remove `!cancelled()`/`always()` — some row now wrongly passes; (2) narrow so `needs.<entry-job>.result == 'failure'` is dropped — the "entry job itself failed" row now wrongly fails; (3) widen to also fire on `needs.<entry-job>.result == 'success'` — the healthy-run/refusal rows now wrongly pass; (4) point one of the seven call sites at a bespoke condition string not matching the shared table — asserted directly against the shared shape, not just re-evaluated. Follow the `if mutated == original` guard `verify-stall-restart-runbook.py` already establishes so a mutation that silently failed to apply cannot produce a false pass.
- [ ] T028 [US4] Wire Gate 28 into `.github/workflows/lint-workflows.yml` as a new step, `"Gate 28 — a stage that dies at entry reaches the chain-stop notice, and nothing else does"`, `run: python3 .github/scripts/verify-chain-stop-notice.py` — following Gate 14's single-line wiring pattern (`lint-workflows.yml:1315-1316`), not Gate 15's inline-heredoc-plus-self-test pattern. No registry file to hand-edit; `wc_gate_registry.py`'s filename convention picks it up automatically, and Gate 10 (`lint-workflows.yml:2724`) asserts the wiring is complete in both directions (FR-014).
- [ ] T029 [US4] Amend `.github/scripts/verify-gate-15.py` and Gate 15's inline detection heredoc in `lint-workflows.yml` (`:1335-1430`): broaden the `NON_SUCCESS_ARM` regex (`needs\.[A-Za-z0-9_-]+\.result\s*[=!]=\s*'(skipped|failure|cancelled)'`) to also match `needs.<job>.outputs.<name> == '<value>'` comparisons with no status-check function in the same expression; keep every existing `CASES` entry in `verify-gate-15.py` byte-for-byte unchanged, and append three new cases per contracts/chain-stop-gate-coverage.md: (1) a synthetic job whose `if:` is exactly `stalled`'s pre-fix condition (`needs.implement.outputs.final-ok == 'false'`, no status function) — must be flagged; (2) the same shape with `!cancelled() &&` prefixed — must not be flagged; (3) an existing-style `.result` comparison, unchanged — still flagged (FR-015).

**Checkpoint**: The notice path's reachability is mechanically proven, not merely observed once; Gate 15 now catches the output-based cousin of the shape it already caught.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T030 [P] Run quickstart.md's full validation sequence end-to-end (Gate 28 §1, Gate 15 self-test §2, composite shell harness §3, refusal-exclusion harness §4) and confirm every step passes together, not just individually.
- [ ] T031 [P] Re-read every edited workflow file's `Preflight`/identity-check steps once more against contracts/refusal-signal-contract.md's "Explicitly NOT covered" list — confirm `wing-commander-lifecycle-gate`'s own failures and the `Note closed lifecycle and stop` step were left untouched at all seven call sites (research.md D10 — these are abnormal termination, not refusal, by design).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: No dependencies.
- **Foundational (T002-T003)**: T002 has no dependency on T001; T003 depends on T001's scaffold. Both BLOCK every User Story task.
- **User Story 1 (T004-T016)**: Depends on Foundational completion. The six stages' task-pairs (T004-T005/T006, T007/T008, T009/T010, T011/T012, T013/T014, T015-T016) are independent of each other (different files) but each pair is internally sequential (the survivor-job task reads the refusal-reason output the signal task adds).
- **User Story 2 (T017-T020)**: Depends on US1 completion (needs real survivor-job conditions and composite calls to test against).
- **User Story 3 (T021-T024)**: Depends on US1 (T021 also depends on T025-T026's fixture table, so in practice run T025-T026 before T021 even though they're nominally "US4" work — see note below).
- **User Story 4 (T025-T029)**: Depends on US1 (extracts the shipped conditions T004-T016 produce). T025-T026 should be done before T021 (US3) despite the phase ordering, since T021 reuses Gate 28's fixture table.
- **Polish (T030-T031)**: Depends on all prior phases.

### Parallel Opportunities

- T002 (preflight) has no dependency on T001 and can start immediately alongside it.
- Within Phase 3, the six stage task-pairs are file-disjoint and fully parallelizable: `{T004,T005,T006}`, `{T007,T008}`, `{T009,T010}`, `{T011,T012}`, `{T013,T014}`, `{T015,T016}` can each be assigned to a different implementer/agent once Foundational is done.
- T030-T031 in Polish are independent of each other.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Setup (T001) + Foundational (T002-T003).
2. Complete User Story 1 (T004-T016) — all seven call sites.
3. **STOP and VALIDATE**: manually confirm (quickstart.md §5) that a broken `container-image` dispatch to `implement` produces the "stage did not start" notice, the `stage:stalled` label, and the marked record — the defect spec.md opens with is now fixed for all six stages.

### Incremental Delivery

1. Setup + Foundational → composite and refusal signal exist.
2. User Story 1 → the notice exists at all six stages (MVP, matches spec.md's own framing: "this one is the notice existing at all").
3. User Story 2 → the notice is provably correct per stop-cause and per-stage restart instructions.
4. User Story 4 → reachability is provably guarded (do before or alongside US3 — T021 reuses T025-T026's fixtures).
5. User Story 3 → quiet paths are provably still quiet, and refusal/stall are provably mutually exclusive.
6. Polish → full end-to-end validation pass.
