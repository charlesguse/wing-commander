# Tasks: Gate the skill scripts' self-tests and cross-tree imports

**Input**: `specs/131-skill-script-gate/` (plan.md, spec.md, research.md, data-model.md, contracts/verify-skill-scripts.md, quickstart.md)

**Tests**: The gate's own `--self-test` with checked-in fixtures is required by FR-006; fixture tasks below are that, not a separate test suite.

**Organization**: By user story. One PR (research D6). Standing guidance, not tasks: run `python .github/scripts/run-local-gates.py` before pushing; the gate suite must stay green; nothing under `.claude/` is edited.

## Format: `- [ ] T### [P?] [Story] Description with path`

## Phase 1: Setup

- [X] T001 Inventory how each `.claude/skills/*/scripts/*.py` reaches `.github/scripts` (`from M import n`, `import M as m`, `sys.path` insertion, `importlib.util.spec_from_file_location`) and which declare `--self-test`; record the exact loader patterns as a comment block at the top of `.github/scripts/verify-skill-scripts.py` (research D2, D3)
- [X] T002 Check which PR-time layout from spec 129 is live in `.github/workflows/lint-workflows.yml` (sharded or single `lint` job), find the next free gate number, and read `docs/reference.md` "Keeping this current" to confirm no category changes (research D5)

---

## Phase 2: Foundational

**Purpose**: Core data and parsing that every story uses.

- [X] T003 Create `.github/scripts/verify-skill-scripts.py` skeleton with discovery of `.claude/skills/*/scripts/*.py` from the tree (no hand list, FR-003), exit 1 on zero scripts, and `Finding` output in the contract format `skill-script: <path>: <module>.<name>: <reason>` plus summary line, per data-model.md `SkillScript` and `Finding` entities (reason values constrained by `Finding.reason`)
- [X] T004 Implement `ModuleNames` extraction in `.github/scripts/verify-skill-scripts.py`: parse `.github/scripts/<module>.py` with `ast` and collect top-level names (def, class, assignment, import-as, `__all__`) per data-model.md `ModuleNames.names`; never import a module (FR-005)

**Checkpoint**: Script discovers and parses; no checks yet.

---

## Phase 3: User Story 1 - A rename that breaks a skill script fails the PR (P1) 🎯 MVP

**Goal**: A removed or renamed cross-tree name, attribute or module fails the gate naming script, module and name.

**Independent Test**: Run the gate on main (passes); rename `diff_name_list` on a scratch copy; it fails naming `redrive_candidates.py` and `diff_name_list`.

- [X] T005 [US1] Implement `Reach` collection in `.github/scripts/verify-skill-scripts.py` for `from M import n`, `import M as m` plus `m.attr` loads, and the recognised dynamic-loader pattern from T001, per data-model.md `Reach.kind` (`from-import`, `attribute`, `module`); an unrecognised loader yields `unrecognised-loader` instead of skipping
- [X] T006 [US1] Implement resolution in `.github/scripts/verify-skill-scripts.py`: stdlib via `sys.stdlib_module_names`, third-party (e.g. `yaml`) never reported as a repo name, a `kind=module` reach passes when the module file exists, a named reach passes when in `ModuleNames.names` or a submodule file; emit `missing-name` / `missing-module` (spec FR-001, FR-002; data-model.md `Reach.name`)
- [X] T007 [P] [US1] Add fixtures under `.github/scripts/verify-skill-scripts-fixtures/`: `bad-missing-name`, `bad-attribute`, `bad-missing-module`, `ok-stdlib-thirdparty`, each a small skill-tree plus module tree
- [X] T008 [US1] Run the gate against the real tree and confirm it passes with all six scripts' reaches counted; fix any false positive in `.github/scripts/verify-skill-scripts.py`

**Checkpoint**: Imports gate works standalone.

---

## Phase 4: User Story 2 - A skill script's self-test runs on every PR (P2)

**Goal**: Every script that accepts `--self-test` has it run offline; failure fails the gate.

**Independent Test**: Break `thrash_signals.py`'s expected value on a scratch copy; the gate fails with `self-test-failed`.

- [X] T009 [US2] Implement `has_self_test` detection by AST (string constant `"--self-test"` in `add_argument` or an `argv` comparison, research D3) in `.github/scripts/verify-skill-scripts.py`
- [X] T010 [US2] Implement the self-test runner in `.github/scripts/verify-skill-scripts.py`: subprocess `<script> --self-test` at repo root, `GH_TOKEN`/`GITHUB_TOKEN` unset, 60 s timeout, non-zero exit or timeout yields `self-test-failed`; print the clean summary `OK (<S> scripts, <R> reaches, <T> self-tests)` (FR-004, FR-005, research D7)
- [X] T011 [P] [US2] Add fixtures `bad-self-test` and `ok-self-test` under `.github/scripts/verify-skill-scripts-fixtures/`

**Checkpoint**: Gate default mode complete.

---

## Phase 5: User Story 3 - The check cannot go blind (P3)

**Goal**: The gate's `--self-test` proves it fails each seeded defect and discovers new scripts.

**Independent Test**: `python3 .github/scripts/verify-skill-scripts.py --self-test` exits 0; weakening any check makes it exit 1.

- [X] T012 [US3] Implement `--self-test` in `.github/scripts/verify-skill-scripts.py` covering all seven contract cases: removed name, removed attribute, removed module, failing skill self-test, new script discovered without a gate edit, stdlib/third-party-only passes, empty skill tree fails loudly (FR-006)
- [X] T013 [US3] Wire two steps into the `lint` job (or the shard T002 found) of `.github/workflows/lint-workflows.yml`, each `if: "!cancelled()"`, with unique names `Gate NNN — skill scripts' cross-tree names resolve and their self-tests pass` and `Gate NNN fixtures — verify-skill-scripts self-test`; add no `paths:` entry (already covered, FR-008, FR-011)
- [X] T014 [US3] Run `python .github/scripts/run-local-gates.py` and confirm both new steps are derived and pass with no registry edit (FR-007); fix any gate that the new steps or fixtures trip (comment-pointer, waiver, single-home checks)
- [X] T015 [US3] Edit `docs/reference.md` only if T002 found a "Keeping this current" category changed; otherwise skip and note it in the PR body

---

## Phase 6: Polish

- [X] T016 Verify run time of both steps is under one minute (SC-004) and the PR stays within the board's size-and-path backstop; trim fixtures if not
- [X] T017 Walk `specs/131-skill-script-gate/quickstart.md` against the implemented gate and correct the live contract `specs/131-skill-script-gate/contracts/verify-skill-scripts.md` if behaviour differs

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

## Review Gate Round 1 Findings

- [X] Review finding: Local sys.path insert causes false missing-module

  inserts_scripts_path returns True for any sys.path.insert/append, so a skill script importing a sibling helper from its own scripts dir gets a false missing-module finding and CI goes red.

  - .github/scripts/verify-skill-scripts.py

  Detail: Resolve the inserted path and only set scripts_on_path when it points at .github/scripts.

- [X] Review finding: Third-party allowlist built only from repo script imports

  A skill script importing a legitimate third-party package that no .github/scripts file imports is reported as missing-module when it also inserts a path, contradicting the contract.

  - .github/scripts/verify-skill-scripts.py

  Detail: Also try importlib.util.find_spec, or only fail names that look repo-local.

- [X] Review finding: Attribute check is unscoped and checks dunder attributes

  The alias map is file-global, so a parameter or local that shares an alias name, or a dunder access such as mod.__name__, produces false missing-name findings.

  - .github/scripts/verify-skill-scripts.py

  Detail: Skip dunder attributes and drop aliases that are rebound elsewhere in the file.

- [X] Review finding: module_names misses for/with/walrus/match/TryStar bindings

  Names bound by for targets, with-as targets, walrus, match bodies or TryStar are not collected, so a valid from-import of them is reported as missing-name.

  - .github/scripts/verify-skill-scripts.py

  Detail: Add For.target and withitem.optional_vars, and recurse into match cases and TryStar.

- [X] Review finding: Self-test failure discards output

  run_self_test_of drops stdout and stderr, so a timeout and a non-zero exit both give a bare self-test-failed with no diagnostics.

  - .github/scripts/verify-skill-scripts.py

  Detail: Print the tail of the captured output or a timeout message.

- [X] Review finding: Gate self-test lacks unrecognised-loader and SyntaxError cases

  No seeded case covers unrecognised-loader, the timeout path or a SyntaxError script, and check crashes with a traceback on a syntax error instead of a structured finding.

  - .github/scripts/verify-skill-scripts.py

  Detail: Add the fixtures, and catch SyntaxError in check.

- [X] Review finding: Dynamic-loader module attributes are not checked

  spec_from_file_location is counted only as a module reach and no alias is recorded for the loaded module, so a renamed attribute reached through a dynamic loader goes undetected.

  - .github/scripts/verify-skill-scripts.py

  Detail: Record the assignment target of module_from_spec as an alias, or fail with unrecognised-loader.

## Review Gate Round 2 Findings

- [ ] Review finding: Skill-local sys.path insert mistaken for .github/scripts

  inserts_scripts_path accepts any literal "scripts" path part, so a skill-local scripts dir makes sibling helper imports report missing-module and fail the gate.

  - .github/scripts/verify-skill-scripts.py

  Detail: Require literal ".github" then "scripts", or resolve the path. Add an ok- fixture for a skill-local scripts dir.

- [ ] Review finding: Third-party allowlist hides a deleted repo module

  third_party_names counts any non-stdlib import in any .github/scripts file as third-party, so a leftover try/except import of a deleted module makes the skill script's import pass.

  - .github/scripts/verify-skill-scripts.py

  Detail: Build the allowlist from names that are not importable and not repo-shaped, or rely on find_spec.

- [ ] Review finding: SyntaxError in a target module crashes the gate

  module_names(mpath) parses a target .github/scripts module with no handler, so a syntax error there produces a traceback instead of a structured finding.

  - .github/scripts/verify-skill-scripts.py

  Detail: Catch SyntaxError, ValueError and UnicodeDecodeError around module_names and around the skill-script parse.

- [ ] Review finding: Alias rebinding disables attribute checks file-wide

  The rebound set covers any arg, Name Store or loop variable file-wide, so one parameter named like an alias turns off attribute checking for every use of that alias.

  - .github/scripts/verify-skill-scripts.py

  Detail: Scope the rebinding check to the enclosing function, or fail loudly when an alias is dropped.

- [ ] Review finding: Self-test uses subset matching and does not assert reach or self-test counts

  bad-* cases pass even with spurious findings, and ok-self-test and the ok- import cases pass even if has_self_test or collect_reaches finds nothing.

  - .github/scripts/verify-skill-scripts.py

  Detail: Assert exact reason sets for bad-* cases. Assert selftests == 1 for ok-self-test and reaches > 0 for the ok- import cases.

- [ ] Review finding: module_names misses some module-level bindings

  The walrus scan breaks at the first Lambda or def, and match capture patterns and global-assigned names are not collected, which gives false missing-name findings.

  - .github/scripts/verify-skill-scripts.py

  Detail: Use a visitor that skips nested scopes instead of break. Collect MatchAs and MatchStar names and Global assignments.

- [ ] Review finding: Live contract lacks syntax-error and no-skill-scripts reasons

  The contract lists four reasons while the code also emits syntax-error and no-skill-scripts, and prints '-.-' where the contract format is <module>.<name>. The data-model line also omits the colon.

  - specs/131-skill-script-gate/contracts/verify-skill-scripts.md

  Detail: Add the two reasons and the '-' placeholder to the contract and data-model.

- [ ] Review finding: Self-test summary count is wrong and fixture output is noisy

  It prints len(SEEDED)+1 cases but 15 checks run, and a failing seeded skill self-test prints to stdout during a passing run, so the log looks like failures.

  - .github/scripts/verify-skill-scripts.py

  Detail: Count the cases accurately and capture or suppress per-script output in fixture mode.
