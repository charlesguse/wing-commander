# Tasks: Gate the skill scripts' self-tests and cross-tree imports

**Input**: `specs/131-skill-script-gate/` (plan.md, spec.md, research.md, data-model.md, contracts/verify-skill-scripts.md, quickstart.md)

**Tests**: The gate's own `--self-test` with checked-in fixtures is required by FR-006; fixture tasks below are that, not a separate test suite.

**Organization**: By user story. One PR (research D6). Standing guidance, not tasks: run `python .github/scripts/run-local-gates.py` before pushing; the gate suite must stay green; nothing under `.claude/` is edited.

## Format: `- [ ] T### [P?] [Story] Description with path`

## Phase 1: Setup

- [ ] T001 Inventory how each `.claude/skills/*/scripts/*.py` reaches `.github/scripts` (`from M import n`, `import M as m`, `sys.path` insertion, `importlib.util.spec_from_file_location`) and which declare `--self-test`; record the exact loader patterns as a comment block at the top of `.github/scripts/verify-skill-scripts.py` (research D2, D3)
- [ ] T002 Check which PR-time layout from spec 129 is live in `.github/workflows/lint-workflows.yml` (sharded or single `lint` job), find the next free gate number, and read `docs/reference.md` "Keeping this current" to confirm no category changes (research D5)

---

## Phase 2: Foundational

**Purpose**: Core data and parsing that every story uses.

- [ ] T003 Create `.github/scripts/verify-skill-scripts.py` skeleton with discovery of `.claude/skills/*/scripts/*.py` from the tree (no hand list, FR-003), exit 1 on zero scripts, and `Finding` output in the contract format `skill-script: <path>: <module>.<name>: <reason>` plus summary line, per data-model.md `SkillScript` and `Finding` entities (reason values constrained by `Finding.reason`)
- [ ] T004 Implement `ModuleNames` extraction in `.github/scripts/verify-skill-scripts.py`: parse `.github/scripts/<module>.py` with `ast` and collect top-level names (def, class, assignment, import-as, `__all__`) per data-model.md `ModuleNames.names`; never import a module (FR-005)

**Checkpoint**: Script discovers and parses; no checks yet.

---

## Phase 3: User Story 1 - A rename that breaks a skill script fails the PR (P1) 🎯 MVP

**Goal**: A removed or renamed cross-tree name, attribute or module fails the gate naming script, module and name.

**Independent Test**: Run the gate on main (passes); rename `diff_name_list` on a scratch copy; it fails naming `redrive_candidates.py` and `diff_name_list`.

- [ ] T005 [US1] Implement `Reach` collection in `.github/scripts/verify-skill-scripts.py` for `from M import n`, `import M as m` plus `m.attr` loads, and the recognised dynamic-loader pattern from T001, per data-model.md `Reach.kind` (`from-import`, `attribute`, `module`); an unrecognised loader yields `unrecognised-loader` instead of skipping
- [ ] T006 [US1] Implement resolution in `.github/scripts/verify-skill-scripts.py`: stdlib via `sys.stdlib_module_names`, third-party (e.g. `yaml`) never reported as a repo name, a `kind=module` reach passes when the module file exists, a named reach passes when in `ModuleNames.names` or a submodule file; emit `missing-name` / `missing-module` (spec FR-001, FR-002; data-model.md `Reach.name`)
- [ ] T007 [P] [US1] Add fixtures under `.github/scripts/verify-skill-scripts-fixtures/`: `bad-missing-name`, `bad-attribute`, `bad-missing-module`, `ok-stdlib-thirdparty`, each a small skill-tree plus module tree
- [ ] T008 [US1] Run the gate against the real tree and confirm it passes with all six scripts' reaches counted; fix any false positive in `.github/scripts/verify-skill-scripts.py`

**Checkpoint**: Imports gate works standalone.

---

## Phase 4: User Story 2 - A skill script's self-test runs on every PR (P2)

**Goal**: Every script that accepts `--self-test` has it run offline; failure fails the gate.

**Independent Test**: Break `thrash_signals.py`'s expected value on a scratch copy; the gate fails with `self-test-failed`.

- [ ] T009 [US2] Implement `has_self_test` detection by AST (string constant `"--self-test"` in `add_argument` or an `argv` comparison, research D3) in `.github/scripts/verify-skill-scripts.py`
- [ ] T010 [US2] Implement the self-test runner in `.github/scripts/verify-skill-scripts.py`: subprocess `<script> --self-test` at repo root, `GH_TOKEN`/`GITHUB_TOKEN` unset, 60 s timeout, non-zero exit or timeout yields `self-test-failed`; print the clean summary `OK (<S> scripts, <R> reaches, <T> self-tests)` (FR-004, FR-005, research D7)
- [ ] T011 [P] [US2] Add fixtures `bad-self-test` and `ok-self-test` under `.github/scripts/verify-skill-scripts-fixtures/`

**Checkpoint**: Gate default mode complete.

---

## Phase 5: User Story 3 - The check cannot go blind (P3)

**Goal**: The gate's `--self-test` proves it fails each seeded defect and discovers new scripts.

**Independent Test**: `python3 .github/scripts/verify-skill-scripts.py --self-test` exits 0; weakening any check makes it exit 1.

- [ ] T012 [US3] Implement `--self-test` in `.github/scripts/verify-skill-scripts.py` covering all seven contract cases: removed name, removed attribute, removed module, failing skill self-test, new script discovered without a gate edit, stdlib/third-party-only passes, empty skill tree fails loudly (FR-006)
- [ ] T013 [US3] Wire two steps into the `lint` job (or the shard T002 found) of `.github/workflows/lint-workflows.yml`, each `if: "!cancelled()"`, with unique names `Gate NNN — skill scripts' cross-tree names resolve and their self-tests pass` and `Gate NNN fixtures — verify-skill-scripts self-test`; add no `paths:` entry (already covered, FR-008, FR-011)
- [ ] T014 [US3] Run `python .github/scripts/run-local-gates.py` and confirm both new steps are derived and pass with no registry edit (FR-007); fix any gate that the new steps or fixtures trip (comment-pointer, waiver, single-home checks)
- [ ] T015 [US3] Edit `docs/reference.md` only if T002 found a "Keeping this current" category changed; otherwise skip and note it in the PR body

---

## Phase 6: Polish

- [ ] T016 Verify run time of both steps is under one minute (SC-004) and the PR stays within the board's size-and-path backstop; trim fixtures if not
- [ ] T017 Walk `specs/131-skill-script-gate/quickstart.md` against the implemented gate and correct the live contract `specs/131-skill-script-gate/contracts/verify-skill-scripts.md` if behaviour differs

---

## Phase 7: Maintainer follow-up

- [ ] T018 [maintainer] Close PR #1205 with a pointer to lifecycle #1206 (FR-009)
- [ ] T019 [maintainer] After merge, tick Maintenance backlog line `bl-ddabf5f6` through `python .github/scripts/board_backlog_edit.py` (FR-009, SC-005)
- [ ] T020 [maintainer] After merge, re-drive one lint-workflows run and confirm both new steps ran on main (`prove-after-merge`)

---

## Dependencies & Execution Order

- T001, T002 first; T003 → T004 → US1 (T005 → T006 → T008). T007 parallel with T005/T006 (different files).
- US2 (T009 → T010) depends on T003; T011 parallel. US1 and US2 touch the same script, so sequence their code tasks.
- US3 depends on US1 and US2 (T012 needs fixtures from T007, T011); T013 after T012; T014 after T013.
- Maintainer phase after merge.

## Parallel Example

T007 (import fixtures) and T011 (self-test fixtures) can be written in parallel with the script code.

## Implementation Strategy

MVP = Phase 1–3 (import resolution catches renames, the defect itself). Ship as one PR with US2 and US3, since a half-gate on main is worse (research D6). Totals: 20 tasks — Setup 2, Foundational 2, US1 4, US2 3, US3 4, Polish 2, Maintainer 3.
