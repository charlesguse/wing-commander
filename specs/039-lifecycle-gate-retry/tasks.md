---

description: "Task list for A Transient API Blip No Longer Kills Six Stages at Entry, and the Gate Says What Actually Happened"
---

# Tasks: A Transient API Blip No Longer Kills Six Stages at Entry, and the Gate Says What Actually Happened

**Input**: Design documents from `/specs/039-lifecycle-gate-retry/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/wing-commander-lifecycle-gate.md, contracts/lifecycle-gate-retry-coverage.md, quickstart.md

**Tests**: Requested — FR-011 through FR-014 require executable coverage that drives the shipped step against a stubbed `gh` and proves both the retry and fast-fail paths run, with mutation coverage proving each can independently fail. Coverage tasks are folded into the user-story phase whose behavior they prove (US1's retry mechanic, US2's message wording, US3's fast-fail path), plus a dedicated mutation-proof phase for US4, rather than a separate testing phase.

**Organization**: This feature's footprint is one step of one existing file rewritten in place (`.github/actions/wing-commander-lifecycle-gate/action.yml`), one new coverage script (`.github/scripts/verify-lifecycle-gate-retry.py`), and one new gate step wiring it into `.github/workflows/lint-workflows.yml` (plan.md's Structure Decision). No new directory, no new composite, zero edits to any of the six calling stage workflows. Because the retry loop, classification, and diagnostic rendering are one inseparable rewrite of a single step (research.md D1–D5), the core implementation is a single task under User Story 1; the later P1/P2 stories build coverage on top of it rather than re-touching `action.yml`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split. All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the gate number this feature claims is actually free, and establish the pre-feature baseline every scenario below is compared against.

- [X] T001 Run `grep -n "name: Gate [0-9]" .github/workflows/lint-workflows.yml` and confirm no step is already named `Gate 25` (research.md D7, data-model.md's Gate registry entry — the highest number in use today is 24). Record the current `Check lifecycle issue state` step's byte-for-byte text (`git show HEAD:.github/actions/wing-commander-lifecycle-gate/action.yml`) as the SC-005 first-attempt-success baseline T012 will diff against.

**Checkpoint**: Gate 25 numbering is free; the pre-feature baseline is captured.

---

## Phase 2: Foundational (Blocking Prerequisites)

**No blocking prerequisites.** This feature's entire implementation is one step of one file (T002) plus one coverage script that grows across the user-story phases below (T003-T009); there is no shared scaffolding to build before story work can begin.

---

## Phase 3: User Story 1 - A momentary API blip costs a retry, not a run (Priority: P1) 🎯 MVP

**Goal**: The gate's state read survives a transient failure by retrying, bounded to a small budget, and a later-attempt success is indistinguishable from a first-attempt success.

**Independent Test**: Drive the shipped gate against a stubbed API that fails with a transient server error on its first call and succeeds afterwards, and confirm the gate reports the correct issue state and succeeds — and that a stage entering through it proceeds normally.

### Implementation for User Story 1

- [X] T002 [US1] Rewrite `Check lifecycle issue state`'s `run:` block in `.github/actions/wing-commander-lifecycle-gate/action.yml` (lines 51-82) per research.md D1-D5 and contracts/wing-commander-lifecycle-gate.md's "Behavior — CHANGED" section:
  - Wrap the existing `gh issue view "$ISSUE_NUMBER" --json state --jq .state` read in a loop of up to 3 attempts. Each attempt: `timeout 4` around the `gh` call; stderr redirected to a per-attempt `mktemp` file (`2>"$stderr_file"`), read and removed immediately after the attempt (research.md D3) — stdout (`state="$(...)"`) stays isolated from stderr, unlike today's stdout-only capture.
  - On success (non-empty `state`), break the loop immediately and fall through to the existing `case`/`is-open` logic unchanged (FR-007, FR-008 — this path is untouched by the retry).
  - On failure (non-zero exit or empty `state`), capture the diagnostic: the stderr file's contents, or the synthetic string `"gh exited 0 but returned an empty state"` when the call exited 0 with nothing to quote (research.md D5). Classify it against two permanent, case-insensitive patterns, checked in order (research.md D2, data-model.md's Failure classification table): (1) not-found — `Could not resolve to an.*[Ii]ssue` or `HTTP 404`; (2) credential-rejected — `HTTP 401`, `Bad credentials`, `Resource not accessible by integration`, or scope-shaped wording (`requires authentication`, `insufficient .* scope`, `missing .* scope`). Do **not** match a bare `HTTP 403` against the credential pattern (research.md D2's rationale — a rate-limited 403 must fall through to retry).
  - A permanent classification fails immediately: `::error::` naming the specific condition (not-found keeps today's "may not exist, or the token lacks issues: read" wording, scoped now to only this class; credential-rejected names the credential, never the issue — FR-002, FR-005), quoting the sanitised diagnostic (below), `exit 1`. No further attempt is made.
  - Anything else (a recognised transient shape — `HTTP 5\d\d`, `timed out`, `Could not connect`, connection-reset wording — or an unrecognised fault, or the empty-state case) is retried: log with `::warning::` (never `::error::` — FR-007 forbids annotating the run failed for a read that goes on to succeed), sleep 1 second if attempts remain, and loop. Internally tag the failure `transient` or `unclassified` (matches neither permanent nor recognised-transient pattern) purely so the exhaustion message below can say which (FR-006).
  - If all 3 attempts are exhausted with no success, fail with a single `::error::` stating: the read was retried, how many attempts were made, whether the retried failures were a recognised transient class or could not be classified, and the last attempt's sanitised diagnostic (FR-006, FR-010 — exactly one result published either way).
  - Before any diagnostic text reaches a `::warning::`/`::error::` line, sanitise it (research.md D4, FR-017, FR-018): strip `\r`/`\n` (replace with a space), collapse repeated whitespace, cap at 300 characters with a `… (truncated)` suffix when longer, then `%`-escape (`%` → `%25`). Never construct any string containing `$GH_TOKEN`'s value.
  - Leave the existing unrecognised-state `case`/`is-open` fail-loud path (current lines 71-82) exactly as it is today, running once after the retry loop's first successful read — it is never retried (FR-008).

**Checkpoint**: A transient failure now costs a retry, not a run; a permanent failure and a first-attempt success are structurally unchanged. Not yet provable without T003.

- [X] T003 [P] [US1] Create `.github/scripts/verify-lifecycle-gate-retry.py` (contracts/lifecycle-gate-retry-coverage.md), following `verify-stall-restart-runbook.py`'s established shape: `use_utf8_stdout()`, `resolve_bash()`, `ensure_jq()`, `find_step()` to extract the real, unmutated `Check lifecycle issue state` step from `.github/actions/wing-commander-lifecycle-gate/action.yml` at run time (no second copy), and `run_step()`/`parse_github_output()` to execute it and read `state`/`is-open`. Build the stub mechanism (research.md D6, contracts/lifecycle-gate-retry-coverage.md's "Stub mechanism"): a small Python helper that writes a `#!/bin/sh` script to `bindir/gh` (`chmod 0o755`), `PATH`-prepended via `run_step`'s `env_extra`, which increments a call-count file (`GH_CALL_COUNT`, unique per test case under the per-test `RUNNER_TEMP`) on every invocation and branches its exit code/stdout/stderr on the resulting count — a distinct generated stub per scenario rather than one scenario-selector mega-stub. Implement and assert these first three scenarios (this story's own Acceptance Scenarios 1, 4, 6):
  - **Transient-then-succeed**: stub fails with `HTTP 502` on calls 1-2, returns `OPEN` on call 3. Assert `rc == 0`, `state == "OPEN"`, `is-open == "true"`, and `GH_CALL_COUNT == 3` (more than one read attempted).
  - **Unclassified-then-succeed**: stub fails with an unrecognised, made-up fault string on call 1, returns `CLOSED` on call 2. Assert `rc == 0`, correct outputs, `GH_CALL_COUNT == 2` — proves FR-009's retry-by-default is exercised for a fault matching no known class, not only stated (SC-009).
  - **Success, empty state**: stub exits 0 with empty stdout on call 1, returns `OPEN` on call 2. Assert `rc == 0`, correct outputs, `GH_CALL_COUNT == 2` — proves the empty-successful-read case is retried (research.md D5), not folded into a generic failure.

  Each assertion failure must print enough context (scenario name, expected vs. actual, captured stdout/stderr) to diagnose without re-running by hand, matching every other `verify-*.py` gate's convention. Exit 0 iff every scenario in the script (including those T005/T006/T007 add later) passes; non-zero otherwise. This task's own scenarios will not pass until T002 lands.

**Checkpoint**: `python3 .github/scripts/verify-lifecycle-gate-retry.py` exists and, once T002 has landed, proves SC-001 and this story's Acceptance Scenarios 1 and 6 against the real shipped step.

- [X] T004 [US1] Wire `verify-lifecycle-gate-retry.py` into `.github/workflows/lint-workflows.yml`'s `lint` job as a single step named `Gate 25 — the lifecycle gate retries transient failures and fails fast on permanent ones` (`run: python3 .github/scripts/verify-lifecycle-gate-retry.py`), placed immediately after Gate 24's self-test step and before Gate 10's registry-wiring check — a single-step shape matching Gate 14's precedent (no separate self-test step; the mutation checks T007 adds live inside the script itself, per research.md D7). Confirm `python3 .github/scripts/run-local-gates.py` and Gate 10 (`verify-gate-wiring.py`'s naming-convention discovery, if run locally) would pick it up automatically with no manifest edit.

**Depends on**: T004 depends on T003 (the step must exist before it can be wired). T003's scenario assertions depend on T002 having landed.

**Checkpoint**: User Story 1 is independently testable — `python3 .github/scripts/verify-lifecycle-gate-retry.py` passes its three scenarios, proving a transient blip costs a retry, not a run.

---

## Phase 4: User Story 2 - The error says what actually happened (Priority: P1)

**Goal**: A gate failure's `::error::` line quotes what the API actually reported and names the condition that actually occurred, with the "may not exist" wording scoped to only the not-found case.

**Independent Test**: Drive the shipped gate against stubbed failures of each class in turn and confirm each failure line quotes what the API reported and describes the class that actually occurred.

### Implementation for User Story 2

- [X] T005 [US2] Extend `.github/scripts/verify-lifecycle-gate-retry.py` (T003) with two budget-exhaustion scenarios (this story's Acceptance Scenarios 4 and 6, spec Edge Case "every attempt fails transiently"):
  - **Budget exhausted, recognised transient**: stub fails every call with `HTTP 503`. Assert `rc != 0`, `GH_CALL_COUNT == 3` (the full budget spent), and the captured `::error::` output (a) states 3 attempts were made, (b) quotes the last attempt's `HTTP 503` diagnostic verbatim, and (c) says the failures were a recognised transient class (not "could not be classified").
  - **Budget exhausted, unclassified**: stub fails every call with an unrecognised, made-up fault string. Assert `rc != 0`, `GH_CALL_COUNT == 3`, and the `::error::` output (a) states 3 attempts were made, (b) quotes the last diagnostic verbatim, and (c) says the failures could not be classified — not that they were a known transient fault. Assert this wording differs from the recognised-transient scenario's (FR-006's distinction must be visible in the log).

- [X] T006 [US2] Extend `.github/scripts/verify-lifecycle-gate-retry.py` with message-content assertions layered on top of the not-found and credential-rejected scenarios T007 introduces for User Story 3 — add these assertions in this task if T007 has not yet run, or extend them in place if it has (same file, sequential edit; either order is fine since both scenarios are additive):
  - The not-found scenario's `::error::` output contains "may not exist" wording and the issue number, and does **not** name the credential/token.
  - The credential-rejected scenario's `::error::` output names the token/credential as the cause and does **not** contain "may not exist" wording.

  Together with T005, this proves US2's Acceptance Scenarios 1-5 and SC-003/SC-007: every failure message contains what was actually observed, and the three failure kinds (transient-exhausted, not-found, credential-rejected) read as distinguishable from the reported line alone.

**Depends on**: T005 and T006 depend on T002 (the wording they assert on) and T003 (the harness scaffolding). T006 depends on T007 existing for the scenarios it decorates, or is written first and T007 reuses its stubs — either ordering is acceptable since they touch the same file additively.

**Checkpoint**: A maintainer reading only the `::error::` line can tell a transient-exhausted failure, a missing issue, and a credential problem apart (SC-007) — the direct fix for the source incident's misdirection.

---

## Phase 5: User Story 3 - A real failure still fails immediately (Priority: P2)

**Goal**: A permanent failure — missing issue or rejected credential — still fails on the first attempt, spending none of the retry budget, and an unrecognised-but-successful state value still fails loudly without retrying.

**Independent Test**: Drive the shipped gate against a stubbed API that always reports the issue as missing, and confirm exactly one read is attempted; repeat for a credential failure. A test that cannot tell one attempt from several does not satisfy this story.

### Implementation for User Story 3

- [X] T007 [US3] Extend `.github/scripts/verify-lifecycle-gate-retry.py` with three fast-fail scenarios (this story's Acceptance Scenarios 1, 2, 4):
  - **Always not-found**: stub emits `Could not resolve to an issue with the number of X.` and exits 1 on every call. Assert `rc != 0` and, critically, `GH_CALL_COUNT == 1` — exactly one read attempted, not merely a failing one (this story's explicit bar: "a test that cannot tell one attempt from several does not satisfy this story").
  - **Always credential-rejected**: stub emits `HTTP 401: Bad credentials` and exits 1 on every call. Assert `rc != 0`, `GH_CALL_COUNT == 1`.
  - **Success, unrecognised value**: stub exits 0 with `MERGED` (a real but unhandled state) on call 1. Assert `rc != 0`, `GH_CALL_COUNT == 1` — proves an unrecognised *answer* is not retried, unchanged FR-008 behavior (this story's Acceptance Scenario 4: "an unrecognised answer is an answer, not an absence of one").

**Depends on**: T007 depends on T002 and T003.

**Checkpoint**: Zero added delay on a permanent failure (SC-002); User Story 3 is independently testable and does not regress today's fast-fail behavior.

---

## Phase 6: User Story 4 - The retry is proven to run, not merely shipped (Priority: P2)

**Goal**: Reverting the retry, widening it to swallow permanent failures, or narrowing it so an unclassified failure is fatal, each independently fail a check — and the check's own removal is caught too.

**Independent Test**: Revert the retry and confirm a check fails; separately, make every failure class retryable and confirm a check fails; separately, make an unclassifiable failure fatal instead of retried and confirm a check fails; then confirm all three checks pass on the delivered feature.

### Implementation for User Story 4

- [X] T008 [US4] Add FR-013's four required mutations to `.github/scripts/verify-lifecycle-gate-retry.py` (research.md D7, contracts/lifecycle-gate-retry-coverage.md's "Required mutations" table), applied to a deep copy of the real step text extracted by `find_step()` — never to the file on disk — using the `if mutated == steps: raise` guard `verify-stall-restart-runbook.py:345` establishes, so a mutation helper that silently fails to apply is itself caught rather than producing a false pass:
  1. **Revert the retry**: collapse the loop to a single attempt (today's shape). Assert the transient-then-succeed scenario (T003) now fails (`rc != 0` where the unmutated suite gets `0`).
  2. **Widen the permanent-pattern classifier**: make the not-found pattern also match `HTTP 502`. Assert the transient-then-succeed scenario now fails after exactly one attempt instead of retrying.
  3. **Narrow the retry**: replace the allow-list classifier with a fixed list of known transient shapes, so an unclassified failure fails immediately instead of retrying. Assert the unclassified-then-succeed scenario (T003) now fails after exactly one attempt.
  4. **Gate 25 removed from the registry**: read `.github/workflows/lint-workflows.yml` directly (not the step text `find_step()` extracts) and assert a step whose name starts with `Gate 25` exists and is not `if: false` — the FR-014 reflexive check this script must make about itself, per repository convention (Gate 15's own finding), since a script cannot detect its own absence from a file it isn't in.

**Depends on**: T008 depends on T002, T003, T005, T006, and T007 (mutates and re-runs the scenarios they establish) and T004 (the fourth mutation reads the wired step).

**Checkpoint**: `python3 .github/scripts/verify-lifecycle-gate-retry.py` fails on each of the four mutations and passes on the delivered feature — SC-006 holds, and Gate 25 proves itself rather than only the composite.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Whole-feature validation once every story has landed.

- [X] T009 [P] Run quickstart.md's six scenarios end to end: `python3 .github/scripts/verify-lifecycle-gate-retry.py` and its `-v` variant (Scenarios 1-3), the byte-for-byte diff of a first-attempt-success run against T001's captured pre-feature baseline (Scenario 4, SC-005), the by-hand mutation drill confirming a non-zero exit per mutation and exit 0 once reverted (Scenario 5), and the `grep -nE "timeout 4|sleep 1"` constant check confirming the 14-second worst case stays inside the 15-second ceiling (Scenario 6, FR-003/SC-004).
- [X] T010 [P] Confirm FR-015/FR-016/SC-008: diff `.github/actions/wing-commander-lifecycle-gate/action.yml`'s `inputs:`/`outputs:` blocks against the pre-feature version (unchanged), and confirm none of `clarify.yml`, `finalize.yml`, `implement.yml`, `intake.yml`, `pr-conversation.yml`, or `tasks.yml` (the six calling stage workflows) or any other composite action was edited by this feature.
- [X] T011 Run `actionlint` (with shellcheck) against `.github/actions/wing-commander-lifecycle-gate/action.yml` and `.github/workflows/lint-workflows.yml`, and run `python3 .github/scripts/run-local-gates.py` if available in the executing environment, confirming every gate — including the new Gate 25 — passes cleanly against the repository as it stands after all four user stories land.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Empty — no blocking prerequisites beyond Setup.
- **User Stories (Phase 3-6)**: All depend on T002 (the one `action.yml` rewrite) having landed for their scenarios to pass, though the coverage script's scaffolding (T003) can be drafted in parallel with T002. US2 (Phase 4) and US3 (Phase 5) both extend the same file T003 creates and can proceed in either order. US4 (Phase 6) depends on every earlier story's scenarios existing, since its mutations re-run them.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories — the MVP. Contains the only edit to `action.yml` (T002).
- **User Story 2 (P1)**: Depends on User Story 1's T002 (the wording it asserts on) and T003 (the harness).
- **User Story 3 (P2)**: Depends on User Story 1's T002 and T003.
- **User Story 4 (P2)**: Depends on User Stories 1, 2, and 3 (mutates and re-runs their scenarios) and User Story 1's T004 (Gate 25's own wiring, for its fourth mutation).

### Within Each User Story

- T002 (the rewrite) must land before any scenario asserting on it can genuinely pass, even though T003's scaffolding can be written first.
- Story complete before moving to the next priority, per the Implementation Strategy below.

### Parallel Opportunities

- T003 (new coverage script scaffolding) can be drafted in parallel with T002 (the `action.yml` rewrite it will validate), marked `[P]` — though its scenarios only pass once T002 lands.
- T009, T010, and T011 (Polish) touch different concerns (behavioral quickstart validation, contract-surface diffing, linting) and are marked `[P]`.
- T005/T006 (US2) and T007 (US3) all extend the same single file (`verify-lifecycle-gate-retry.py`) additively and are not marked `[P]` against each other — sequential edits to one file.

---

## Parallel Example: User Story 1

```bash
# T002 and T003 can start together once Setup completes:
Task: "Rewrite the retry/classification loop in action.yml (T002)"
Task: "Scaffold verify-lifecycle-gate-retry.py's harness and stub mechanism (T003)"
# T003's own scenario assertions will not pass until T002 lands.
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 3: User Story 1 — this alone fixes the defect the incident named: a transient API blip no longer kills a stage at entry.
3. **STOP and VALIDATE**: Run `python3 .github/scripts/verify-lifecycle-gate-retry.py`; confirm its three US1 scenarios pass against the real shipped step.

### Recommended Scope: Both P1 Stories

User Story 1 stops the failure; User Story 2 fixes the misdirection that made the source incident worse than a plain failure would have been. Both are P1 for that reason — deliver Phases 3-4 together before considering this feature's core value shipped.

### Incremental Delivery

1. Complete Setup → Gate 25 numbering confirmed free, baseline captured.
2. Add User Story 1 → validate via `verify-lifecycle-gate-retry.py`'s first three scenarios → the defect is fixed.
3. Add User Story 2 → validate via the extended script's message-content assertions → the misdirection is fixed.
4. Add User Story 3 → validate via the fast-fail scenarios → today's behavior is confirmed not regressed.
5. Add User Story 4 → validate via the four mutations → the fix is proven to stay proven.
6. Phase 7 Polish → whole-feature sweep.

---

## Notes

- `[P]` tasks touch different files, or the same file in a way with no ordering dependency on other unfinished tasks.
- `[Story]` label maps each task to its user story for traceability.
- T002 is the only task that edits `.github/actions/wing-commander-lifecycle-gate/action.yml` — every other task either builds or extends `verify-lifecycle-gate-retry.py`, wires it into `lint-workflows.yml` (T004), or validates the result. There is no task-level file collision to resolve.
- Reverting T002 must fail T008's first mutation-check scenario, not only reduce test count — this is the FR-013/US4 bar the whole story exists to enforce.
- This feature does not touch `.github/actions/wing-commander-lifecycle-gate`'s inputs/outputs, any of the six calling stage workflows, or the `implement` silent chain-stop tracked separately as #231 (FR-016, Out of Scope) — no task above should introduce such an edit.
