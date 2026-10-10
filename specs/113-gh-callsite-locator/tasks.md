# Tasks: Gate 12 — gh call-site authoring rule and shared locator

**Input**: Design documents from `/specs/113-gh-callsite-locator/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/locator-api.md, contracts/authoring-rule.md, quickstart.md

**Tests**: Requested by the spec (FR-013 to FR-016, Principle VIII): fixtures, corpus replay, real-bash differential and mutation check are part of the deliverable.

**Organization**: Grouped by user story. All paths are relative to the repository root. Run `python .github/scripts/run-local-gates.py` before pushing (CLAUDE.md); workflow comments are load-bearing, so re-run the suite after any comment edit.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: Bring the archived material in and read the current gate.

- [x] T001 Read the current Gate 12 inline body in `.github/workflows/lint-workflows.yml` and note its entry points (permission table, token resolution, `docs/setup.md` grant parse, composite call-site walk, agent tool-grant check) in a scratch list, so T006 moves it unchanged (FR-007).
- [x] T002 [P] Extract the 183 scenarios from `.github/scripts/verify-gate-12.py` on branch `archive/pr-969-gate-12-corpus` (`git show archive/pr-969-gate-12-corpus:.github/scripts/verify-gate-12.py`) into `.github/scripts/gate-12-corpus.json` with fields: id, snippet, token setup, expected verdict (`pass | permission | disallowed`), optional `changed_from_969: true`.
- [x] T003 [P] Copy the generator, real-bash runner, shrinker and minimized repros from `archive/gate-12-fuzz/` on that branch (`git ls-tree -r archive/pr-969-gate-12-corpus`) into `.github/scripts/gate-12-fuzz/`.
- [x] T004 [P] Inspect `.github/scripts/wc_shell_harness.py` for argv-recording stub-`gh` support; note whether T018 must extend it.

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: The shared locator and the gate moved into a script.

- [x] T005 Create `.github/scripts/wc_gh_callsites.py` implementing `locate(script) -> list[Token]` per `contracts/locator-api.md` and `data-model.md`: single left-to-right scanner with state stack (normal, single quote, double quote, `$( )` depth, backtick, comment, heredoc body); heredoc delimiters consumed in the same pass (linear, FR-008); mention only under FR-004 (a) quoted span without `$(`/backtick, (b) quoted-delimiter heredoc body, (c) comment; everything uncertain is `call` (FR-006); allowed positions per research R2 (statement level or first command of one-level `$(…)`, optional `GH_TOKEN=<word>`, optional `timeout N`; literal subcommand and `gh api` method flag, incl. glued `-XPOST`/`--method=POST`); never raises on malformed input; stdlib only, about 250 lines (SC-003, FR-019).
- [x] T006 Create `.github/scripts/verify-gate-12-token-permissions.py` by moving the Gate 12 body out of `.github/workflows/lint-workflows.yml` with token/permission logic unchanged (FR-007), replacing its inline bash parser with `wc_gh_callsites.locate()`; emit the disallowed-form message `<file>:<line>: gh call in a form Gate 12 cannot verify (<reason>) — rewrite it to the allowed form; see <authoring-rule heading>.` (FR-005).
- [x] T007 Replace the Gate 12 inline step in `.github/workflows/lint-workflows.yml` with `python3 .github/scripts/verify-gate-12-token-permissions.py`, keeping the step name; add path triggers for `.github/scripts/wc_gh_callsites.py`, the new script, `docs/setup.md`, workflows and actions (FR-009). Depends on T006.
- [x] T008 Register the new script in `.github/scripts/wc_gate_registry.py` so `run-local-gates.py` runs it with the same arguments as CI; update `verify-gate-wiring.py` references only if it fails (keep "Gate 12" numbering).
- [x] T009 Switch `.github/scripts/verify-gate-12.py` (self-test) to import the gate script instead of extracting source from the workflow YAML. Depends on T006.

**Checkpoint**: locator and moved gate exist; the repository census can now be measured.

---

## Phase 3: User Story 1 - A miss becomes impossible by construction (P1) 🎯 MVP

**Goal**: Allowed forms are checked; unprovable forms fail closed; provable mentions pass.

**Independent Test**: Synthetic trees: insufficient token on an allowed call fails with a permission error; backticks, nested `$( $( ) )`, `gh "$VERB"` fail "rewrite to the allowed form"; quoted string, comment and `<<'EOF'` body pass.

- [x] T010 [P] [US1] Add fixtures in `.github/scripts/verify-gate-12.py` for every acceptance scenario of US1 (statement-level permission miss, `GH_TOKEN=` prefix wins, backticks, nested substitution, variable subcommand, quoted mention, comment, quoted-heredoc mention, unquoted heredoc, `$'…'`, `case` arm inside `$( )`).
- [x] T011 [P] [US1] Add fixtures for each remaining failure branch: unresolvable token, unknown subcommand/path, unused composite, plus the mention/call boundary of each FR-004 clause (FR-013). Also cover edge cases: `ghost`, `gh-pages`, line continuation, `${{ … }}` text, double quote containing `$(`.
- [x] T012 [US1] Fix locator and gate until T010/T011 pass and the six #889 gaps each have a named fixture (ANSI-C quoting, unquoted heredoc body, `case` in `$( )`, glued method flags, separators in escaped backticks, quadratic heredoc timing on a large heredoc) (FR-018).
- [x] T013 [US1] Write the authoring-rule section "Authoring rule for `gh` call sites" once, in the contributor doc chosen per research R8 (`Grep` for `CONTRIBUTING.md` or a `docs/` contributor doc), following `contracts/authoring-rule.md`; make the T006 message point at that exact heading (FR-001, FR-002).

**Checkpoint**: US1 independently verifiable via the self-test.

---

## Phase 4: User Story 2 - The current repository passes with minimal migration (P1)

**Goal**: `main` stays green and Gate 12 checks at least the 478 calls it checks today.

**Independent Test**: Full local gate suite passes; before/after (file, line, subcommand, token) sets show no lost call.

- [x] T014 [US2] Run the new locator in report mode over all 87 workflow/action files; record counts of executable calls (expect 478), disallowed forms, and mentions in unquoted heredocs or `$(`-bearing double quotes (research R7). Record the result in the PR description draft and the issue comment.
- [x] T015 [US2] Compare Gate 12's checked-call set before (current `main` parser, via `git show main:.github/workflows/lint-workflows.yml`) and after; confirm no executable call is dropped (SC-002) and that `wing-commander-lifecycle-gate/action.yml`'s `timeout` call is accepted (US2 scenario 2).
- [x] T016 [US2] Migrate each non-conforming call site and each unquoted-heredoc / `$(`-bearing mention found in T014 to an allowed form (quote the heredoc delimiter only where the body has no intended expansion, otherwise reword), with unchanged runtime behaviour and no stage input/output/secret change (FR-017). Edit files under `.github/workflows/` and `.github/actions/` as listed by T014.
- [x] T017 [US2] Run `python .github/scripts/run-local-gates.py`; fix any red gate. Because workflow comments are load-bearing, re-run after each comment edit. Apply the `review-step-gating` skill if any `if:`/`continue-on-error:` was touched.

**Checkpoint**: repository conforms; US1+US2 form the MVP.

---

## Phase 5: User Story 3 - Corpus and real-bash oracle prove it (P2)

**Goal**: Self-test replays the 183 scenarios, differential-checks against real bash, and fails on a mutation.

**Independent Test**: `python .github/scripts/verify-gate-12.py` runs corpus, differential and mutation; reports zero unaccounted invocations.

- [x] T018 [US3] Extend `.github/scripts/wc_shell_harness.py` with an argv-recording stub `gh` if T004 found none.
- [x] T019 [US3] Add corpus replay to `.github/scripts/verify-gate-12.py` reading `gate-12-corpus.json`: every scenario #969 expected to fail still fails; any verdict change must be pass→`disallowed` and carry `changed_from_969: true` (FR-014). Depends on T002, T012.
- [x] T020 [US3] Add the seeded differential check to `.github/scripts/verify-gate-12.py` using `.github/scripts/gate-12-fuzz/` and the stub `gh`: fixed seed, fixed count (bounded CI time); fail if bash executed an invocation the gate neither located nor rejected as disallowed (FR-015, SC-001). Depends on T003, T018.
- [x] T021 [US3] Add the mutation check (FR-016): monkeypatch the `wc_gh_callsites` classifier to return `mention` for a known call and assert the corpus run goes red.

**Checkpoint**: Principle VIII proof in place.

---

## Phase 6: User Story 4 - One home for locating gh call sites (P2)

**Goal**: Gate 28 on the locator; a gate fails on any second reader; #954's reader waived.

**Independent Test**: Reintroducing a gh-tokenising script makes `verify-single-home-idioms.py` fail; Gate 28 imports the locator.

- [x] T022 [P] [US4] Migrate `.github/scripts/verify-gh-api-explicit-method.py` to `wc_gh_callsites.locate()`, parsing `-X`/`--method` (incl. glued `-XPOST`, `--method=POST`) from the located call's literal words and deleting its own tokeniser (FR-012); add fixtures for glued forms to its self-test.
- [x] T023 [P] [US4] Add a "no second gh locator" idiom to `.github/scripts/verify-single-home-idioms.py` (research R5) with a fixture that fails on a planted duplicate and passes on the real tree (FR-011).
- [x] T024 [US4] Add a waiver for `verify-stop-point-recording.py` to `.github/scripts/single-home-waivers.json`, cited to the #889 checklist line. First read the current Maintenance backlog (#889) with `gh issue view 889` and confirm the number is still the open `disposition:tracking` "Maintenance backlog" issue; the line itself is added by the implementer (research R9). Verify with `grep -rnE '"#N"|issue *= *\([^)]*\bN\b' .github/scripts/` that Gate 124 (`verify-waiver-citations.py --check-open`) accepts the citation.
- [x] T025 [US4] Confirm Gate 12 (T006) and Gate 28 (T022) are the only consumers of the locator and that the T023 idiom passes on the tree.

---

## Phase 7: Polish & Cross-Cutting

- [x] T026 [P] Check SC-003: count the shell-reading lines in `wc_gh_callsites.py` (target at most about 250) and confirm the Gate 12 inline heredoc is gone from `lint-workflows.yml`.
- [x] T027 [P] Confirm SC-008: no new dependency in CI or the implement image (no `shfmt`, `bashlex`).
- [x] T028 Run the `quickstart.md` validation steps.
- [x] T029 Final `python .github/scripts/run-local-gates.py`; paste the result into the PR. After merge, the owner/maintainer ticks the six gap lines on #889 and runs `prove-after-merge` on the `lint-workflows.yml` change.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (T005 → T006 → T007/T009; T008 after T006).
- US1 (T010–T013) needs T005, T006. US2 needs US1's T012 (locator behaviour settled). US3 needs T012 and T002/T003/T018. US4: T022/T023 need only T005; T024 after T023.
- Polish after all stories.

### Parallel Opportunities

- T002, T003, T004 together; T010 and T011 together; T022 and T023 together; T026 and T027 together.
- US4 can proceed in parallel with US1 after T005.

## Implementation Strategy

- **MVP**: Phases 1–4 (US1 + US2): locator, moved gate, fail-closed fixtures, repository migrated and green. Do not merge without the US3 proof if possible; US3 and US4 may land in follow-up commits of the same PR.
- Then US3 (proof), then US4 (single home), then polish.

## Phase 8: Convergence

- [ ] T030 Bring the shell-reading code of `.github/scripts/wc_gh_callsites.py` (the `_Scan` class, about 380 lines with comments) toward the SC-003 target of about 250 lines without losing a behaviour the self-test pins: merge the near-duplicate span helpers, drop dead branches, and re-run `python3 .github/scripts/verify-gate-12.py` (zero unaccounted invocations, mutation caught) and `python3 .github/scripts/run-local-gates.py` per SC-003 (partial)
