# Tasks: Classify the cancel call's own error instead of racing a pre-read status

**Input**: Design documents from `/specs/087-stop-cancel-error-classification/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/board-stop-check-classification.md, contracts/cancel-already-terminal-script.md, contracts/gate-coverage-087.md, contracts/pr-conversation-vocabulary-consolidation.md, quickstart.md (all present)

**Tests**: This feature's test suite is the two existing gate scripts' own fixture/self-test harnesses (`verify-board-stop-check.py`'s `SHELL_CASES`/`MUTATIONS`, `verify-single-home-idioms.py`'s `--self-test`), extended rather than duplicated — no separate test framework. Every phase below includes the fixture/mutation work FR-007/FR-008/FR-009a require alongside the shipped-code edits, not as a separate "tests" subsection.

**Organization**: Tasks are grouped by user story (US1 = no spurious warning on an already-terminal target, US2 = a real cancellation failure is still warned, US3 = the existing ownership/self-run protections survive unchanged). The vocabulary consolidation (FR-005/FR-009/FR-009a) and the `pr-conversation.yml` repoint serve both stop procedures rather than any one user story, so they land in Foundational (the shared predicate, needed before either story's fixtures can exercise it) and Polish (the second consuming site and its own gate).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, or US3 — omitted for Setup/Foundational/Polish tasks
- File paths are exact; line numbers cited from the current tree are approximate ("~line N") and may have drifted — locate steps by name or surrounding code, not by line number alone.

## Path Conventions

Single project — this repository's own GitHub Actions workflows, composite actions, and the Python gate scripts that verify them. No `src/`/`tests/` split; all paths are repository-root-relative.

---

## Phase 1: Setup

**Purpose**: Establish the baseline before any edit lands.

- [X] T001 Run `python .github/scripts/run-local-gates.py` on the current tree and confirm it passes clean, so any later failure is attributable to this feature's own edits, not pre-existing drift (quickstart.md "Run the full pre-push gate suite"; CLAUDE.md "Before pushing").

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Stand up the shared already-terminal predicate script (FR-005, FR-009, D1/D2) and the test-harness plumbing both `verify-board-stop-check.py`'s US1 and US2 fixtures need to drive a failing `gh run cancel` through it. Nothing in US1/US2 can be fixtured correctly until this lands.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Create `.github/actions/_shared/cancel-already-terminal.sh` per contracts/cancel-already-terminal-script.md: invoked as `bash <path> "$ERROR_TEXT"` (never sourced, never relies on its executable bit — the same invocation discipline `_shared/normalise-transcript.sh` documents for itself). Exit 0 when `$1` case-insensitively contains `HTTP 409` (protocol-prefixed — the bare digits `409` alone, e.g. inside a run id or URL a permission error happens to quote, MUST NOT match), `already completed`, or `cannot cancel`; exit 1 otherwise. No stdout — this is a predicate, not a transform (FR-005; data-model.md "Already-terminal vocabulary").
- [X] T003 Validate the new script directly against quickstart.md's five example invocations (`HTTP 409: Conflict` → 0, the "already completed" sentence → 0, `HTTP 403: Resource not accessible by integration` → 1, `permission denied for run id 4091234` → 1) and confirm every exit code matches before it has any caller.
- [X] T004 [P] In `.github/scripts/verify-board-stop-check.py`, extend `STUB_GH`'s `if [ "$1" = "run" ] && [ "$2" = "cancel" ]; then` branch: when env var `STUB_CANCEL_FAIL=1` is set, write `$STUB_CANCEL_ERROR` to stderr and exit 1; otherwise keep exiting 0 as today. This is the capability both US1's already-terminal fixture and US2's real-failure fixtures need to drive a configurable `gh run cancel` failure.
- [X] T005 In the same file, extend `_run_shell_case()`: (a) add `GITHUB_ACTION_PATH` to its env dict, pointing at a per-case stand-in `actiondir` directory it creates as a sibling of a per-case `_shared/` directory (both under `case_dir`, mirroring `verify-agent-verdict.py`'s Gate 22 `action_dir`/`shared_dir` staging exactly), so the composite's own `$GITHUB_ACTION_PATH/../_shared/cancel-already-terminal.sh` call resolves; (b) read the real shipped script's content once at import time into a module-level `CANCEL_VOCAB_SCRIPT` constant (same pattern as Gate 22's `SHARED_SCRIPT`) and write it into that per-case `_shared/cancel-already-terminal.sh`, unless a new optional `cancel_vocab_script=None` parameter overrides it (used later by the mutation task); (c) wire two new optional `SHELL_CASES` fields, `cancel_fail` (bool, default `False`) and `cancel_stderr` (str, default `""`), into the `STUB_CANCEL_FAIL`/`STUB_CANCEL_ERROR` env vars T004 added.
- [X] T006 In `run_shell_cases()`, split `proc.stdout` into lines and collect (a) lines starting with `::warning::` and (b) lines that carry the FR-010 informational wording without any `::...::` prefix. Add two new `SHELL_CASES` expectation fields, `want_warning` (bool) and `want_info_line` (bool), and assert `bool(warning_lines) == want_warning`, `len(warning_lines) <= 1` (never a forged second annotation), and `bool(info_lines) == want_info_line` for every case. Default both new fields to `False` on every existing `SHELL_CASES` entry so current behaviour is unchanged (SC-004).
- [X] T007 Run `python3 .github/scripts/verify-board-stop-check.py` and confirm it still passes with the extended harness — only plumbing has been added so far; no `SHELL_CASES` content has changed yet, so every existing case's `want_warning`/`want_info_line` default to `False` and pass trivially.

**Checkpoint**: The shared predicate script exists and is directly validated; the fixture harness can drive and observe a configurable `gh run cancel` failure through the real shared script. User story implementation can now begin.

---

## Phase 3: User Story 1 - A stop request that lands as the target run finishes produces no spurious warning (Priority: P1) 🎯 MVP

**Goal**: Once the ownership guard passes, `gh run cancel` is attempted unconditionally; when it fails because the target already finished, the step emits no warning, one non-warning informational line, and still reports `paused=true` with a successful exit.

**Independent Test**: Drive the stop check against a target run whose cancellation is refused with an already-terminal response, and confirm the step emits no warning annotation, emits a non-warning informational line, still reports the item as paused, and still exits successfully (spec.md's own Independent Test for this story).

### Implementation for User Story 1

- [X] T008 [US1] In `.github/actions/wing-commander-board-stop-check/action.yml`'s `check` step (~lines 160-173): delete the `cancel_target_status="$(printf '%s' "$cancel_target_json" | jq -r '.status // empty' ...)"` extraction (~line 161), and collapse `elif [ "$cancel_target_status" != "completed" ]; then` (~line 169) into a plain `else` — once the ownership guard (~line 167, unchanged) passes, the cancellation is attempted unconditionally (FR-001, FR-002). Wrap the existing `if ! cancel_error="$(GH_TOKEN="$CANCEL_TOKEN" gh run cancel ...)"` failure branch with the classification call: `if bash "$GITHUB_ACTION_PATH/../_shared/cancel-already-terminal.sh" "$cancel_error"; then` — on match, `echo` a plain line naming `$stop_run_id` and stating it had already finished before the cancel attempt and nothing was cancelled, with **no** `::...::` prefix (FR-003, FR-010); on no match, keep the existing `echo "::warning::gh run cancel $stop_run_id failed: $cancel_error"` line unchanged for now — US2 (T012) replaces `$cancel_error` with a sanitised value there. Exact code shape: contracts/board-stop-check-classification.md's "Added" block.
- [X] T009 [US1] Rewrite the header comment block at ~lines 127-146 (the concurrency-group / "`gh run cancel` on a completed run always 409s" / "peer review of #465, round 2" reasoning): state that the classification is now decided from the cancel call's own error output via `cancel-already-terminal.sh`, never from `status`, and that the concurrency-group reasoning is retained only as *context* — per spec.md's Assumptions, it is "no longer relied on to decide anything." Leave the target-ownership comment block (~lines 148-159) untouched (CLAUDE.md: workflow comments are load-bearing; this block still describes unchanged logic — User Story 3).
- [X] T010 [US1] In `.github/scripts/verify-board-stop-check.py`, replace the `SHELL_CASES` entry `("a completed run is not cancelled", [_marker(555), STOP], "true", None)` with `("an already-terminal refusal is attempted, not warned, and recorded", [_marker(555), STOP], "true", "555", cancel_fail=True, cancel_stderr="HTTP 409: Conflict", want_warning=False, want_info_line=True)` (field order per T005/T006's extended tuple shape) — the attempt now happens even though the stubbed `RUNS["555"]["status"]` is `"completed"`, because that field is no longer read at all (gate-coverage-087.md: the old case was about the *ownership* guard, never about status alone blocking a cancel — SC-006).
- [X] T011 [US1] Run `python3 .github/scripts/verify-board-stop-check.py`; confirm the renamed case passes, `grep -n "cancel_target_status" .github/actions/wing-commander-board-stop-check/action.yml` returns no match, and the existing `EXPECTED_FILES`/`COMMAND_CASES_FILE` Python-level fixtures (unrelated to the composite shell) still pass unmodified.

**Checkpoint**: An already-terminal target produces no warning and one informational line; the run is attempted regardless of any pre-read status.

---

## Phase 4: User Story 2 - A cancellation that fails for a real reason is still reported (Priority: P1)

**Goal**: A cancellation failure that is not an already-terminal refusal — including empty error output, and including error text that merely contains the already-terminal status code's bare digits — is warned about, naming the run and carrying a neutralised copy of the error text.

**Independent Test**: Drive the stop check against a target run whose cancellation fails with a permission-style error, and confirm a warning is emitted that names the run and carries the error text (spec.md's own Independent Test for this story).

### Implementation for User Story 2

- [X] T012 [US2] In the `check` step's script, add a local `sanitize()` shell function — newline/tab flatten (`tr '\r\n\t' '   '`), collapse repeated spaces (`tr -s ' '`), truncate at 300 chars with a `… (truncated)` suffix, escape `%` to `%25` — byte-for-byte the same idiom `wing-commander-lifecycle-gate`'s `check` step already defines for itself (research.md D4). Apply it to `$cancel_error` before the FR-004 warning: `safe_cancel_error="$(sanitize "$cancel_error")"` then `echo "::warning::gh run cancel $stop_run_id failed: $safe_cancel_error"` (FR-011). Do **not** promote `sanitize()` to `_shared/` — the spec's own scope boundary (research.md D4) keeps it local; a third caller some day is the trigger to promote it, not this feature.
- [X] T013 [P] [US2] In `.github/scripts/verify-board-stop-check.py`'s `RUNS` dict, add four entries — `"777"`, `"888"`, `"1010"`, `"1111"` — each `{"status": "in_progress", "path": OWN_PATH, "repository": {"full_name": REPO}}` (the `status` field is unused by the composite now but kept for fixture realism). Do not reuse run id `"999"`; the harness's `GITHUB_RUN_ID` env is `"999"` (this run's own id).
- [X] T014 [US2] Add four `SHELL_CASES` entries (depends on T010, T013): (a) `"a non-terminal (permission) failure is warned"` — run `777`, `cancel_fail=True, cancel_stderr="HTTP 403: Resource not accessible by integration"`, `want_cancel="777"`, `want_warning=True`, `want_info_line=False`; (b) `"an empty-stderr failure is warned"` — run `888`, `cancel_stderr=""`, same expectations as (a) (FR-004's "including a failure with empty or unrecognised error output"); (c) `"a bare-409-without-HTTP-prefix failure is warned, not treated as already-terminal"` — run `1010`, `cancel_stderr="permission denied for run id 4091234"`, same expectations as (a) (SC-002's third checked-in case, proving the anchoring); (d) `"newline/workflow-command-shaped error text produces exactly one warning"` — run `1111`, `cancel_stderr="first line\n::warning::forged annotation should not survive\nsecond line"`, `want_cancel="1111"`, `want_warning=True`, `want_info_line=False`, plus an assertion beyond T006's shared checks that exactly one line of `proc.stdout` starts with `::warning::` (a line-anchored count, not a substring count of `"::warning::"` — the sanitised text still contains that substring a second time, mid-line, after flattening) and that no line of `proc.stdout` contains a raw, un-flattened newline inside the warning text (SC-008).
- [X] T015 [US2] Add a mutation to `.github/scripts/verify-board-stop-check.py` that inverts the already-terminal classification: read `CANCEL_VOCAB_SCRIPT_PATH` fresh from disk, swap its literal `exit 0`/`exit 1` outcomes, and pass the mutated text as `_run_shell_case()`'s `cancel_vocab_script=` override for a fresh `run_shell_cases()` pass — the same "swap and restore" idiom `verify-agent-verdict.py`'s Gate 22 uses for its own subprocess-invoked `SHARED_SCRIPT`. Assert at least one of T010's or T014's cases now fails; restore the original content after the check (FR-008, SC-003).
- [X] T016 [US2] Run `python3 .github/scripts/verify-board-stop-check.py`; confirm all four new cases and T010's renamed case pass, T015's mutation is reported caught, and `grep -n "sanitize(" .github/actions/wing-commander-board-stop-check/action.yml` shows it applied only on the FR-004 warning path.

**Checkpoint**: Every non-already-terminal cancellation failure — permission error, empty output, bare-digits-only, or workflow-command-shaped — produces exactly one warning naming the run, safely neutralised.

---

## Phase 5: User Story 3 - The existing target and self-run protections are untouched (Priority: P2)

**Goal**: The ownership guard, its warning, the target-check rationale comment, and the self-run skip survive this feature exactly as they were.

**Independent Test**: Re-run the existing checked-in stop-check cases — a different workflow's run, an unreadable run, a forged marker from a human, a stop request naming the current run — and confirm every one still results in no cancellation attempt, the same paused result, and a successful step (spec.md's own Independent Test for this story).

### Implementation for User Story 3

- [X] T017 [US3] Diff `.github/actions/wing-commander-board-stop-check/action.yml`'s ownership guard (`if [ -z "$cancel_target_path" ] ...; then`, ~line 167), its warning (~line 168), the target-check rationale comment block (~lines 148-159), and the self-run skip (`if [ "$stop_run_id" != "$GITHUB_RUN_ID" ]`, ~line 126) against the pre-feature version; confirm they are byte-identical except for T008's deletions/collapse immediately below them — no wording, no comparison operator, and no token routing changed (FR-006).
- [X] T018 [US3] Run `python3 .github/scripts/verify-board-stop-check.py` and confirm the unmodified `SHELL_CASES` entries — `"a different workflow's run is not cancelled"`, `"an unreadable run is not cancelled"`, `"an OWNER human's forged marker never reaches gh run cancel"`, `"no stop request, nothing cancelled"` — and every `EXPECTED_FILES`/`COMMAND_CASES_FILE` fixture (ownership/unreadable/forged-marker/self-run families) still pass with identical `paused` results, identical cancellation targets (`None` in every one of these), and identical token routing; confirm `composite_shell_check()`'s existing "cancel guard disabled" mutation is still caught (SC-004).

**Checkpoint**: Every pre-existing protection this feature does not touch still behaves exactly as before.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: FR-005/FR-009/FR-009a's vocabulary consolidation is not itself a user story — it is what makes both stop procedures share one recognition source — plus the repository-wide acceptance bar.

- [X] T019 In `.github/scripts/verify-single-home-idioms.py`, add `"cancel-already-terminal": ".github/actions/_shared/cancel-already-terminal.sh"` to `DECLARED_HOMES` (this alone extends `CHECK_NAMES`, which is `tuple(DECLARED_HOMES) + ("promotion",)`).
- [X] T020 Add a structural check `check_cancel_already_terminal(root=".")`, registered in `ALL_CHECKS`, that scans every quoted string literal (single- or double-quoted) in every subject file except the declared home, and flags any single literal that case-insensitively contains all three vocabulary substrings — `409`, `already completed`, `cannot cancel` — in any order. Use single-literal co-occurrence, not file-wide co-occurrence (the `check_board_stop_check`/`check_dispatch_and_wait` style): a file-wide check would false-positive on `pr-conversation.yml` itself once T023 lands, because that file's own surviving rationale comments and PR-facing prose legitimately mention all three phrases — each in a *separate* line/string, never combined into one literal. Only a single-literal check tells a re-implemented recognition pattern (one grep/case/regex argument) apart from that scattered, unrelated prose (research.md D7's "co-occurrence... in one grep/regex-shaped construct"). Use the bare substring `409` (not `HTTP 409`) for this *detection* heuristic specifically, so a re-pasted copy of the *original, unanchored* `'409|already completed|cannot cancel'` pattern is still caught — contracts/cancel-already-terminal-script.md: "a mutation that reintroduces a bare-409 third copy must be caught by this check" (SC-007). FR-005's `HTTP`-anchoring requirement is on the shipped predicate's own matching behaviour (T002), not on this gate's duplicate-detection heuristic.
- [X] T021 In `_clean_tree()`, add a synthetic entry at `DECLARED_HOMES["cancel-already-terminal"]` — a `case`/`grep`-shaped snippet whose single literal co-occurs all three fragments, standing in for the real script — required so every existing self-test's "clean tree" baseline does not hard-fail on a missing declared home (`evaluate()`'s `for check, home in DECLARED_HOMES.items()` file-existence check).
- [X] T022 Add two self-tests to `run_selftest()`: (a) `selftest_third_paste_fails("cancel-already-terminal", ".github/workflows/third-cancel-vocab.yml", ...)` with a single-literal `grep -qiE '409|already completed|cannot cancel'`-shaped re-implementation, asserting it is caught; (b) a new `selftest_cancel_vocab_scattered_mentions_pass()` that writes a file containing all three phrases across separate lines/comments (never combined in one literal) — modeled directly on the surviving `pr-conversation.yml` comment lines this feature leaves in place (research.md D6: "unchanged: everything else in this step") — asserting `evaluate()` reports **no** `cancel-already-terminal` finding for it, proving the check does not false-positive on `pr-conversation.yml` once T023 lands.
- [X] T023 In `.github/workflows/pr-conversation.yml`'s "Stop procedure" step (~line 2502), replace `if grep -qiE '409|already completed|cannot cancel' "$RUNNER_TEMP/cancel-err.txt" 2>/dev/null; then` with `if bash .github/actions/_shared/cancel-already-terminal.sh "$(cat "$RUNNER_TEMP/cancel-err.txt" 2>/dev/null)"; then` — the sole edit contracts/pr-conversation-vocabulary-consolidation.md specifies. Everything else in the step (the `outcome` variable, the three `gh pr comment` bodies, the `impl_run_id` lookup-and-cancel block, all token usage) is unchanged. Accept the narrow, documented behaviour change (research.md D6): a failure whose text is not an already-terminal refusal but contains the bare digits `409` now resolves to `outcome="cancel-failed"` instead of `outcome="already-completed"` at this site too, moving it toward its own governing "never report a failure as a completion" requirement.
- [X] T024 Run `python3 .github/scripts/verify-single-home-idioms.py` and `python3 .github/scripts/verify-single-home-idioms.py --self-test` against the real, now-edited tree; confirm both pass clean — in particular confirm `pr-conversation.yml` itself is **not** flagged by the new `cancel-already-terminal` check (T022(b)'s synthetic fixture only approximates this; this run against the real file is the actual proof).
- [X] T025 Run `python .github/scripts/run-local-gates.py` (the full local PR-time gate suite, CLAUDE.md "Before pushing") and confirm every gate passes clean, including `verify-gate-12.py` (its token-routing assertions for the Stop procedure step are unaffected by T023 per contracts/pr-conversation-vocabulary-consolidation.md's "Gate coverage" section) (SC-005).
- [ ] T026 Record, on the implementation PR, a determination of whether CLAUDE.md's `review-step-gating`/`container-shell-safety` skill passes apply: no `container:` block is added, and the only `if:` touched by this feature is a pre-existing bash-level `if` inside the `check` step's own `run:` block — no step-level YAML `if:`/`continue-on-error:` is added, removed, or changed. If that determination changes during implementation (e.g. a step-level `if:` turns out to be needed), get the applicable skill's pass before merge.
- [ ] T027 After this feature's implementation PR merges, re-drive one real run per quickstart.md's "Manual end-to-end sanity check": dispatch `board-loop.yml` (or exercise `wing-commander-board-stop-check` in isolation) against a stop request naming an already-completed run, and, separately, one that genuinely fails to cancel (e.g. a temporarily under-permissioned cancel token in a disposable test repository). Record on the PR or issue #621 that the already-terminal case shows no `::warning::` and one informational line, the real-failure case shows a `::warning::` naming the run with no broken/forged annotation, and both show `paused=true` and a successful exit (CLAUDE.md "Working the issue board" prove step).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user stories — the shared predicate script (T002) and the fixture harness's ability to drive a failing `gh run cancel` through it (T004-T006) are what every story's fixtures exercise.
- **User Stories (Phase 3-5)**: All depend on Foundational completion.
  - US1 (T008-T011) is the first to touch `action.yml`'s `check` step; US2 (T012-T016) edits the same step immediately after (its `sanitize()` call sits inside the branch T008 already created) — **US2 depends on US1's T008 landing first**, even though both are P1.
  - US3 (T017-T018) is a verification-only story: it depends on T008 (the restructure it verifies survived) but not on US2's sanitize/fixture work, so it may run in parallel with US2 once T008-T011 are done.
- **Polish (Phase 6)**: T019-T022 (the single-home gate extension) depend only on T002 (the shared script must exist to have a declared home). T023 (the `pr-conversation.yml` repoint) depends only on T002 as well, and touches a disjoint file from every user story — it may run any time after Foundational, in parallel with US1-US3. T024-T027 depend on all prior tasks.

### Within Each User Story

- Composite edits before the gate-script fixtures that assert them.
- Fixture additions before the mutation that must be caught by at least one of them.
- Each story's own checkpoint task runs last within that story.

### Parallel Opportunities

- T002 (shared script) and T004 (`STUB_GH` extension) touch different files and can run in parallel within Foundational; T003 depends on T002, T005 depends on both T002 and T004.
- T013 (`RUNS` dict additions) can run in parallel with T012 (`sanitize()` in `action.yml`) — different files.
- US3 (T017-T018) can run in parallel with US2 (T012-T016) once US1 (T008-T011) is done.
- T023 (`pr-conversation.yml`) can run in parallel with any of US1/US2/US3 — it touches neither `action.yml` nor `verify-board-stop-check.py`, and needs only T002.
- T019-T022 (single-home gate extension) can run in parallel with US1-US3 once T002 is done, but T024 (verifying the real, edited `pr-conversation.yml` isn't flagged) must wait for T023.

---

## Parallel Example: Foundational

```bash
# T002 and T004 touch different files and have no dependency on each other:
Task: "Create .github/actions/_shared/cancel-already-terminal.sh"
Task: "Extend STUB_GH's gh run cancel branch with a configurable failure"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks every story).
3. Complete Phase 3: User Story 1 — this alone eliminates the spurious warning, the feature's entire reason for existing.
4. **STOP and VALIDATE**: run T011's checkpoint independently.

### Incremental Delivery

1. Setup + Foundational → the shared predicate exists and the harness can drive a configurable cancel failure through it.
2. Add User Story 1 → validate independently (T011) → MVP: no more spurious already-terminal warnings.
3. Add User Story 2 → validate independently (T016): every real failure is still warned, safely.
4. Add User Story 3 → validate independently (T018): nothing else moved.
5. Polish: vocabulary consolidation at the second site (T019-T024), full gate suite (T025), skill-pass determination (T026), post-merge live-run proof (T027).

### Notes

- [P] tasks = different files, no dependencies.
- FR-008/SC-003 and FR-009a/SC-007 are each self-test-first in spirit: the classification mechanism (T008) and the single-home check (T020) each ship together with the mutation that proves they are enforced (T015, T022(a)), not after.
- T022(b) and T024 exist specifically because a naive file-wide co-occurrence check would have shipped a gate that fails on its own second consuming site (`pr-conversation.yml`) the moment T023 lands — the single-literal design and its dedicated proof are what keep that from happening.
