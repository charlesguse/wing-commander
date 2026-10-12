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

- [x] T030 Bring the shell-reading code of `.github/scripts/wc_gh_callsites.py` (the `_Scan` class, about 380 lines with comments) toward the SC-003 target of about 250 lines without losing a behaviour the self-test pins: merge the near-duplicate span helpers, drop dead branches, and re-run `python3 .github/scripts/verify-gate-12.py` (zero unaccounted invocations, mutation caught) and `python3 .github/scripts/run-local-gates.py` per SC-003 (partial)
  - Done: `_Scan` went from 381 to 315 lines (file 578 to 512). One `_close` replaces `_skip_quoted`, the backtick loop and the two bare `find` quote scans; one `_span` replaces `_dq` and `_brace`; `_mark` replaces `_mention`/`_deny`; the `(`, `)` and word-keeping branches of `_cmds` were folded. Every token, reason, line and argv stayed byte-identical to the old scanner across the 1112 scripts the gate self-tests and the repository feed it, plus 300000 generated scripts.
  - Why not 250: branch coverage over that corpus reaches every branch except the two `MAX_DEPTH` guards (`_nest`, `_span`), which are the FR-006 fail-closed exits for nesting the scanner cannot follow, so they stay. The remaining lines each carry a behaviour the Gate 12 self-test pins (an unterminated quote, heredoc, substitution or `${...}` turning later `gh` words into disallowed calls, the `${{` escape, case arms, arithmetic). Cutting further would mean dropping one of those, and FR-006 outranks SC-003's size target.
  - The code review of that change found places where the scanner, already before it, lost a `gh` call outright (FR-006): an unterminated `$'...` ending in `gh`, `${X:-gh}` as the command word, the `function` keyword, `time -p`, and `coproc`. Fixing them, and the gaps a second review found in those fixes (`${X:-gh}` behind a wrapper or quoted or nested, a quoted `gh` behind a wrapper, a redirect target spelled `function`, a dashed operand outside `time`, a `gh` after a wrapper word that already holds a call, `function` as a case pattern, a command word that may expand to nothing (`$SUDO gh`), and runners missing from the wrapper list), each with a Gate 12 locator case, brings `_Scan` to 334 lines.

## Phase 9: Review Fixes

- [x] T031 (code review of PR #1004) Fail closed on a command word that could expand to `gh` across an expansion (FR-006). `${X:-g}h api …` was located as nothing at all, which is a silent pass. In `.github/scripts/wc_gh_callsites.py`, each word now records its literal text with a marker for each expansion (`_Word.pat`). In that record a `$'…'` is decoded (cut at a NUL as bash does, or, when it cannot be decoded, counted as an unknown command word), a `{a,b}` brace list is spelled out, and a glob or a sequence brace (`{g..g}`) becomes a marker. `_may_run_gh` uses it to decide whether a command word could be `gh`. The literal text after the last marker must be `gh` after a `/` (`$HOME/bin/gh`, `/usr/bin/gh`), or else a suffix of `gh` that the marker could complete (`${X:-g}h`, `g$X`, `$(printf g)h`, `{g,}h`, `h$X`). A word made only of markers counts when it holds a `${…}` or more than one marker (`${CMD}`, `${X}${Y}`). The word that runs also counts when it holds an unquoted expansion that may split off a first word `gh` (`${X}g` with X=`gh `). Such a word is a disallowed call; a literal `/usr/bin/gh` gets the new reason `gh-by-path`. The same check now applies in four more places: every word of a literal wrapper, because its operands come before the command (`flock FILE`, `timeout 5s`); the word a dynamic command word runs, and the word after one of its options; each command-like piece of a string re-read as shell, by `eval`, `watch` or `script`, by a wrapper's `-c`/`-S` (combined flags such as `-lc` included), or by `bash -c`/`sh -c`; and `$"…"`, which is read as the quoted string it is. A lone bare `$CMD` or `$(…)` is left out because the scanner reads the `$(…)` inside `$(( $(…) ))` as a command word, and the authoring rule says so. Accepted false failures, per FR-006: `sudo -u ${U} make`, `sudo chown "$U:$G" f`, `sudo ln -s … /usr/local/bin/gh`, and `eval "x=${y}"`. Accepted gap: a dynamic command word's arguments past the first are not checked, so a variable holding a wrapper (`"$PY" lockfile g$F`) passes. So that lines which run nothing do not fail, the scanner now reads four constructs as data instead of command words: an array assignment's list (`a=("$x")`, `declare -A m=(…)`; the assignment stays a prefix, so `GH_TOKEN=(t) gh` is an unsupported prefix), a subscripted assignment (`a[$k]=…`, read as an assignment prefix), a case pattern (`*/*|/*)`), and the operands of a `[[ … ]]` test (`=~ ^([0-9]+)*$`). Their expansions are still read, and that includes a process substitution in a test. A case pattern cut short by `;` or a newline is unprovable. The first word of each command (after any keyword, and every word after a wrapper) in a backtick body, and in the `$(…)` spans of an unquoted heredoc body (nested ones included), is checked the same way. A `time` that is not the leading word, as in `X=1 time gh`, is `/usr/bin/time` and is treated as a wrapper. A test or list that cannot be read to its close is unprovable: each `gh` or may-be-`gh` word in it, and every `gh` after it, becomes a disallowed call. Nothing is read twice, so `locate` stays linear. Gates 12 and 28 stay green on the repository. Thirty-nine new Gate 12 locator cases in `.github/scripts/verify-gate-12.py` cover these forms, and the forms that ran `gh` unseen fail without the change. The authoring rule in `CONTRIBUTING.md` and `contracts/authoring-rule.md` names the forms. `verify-gate-12.py`'s differential (0 unaccounted, and 0 over 8000 extra seeds) and mutation (caught) checks still pass.

## Review Gate Round 1 Findings

- [x] Review finding: Quoted stdin to a shell classified as inert mention

  bash <<'EOF', here-strings, or echo '...' | bash bodies are treated as mentions so real gh calls are missed, contradicting the fail-closed contract.

  - .github/scripts/wc_gh_callsites.py

  Detail: _heredocs marks the quoted heredoc as a mention; _end only treats bash/sh as running a string with -c/-S.

- [x] Review finding: Wrapper/shell list is a closed denylist

  find -exec, parallel, ssh, docker exec and chroot are not recognised, so gh run through them is not flagged or checked.

  - .github/scripts/wc_gh_callsites.py

  Detail: `find . -exec gh issue close {} \;` emits no token; the quoted sh -c variant becomes a mention.

- [x] Review finding: Partly quoted owner/repo in gh api path skipped as cross-repo

  norm_expr only strips quotes wrapping the whole word, so repos/"$GITHUB_REPOSITORY"/... is classified CROSS and its permission is never checked.

  - .github/scripts/verify-gate-12-token-permissions.py

  Detail: check_gh_invocation skips CROSS paths, so the Actions-needs-permission 403 the gate exists to catch passes.

- [x] Review finding: Redirection fd number parsed as an argv word

  The 2 in 2>/dev/null becomes part of the gh call's argv and shifts the path or subcommand.

  - .github/scripts/wc_gh_callsites.py

  Detail: `gh api 2>/dev/null "repos/$R/actions/runs"` gives argv ['api','2',...], so the real path is never checked.

- [x] Review finding: run_blocks line offset wrong for non-literal scalars

  start_mark.line + 1 + (style in '|>') is correct only for literal block scalars but is applied to folded, plain and quoted scalars.

  - .github/scripts/wc_gh_callsites.py

  Detail: Folded newlines make locator line N differ from the file line, so Gate 28 annotations and wc-gh-method-exempt lookups use the wrong line.

- [x] Review finding: Duplicate run: scalar walk and line-offset formula

  run_lines() in Gate 12 re-implements what wc_gh_callsites.run_blocks() already provides, violating the single-home rule.

  - .github/scripts/verify-gate-12-token-permissions.py
  - .github/scripts/wc_gh_callsites.py

  Detail: Two copies of the line-offset formula can drift with nothing failing.

- [x] Review finding: splitlines vs newline-count mismatch in exemption lookup

  scan_script indexes script.splitlines() with a locator line number that counts only \n.

  - .github/scripts/verify-gh-api-explicit-method.py

  Detail: \r, \x0b, \x0c, \x85 or \u2028 in a script yields extra lines, so _is_exempt checks the wrong line.

- [x] Review finding: Gate 28 scope narrowed and disallowed calls skipped

  Python scripts and non-.sh executables are no longer scanned, and calls the locator marks disallowed are skipped on the assumption Gate 12 reports them.

  - .github/scripts/verify-gh-api-explicit-method.py

  Detail: Gate 12 does not scan .github/scripts, so an implicit-POST gh api there can land unflagged.

- [x] Review finding: Wall-clock linear-time check and host-dependent differential

  run_locator_cases fails a case that takes over 5s as not linear, and differential() runs generated scripts under real bash, so the self-test can flake or depend on the host.

  - .github/scripts/verify-gate-12.py

  Detail: A loaded runner can push the 60000-line heredoc case past 5s; a step-count or size-scaling check would be deterministic.

- [x] Review finding: Garbled gate comment and opaque fuzz repro files

  A half-edited self-correcting comment is left in a gate file's fixture header, and mins3/3b/3c/5-10 .jsonl files are added with no manifest saying which bug each guards.

  - .github/scripts/verify-gh-api-explicit-method.py

  Detail: Comments in gate files are load-bearing; every .jsonl in gate-12-fuzz/ is replayed with no manifest.

## Phase 10: Merge of main and Round 1 Re-check

- [x] T032 Merge `main` (#991, #1003, #1015) and bring Gate 12 back to green. #1003's agent start-up check runs `docker run ... sh -c '<script>'` in 15 workflows, and the script holds `${v#git version }`. The locator judged every piece of a string a shell re-reads as a command word, and once that string held a `${…}`, a lone `"$t"` counted as one, so all 15 failed as `unquoted-wrapper` although none runs `gh`. The locator misread a form; no call site broke the authoring rule. `_script_may_run_gh` in `.github/scripts/wc_gh_callsites.py` now reads a literal script string (`sh -c`, `bash -c`, `eval`, `trap`, a remote shell's words, a glued `-S'...'`) with the locator itself: a call in it fails, and so does every `gh` in it that is not a provable mention (`sh -c 'X=gh; $X api'`). A string holding an expansion is still judged piece by piece. Trade-off: inside a literal script string, a lone bare `$CMD` command word is now unchecked, exactly as it is at statement level (the authoring rule's existing "never run `gh` through one"); the old piece-by-piece check flagged `sh -c 'X=g$(:)h; $X api'`, the new one does not, as `X=g$(:)h; $X api` at statement level never was. Covered by the Gate 12 locator cases "a literal script a shell runs is read as a script" and "... still fails on gh it may run"; the first fails without the change.

### Round 1 findings: status at this head

1. **Quoted stdin to a shell**: fixed in T027's cycle for heredocs, here-strings and `|`; still silent through `|&`, a `{ …; }`/`( … )` group piped to a shell, `bash <(echo '…'; :)`, `bash /dev/stdin` and `source`/`.` of stdin or a process substitution, and `trap '…'`. Fixed here (pipeline start kept across groups and substitutions, `|&` read as a pipe, `/dev/` operands and `source`/`.` read as stdin, `trap` a shell runner). Locator case "a group, |&, a process substitution or /dev/stdin still feed a shell" fails without it. Refuted remainder: a script written to a file and run by a later command (`echo '…' > f; . f`) is data flow across commands; FR-004 (a) makes that quoted string a mention.
2. **Closed wrapper list**: fixed (`find -exec`, `ssh`, `parallel`, `docker`, `chroot` and the other runners), covered by "find, ssh and docker run the rest of their words". Refuted remainder: another interpreter's string (`perl -e`, `awk 'system(…)'`, `python3 -c`) is a quoted span under FR-004 (a), not shell.
3. **Partly quoted owner/repo classified cross-repo**: fixed for double quotes only; `'repos/'"$GITHUB_REPOSITORY"'/actions/…'` and `P='repos/{owner}/{repo}/…'; gh api "$P"` still classified as not this repository and were skipped. `resolve_paths` in `verify-gate-12-token-permissions.py` now drops both quote kinds. Fixtures "a single-quoted piece of a gh api path …" and "… held in a variable …" fail without it.
4. **Redirect fd number in argv**: fixed for `2>`; a named fd (`{fd}>file`) still became the path. Fixed (`NAMED_FD`); fixture "a named fd redirect is not the path of the call" fails without it.
5. **Line offset for non-literal scalars**: fixed. `Run.line` maps lines one to one only for a literal (`|`) scalar and otherwise reports the line the text starts on.
6. **Duplicate run: walk**: fixed. `run_lines()` is gone; Gate 12 uses `wc_gh_callsites.step_runs()`.
7. **splitlines vs `\n` count**: fixed, covered by Gate 28's "an exemption on the right line despite a form feed in an earlier one".
8. **Gate 28 scope**: disallowed calls are counted again ("a call in a form Gate 12 rejects still counts here") and extensionless shell scripts are scanned. Refuted: `.py` files. `main`'s raw-line regex never matched the list form (`["gh", "api", …]`) that the scripts under `.github/scripts/` actually use, so only their docstrings matched. Reading Python with a second `gh` reader would break FR-010/FR-011.
9. **Wall-clock linearity check**: fixed; `steps_ratio` counts Python calls. A long literal script handed to a shell is a scaling case too. Refuted: the real-bash differential is FR-015's oracle; it runs a fixed seed range, so its input does not vary by host.
10. **Garbled comment and fuzz files**: the comment is fixed; `gate-12-fuzz/manifest.json` lists every `.jsonl` and the differential fails on a mismatch. Refuted remainder: the per-record bug of PR #969's shrinker rounds is not recoverable from the archive. Each record carries its repro script, and every one is replayed.

- [x] T033 (code review of PR #1004 after the merge of main) Fix the review's real findings. Each has a test that fails without its fix:
  - A `gh` word fed to a shell unquoted (`echo gh api x | bash`, `source <(echo gh api x)`, `bash <<< gh\ api\ x`) got no token. `_stdin_shell` now notes every `gh` word in the pipeline's text that is neither a call nor a mention (FR-006). Covered by the locator case "a group, |&, ... still feed a shell".
  - A lone `$CMD` or `"$@"` command word now becomes a disallowed call when the script names a `gh` that is neither a call nor a mention (`GH=gh; $GH api`, `set -- gh api x; "$@"`, `X=/usr/bin/gh`). An `eval` or `sh -c` string that holds an expansion now counts as a call when it holds `gh` text at all (`eval "$(echo gh api x)"`). Covered by "a lone $CMD may run a gh the script names".
  - Gate 28 skipped a call Gate 12 rejects when the call has no words of its own: backticks, `sudo`, `eval`, `bash -c`, or a heredoc fed to bash. `main`'s line scan caught these. `wc_gh_callsites.call_words` now reads such a call's words on its own line. Covered by Gate 28's five "a call Gate 12 rejects, ..., still counts here" fixtures.
  - A job named like a YAML 1.1 boolean (`on:`) reported its failures at line 1 (FR-005). `step_runs` now keys jobs as `safe_load` does. Covered by the fixture "a disallowed call in a job named like a YAML boolean names its own line".
  - Refuted: `accounted()` in the differential treats a script holding any disallowed call as accounted. US3 scenario 2 requires exactly that: "the gate must have failed that script as a disallowed form", and Gate 12 is then red on that script.
  - Refuted: Gate 28 no longer reads `.py` files (see Round 1 finding 8; FR-012 moves Gate 28 onto the shell locator).
  - Refuted: the single-home check for the locator matches two source signatures. Like the other checks in `verify-single-home-idioms.py`, it is an idiom check (FR-011).
  - Refuted: the explicit `CONTRIBUTING.md` path entry is redundant with `*.md`. It follows `main`'s convention of naming each gate's subject even under a glob (`docs/setup.md` under `docs/**`).
  - Out of scope: the default-branch two-liner already sat in 9 run blocks on `main`. FR-017 rewrote each copy in place; giving it one home is a backlog line.

## Review Gate Round 2 Findings

- [ ] Review finding: call_words stops at end of line, missing continued flags

  For eval/bash -c/sudo calls with no argv, call_words reads only to the next newline, so a -f/-F flag on a continuation line is missed and Gate 28 passes an implicit-POST gh api call.

  - .github/scripts/verify-gh-api-explicit-method.py

  Detail: e.g. eval "gh api repos/x \
 -f a=b" yields argv 'api repos/x' only

- [ ] Review finding: Gate 28 scope narrowed to run scalars and shell files

  Gate 28 no longer scans .py files or non-run fields, and sweep() errors out if there are zero .sh/shebang files.

  - .github/scripts/verify-gh-api-explicit-method.py

- [ ] Review finding: Default-branch rewrite changes set -e failure semantics

  The ${DEFAULT_BRANCH:-$(gh repo view ...)} rewrite into a separate assignment makes a transient gh failure abort steps under set -e, applied at 7 sites without a test or comment.

  - .github/workflows/cleanup.yml
  - .github/workflows/auto-update-spec-kit.yml

- [ ] Review finding: Unbounded recursion locate -> _script_may_run_gh -> locate

  Nested literal sh -c / eval strings recurse without a depth bound, so the 'never raises' locator can hit RecursionError.

  - .github/scripts/wc_gh_callsites.py

- [ ] Review finding: Partly quoted heredoc delimiter mis-parsed

  Delimiters like <<E"O"F are treated as unquoted and truncated, so the body is never matched and later gh calls are flagged as disallowed.

  - .github/scripts/wc_gh_callsites.py

- [ ] Review finding: Unterminated heredoc leaves pending/shell_stdin stale

  _heredocs returns early without clearing self.pending or shell_stdin, so nested scans sharing the _Scan misclassify tokens as shell-stdin.

  - .github/scripts/wc_gh_callsites.py

- [ ] Review finding: Single-home scanner check matches one regex spelling

  SCANNER_HEREDOC_RE matches only a specific regex source text, so a second shell scanner written differently escapes the single-home guard.

  - .github/scripts/verify-single-home-idioms.py

- [ ] Review finding: step_runs key construction unguarded and loader leaked

  construct_object on job keys runs outside the try, so an odd key crashes instead of returning {}, and the SafeLoader is never disposed.

  - .github/scripts/wc_gh_callsites.py

- [ ] Review finding: run_blocks matches any run key, no cycle guard

  Any mapping key named run with a scalar value (e.g. with: inputs) is scanned as shell, and alias cycles could loop forever.

  - .github/scripts/wc_gh_callsites.py

- [ ] Review finding: Argv log delimiters collide with argument bytes

  gh_argv_calls splits on \x1f/\x1e, which script-controlled arguments can contain, corrupting the differential check's records.

  - .github/scripts/wc_shell_harness.py
