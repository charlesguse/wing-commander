# Tasks: Review findings — fix now, record only what fails silently, drop the rest

**Input**: `/specs/128-review-finding-triage/` (plan.md, spec.md, data-model.md, contracts/finding-triage.md, research.md, quickstart.md)

**Tests**: Fixture corpora plus the new `verify-finding-triage-report.py` gate (required by plan and Constitution VIII). Run `python .github/scripts/run-local-gates.py` before pushing; workflow comments are byte-compared by gates, so re-run the suite after any comment edit. Changes touching `if:`/`continue-on-error:` get a `review-step-gating` pass.

**Format**: `[ID] [P?] [Story] Description` — [P] = different files, no dependencies.

## Phase 1: Setup

- [ ] T001 Read `specs/128-review-finding-triage/quickstart.md` and the current call sites (`.github/workflows/lifecycle-review-gate.yml`, `.github/actions/wing-commander-stage-findings/action.yml`) and note the exact steps named in contracts/finding-triage.md "Consumers"; no file changes.

## Phase 2: Foundational (blocks all stories)

**Purpose**: the single home of the rule, schemas, and the PR-time gate.

- [ ] T002 Create `.github/scripts/wc_finding_triage.py` (stdlib only, pure): `route`, `route_all`, `render_triaged`, `silent_note` per contracts/finding-triage.md and the precedence in data-model.md (`Finding.failure_class`, `Finding.silent_description`, `Finding.severity`, `Finding.security`; routing outcome table). Titles render as code spans, backticks removed, `<!--` broken.
- [ ] T003 [P] Add optional `failure_class` (unrecognised values must still validate), `silent_description`, `severity`, `security` to `.github/schemas/board-review-finding.schema.json` and `.github/schemas/stage-finding.schema.json` (data-model.md `Finding`); none `required`.
- [ ] T004 [P] Update `.github/scripts/verify-board-review-finding-schema.py` and `.github/scripts/verify-stage-finding-schema.py` to accept the four fields and assert existing board-loop fixtures still validate.
- [ ] T005 Create fixtures under `.github/scripts/fixtures/finding-triage/`: one positive corpus covering every row of the data-model.md outcome table, plus one fixture per failure branch (missing drop in list, missing reason, important/security dropped, rejected rendered as dropped, rule reimplemented at a call site, unreachable subject).
- [ ] T006 Create `.github/scripts/verify-finding-triage-report.py`: checks the renderer lists every drop/reject with its literal reason (FR-011), nothing important/security or unreadable-class is dropped (FR-007, FR-009), rejects are never rendered as dropped, both call sites import the module and neither reimplements the rule (literal `fails loudly` / `no output change` outside the module and fixtures), and fails loudly if its subject is unreachable.
- [ ] T007 Register the new gate in `.github/workflows/lint-workflows.yml` (triggered by the files it checks) and confirm `run-local-gates.py` picks it up; update any gate-count/registry list the suite enforces.

**Checkpoint**: module, schemas and gate green on fixtures.

## Phase 3: User Story 1 - Lifecycle review gate records only silent out-of-scope findings (P1) 🎯 MVP

**Goal**: in-scope folded as today; out-of-scope silent recorded with description; loud/none dropped and listed with reason in the round's review body.

**Independent Test**: feed the gate's routing one in-scope, one silent, one loud, one none finding; only the in-scope is folded, only silent recorded, other two listed as dropped with reasons (quickstart.md).

- [ ] T008 [US1] In `.github/workflows/lifecycle-review-gate.yml` review job *extract*, annotate each finding in `lifecycle-review-findings.json` with its `triage` outcome via `wc_finding_triage.route` (finding text never enters annotations, FR-026); fallback if the module cannot load is *record*.
- [ ] T009 [US1] In the same workflow's *Compose the review body*, append a "Dropped and rejected" section from `render_triaged` (rendered by code, not the agent); rejects also emit a warning.
- [ ] T010 [US1] In the disposition job *Partition…*, re-derive outcomes and keep only `record` findings for the `[:3]` slots; fix-now stays on the existing in-scope path so readiness and round budget are unchanged; include `silent_note` in the filed issue body (FR-004).
- [ ] T011 [US1] Update the gate's reviewer prompt in `.github/workflows/lifecycle-review-gate.yml` to emit `failure_class`, `silent_description`, `severity`, `security`; keep the board loop's reviewer untouched.
- [ ] T012 [US1] Update live contract `specs/062-*/contracts/review-and-findings.md` for the new fields and drop/reject reporting (FR-014).

**Checkpoint**: gate fixtures and full suite green; US1 deliverable.

## Phase 4: User Story 2 - Stage-found defects follow the record/drop rule (P2)

**Goal**: stage-findings path sorts proposals record/drop/reject (never fix-now); run summary lists drops and rejects.

**Independent Test**: three proposals (silent, loud, none) → only silent filed; summary lists the other two with reasons; unclassified is recorded (FR-009).

- [ ] T013 [US2] In `.github/actions/wing-commander-stage-findings/action.yml` *Extract, validate, cap, and prepare findings*, route survivors with `route_all` (`in_scope=False`) after errata/in-flight filtering and before the cap; store `triaged_out` in `state.json`; `routed-task` stays exempt; composite still always exits 0, no output renamed.
- [ ] T014 [US2] In the same action's *Emit summary*, render `triaged_out` via `render_triaged`; a reject also emits a warning; recorded findings' bodies include `silent_note`.
- [ ] T015 [P] [US2] Add stage-findings fixtures/cases to the existing `stage-findings-tests/run_fixtures.py` corpus: silent, loud, none, unclassified, silent-without-description, important-and-none, security nit, cap not consumed by drops.
- [ ] T016 [P] [US2] Update stage workflows' findings prompts to emit the four fields (search `wing-commander-findings` prompts under `.github/workflows/`).
- [ ] T017 [US2] Update live contract `specs/056-*/contracts/wing-commander-stage-findings.md` for the routing step, summary section and fields (FR-014).

**Checkpoint**: both paths give identical outcomes for the same findings (SC-005); add a parity case to the T006 gate if not already present.

## Phase 5: Polish

- [ ] T018 [P] Update `docs/reference.md` where it lists findings defaults/cap wording (filing now follows the record/drop rule; cap applies after drops).
- [ ] T019 Re-run the quickstart.md scenarios against the fixtures and fix drift; run `python .github/scripts/run-local-gates.py` and `review-step-gating` on the workflow edits until green.

## Phase 6: Maintainer follow-up

- [ ] T020 [maintainer] After the final PR merges, sweep open #889 lines once by the silent/loud rule through `python .github/scripts/board_backlog_edit.py`, ticking (never deleting) each dropped line with its reason, and post one comment on #889 listing them (FR-012).
- [ ] T021 [maintainer] Run `prove-after-merge`: re-drive one lifecycle review gate round and one stage run, and record that the dropped/rejected list rendered on the merged code; measure SC-001 after 30 days.

## Dependencies

- Phase 2 blocks both stories; T002 before T005–T006; T006 before T007.
- US1 and US2 are independent after Phase 2 (different files); T012/T017 follow their story's code.
- Polish follows both stories; Phase 6 follows merge.

## Parallel examples

- After T002: T003 ‖ T004.
- After Phase 2: US1 (T008–T012) ‖ US2 (T013–T017); T015 ‖ T016.

## Implementation strategy

MVP = Phases 1–3 (module + gate + lifecycle review gate). Then US2, then polish. Standing guidance, not tasks: keep the gate suite green after each change and re-run it after any workflow comment edit.
