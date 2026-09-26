---

description: "Task list for 082-script-grant-existence-scope"
---

# Tasks: Every Granted Script Is Checked, Not Just The `.specify` Ones At Composite Call Sites

**Input**: Design documents from `/specs/082-script-grant-existence-scope/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/gate-27-extension.md, contracts/waiver-schema.md, quickstart.md (all present and read)

**Tests**: Not a separate test suite — this feature's "tests" ARE its `--self-test` mutations (Constitution VIII). No `tests/` tree exists or is created; every verification task edits `self_test()` in the one gate script.

**Organization**: Tasks are grouped by user story (spec.md's P1/P2/P3), on top of one Foundational phase that all three stories build on.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)
- Include exact file paths in descriptions

## Path Conventions

This is not an application with a `src/`/`tests/` split — it is a GitHub
Actions gate script. Every task below edits one of exactly two files:

- `.github/scripts/verify-stage-tool-lists.py` (Gate 27 — the only code file)
- `.github/scripts/script-grant-waivers.json` (new data file)

No other file changes (per plan.md's Summary: "No workflow file needs an
edit"). Because nearly every task edits the *same* file, most tasks are
necessarily sequential — see "Parallel Opportunities" below for the one real
exception.

---

## Phase 1: Setup

**Purpose**: Establish the pre-change regression baseline this feature's
edits must not break (FR-014).

- [X] T001 Run `python3 .github/scripts/verify-stage-tool-lists.py --self-test` and `python3 .github/scripts/verify-stage-tool-lists.py` against the unmodified tree and confirm both exit 0 — this is the "other checks unchanged" baseline every later task's self-test additions are compared against (FR-014). No file is edited by this task.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared substrate every user story's collector or check
depends on — the workflow loader, the generalized path classifier, and the
waiver file/loader. `⚠️ CRITICAL`: research.md D0's refreshed inventory found
that grants needing a waiver already exist at the **composite** surface
(three `.wing-commander-pipeline/...` sites) — the surface User Story 1
alone widens — so the waiver mechanism must land before US1's checkpoint can
honestly claim the real repository stays green, not only after US2/US3.

- [X] T002 Add `_load_workflows(root=".")` to `.github/scripts/verify-stage-tool-lists.py` per contracts/gate-27-extension.md §1: glob `WORKFLOW_DIR`/`WORKFLOW_GLOBS` once, `yaml.safe_load` each file, catch `yaml.YAMLError` per file and append `"{file} could not be parsed as YAML and was skipped: {error}"` to an error list instead of raising (FR-009, research.md D6), returning `({path: parsed_doc}, [error, ...])`.
- [X] T003 Refactor `collect_sites()` in `.github/scripts/verify-stage-tool-lists.py` to read from the `docs` map `_load_workflows()` (T002) returns instead of its own inline glob-and-`yaml.safe_load` loop, keeping its per-file `for job in ... for step in ...` body, its `step-label` duplicate-detection error message, and its return shape (`{step-label: (allowed, disallowed)}, [error, ...]`) byte-for-byte unchanged (research.md D2).
- [X] T004 Replace `SCRIPT_GRANT` and its hardcoded `\.specify/scripts/bash/` prefix in `.github/scripts/verify-stage-tool-lists.py` with `GRANT_TOKEN` (a regex extracting the first token inside `Bash(...)` after an optional `bash|sh|python|python3` interpreter prefix followed by zero or more `-flag` tokens — FR-002, so `python3 -I <path>` and a bare `<path>` yield the same captured token), `_classify_grant_token(token)` (returns the repository-relative path when the token starts with `./`, stripped once, or contains `/` anywhere; returns `None` for a bare command with neither — FR-003), and `_grant_path(tool)` (returns `None` immediately, before any regex match, when the raw untouched grant string contains `${{` — FR-008, research.md D5; otherwise applies `GRANT_TOKEN` then `_classify_grant_token`), exactly as specified in contracts/gate-27-extension.md §2.
- [X] T005 [P] Create `.github/scripts/script-grant-waivers.json` per contracts/waiver-schema.md's schema and shipped content: the `$comment` block explaining the exact-path-only schema and the two-direction stale check, plus a `"waivers"` list with exactly two entries — `{"path": ".wing-commander-pipeline/.github/scripts/git_read.py", "issue": "#599", "reason": "..."}` (covering all four composite/`claude_args` sites that grant this run-time-checked-out, never-committed path) and `{"path": "e2e-scratch/.specify/scripts/bash/create-new-feature.sh", "issue": "#436", "reason": "..."}` (covering both grant spellings of the e2e provisioning step's run-time-created scratch directory).
- [X] T006 Add `import json` to `.github/scripts/verify-stage-tool-lists.py`'s import block, plus `WAIVER_FILE = ".github/scripts/script-grant-waivers.json"` and `load_waivers(root=".")`, which `json.load`s the file T005 creates and returns `({path: entry}, [error, ...])` keyed by each entry's `"path"` field (contracts/gate-27-extension.md §4).
- [X] T007 In `.github/scripts/verify-stage-tool-lists.py`'s `self_test()`, add a standalone assertion calling `_grant_path()` directly on a bare-command grant string (`"Bash(jq:*)"`) and asserting it returns `None` — exercises the classifier's "no `/`, no `./`" branch directly, independent of any collector or surface (research.md D9 mutation 4, FR-003, FR-012).
- [X] T008 In the same `self_test()`, add a standalone assertion calling `_grant_path()` directly on an expression-valued grant string (`"Bash(python3 -I ${{ runner.temp }}/x.py:*)"`) and asserting it returns `None` — distinct from T007 because this token contains a `/` and would be misclassified as a resolvable path if the raw-string `${{` check in `_grant_path` (T004) were ever removed or reordered after token extraction (research.md D9 mutation 5, FR-008, FR-012).

**Checkpoint**: The shared loader, classifier, and waiver plumbing exist and
are unit-verified on their own; no user story's collector or check has been
wired to them yet.

---

## Phase 3: User Story 1 - A renamed first-party helper script fails the gate (Priority: P1) 🎯 MVP

**Goal**: Widen the existence check so any granted path — not only one
starting with `.specify/scripts/bash/` — is resolved against the tree when
granted at a `wing-commander-tool-args` composite call site.

**Independent Test**: Delete or rename any granted `.github/scripts/*.py`
helper in a scratch tree and run Gate 27 — it must report a failure naming
the grant and the step-label. Restore it and the gate is green again.

### Implementation for User Story 1

- [X] T009 [US1] Rewrite `check_script_grants` as `check_grant_existence(all_sites, waivers, root=".")` in `.github/scripts/verify-stage-tool-lists.py` per contracts/gate-27-extension.md §4: for each `(label, tools)` pair and each `tool`, compute `rel = _grant_path(tool)` (T004) and skip when `None`; check `waivers` (T006) before the filesystem — a hit is silently accepted, no failure; memoize `_script_exists(root, rel)` in the existing `exists` dict, unchanged (FR-011); report a failure naming the label, the grant, the unresolved path, and `WAIVER_FILE` for anything resolved-as-path but absent from both disk and waivers; then, for every waiver entry whose `path` *does* resolve on disk, report the FR-007 staleness failure naming `WAIVER_FILE`, the path, and the entry's issue.
- [X] T010 [US1] Wire `run()` in `.github/scripts/verify-stage-tool-lists.py` to call `_load_workflows` (T002), `load_waivers` (T006), and `check_grant_existence` (T009) fed by `collect_sites()`'s allowed-tools half (`[(label, allowed) for label, (allowed, _disallowed) in sites.items()]`), replacing the old direct `check_script_grants(sites, root)` call — composite surface only for now; the two new collectors are folded into this same list in Phase 4 (contracts/gate-27-extension.md §5).
- [X] T011 [US1] In `self_test()`, replace every `check_script_grants(...)` call with the equivalent `check_grant_existence([(label, tools) for ...], waivers, root)` call, preserving each existing assertion's coverage exactly: the baseline "every granted `.specify` script exists" pass, the #426 ghost-grant replay in both spellings on `plan.direct-commit`, the `sh`-prefixed/`./`-prefixed/trailing-argument mutations against `ghost2`, the case-mismatched-grant mutation on its `tempfile.mkdtemp()` fixture tree, and the real-grant pass-through assertion — using the real `load_waivers(root)` map for assertions run against the real repository's `sites`, and `{}` for assertions run against a synthetic mutation.
- [X] T012 [US1] Add a new mutation to `self_test()`: append a grant for a script outside `.specify/scripts/bash/` that does not exist (e.g. `Bash(.github/scripts/zzz-does-not-exist.py:*)`) to `plan.direct-commit`'s allowed tools, and assert `check_grant_existence` reports exactly one failure naming the site and the path (research.md D9 mutation 1, FR-001, FR-012).

**Checkpoint**: A composite-site grant for any missing script, in any
directory, now fails Gate 27 — proven both by a real rename (Independent
Test) and by T012's synthetic fixture.

---

## Phase 4: User Story 2 - A grant composed outside the composite is checked too (Priority: P2)

**Goal**: Extend collection to the two non-composite surfaces this
repository uses — a reusable-workflow caller's `extra-allowed-tools`/
`allowed-tools-override`, and a bare `claude_args --allowedTools` string on a
`claude-code-action` step.

**Independent Test**: Point a `claude_args` `--allowedTools` grant (or a
wrapper's `extra-allowed-tools`) at a script path that does not exist and
carries no waiver; Gate 27 must fail naming the workflow, the job, and (for
`claude_args`) the step.

### Implementation for User Story 2

- [X] T013 [US2] Add `collect_reusable_workflow_grants(docs)` to `.github/scripts/verify-stage-tool-lists.py` per contracts/gate-27-extension.md §3: for every job whose `uses` starts with `./.github/workflows/`, read `with.extra-allowed-tools` / `with.allowed-tools-override` and return `[(f"{rel}:{job_name} ({key})", split_tools(str(val))), ...]` — no step component, since a reusable-workflow-call job has no `steps:` list of its own (research.md D2/D3, FR-004, FR-005).
- [X] T014 [US2] Add `_ALLOWED_TOOLS_RE` (a two-pattern tuple tolerant of `"` then `'` quoting), `_extract_allowed_tools(claude_args)`, and `collect_claude_args_grants(docs)` to `.github/scripts/verify-stage-tool-lists.py` per contracts/gate-27-extension.md §3: for every step whose `uses` contains `claude-code-action`, extract `with.claude_args`'s `--allowedTools` value and return `[(f"{rel}:{job_name}:{step_name!r}", split_tools(allowed)), ...]`, with `step_name` falling back from `step.get("name")` to `step.get("id")` to `"step[{idx}]"` (research.md D2/D3, FR-004, FR-005).
- [X] T015 [US2] Extend `run()`'s grant-site list in `.github/scripts/verify-stage-tool-lists.py` to concatenate `collect_reusable_workflow_grants(docs)` and `collect_claude_args_grants(docs)` (T013, T014) onto the composite-derived list already wired in T010, so `check_grant_existence` (T009) sees all three surfaces at once (contracts/gate-27-extension.md §5).
- [X] T016 [US2] Add a fixture and mutation to `.github/scripts/verify-stage-tool-lists.py`'s self-test (alongside `_collector_fixtures()`'s existing `tempfile.mkdtemp()` pattern): a synthetic workflow with a job `uses: ./.github/workflows/x.yml` whose `extra-allowed-tools` grants a missing script → assert `collect_reusable_workflow_grants` + `check_grant_existence` report exactly one failure naming the workflow file and job (research.md D9 mutation 2, FR-004, FR-012).
- [X] T017 [US2] Add a fixture and mutation to the same self-test: a synthetic workflow with a `claude-code-action` step whose `claude_args` `--allowedTools` grants a missing script → assert `collect_claude_args_grants` + `check_grant_existence` report exactly one failure naming the workflow file, job, and step (research.md D9 mutation 3, FR-004, FR-005, FR-012).

**Checkpoint**: All three grant surfaces (composite, reusable-workflow
caller, bare `claude_args`) are now checked for existence.

---

## Phase 5: User Story 3 - A grant for a path created at run time is recorded, not exempted by accident (Priority: P3)

**Goal**: Prove the waiver mechanism's reverse-direction check — a waiver
entry whose path *does* resolve is itself a failure — so `e2e-scratch/`'s
exemption (and any other waiver) stays an auditable, self-expiring record
rather than a permanent blind spot.

**Independent Test**: Remove the e2e grant's entry from
`script-grant-waivers.json` and run Gate 27 — it must fail. Restore the
entry and it must pass. Add an entry for a path that *does* resolve, and the
gate must report that entry as stale.

### Implementation for User Story 3

- [X] T018 [US3] Add a mutation to `.github/scripts/verify-stage-tool-lists.py`'s `self_test()`: in a `tempfile.mkdtemp()` fixture tree (per contracts/waiver-schema.md's Verification note — never against either of the two real waiver entries, since neither is expected to ever resolve), create a real file and a waiver map entry whose `path` names it, then assert `check_grant_existence` reports the FR-007 staleness failure naming `WAIVER_FILE`, the path, and the entry's issue (research.md D9 mutation 6, FR-007, FR-012).
- [X] T019 [US3] Add the baseline assertion to `self_test()` that running `check_grant_existence` against the real repository's `sites` (T010), `collect_reusable_workflow_grants(docs)` and `collect_claude_args_grants(docs)` (T015), and the real `load_waivers(root)` map (T006/T005) together produces zero failures — mechanically proving research.md D0's "13 grant occurrences, 2 waiver entries, repository green" claim (FR-012's "the real repository passing clean" case, SC-003).

**Checkpoint**: All three user stories are independently functional; the
full widened check is green against the real repository, with every
exemption traceable to a waiver-file entry.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: The scope-statement update FR-013 requires, plus the full
local verification CLAUDE.md's "Before pushing" section mandates.

- [X] T020 Rewrite the module docstring's "WHAT IT CHECKS" bullet 3, "WHAT IT DOES NOT CHECK"'s closing sentence, and the "SELF-TEST" section's closing sentence in `.github/scripts/verify-stage-tool-lists.py`, verbatim per contracts/gate-27-extension.md §6, so a reader can tell in-scope from out-of-scope without reading the regex (FR-013, SC-005).
- [X] T021 Run `python3 .github/scripts/verify-stage-tool-lists.py --self-test` and `python3 .github/scripts/verify-stage-tool-lists.py` (quickstart.md §1-2) and confirm exit 0 for both, with one `[ok] mutation caught` (or equivalent `[ok]`) line for each of T007, T008, T012, T016, T017, T018, plus the T019 baseline (SC-004).
- [X] T022 Run `python .github/scripts/run-local-gates.py` (quickstart.md §5, CLAUDE.md's "Before pushing" section) and confirm a clean full-suite run, including this gate's own widened self-test (SC-003, SC-006).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — establishes the pre-change baseline.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS every user story: the
  classifier (T004) and waiver loader (T006) are used by `check_grant_existence`
  (T009, built in US1) and both new collectors (T013/T014, built in US2); the
  waiver file (T005) must exist before T010 wires waivers into `run()`, since
  real composite-surface grants already need it (see Phase 2's purpose note).
- **User Story 1 (Phase 3)**: Depends on Foundational. Builds
  `check_grant_existence` and wires it for the composite surface only.
- **User Story 2 (Phase 4)**: Depends on Foundational AND on T009's
  `check_grant_existence` existing (T015 feeds it the two new collectors'
  output) — cannot start meaningfully before US1's T009 lands, despite being
  a separately-prioritized story, because there is only one check function.
- **User Story 3 (Phase 5)**: Depends on Foundational (T005/T006) and on
  T015 (US2) — its Independent Test exercises the `claude_args` surface's
  `e2e-scratch/` grant, which only reaches `check_grant_existence` once US2's
  collector is wired.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within This Feature

Because every task except T005 edits the same single file, "parallel by
story" in the usual multi-developer sense does not apply here — the real
ordering constraint is: Foundational must land whole before any story
starts, US1's `check_grant_existence` must exist before US2 can feed it a
second/third surface, and US2's collectors must exist before US3's
Independent Test has anything to exercise. Tasks within a phase are listed
in the order they should be applied to the file.

### Parallel Opportunities

- T005 (the new waiver JSON file) can be done in parallel with T002-T004 and
  T006-T008 (all edits to the `.py` file) — different file, no code
  dependency in either direction at edit time.
- No other task pair is genuinely parallel-safe: every other task edits
  `.github/scripts/verify-stage-tool-lists.py`, and most later tasks depend
  on an earlier task's function existing in that same file.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational) — CRITICAL, blocks
   every story.
2. Complete Phase 3 (User Story 1).
3. **STOP and VALIDATE**: run User Story 1's Independent Test (rename a
   granted `.github/scripts/*.py` helper in a scratch tree). Note that the
   *real repository* is not yet fully green at this checkpoint in the sense
   of SC-003/quickstart §1 — that needs US2's collectors wired (T015) so the
   `claude_args`-surface `e2e-scratch/` waiver is exercised — but US1's own
   scope (composite-surface grants, including the three
   `.wing-commander-pipeline/` sites T005/T006 already waive) is green and
   independently provable via the Independent Test and T012's fixture.

### Incremental Delivery

1. Setup + Foundational → shared substrate ready, unit-verified in isolation
   (T007, T008).
2. Add User Story 1 → composite surface widened and provable (MVP).
3. Add User Story 2 → all three surfaces checked; `run()`'s wiring is now
   complete end-to-end.
4. Add User Story 3 → the waiver mechanism's reverse (staleness) direction
   is proven, closing FR-007/SC-002/SC-003.
5. Polish → docstring states the widened scope (FR-013); a full local gate
   sweep (T022) is the final proof this feature passes the suite it edits.

Because this feature is a single-file, single-PR change (per plan.md's
Summary — no workflow file needs editing, the repository is green the day
this lands), "incremental delivery" here means incremental *task* order
within one PR, not separately shippable increments across multiple PRs.
