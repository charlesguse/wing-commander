# Tasks: Haiku 5.5 Tier Upgrade and Measured Trial

**Input**: Design documents from `specs/110-haiku-5-5-tier-trial/` (plan.md, spec.md, research.md, data-model.md, contracts/trial-record.md, contracts/trial-switches.md, quickstart.md)

**Tests**: Not requested as a separate TDD phase. Per Principle VIII every new gate ships with checked-in failure fixtures under `.github/scripts/fixtures/`; those fixtures are part of the gate task, not separate test tasks.

**Organization**: Grouped by user story. Run `python .github/scripts/run-local-gates.py` before every push (CLAUDE.md). Workflow comments are load-bearing: treat comment edits as code edits.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (verification before any model ID changes)

- [ ] T001 Verify `anthropics/claude-code-action@v1` accepts `--model claude-haiku-5-5` (research D1): drive one real run through a Haiku-tier step (e.g. dispatch cleanup/finalize summary or auto-update-spec-kit T026 path) and record the evidence in a comment on #972; if rejected, STOP and report the upgrade as blocked
- [X] T002 [P] Audit 400-triggering settings (research D4): Grep `.github/` for `thinking`, `budget_tokens`, `temperature`, `top_p`, `prefill`, computer-use; record the result (none expected) in the #972 comment, remove any hit for the Haiku path
- [ ] T003 [P] Check whether repository variable `WING_COMMANDER_SUMMARY_MODEL` is set (`gh variable list`); if it equals `claude-haiku-4-5`, delete it with the change (#970 precedent) and note it on #972

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Hand-off of the constitution amendment and the diagnose-agent extraction that Story 2 builds on.

- [X] T004 Write the Principle II amendment text (MINOR 2.3.1 → 2.4.0: Haiku tier `claude-haiku-5-5`, per-lifecycle `model:haiku` implement opt-in, trial shadow declares an explicit Haiku model and acts on nothing) with its Sync Impact Report moved to the top of `.specify/memory/constitution-history.md`, on a branch separate from `spec/110-haiku-5-5-tier-trial`; hand the PR to the owner for human merge and report this manual step on #972. The lifecycle PR MUST contain no `.specify/memory/` edit (research D5, FR-003) — done: PR #988 (branch `constitution-2.4.0-haiku-5-5`), handed to the owner for human merge; until it merges, Gate 141 still flags `constitution.md`. Only T011 and T034 wait on it.
- [ ] T005 Extract the diagnose prompt and `claude-code-action` call from `.github/workflows/watchdog.yml` into new composite `.github/actions/wing-commander-diagnose-agent/action.yml` taking `model`, `max-turns`, `output-name`; the acting step calls it with unchanged values. Extraction-only commit, no behaviour change; run the full gate suite and fix gates that scan workflows for `claude-code-action` steps (Gate 68 timeout exemption, verdict/metrics pairing) so they follow the composite (research D7). If extraction is unworkable under the gates, use the byte-equality fallback and record the decision in this file

**Checkpoint**: Gate suite green with extraction in place.

---

## Phase 3: User Story 1 - Haiku tier names the current model (Priority: P1) 🎯 MVP

**Goal**: No pipeline-chosen `claude-haiku-4-5` remains; a gate fails if one reappears.

**Independent Test**: Grep of `.github/workflows/`, `.github/actions/`, `.specify/memory/constitution.md`, `docs/` for `claude-haiku-4-5` finds nothing; the new gate passes and its fixtures fail as designed.

- [X] T006 [P] [US1] Change `summary-model` default to `claude-haiku-5-5` in `.github/workflows/implement.yml`, `.github/workflows/finalize.yml`, `.github/workflows/cleanup.yml`
- [X] T007 [P] [US1] Change the summary-model fallbacks to `claude-haiku-5-5` in `.github/workflows/wing-commander-5-implement.yml`, `.github/workflows/wing-commander-6-finalize.yml`, `.github/workflows/wing-commander-7-cleanup.yml` (cleanup has two)
- [X] T008 [P] [US1] Change T026's literal `--model` and its comment to `claude-haiku-5-5` in `.github/workflows/auto-update-spec-kit.yml` (no new input, research D2)
- [X] T009 [P] [US1] Replace `claude-haiku-4-5` with `claude-haiku-5-5` in `docs/setup.md` (2), `docs/adoption.md` (2), `docs/architecture.md` (3)
- [X] T010 [US1] Create `.github/scripts/verify-haiku-tier-model-id.py` scanning `.github/workflows/`, `.github/actions/`, `.specify/memory/constitution.md`, `docs/` for `claude-haiku-4-5` (any suffix); ignore `.github/scripts/` fixtures, `constitution-history.md`, `specs/`; fail loudly on an empty scan root. Add failure fixtures under `.github/scripts/fixtures/` (workflow hit, docs hit, constitution hit, empty root); register it in the gate registry and wire it in `.github/workflows/lint-workflows.yml` like sibling gates
- [X] T011 [US1] Confirm the constitution scan (T010) passes only after the T004 amendment PR has merged to `main`; note on #972 that the lifecycle PR must not merge before it (FR-003, FR-005)
- [ ] T012 [US1] Run `python .github/scripts/run-local-gates.py`; all gates green

**Checkpoint**: Story 1 complete and independently shippable.

---

## Phase 4: User Story 2 - Watchdog diagnose Haiku 5.5 shadow (Priority: P2)

**Goal**: An opt-in, bounded, read-only Haiku 5.5 shadow whose comparison is deterministic and whose trial record lands on the metrics branch.

**Independent Test**: With the shadow enabled, a watchdog run files/routes identically to one with it disabled, and a `diagnose-shadow` record with a `trial` object appears on the metrics branch.

- [X] T013 [P] [US2] Add additive boolean `refusal` (true iff the transcript's terminal result has `stop_reason == "refusal"`) to `.github/actions/wing-commander-metrics-summary/action.yml`; add a fixture and extend `verify-metrics-summary-record-emission.py` (research D8)
- [X] T014 [P] [US2] Create `.github/scripts/compare-diagnose-shadow.py` implementing research D9 rules in order (Opus not `healthy` → `no-baseline`; `refusal` → `refused`; `exhausted`; error; `malformed` against the same JSON schema; else compare filing agreement over `(class, signalId set)` keys and class agreement over shared signalId sets; `__new__` compared by normalised `proposedClass`) emitting the `trial` object per `contracts/trial-record.md`
- [X] T015 [US2] Create gate `.github/scripts/verify-compare-diagnose-shadow.py` (Gate 142; the comparator now lives at `.github/actions/_shared/compare-diagnose-shadow.py` because composites ship only the actions tree) with one fixture per outcome (agreed, disagreed, exhausted, malformed, error, refused, no-baseline); register and wire in `lint-workflows.yml` (depends on T014)
- [X] T016 [P] [US2] Create composite `.github/actions/wing-commander-trial-record/action.yml` adding the additive top-level `trial` object to a metrics record before upload, preserving `schema_version` 1, top-level `outcome` meaning and the `per_model` sum invariant (FR-011)
- [X] T017 [P] [US2] Create `.github/actions/_shared/trial-bound.py` (moved from `.github/scripts/`: composites ship only the actions tree) and composite `.github/actions/wing-commander-trial-bound/action.yml`: read `records.jsonl` on the metrics branch, count records with `run.run_label == "diagnose-shadow"`, `trial.outcome` not in `{error, no-baseline}`, `started_at >= SINCE`; output `enabled = SINCE set && today < SINCE + 60d && compared < 300` (research D10)
- [X] T018 [US2] Create gate (Gate 143) `.github/scripts/verify-trial-bound.py` with fixtures (unset SINCE, expired by date, expired by count, error/no-baseline not counted, enabled); register and wire (depends on T017)
- [ ] T019 [US2] Add additive inputs `diagnose-shadow-enabled` (boolean, default false), `diagnose-shadow-model`, `diagnose-shadow-max-turns` to `.github/workflows/watchdog.yml`; add the shadow step as the LAST step of the `diagnose` job after read-back, findings upload and metrics record: calls `wing-commander-diagnose-agent` with `claude-haiku-5-5`, own budget, read-only allowlist, `GH_TOKEN` = `github.token`, `continue-on-error: true`, `timeout-minutes: 5`; copy its transcript to `claude-execution-output-diagnose-shadow.json`; run comparator, metrics-summary with `run-label: diagnose-shadow`, `stage: watchdog`, trial-record, and upload artifact `metrics-record-diagnose-shadow`. Stage reads no `vars.*` for it (depends on T005, T013–T016)
- [ ] T020 [US2] In `.github/workflows/wing-commander-8-watchdog.yml` and `.github/workflows/wing-commander-8b-watchdog-self.yml`, call `wing-commander-trial-bound` (switch: variable `WING_COMMANDER_DIAGNOSE_SHADOW_SINCE`) and pass its `enabled` output as `diagnose-shadow-enabled`, with a one-line `false` fallback if the composite never ran (depends on T017, T019)
- [ ] T021 [US2] Create gate `.github/scripts/verify-diagnose-shadow-acts-on-nothing.py`: shadow step has no write tools, uses `github.token`, runs after the acting outputs, is `continue-on-error`, and `timeout-minutes` plus acting step stays under the job backstop; fixtures per failure branch; register and wire (depends on T019)
- [ ] T022 [US2] Verify the watchdog turn-budget trend collector ignores `run_label == "diagnose-shadow"`; add a fixture and fix the filter if it does not (FR-011)
- [ ] T023 [US2] Re-check Gate 68 credential handling for the second action invocation in the job and run `python .github/scripts/run-local-gates.py`; run the `review-step-gating` skill over the watchdog.yml and wrapper changes

**Checkpoint**: Shadow can be enabled by setting the one variable and stops itself at 60 days / 300 compared runs.

---

## Phase 5: User Story 3 - Implement `model:haiku` opt-in (Priority: P3)

**Goal**: One lifecycle can run implement on Haiku 5.5 with Sonnet escalation; nothing else reads the label.

**Independent Test**: A `model:haiku` lifecycle's implement record shows `claude-haiku-5-5`; with both labels `model:opus` wins; pr-conversation and the board loop ignore the label.

- [X] T024 [US3] In `.github/workflows/wing-commander-5-implement.yml` `resolve-model` job: when the lifecycle issue has `model:haiku` and not `model:opus`, output `model=claude-haiku-5-5`, `escalation-model=claude-sonnet-5-5`, `max-turns=${{ vars.WING_COMMANDER_IMPLEMENT_HAIKU_MAX_TURNS || '180' }}`; other cycles keep their model and escalation variable and get `max-turns` literal `180`; `model:opus` wins. Make `escalation-model` step-computed and pass `max-turns` to implement (research D11); implement.yml stays unchanged
- [X] T025 [US3] Add a gate (extend the nearest input-default gate, else a small new `verify-*.py` with fixtures) asserting the wrapper's literal `180` equals implement.yml's `max-turns` input default; register and wire
- [X] T026 [P] [US3] Add a gate fixture/check asserting pr-conversation and the board loop never grep `model:haiku` nor treat it as Opus; confirm finalize's label mirroring is unchanged
- [ ] T027 [US3] Run the gate suite and the `review-step-gating` skill over the wrapper change

**Checkpoint**: Haiku implement opt-in works per lifecycle; no default moved (FR-016).

---

## Phase 6: User Story 4 - Trial summary (Priority: P3)

**Goal**: Deterministic per-step summary from the metrics branch alone.

**Independent Test**: Dispatch the summary wrapper; every figure matches `records.jsonl`; a Sonnet record with a `claude-haiku-5-5` helper `per_model` entry is not counted.

- [X] T028 [US4] Create `.github/scripts/trial-summary.py` (research D12): diagnose runs, agreement, refusal and exhaustion counts, median turns and cost per run per model, and `meets`/`misses`/`sample too small` at 200 compared runs per FR-017 (a, b, c; errors excluded from the 2%); implement section grouped by `spec.issue` for `stage == implement` top-level `model == claude-haiku-5-5` against the median Sonnet lifecycle (cycles to converge, escalations and tier, refusals, exhaustions, total cost incl. retries) with no verdict. Model identity is always the top-level `model`
- [X] T029 [US4] Create gate (Gate 144) `.github/scripts/verify-trial-summary.py` with fixtures (meets, misses, too small, no-baseline excluded, Sonnet record with Haiku helper `per_model` not counted); register and wire (depends on T028)
- [X] T030 [US4] Create `workflow_dispatch`-only `.github/workflows/wing-commander-trial-summary.yml` that checks out the metrics branch and writes the summary to the job summary; read-only permissions (depends on T028)

---

## Phase 7: Polish and cross-cutting

- [ ] T031 [P] Document the `WING_COMMANDER_DIAGNOSE_SHADOW_SINCE` variable and `model:haiku` label in `docs/setup.md`, the three new `watchdog.yml` inputs in `docs/adoption.md`, and the trial design in `docs/architecture.md`
- [ ] T032 Run the `spec-cross-reference` skill over the changed files, then `python .github/scripts/run-local-gates.py` clean
- [ ] T033 Run the `quickstart.md` validation steps that can run pre-merge
- [ ] T034 Post-merge proof (owner/maintainer, after the T004 amendment has merged): re-drive one watchdog run with the shadow on and off and show identical filed outcomes (SC-003); run one Haiku implement cycle; dispatch the trial summary; record the evidence on #972 and the PR

---

## Dependencies and execution order

- Phase 1 first; T001 gates all model ID changes. Phase 2: T005 blocks Story 2; T004 is a manual hand-off needed before the lifecycle PR merges.
- US1 (Phase 3) needs only Phase 1; it is the MVP. US2 needs T005. US3 and US4 are independent of US2 except that T028 reads the `trial` shape from T016/T014. US4 reads records from US2/US3 at run time only.
- Within US2: T013/T014/T016/T017 parallel → T015, T018 → T019 → T020, T021.

## Parallel examples

- US1: T006, T007, T008, T009 together, then T010.
- US2: T013, T014, T016, T017 together.

## Implementation strategy

MVP = Phase 1 + Phase 2 (T004) + Story 1 (T006–T012): the tier upgrade and its gate. Then US2 (shadow), US3 (opt-in), US4 (summary) in order. Gate suite stays green after every phase.
