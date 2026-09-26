---

description: "Task list for Composite Test Harness Gate Discovery"
---

# Tasks: Composite Test Harness Gate Discovery

**Input**: Design documents from `/specs/080-composite-harness-gate-discovery/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/gate-registry-extensions.md, contracts/enforcement-gate-cli.md, quickstart.md

**Tests**: This feature's own testing convention (plan.md "Testing") is
each gate's `--self-test` flag against in-source, checked-in fixtures —
that IS the implementation deliverable FR-010 requires, not a separate
TDD layer, so self-test fixture tasks are listed as implementation tasks
within each story rather than a distinct "tests" sub-phase.

**Organization**: Tasks are grouped by user story (spec.md priorities
P1/P1/P2) to enable independent implementation and testing of each story.
This feature ships no application code — every task edits this
repository's own CI tooling tree (`.github/scripts/`, `.github/workflows/`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are included in every task description

## Path Conventions

Concrete paths from plan.md's Project Structure — no generic template
options apply:

- `.github/scripts/wc_gate_registry.py` — shared discovery module
- `.github/scripts/verify-actions-no-gate-scripts.py` — new gate (US2)
- `.github/scripts/verify-gate-wiring.py` — Gate 10, extended (US1/US2/US3)
- `.github/scripts/run-local-gates.py` — local runner, extended (US1)
- `.github/scripts/dispatch-and-wait-tests/run-tests.sh`,
  `.github/scripts/size-path-backstop-tests/run-tests.sh`,
  `.github/scripts/stage-findings-tests/run-tests.sh` — prose → pointer (US2)
- `.github/workflows/lint-workflows.yml` — new gate's wiring (US2)

---

## Phase 1: Setup (verification of what research.md D1 already claims true — no code change expected)

**Purpose**: Confirm the baseline this feature builds on before writing new
code, so a defect discovered later cannot be mistaken for something this
feature introduced.

- [X] T001 Run `grep -n '".github/actions/\*\*"\|".github/scripts/\*\*"' .github/workflows/lint-workflows.yml` and confirm both patterns already appear in `lint-workflows.yml`'s `pull_request: paths:` list (FR-008; research.md D1; quickstart.md §0). No edit expected — record the result for the PR description.
- [X] T002 Run `python .github/scripts/run-local-gates.py dispatch-and-wait-tests size-path-backstop-tests stage-findings-tests` and confirm all three composite harnesses run locally with CI's own arguments, and separately run `python .github/scripts/verify-gate-wiring.py` and confirm its `check_local_runner_parity()` "ok all N PR-time gate(s) are reproducible locally" line already counts the three harnesses (FR-002/FR-003/FR-005; research.md D1; quickstart.md §0).
- [X] T003 [P] Determine the next unclaimed gate number in `.github/workflows/lint-workflows.yml` (provisionally 99 per research.md D3, since the highest number present at plan time was Gate 98) — record it for T014, and re-verify it against `main` immediately before that task lands, since a concurrent spec may claim it first.

**Checkpoint**: Baseline confirmed. Nothing above should require a code change; if any of T001/T002 fails, that is a defect in the current tree, not a task this feature's plan accounts for.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: `verify-gate-wiring.py` gains the `--self-test` scaffold every
story's fixture tasks (T007, T008, T015, T022, T023) plug into. Gate 10 has
never had a self-test before (research.md D6): it runs live-only today, so
this is new infrastructure, not an extension of existing fixtures.

**⚠️ CRITICAL**: No fixture task below (US1's T007/T008, US2's T015, US3's
T022/T023) can be written until this phase is complete, since they all add
cases to the same `--self-test` dispatcher.

- [ ] T004 Add a `--self-test` argparse flag to `.github/scripts/verify-gate-wiring.py`, refactoring `main()` so every check function it calls takes an optional `root` parameter where it does not already have one (most already do, via `wc_gate_registry`'s existing `root="."` parameters). `--self-test` builds fixture trees under `tempfile.mkdtemp()` using the same `_write`-into-tempdir shape `verify-actions-layer-invariants.py` already uses, and reports pass/fail per fixture. This step only adds the dispatcher and scaffold — no fixture assertions yet; the live (no-flag) run's behavior and output must be unchanged (SC-007). (research.md D6)

**Checkpoint**: `verify-gate-wiring.py --self-test` runs (with zero fixtures asserted yet) and exits 0; the live run is byte-for-byte unchanged from before this task.

---

## Phase 3: User Story 1 - The local suite is a true rehearsal of CI (Priority: P1) 🎯 MVP

**Goal**: Every gate the local runner lists carries an identity unique
across the whole gate population, so the five `.github/scripts/*/run-tests.sh`
harnesses sharing the basename `run-tests.sh` are never conflated in the
local runner's output, its timing cache, its filter arguments, or Gate 10's
attribution of invocations to files (FR-007).

**Independent Test**: Compare the set of gates the local suite runs against
the PR-time gate list CI derives and confirm they are identical (asserted
by a gate, not inspection); confirm every harness in the suite's gate list
is reported under an identity distinct from every other (spec.md
Independent Test, Story 1).

### Implementation for User Story 1

- [ ] T005 [P] [US1] Add `gate_label(script, args, root=".") -> str` to `.github/scripts/wc_gate_registry.py`: `script`'s path relative to `.github/scripts/` — never `os.path.basename`, which "collapses every `.github/scripts/*/run-tests.sh` harness to the identical string `run-tests.sh`" — joined with `args` exactly as the existing inline `label_of` did: `(relative_path + " " + " ".join(args)).strip()`. For a script directly under `.github/scripts/` with no subdirectory, the relative form and the basename must coincide, so this is a drop-in replacement for every gate that was never colliding, not only the ones that were. (contracts/gate-registry-extensions.md `gate_label`; FR-007; research.md D5)
- [ ] T006 [US1] In `.github/scripts/run-local-gates.py`, delete the inline `label_of(script, args)` function and replace every call site with `wc_gate_registry.gate_label(script, args)`: the `--jobs` filter token matching, the timing-cache key used by `_load_timing_cache`/`_save_timing_cache`'s scheduling sort, the serial (`--jobs 1`) PASS/FAIL and header lines, the parallel live-run PASS/FAIL lines, and the final summary table. Output format, the timing-cache file shape, and `--jobs 1`'s byte-identical-output contract must not change — only the *value* of the label changes for the five colliding harnesses. (contracts/gate-registry-extensions.md Call-site changes; FR-007) — depends on T005
- [ ] T007 [US1] Add a fixture to `verify-gate-wiring.py --self-test` (from T004): a fixture pair of harnesses sharing the basename `run-tests.sh` under two different `.github/scripts/<name>-tests/` directories must produce two distinct `gate_label()` identities. (research.md D6, fifth bullet; FR-007) — depends on T004, T005
- [ ] T008 [US1] Add a fixture to `verify-gate-wiring.py --self-test` (from T004): a fixture composite harness at `.github/scripts/<name>-tests/run-tests.sh` with no invoking workflow must report as orphaned by Gate 10's existing forward check — this fixture is what proves FR-003's already-true behaviour is real, not new logic. (research.md D6, first bullet; FR-003) — depends on T004
- [ ] T009 [US1] Run quickstart.md §1 (`python .github/scripts/run-local-gates.py --jobs 1 dispatch-and-wait-tests size-path-backstop-tests stage-findings-tests`, then repeat with all five `*/run-tests.sh` harnesses) and confirm the final table lists distinct identities of the shape `<name>-tests/run-tests.sh` — never a collapsed `run-tests.sh` repeated — with five distinct timing-cache keys. (FR-007; SC-008) — depends on T006

**Checkpoint**: The local runner's gate list, timing cache, and `--jobs` filter all key on `gate_label`, and no two entries share an identity across the whole population (SC-008).

---

## Phase 4: User Story 2 - A harness in the wrong place fails loudly instead of disappearing (Priority: P1) 🎯 MVP

**Goal**: A test harness or standalone gate script placed under
`.github/actions/` (outside `.github/actions/_shared/`) fails a gate that
names the offending path and the supported location, at any depth, read
mechanically off the directory tree rather than a manifest of harness
names (FR-001/FR-006/FR-012/FR-014).

**Independent Test**: Add a `run-tests.sh` under `.github/actions/`, run the
enforcement gate, and confirm it fails naming that file and the supported
location; move the harness to `.github/scripts/<name>-tests/run-tests.sh`
and confirm the gate passes; repeat with a standalone `verify-*.sh`; confirm
a helper under `.github/actions/_shared/` is not flagged (spec.md
Independent Test, Story 2).

### Implementation for User Story 2

- [ ] T010 [P] [US2] Add `unsupported_actions_scripts(root=".") -> list[str]` to `.github/scripts/wc_gate_registry.py`: walks exactly `<root>/.github/actions` (`os.path.join(root, ACTIONS_DIR)`), "never a broader recursive scan from `<root>`" — a sibling `.wing-commander-pipeline/.github/actions/**` tree must be unreachable from this walk by construction, not by an exclusion rule. Matches, at any depth: a file named exactly `run-tests.sh`, or a *standalone* `verify-*.py`/`verify-*.sh` (a `verify-*.py` imported by a sibling `run-tests.sh` in the same directory is part of that harness, not a second violation). Excludes anything whose repo-relative path has `.github/actions/_shared/` as a prefix. Returns repo-relative, forward-slash, sorted paths; returns `[]` when nothing matches. (contracts/gate-registry-extensions.md `unsupported_actions_scripts`; FR-006/FR-012/FR-014; research.md D2)
- [ ] T011 [US2] Create `.github/scripts/verify-actions-no-gate-scripts.py`: argparse CLI with `--root` (default `.`, matching `verify-actions-layer-invariants.py`'s convention) and `--self-test`. Its module docstring carries the ONE canonical explanation FR-009 requires — both reasons a composite's test harness lives under `.github/scripts/<name>-tests/`, never beside the composite: gate discovery reads only that root, and test fixtures stay out of the adopter-pinned composite directories (Constitution VII). Calls `wc_gate_registry.unsupported_actions_scripts(root)`; for each result emits one `::error::` line naming the offending path, whether it is a `run-tests.sh` harness or a standalone `verify-*` script, the supported location computed mechanically from the offending path's own composite-directory name (e.g. `.github/actions/wing-commander-widget/tests/run-tests.sh` → "belongs at `.github/scripts/wing-commander-widget-tests/run-tests.sh` instead"), and a pointer to this same file as the canonical explanation. Prints `verify-actions-no-gate-scripts: <n> unsupported location(s) found under .github/actions/; <n> failure(s).`; exit 1 iff any failure. (contracts/enforcement-gate-cli.md Usage/Inputs/Behavior; FR-006/FR-009) — depends on T010
- [ ] T012 [US2] Implement `verify-actions-no-gate-scripts.py --self-test`, using the same in-tempdir `_write`/`FIXTURES` shape `verify-actions-layer-invariants.py` already uses, covering every fixture in research.md D8: a `run-tests.sh` directly under `.github/actions/<composite>/` (fails); one two levels deep, e.g. `.github/actions/<composite>/tests/nested/run-tests.sh` (fails the same way, proving FR-012's "at any depth"); a standalone `verify-widget.py` AND a standalone `verify-widget.sh` under `.github/actions/<composite>/` (both fail); a helper at `.github/actions/_shared/run-tests.sh` with a name that would otherwise match (NOT flagged, pinned by its own fixture); a composite with no harness at all (clean pass); confirmation the walk is rooted at `<root>/.github/actions` specifically by placing a same-shaped violation outside that directory, e.g. at repo root (correctly ignored). Reports `[ok]`/`[FAIL]` per fixture and a final `x/y fixtures behaved as specified.` line; exit 1 iff any fixture misbehaved. (contracts/enforcement-gate-cli.md Behavior item 5; FR-010/FR-012) — depends on T011
- [ ] T013 [US2] In the same `--self-test`, assert the failure-message contract for each failing fixture: the emitted message must contain, as a substring of the real output — in any order — the literal offending path, the literal substring `.github/scripts/`, and the literal substring `verify-actions-no-gate-scripts.py`. (contracts/enforcement-gate-cli.md "Failure message contract"; FR-006/FR-009) — depends on T012
- [ ] T014 [US2] Wire the new gate into `.github/workflows/lint-workflows.yml`'s existing PR-time job, immediately following Gate 10, as two steps matching every other numbered gate's two-step convention: `Gate <N> — no test harness or standalone gate script lives under .github/actions/` running `python3 .github/scripts/verify-actions-no-gate-scripts.py`, and `Gate <N> self-test — a harness or standalone verify-* script under .github/actions/ (outside _shared/), at any depth, is caught; a _shared/ helper is not` running the same with `--self-test`. Use the gate number re-verified against `main` (T003). No `paths:` filter change — both `.github/actions/**` and `.github/scripts/**` are already listed (T001). (contracts/enforcement-gate-cli.md Wiring; research.md D3) — depends on T003, T012
- [ ] T015 [US2] Add a fixture to `verify-gate-wiring.py --self-test` (from T004): a `run-tests.sh` under `.github/actions/` outside `_shared/`, invoked once by a workflow but NOT wired to `lint-workflows.yml`, must still report correctly as an ordinary orphan by Gate 10's existing forward check — proving Gate 10 and the new placement gate (T011) do not double-report or contradict each other for the same file. (research.md D6, fourth bullet; spec.md Edge Case; Story 2 Acceptance Scenario 4) — depends on T004, T011
- [ ] T016 [P] [US2] In `.github/scripts/dispatch-and-wait-tests/run-tests.sh`, replace the "Lives under .github/scripts/ rather than beside the composite for the reason spelled out once in size-path-backstop-tests/run-tests.sh..." paragraph (lines 10-13) with a single pointer comment in the phrasing Gate 47 (`verify-comment-canonical-pointers.py`) recognises: `-- see verify-actions-no-gate-scripts.py.` (FR-009/FR-011; research.md D7)
- [ ] T017 [P] [US2] In `.github/scripts/size-path-backstop-tests/run-tests.sh`, replace the entire "WHY THIS LIVES UNDER .github/scripts/ AND NOT BESIDE THE COMPOSITE" block (lines 15-24) with the same pointer comment, `-- see verify-actions-no-gate-scripts.py.` (FR-009/FR-011; research.md D7)
- [ ] T018 [P] [US2] In `.github/scripts/stage-findings-tests/run-tests.sh`, replace the "Lives under .github/scripts/stage-findings-tests/ (Maintainer review item 11), not .github/actions/wing-commander-stage-findings/tests/ where it first shipped..." paragraph (lines 9-14) with the same pointer comment, `-- see verify-actions-no-gate-scripts.py.` (FR-009/FR-011; research.md D7)
- [ ] T019 [US2] Run `python .github/scripts/verify-comment-canonical-pointers.py` and confirm it reports no violation for the three new pointer comments; separately, for each of the three harness files, run `git log --oneline -- <file>` and confirm no second full copy of the removed prose was reintroduced. (quickstart.md §5; FR-009/SC-006) — depends on T016, T017, T018, T011

**Checkpoint**: A `run-tests.sh` or standalone `verify-*` script anywhere under `.github/actions/` (outside `_shared/`) fails a gate naming the file and the one canonical home; the three existing harnesses each carry a single pointer comment instead of restating the rationale.

---

## Phase 5: User Story 3 - The reverse direction covers `.github/actions/` paths too (Priority: P2)

**Goal**: A `run:` block naming a `.github/actions/` script path that does
not exist on disk is reported by the wiring gate, the same way it already
is for `.github/scripts/...` paths, including through the self-checkout
prefix a published stage uses (FR-004/FR-013).

**Independent Test**: Point a workflow step at a `.github/actions/` script
path that does not exist on disk and confirm the wiring gate reports it as
missing (spec.md Independent Test, Story 3).

### Implementation for User Story 3

- [ ] T020 [P] [US3] Add `referenced_actions_script_paths(root=".") -> dict[str, list[str]]` to `.github/scripts/wc_gate_registry.py`: identical shape and technique to the existing `referenced_script_paths()`, reusing `_run_text()`'s comment-stripped extraction (so a path named only in a shell comment is never counted), but matching `\.github/actions/[A-Za-z0-9_./-]+` instead of `\.github/scripts/...`. Returns `{path: sorted([workflow, ...])}`. Matches on the substring starting at `.github/actions/` regardless of what precedes it in the source line, so `./.github/actions/_shared/x.sh` and `./.wing-commander-pipeline/.github/actions/_shared/x.sh` both key to the identical string `.github/actions/_shared/x.sh`. (contracts/gate-registry-extensions.md `referenced_actions_script_paths`; FR-004/FR-013; research.md D4)
- [ ] T021 [US3] In `.github/scripts/verify-gate-wiring.py`'s `main()`, alongside the existing `referenced_script_paths()` reverse-direction loop, add a loop over `wc_gate_registry.referenced_actions_script_paths()` that reports a failure for any matched `.github/actions/` path that does not exist on disk, in the same failure-message shape already used for `.github/scripts/` paths. (contracts/gate-registry-extensions.md Call-site changes; FR-004) — depends on T004, T020
- [ ] T022 [US3] Add a fixture to `verify-gate-wiring.py --self-test` (from T004): a fixture `run:` block naming a `.github/actions/` script path with no file on disk must report as missing. (research.md D6, second bullet; FR-004) — depends on T021
- [ ] T023 [US3] Add a fixture to `verify-gate-wiring.py --self-test` (from T004): a fixture pair of `run:` blocks — one `./.github/actions/_shared/x.sh`, one `./.wing-commander-pipeline/.github/actions/_shared/x.sh`, with the same file existing once on disk — must report **one** file, not a spurious second "missing" entry. (research.md D6, third bullet; FR-013) — depends on T021
- [ ] T024 [US3] Run quickstart.md §3: `python .github/scripts/verify-gate-wiring.py --self-test` and `python .github/scripts/verify-gate-wiring.py` both pass, the latter including a clean result against the real `./.wing-commander-pipeline/.github/actions/_shared/...` references already in `auto-update-spec-kit.yml` today. (FR-004/FR-013) — depends on T022, T023

**Checkpoint**: A `.github/actions/` path any workflow's `run:` block names, in either checkout-relative spelling, is checked against disk exactly once.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Whole-suite validation that spans all three stories.

- [ ] T025 Run quickstart.md §4 (placement vs. orphan-hood do not conflate): create `.github/actions/wing-commander-context/tests/run-tests.sh`, confirm `verify-actions-no-gate-scripts.py` fails (placement) while `verify-gate-wiring.py` is unaffected (this path is outside `.github/scripts/`, so Gate 10's forward check has nothing to say about it), then remove the fixture directory. (spec.md Edge Case; Story 2 Acceptance Scenario 4) — depends on T011, T015
- [ ] T026 Run the full suite, `python .github/scripts/run-local-gates.py`, and confirm SC-007: every gate that passed before this feature still passes, no existing gate's subject or arguments changed, and the reported gate count grew by exactly the gates this feature added versus the T001/T002 baseline. (quickstart.md §6; SC-007) — depends on all preceding tasks

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: No dependency on Setup's outcome, but T004 must land before any of T007/T008 (US1), T015 (US2), T022/T023 (US3) are written — they all add cases to the same `--self-test` dispatcher.
- **User Stories (Phase 3-5)**: Each story's new `wc_gate_registry.py` function (T005, T010, T020) has no dependency on the other stories' functions and can be written independently; each story's fixture tasks depend on Phase 2 (T004) plus that story's own new function.
- **Polish (Phase 6)**: Depends on US2 (T011, T015) and, for T026, on every task in the feature.

### User Story Dependencies

- **User Story 1 (P1)**: Independent of US2/US3's new functions; only shares `verify-gate-wiring.py`'s `--self-test` scaffold (Phase 2) as a file, not a functional dependency.
- **User Story 2 (P1)**: Independent of US1/US3's new functions; same file-sharing note applies.
- **User Story 3 (P2)**: Independent of US1/US2's new functions; same file-sharing note applies.

**File-conflict caveat for parallel work**: US1, US2, and US3 each add one function to `.github/scripts/wc_gate_registry.py` (T005, T010, T020) and one fixture set to `.github/scripts/verify-gate-wiring.py`'s `--self-test` (T007/T008, T015, T022/T023). The three stories are independently *testable*, per spec.md, but not independently *mergeable* without conflict if worked concurrently in the same two files — sequence the file-touching tasks across stories, or have one contributor land all three `wc_gate_registry.py` additions together, even if the stories are otherwise parallelizable.

### Within Each User Story

- The shared-module function (T005/T010/T020) precedes the script or gate that calls it.
- Fixture tasks (added to `verify-gate-wiring.py --self-test`) follow both Phase 2's scaffold and that story's own new function.
- Quickstart verification tasks (T009, T019, T024) follow that story's implementation tasks.

### Parallel Opportunities

- T003 (gate-number lookup) can run alongside T001/T002.
- T005, T010, and T020 touch the same file (`wc_gate_registry.py`) but are otherwise independent of each other — safe to write in the same sitting, not safe to land as three simultaneous concurrent edits without merging by hand (see caveat above).
- T016, T017, T018 (the three harness files' prose → pointer) are three different files with no dependency on each other — genuinely parallel.

---

## Parallel Example: User Story 2

```bash
# T016, T017, T018 touch three different files and share no dependency:
Task: "Replace prose with pointer comment in dispatch-and-wait-tests/run-tests.sh"
Task: "Replace prose with pointer comment in size-path-backstop-tests/run-tests.sh"
Task: "Replace prose with pointer comment in stage-findings-tests/run-tests.sh"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

Spec.md weighs Story 2 as "Equal to Story 1 because Story 1 without Story 2
is a one-time repair" — the collision fix (US1) without the enforcement
gate (US2) leaves the next harness free to reintroduce the exact defect
this feature responds to. Treat both P1 stories as the MVP:

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks every story's fixtures)
3. Complete Phase 3: User Story 1 (gate identity)
4. Complete Phase 4: User Story 2 (the enforcement gate + prose consolidation)
5. **STOP and VALIDATE**: run T009 and T019/T025 independently, confirm both
   stories' independent tests from spec.md pass
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → baseline confirmed, self-test scaffold ready
2. Add User Story 1 → gate identity is unique → validate independently
3. Add User Story 2 → placement is enforced, prose has one home → validate
   independently (MVP complete)
4. Add User Story 3 → the reverse check's blind spot closes → validate
   independently
5. Phase 6 → whole-suite regression check (SC-007)

### Task Count Summary

- Setup: 3 tasks (T001-T003)
- Foundational: 1 task (T004)
- User Story 1: 5 tasks (T005-T009)
- User Story 2: 10 tasks (T010-T019)
- User Story 3: 5 tasks (T020-T024)
- Polish: 2 tasks (T025-T026)
- **Total: 26 tasks**

---

## Notes

- No task in this feature widens `gate_scripts()` or adds a manifest of
  harness/gate names — `unsupported_actions_scripts()` (T010) and
  `gate_label()` (T005) are both derived, mechanical answers, matching
  FR-014 and `wc_gate_registry.py`'s own stated philosophy.
- `run-local-gates.py`'s existing "WHAT IT DOES NOT RUN" carve-out
  (gates wired to a workflow other than `lint-workflows.yml`) needs no new
  task: `pr_time_gates()` already filters by workflow membership,
  unconditional on gate shape (research.md D9).
- Every fixture task above is the checked-in artifact FR-010 requires —
  none of this feature's new failure branches may be demonstrated only in
  a PR description.
