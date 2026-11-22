# Tasks: One Reviewer for Every Kind of Pull Request

**Input**: Design documents from `/specs/127-shared-pr-reviewer/` (plan.md, spec.md, research.md, data-model.md, contracts/round-record.md, quickstart.md)

**Tests**: Requested by the plan (fixtures for every Story/SC case, Principle VIII). Test tasks come before the code they cover and must fail first.

**Organization**: By user story. Logic lives in one module, `.github/scripts/wc_shared_review.py`; workflows stay thin (research D2). Run `python .github/scripts/run-local-gates.py` before each push; that is a standing duty, not a task. A change touching an `if:`, `continue-on-error:` or failing step also gets a `review-step-gating` pass, and a `container:` block or a `run:` step inside one gets a `container-shell-safety` pass.

Field constraints are those of `data-model.md`; tasks cite the `Entity.field` they implement rather than restating it.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Create the empty module `.github/scripts/wc_shared_review.py` (imports `board_item_marker.marker_json`, `last_marker_match`, `is_loop_marker_author`, and `wc_review_finding_fingerprint`) and the empty `.github/scripts/tests/test_wc_shared_review.py`
- [x] T002 [P] Locate the gate registry and the published-contract enumeration the contract gate uses (research D3) and note the registration form for an unpublished callable workflow in a comment atop `.github/scripts/wc_shared_review.py`

---

## Phase 2: Foundational (blocking)

**Purpose**: record format and marker that every story reads or writes.

- [x] T003 Write fixture tests in `.github/scripts/tests/test_wc_shared_review.py` for record build/parse round trip with marker `wing-commander-shared-review-round`, `-->` escaping, last-opener-wins, bot-authored-only, and the size cap that never truncates `RoundRecord.open_set` (data-model.md `RoundRecord.open_set`)
- [x] T004 Implement `build_record`, `parse_records` and the `handoff` marker kind in `.github/scripts/wc_shared_review.py` per `contracts/round-record.md` and data-model.md `RoundRecord.schema`, `RoundRecord.reviewer`, `RoundRecord.round`, `RoundRecord.verdict`, `HandoffRecord` (no `verdict` field)
- [x] T005 [P] Add a test in `.github/scripts/tests/test_wc_shared_review.py` that `read_round_records` in `.github/scripts/wc_convergence.py` counts zero shared-reviewer records and that the gate's convergence count is unchanged (Story 3 scenario 4)
- [x] T006 [P] Write `.github/scripts/verify-shared-review-marker-disjoint.py` asserting the marker name differs from `ROUND_MARKER` and matches no pattern in `wc_convergence.py`; register it in the gate registry found in T002

**Checkpoint**: records can be built, parsed, and are invisible to spec 116 readers.

---

## Phase 3: User Story 1 - Review a session's fix PR, report-only (P1) 🎯 MVP

**Goal**: one dispatch on a fix PR produces one record via guard → prepare → code-run → find → check → record, writing nothing else.

**Independent Test**: dispatch on a fix PR with a known originating issue; one record with commit, verdict, round, findings, reviewer commit and run id; no push, label, merge or approval.

### Tests for User Story 1

- [x] T007 [P] [US1] Tests in `.github/scripts/tests/test_wc_shared_review.py` for `compute_verdict` in FR-014 order: agent failure → `incomplete`; blocking open finding → `findings` even with code-run missing; code-run missing otherwise → `incomplete`; undetermined answer or no purpose source → `undetermined`; all positive → `clean`; an earlier-round still-open blocking finding counts (SC-004 tail)
- [x] T008 [P] [US1] Tests for the blocking rule (`Finding.blocking`, `Finding.in_scope`, `Finding.reachable`, `Finding.failing_case` in data-model.md): absent failing case → dismissed; merged-spec-doc-only finding → dismissed with reason; contracts under `specs/*/contracts/` stay reviewable
- [x] T009 [P] [US1] Tests for request validation: `ReviewRequest.kind` derived by code from the PR head branch/labels, non-fix kinds refused (FR-001), `ReviewRequest.purpose_source` resolution order and the "no source of purpose" case (research D10)
- [x] T010 [P] [US1] Seeded-case fixtures for SC-005 (added check passes without the fix → upheld finding, verdict not clean) and SC-006 (checking job dismisses an unreproducible breakage claim) in `.github/scripts/tests/test_wc_shared_review.py`

### Implementation for User Story 1

- [x] T011 [US1] Implement `compute_verdict`, the blocking rule and the spec-doc dismissal rule in `.github/scripts/wc_shared_review.py` (FR-013, FR-014; data-model.md `Finding.blocking`, `Finding.status`, `PurposeAnswers`, `CodeRunResults.status`)
- [x] T012 [US1] Implement request validation, kind derivation and purpose-source resolution (including failing-run step results and error messages, FR-007, and the "version used" note) in `.github/scripts/wc_shared_review.py`
- [x] T013 [US1] Add the thin CLI subcommands the workflow calls (`prepare`, `validate-output`, `record`) in `.github/scripts/wc_shared_review.py`
- [x] T014 [US1] Create callable workflow `.github/workflows/shared-pr-reviewer.yml` (`on: workflow_call`, typed inputs, no `vars`/`github.event` reads) with jobs `guard`, `prepare`, `record`, gated per the `review-step-gating` skill; `record` is the only poster and the only holder of the App token
- [x] T015 [US1] Add the `code-run` job to `.github/workflows/shared-pr-reviewer.yml`: `permissions: {}`, no `secrets` reference, PR tree received as a tarball artifact from `prepare`, runs exactly the discovered named check and the default branch's `run-local-gates.py` against the PR tree, exit codes staged as data (never a job failure), timeouts, one JSON artifact (research D8); apply `container-shell-safety` if a container is used
- [x] T016 [P] [US1] Write the find prompt (purpose questions in FR-008 order a–d; PR description framed as the author's claim; untrusted text as delimited data; may cite earlier ids) and its output schema as default-branch files under `.github/prompts/` or inline in the callable workflow
- [x] T017 [P] [US1] Write the check prompt and schema (re-checks every open finding: confirm or resolve, or "not re-checked: code-run results missing"; reports `in_scope`, `reachable`, `reproduces`, `cites_only_spec_docs`) in the same location as T016
- [x] T018 [US1] Add `find` and `check` jobs to `.github/workflows/shared-pr-reviewer.yml`: `claude-code-action`, models from inputs defaulting `claude-sonnet-5-5`, explicit `--max-turns` (default 40/40), no effort override, read-only tools from the `wing-commander-tool-args` composite, no web tools, no write token; `check` shares no context with `find` (FR-010, FR-024, FR-027)
- [x] T019 [US1] Create wrapper `.github/workflows/wing-commander-shared-pr-reviewer.yml`: `workflow_dispatch` with `pr` and optional `dismissals` JSON, reads `vars.*`, per-PR `concurrency` group `shared-pr-reviewer-<pr>` with `cancel-in-progress: false` (FR-026, FR-003)
- [x] T020 [US1] Register `shared-pr-reviewer.yml` as internal/unpublished with its reason using the form found in T002 (Principle VII; spec FR-002)

**Checkpoint**: a round can run end to end on a fix PR; US1 is demonstrable (MVP).

---

## Phase 4: User Story 2 - A later round remembers earlier rounds (P1)

**Goal**: identity survives rewording, dismissals persist, the open set is folded deterministically.

**Independent Test**: seeded round 1 → round 2 per Story 2 scenarios 1-8 and SC-004.

- [x] T021 [P] [US2] Tests in `.github/scripts/tests/test_wc_shared_review.py` for identity assignment: cited existing id kept; cited unknown id ignored → new id; uncited overlap (same file, overlapping lines) → new id with `Finding.possible_repeat_of`, never merged on location alone (`Finding.id`, `Finding.cites`, `Finding.possible_repeat_of` in data-model.md)
- [x] T022 [P] [US2] Tests for the FR-015 transition table including every rejected transition, reopening only when the checker upholds a showing, re-raise without showing stays dismissed, and `Finding.note` "not re-checked: code-run results missing" leaving status unchanged
- [x] T023 [P] [US2] Tests for open-set folding over confirmed records in round order, requester dismissals applied from the start of their round, dismissal-shaped comments (from anyone, requester included) ignored (Story 2 scenario 8), and `ReviewRequest.dismissals` ids not open at round start dropped with a note
- [x] T024 [US2] Implement identity assignment (`F<round>-<n>`), overlap flagging, the transition table enforcement, and `open_set` fold in `.github/scripts/wc_shared_review.py` (FR-015..FR-018; data-model.md `Finding.status`, `Finding.reason`)
- [x] T025 [US2] Make `prepare` assemble earlier confirmed findings (identity, status, reason, possible-repeat flags) as the find and check jobs' memory input in `.github/scripts/wc_shared_review.py` and `.github/workflows/shared-pr-reviewer.yml`
- [x] T026 [US2] Add the seeded two-round fixture for SC-004 (reworded repeat, dismissed re-raise, resolved by fix commit, still-reproducing finding yields `findings` with nothing new, code-run crash keeps open blocking finding and verdict `findings`) to `.github/scripts/tests/test_wc_shared_review.py`

**Checkpoint**: rounds converge on identity; US1 and US2 both work.

---

## Phase 5: User Story 3 - One readable record per round, counted only when confirmed (P2)

**Goal**: a record counts only after its run is read back and confirmed.

**Independent Test**: forged or mismatched records report unconfirmed; a genuine one confirms.

- [x] T027 [P] [US3] Tests for `confirm_record` covering SC-002: wrong workflow, wrong branch, wrong reviewer commit, missing or non-digit run id, unfetchable run, not completed/success, missing `shared-review-<head_sha>` artifact, `referenced_workflows` lacking the callable workflow (research D5)
- [x] T028 [US3] Implement `confirm_record` mirroring `verification_run_confirms` in `.github/scripts/board_merge.py` (read only; do not edit that file) in `.github/scripts/wc_shared_review.py`, and the latest-round-for-commit selector (Story 3 scenario 3)
- [x] T029 [US3] Upload artifact `shared-review-<head_sha>` from the `record` job in `.github/workflows/shared-pr-reviewer.yml`; ensure the record names the commit actually reviewed, not a newer head, and carries `RoundRecord.pr_state`, `RoundRecord.reviewer_commit` and `RoundRecord.run_id`
- [x] T030 [P] [US3] Implement `.github/scripts/shared_review_compare.py` listing, per fix PR, the confirmed record and the hand-review comment at the same head (FR-029, SC-007), with a test in `.github/scripts/tests/test_shared_review_compare.py`
- [x] T031 [US3] Add the fixed human header line `Shared reviewer — round N at <short sha> — verdict V` above the marker in `.github/scripts/wc_shared_review.py` (research D11)

**Checkpoint**: only confirmed records feed memory and readers.

---

## Phase 6: User Story 4 - The reviewer cannot be brought by the PR it reviews (P2)

**Goal**: default-branch-only, secret-free code-run, agents without write credentials.

**Independent Test**: non-default ref dispatch ends with no agent, no record, a stated refusal; hostile fixture changes nothing.

- [x] T032 [P] [US4] Tests for the `guard` decision (non-default ref refused; non-fix kind refused; kill switch stop; each writes no record and states the refusal in the run summary only) in `.github/scripts/tests/test_wc_shared_review.py`
- [x] T033 [US4] Implement the `guard` job logic in `.github/workflows/shared-pr-reviewer.yml` and the CLI: compare `github.ref` to the default branch input, fail closed, kill switch `WING_COMMANDER_SHARED_REVIEWER_PAUSED`; all scripts and prompts come from the default branch SHA checkout, the PR head only as data (D4)
- [x] T034 [P] [US4] Create the hostile fixture PR tree under `.github/scripts/tests/fixtures/shared-review-hostile/` whose named check tries `env`, `$ACTIONS_*`, writing into the artifact directory, and running a third command
- [x] T035 [US4] Write `.github/scripts/verify-shared-review-isolation.py` asserting SC-008 (a)-(d): `code-run` has `permissions: {}` and references no secret; staged JSON is unaffected by overwrite attempts; only the two allowed commands exist; neither agent job has a write token, web tool or extra Bash tool; register it in the gate registry
- [x] T036 [P] [US4] Write `.github/scripts/verify-shared-review-wiring.py` asserting `record` is the only poster, downstream jobs depend on `guard` output, the models/turns are explicit, and the kill switch and per-PR concurrency are present; register it

**Checkpoint**: trust boundaries are machine-checked.

---

## Phase 7: User Story 5 - A bounded, legible stop (P3)

**Goal**: after the budget, no agent runs and a hand-off record lists the open set.

**Independent Test**: dispatch until the budget is spent, then once more.

- [x] T037 [P] [US5] Tests for budget counting over confirmed rounds (including `incomplete`), default 5, override via `WING_COMMANDER_SHARED_REVIEW_ROUND_BUDGET`, and the hand-off record carrying the last confirmed round's open set and no verdict
- [x] T038 [US5] Implement budget and hand-off building in `.github/scripts/wc_shared_review.py` (FR-025; data-model.md `HandoffRecord`) and route `guard` to skip agents and post the hand-off through `record`

**Checkpoint**: all stories functional.

---

## Phase 8: Polish & Cross-Cutting

- [x] T039 [P] Add the one fix-PR line to CLAUDE.md's fix-PR section exactly as in the spec Scope (FR-004): "A session dispatches the shared reviewer on each of its fix PRs, on the head its hand review covers, during report-only use."
- [x] T040 [P] Update `docs/reference.md` with the loop row, defaults (models, turns 40/40, budget 5), limits and the kill switch, per its rule on which changes must update it
- [x] T041 Confirm the existing reviewers and `review-until-clean` are untouched (FR-005, FR-028): add a check to the nearest existing gate or `verify-shared-review-wiring.py` that no existing workflow or skill reads the shared verdict
- [x] T042 Walk quickstart.md steps 1-3 and 5-6 locally with fixtures; run `python .github/scripts/run-local-gates.py`; get the `review-step-gating` and `container-shell-safety` skill passes on the new workflows

---

## Phase 9: Maintainer follow-up

- [ ] T043 [maintainer] Set the repository variables the wrapper reads (models, turn budgets, round budget, `WING_COMMANDER_SHARED_REVIEWER_PAUSED`) if non-default values are wanted
- [ ] T044 [maintainer] After merge, dispatch a live round on a session fix PR from `main` and run the `prove-after-merge` check (quickstart step 4; SC-001)
- [ ] T045 [maintainer] Merge the final PR (it changes CLAUDE.md, the rules agents run under)

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. US1 first (MVP). US2 builds on US1's module and prepare job. US3 needs T004 and the `record` job from US1. US4 needs the US1 workflow. US5 needs US3's confirmation and US2's open set.
- Polish after all stories; Maintainer follow-up last.
- Same-file edits to `wc_shared_review.py` and `shared-pr-reviewer.yml` are sequential; tasks marked [P] touch different files.

## Parallel Examples

- US1 tests: T007, T008, T009, T010 together; prompts T016, T017 together.
- US2 tests: T021, T022, T023 together.
- US4: T034 and T036 together with T032.

## Implementation Strategy

MVP is Phases 1-3 (US1): a report-only round runs end to end. Then US2 (memory, also P1), US3 (confirmation), US4 (isolation proofs), US5 (budget), polish. Each story is verified by its fixtures before the next starts.

## Phase 10: Convergence

- [x] T046 Add an "unpublished callable" exclusion form (a registry with a reason per entry, read by `wc_published_stages.py` and by Gates 7, 22, 23, 12, `verify-stage-tool-lists.py` and `verify-stage-shell-lint.py`'s inline derivations) so `shared-pr-reviewer.yml` can exist without being a published stage, per FR-002 and T020 (missing)
- [x] T047 Move the parked drafts `specs/127-shared-pr-reviewer/draft-shared-pr-reviewer.yml.txt` and `draft-wing-commander-shared-pr-reviewer.yml.txt` to `.github/workflows/shared-pr-reviewer.yml` and `wing-commander-shared-pr-reviewer.yml` once T046 lands, then finish T014, T015, T018, T019, T025, T029, T033 against them and rerun the gate suite (partial)
