---

description: "Task list for A Failed `gh api` Read Never Becomes Data"
---

# Tasks: A Failed `gh api` Read Never Becomes Data

**Input**: Design documents from `/specs/091-gh-api-error-capture/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not requested as a separate TDD pass; each new gate's own `--self-test` (Gate 28's shape) is the test surface, folded into the tasks that build it.

**Organization**: Tasks are grouped by user story (spec.md's P1/P2/P3), matching plan.md's three-part approach — audit+fix, the gate, harness conformance.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every path below is exact, not illustrative.

## Path Conventions

CI-tooling feature — no `src/`/`tests/` split. Paths are `.github/scripts/`,
`.github/workflows/`, `.github/actions/` at the repository root (plan.md
Project Structure).

---

## Phase 1: Setup

**Purpose**: Confirm the two facts every later task depends on before any
file is touched — the live inventory research.md D1 sized this feature
against, and the gate numbers research.md D6 provisionally assigned.

- [X] T001 Re-run `grep -rnE '[A-Za-z_][A-Za-z0-9_]*="?\$\(\s*gh api\b' .github/workflows .github/actions` (excluding harness `tests/` fixture directories) and confirm it still returns exactly the 32 sites across the 11 files research.md D1 records (`.github/actions/wing-commander-fold-commit/action.yml:92`; `.github/actions/wing-commander-metrics-persist/action.yml:624`; `.github/workflows/auto-release.yml:1214,1455,1488,1572,1638`; `auto-update-spec-kit.yml:558,1021,3461`; `board-loop.yml:1124,1131`; `lint-workflows.yml:4776`; `pr-conversation.yml:625,733,734,1799,1800,2632,2633,3385,3522`; `tasks.yml:537,1632,1861,2004`; `watchdog.yml:1762,1769,4001`; `wing-commander-7-cleanup.yml:115,128`; `wing-commander-watchdog-test.yml:108,171`). If the count or line numbers drifted (a concurrent PR touched one of these files), update the per-file task list below to match the tree as it now stands before proceeding. Confirmed unchanged: 32 sites, same 11 files, same line numbers.
- [X] T002 Re-verify the next unclaimed gate numbers against `main` immediately before this feature wires anything (research.md D6): as of this writing, Gate 125 has already been claimed by `specs/062-lifecycle-review-gate` (`verify-lifecycle-review-gate-composite-provenance.py`, wired in `lint-workflows.yml` around line 4602) since this feature's plan.md was written, so this feature's two new gates are **Gate 126** (`verify-gh-api-error-capture.py`, User Story 2) and **Gate 127** (`verify-gh-error-stub-conformance.py`, User Story 3). Re-check `grep -rn "Gate 12[5-9]" .github/scripts .github/workflows` right before wiring each gate (T023, T028) in case another concurrent spec claims one of these two numbers first, and renumber both this feature's gates and their doc references together if so. Confirmed: 126 and 127 remain unclaimed.

---

## Phase 2: Foundational (Blocking Prerequisites for User Stories 2 and 3)

**Purpose**: The one shared module (research.md D4) both new gates import,
so neither gate invents its own notion of "is this line a covered capture."
**User Story 1 does not depend on this phase** — its fixes are governed
directly by research.md D5's rules and can proceed in parallel with, or
ahead of, this phase.

**⚠️ CRITICAL**: User Stories 2 and 3 cannot start until this phase is complete.

- [X] T003 Create `.github/scripts/wc_gh_capture.py` with `COVERED_GH_SUBCOMMANDS: tuple[str, ...] = ("api",)` (FR-013 — the one list both new gates import; widening it later is adding a tuple entry, never a second list) and `find_capture_sites(text: str, file: str) -> list[CaptureSite]` implementing research.md D2's quote-aware raw-text scan (Gate 28's/Gate 18's technique, not `yaml.safe_load` of `run:` blocks and not a shell parser) for every covered-subcommand command-substitution capture in `text`. Each `CaptureSite` carries `file`, `line`, `variable`, `subcommand`, and `guard_form` (`if-negated` | `or-fallback` | `bare` | `pipeline`) per data-model.md's `Capture site` table. `text` must not be assumed to be a full YAML document — this function is also called against one extracted `run:` block's text by User Story 3 (research.md D7).
- [X] T004 Add `classify_failure_path(text: str, site: CaptureSite) -> Classification` to `.github/scripts/wc_gh_capture.py`, implementing research.md D5's four safe forms — `exits` (an `exit N` or a call to a locally-defined function whose own body contains `exit`, e.g. `fail_infra_on_read`), `reassigns` (a new assignment to the same variable name before its next read), `loop-exits` (`continue`/`break` before the variable's next read, inside an enclosing `for`/`while`), `opted-in` (the `# wc-gh-api-error-exempt: <reason>` marker, research.md D3, same-line or immediately-preceding line, matching Gates 18/28's `EXEMPT_RE`/`_is_exempt` shape) — plus the `unsafe` default. A marker with no non-whitespace reason after the colon is its own distinct failure, not `opted-in`. Return the `evidence` string data-model.md's `Failure path` entity records (the matched token, call, reassignment value, or marker reason) for the failure-message contract.

**Checkpoint**: `wc_gh_capture.py` exists and is importable — User Stories 2 and 3 can now proceed (User Story 1 may already be underway).

---

## Phase 3: User Story 1 - No live capture site can carry an error body downstream (Priority: P1) 🎯 MVP

**Goal**: Every one of the 32 live `gh api` capture sites is corrected,
confirmed already-safe, or carries a stated-reason exempt marker, so a
failed read can never reach a comparison, a branch name, a comment body,
or a downstream output as if it were real data.

**Independent Test**: Re-run T001's grep; for each of the 32 sites, show by
inspection that a non-zero exit from the read now exits the step, reassigns
the captured variable before any further use, or is deliberately annotated
— matching research.md D5's classification. This ships even if User
Stories 2 and 3 never land (spec.md).

### Fixes — confirmed unsafe sites

- [X] T005 [P] [US1] Fix `.github/actions/wing-commander-fold-commit/action.yml:92` — the confirmed defect (research.md D-finding, plan.md Summary): `bot_login="$(gh api user --jq .login 2>/dev/null || true)"` leaves `bot_login` holding the raw error JSON on an HTTP failure, not empty, because `|| true` only masks the exit status without resetting the value — so line 93's `[ -n "$bot_login" ] || bot_login="wing-commander-bot[bot]"` fallback never fires and a failed read reaches `git config user.name`/`user.email` as the literal error text. Replace with a form that resets `bot_login` on failure, e.g. `if ! bot_login="$(gh api user --jq .login 2>/dev/null)"; then bot_login=""; fi`, leaving the successful-read behavior (a valid login is used as-is) unchanged (FR-002/FR-004).
- [X] T006 [P] [US1] Fix `.github/actions/wing-commander-metrics-persist/action.yml:624` — `existing="$(gh api "repos/${GITHUB_REPOSITORY}/issues/${issue}/comments" --paginate --jq '...' 2>/dev/null | head -1)"` has no guard at all on the read's own exit status (`head -1`, the pipeline's last stage, exits 0 regardless of what `gh api` did). Add an explicit guard so a failed read resets `existing` to empty before `existing_id="$(printf '%s' "$existing" | jq -r '.id // empty' 2>/dev/null)"` runs on line 626, without changing today's successful-read shape (the comment-splice logic below, gated on `existing_id` being non-empty, must still work identically on success) (FR-002/FR-004).
- [X] T007 [P] [US1] Fix `.github/workflows/watchdog.yml:1769` and `.github/workflows/watchdog.yml:4001` — `tasks_actual="$(gh api -X GET ... --jq '.content' 2>/dev/null | base64 -d 2>/dev/null | grep -c '^- \[[xX]\]')" || true` (1769) and `jobs_json="$(gh api "repos/.../jobs?per_page=100" 2>/dev/null || echo '{"jobs":[]}')"` (4001) are both unsafe: the first's `|| true` fallback (outside the substitution) never reassigns `tasks_actual` on failure, it only swallows the exit status; the second's `|| echo '{"jobs":[]}'` runs *inside* the substitution, so on failure its output is appended after whatever `gh api` already printed to stdout rather than replacing it, leaving `jobs_json` holding the error body followed by the fallback JSON. Fix each so the captured variable is explicitly reset to a safe default (`""`/`'{"jobs":[]}'`) on a non-zero exit from the read, before any later use, preserving today's successful-read values (FR-002/FR-004).
- [X] T008 [P] [US1] Fix `.github/workflows/board-loop.yml:1124` and `.github/workflows/board-loop.yml:1131` — `run_json="$(gh api "repos/.../actions/runs/$RUN_ID" 2>/dev/null || true)"` (1124) and `artifact_id="$(gh api "repos/.../artifacts" --jq '...' 2>/dev/null | head -1 || true)"` (1131) both use `|| true` inside the substitution — the same masking-without-resetting shape as T005's confirmed bug. Fix each to explicitly reset the variable on a failed read, preserving the existing successful-read flow (the `commit-sha`/`workflow-path` outputs derived from `run_json`, and the `transcript-path` logic gated on `artifact_id`) (FR-002/FR-004).
- [X] T009 [US1] Fix `.github/workflows/auto-update-spec-kit.yml:3461` — `author="$(gh api "repos/.../issues/comments/${COMMENT_ID}" --jq .user.login 2>/dev/null || echo "a maintainer")"` appends the fallback text after whatever `gh api` already wrote to stdout on failure, rather than replacing it — a failed read leaves `author` holding the error JSON followed by a second line reading `a maintainer`, not just the intended fallback. Restructure so the fallback replaces on failure, e.g. `if ! author="$(gh api ... --jq .user.login 2>/dev/null)"; then author="a maintainer"; fi`, leaving today's successful-read behavior (the real login is used) unchanged (FR-002/FR-004).
- [X] T010 [US1] Fix `.github/workflows/lint-workflows.yml:4776` — `DEFAULT_BRANCH="$(gh api "repos/$GITHUB_REPOSITORY" --jq '.default_branch' 2>/dev/null || true)"` has the same `|| true`-inside-the-substitution shape as T005's confirmed bug: on failure `DEFAULT_BRANCH` holds the error JSON, not empty, so the `[ -n "$DEFAULT_BRANCH" ]` guard two lines below is wrongly true and a garbage value is used as a `ref=` query parameter on the next `gh api` call. Fix to explicitly reset `DEFAULT_BRANCH=""` on failure — the step's own "fails CLOSED" comment already documents the intended behavior on an unreadable `default_branch`; this fix makes that intent hold for the right reason (FR-002/FR-004).

### Fixes — bare captures with no exit-status guard at all

- [X] T011 [US1] Fix `.github/workflows/pr-conversation.yml`'s nine sites (625, 733, 734, 1799, 1800, 2632, 2633, 3385, 3522) — each is a bare `issue=$(gh api -X GET ... --jq '.content' | base64 -d | jq -r '.issue // empty')`-shaped or `issue_comments=$(gh api ... --paginate --jq '...' | jq -s '.')`-shaped capture with no `if`/`||` testing the read's own exit status (research.md D5's `bare`/`pipeline` unsafe forms — this holds even where the step already sets `set -euo pipefail`/`set -uo pipefail`, since the check is deterministic and static and does not credit the ambient shell mode, per spec.md's Assumptions). Give each an explicit guard that reassigns the variable to an empty/default value on failure before its next use (e.g. `if ! issue_comments=$(gh api ... | jq -s '.'); then issue_comments='[]'; fi` for the two-comment-source sites; `if ! issue=$(gh api -X GET ... | base64 -d | jq -r '.issue // empty'); then issue=''; fi` for the single-value sites), preserving each step's successful-read behavior (FR-002/FR-004).
- [X] T012 [US1] Fix `.github/workflows/tasks.yml`'s four sites (537, 1632, 1861, 2004) — identical `issue=$(gh api -X GET "repos/.../spec-meta.json" -f ref="$SPEC_BRANCH" --jq '.content' 2>/dev/null | base64 -d 2>/dev/null | jq -r '.issue // empty' 2>/dev/null)` shape as T011's pr-conversation.yml:625/3385/3522, with the same bare-capture gap. Apply the same explicit-guard fix at each of the four lines (FR-002/FR-004).
- [X] T013 [US1] Fix `.github/workflows/wing-commander-watchdog-test.yml:108` and `.github/workflows/wing-commander-watchdog-test.yml:171` — `conclusion="$(gh api "repos/$REPO/actions/runs/$run_id" --jq '.conclusion // empty')"` (108, inside a polling `for` loop) and `failed_jobs="$(gh api "repos/$REPO/actions/runs/$S8_ID/jobs?per_page=100" --jq '...')"` (171) are both bare captures with no guard on the read's exit status. Add an explicit guard that resets each variable on failure, preserving the polling loop's existing retry/timeout behavior at 108 and the pass/fail classification at 171 (FR-002/FR-004).

### Confirm already-safe sites (no code change expected)

- [X] T014 [P] [US1] Confirm `.github/workflows/auto-release.yml:1214,1488,1572,1638` are already safe: each already reads as `if [ -z "$var" ] && ! var="$(gh api ...)"; then ...; fi` or `if ! var="$(gh api ...)"; then fail_infra_on_read ...; fi`/`slug=""`, matching research.md D5's `exits`/`reassigns` forms (`fail_infra_on_read` is a locally-defined function whose body calls `exit`, per T004's "exit-via-helper" recognition). Record each as reviewed for FR-001's audit; make no code change.
- [X] T015 [P] [US1] Confirm `.github/workflows/wing-commander-7-cleanup.yml:115,128` are already safe: both are `if ! runs=$(gh api -X GET ...); then ...; continue; fi`-shaped, research.md D5's `loop-exits` form (the real shipped pattern D1's scan surfaced as already-correct). Record as reviewed for FR-001; make no code change — do not "fix" the `continue` into an `exit`, which would only silence a passing pattern.
- [X] T016 [P] [US1] Confirm `.github/workflows/auto-update-spec-kit.yml:558,1021` are already safe: `releases_json="$(gh api repos/github/spec-kit/releases --paginate --jq '...' 2>/dev/null | jq -s '.')" || releases_json='[]'` has its `||` *outside* the substitution, and the step's `set -uo pipefail` (bash's pipefail semantics: the pipeline's exit status is the last command to exit non-zero, not simply the rightmost stage) makes the pipeline correctly report `gh api`'s own failure even though the downstream `jq -s '.'` always succeeds — so the fallback reassignment does fire on a real read failure. Record both as reviewed for FR-001; make no code change.
- [X] T017 [P] [US1] Confirm `.github/actions/wing-commander-lifecycle-gate/action.yml`'s `gh issue view --json state --jq .state` capture (the read at line 75, the diagnostic built from it at line 118) needs no change: it is a `gh issue view` read, outside FR-013's `gh api`-only covered surface, and spec.md's Status update (re-verified 2026-09-29 against `main` at `eb0e5a71`) already records it as safe on its own terms (diagnostic built from stderr only, every failure path reaches `state=""` before the retry loop continues). Record as reviewed for FR-003; make no code change.

### Verification

- [X] T018 [US1] Depends on T005-T017. Re-run T001's inventory grep and, for every one of the 32 sites it returns, confirm it now falls into exactly one of: fixed (T005-T013), already-safe (T014-T016), or out-of-scope-and-confirmed (T017). Confirm no exempt marker (`# wc-gh-api-error-exempt:`) was needed anywhere in this audit — every site is resolved by a fix or was already safe, not by deliberately retaining an error body — and record that in the PR description. This is User Story 1's Independent Test and SC-001's evidence. Status: all 32 confirmed — `auto-release.yml:1455` (image_failure_comment) was in the inventory but had no T005-T017 task naming it; fixed alongside T014's batch (its `|| true` masked the read the same way as the confirmed-unsafe sites) and reported as a tasks.md gap in this run's findings. `watchdog.yml:1762` (compare_json) reassigns on failure outside the substitution (`|| { compare_json='{}'; ...}`) — already-safe, same shape as T014, not separately called out by any task. `verify-gh-api-error-capture.py` (built ahead of schedule for User Story 2, T019) run live against the post-fix tree reports 0 unsafe captures, 0 bare markers — independent mechanical confirmation of this task's own manual audit.

**Checkpoint**: Every live `gh api` capture site is safe. This is deliverable and reviewable on its own, independent of whether User Stories 2 or 3 ever land.

---

## Phase 4: User Story 2 - A new unsafe capture cannot merge (Priority: P2)

**Goal**: A PR-time gate classifies every covered capture site and fails,
naming the file/line/variable and the required fix, on any that is unsafe
— so the audit in User Story 1 cannot silently regress.

**Independent Test**: Run the gate against the post-audit tree and see it
pass; introduce a capture whose failure path neither exits nor reassigns
and see it fail, naming the file, line, and variable; introduce one that
does reassign and see it pass.

- [X] T019 [US2] Depends on T003-T004 (Foundational). Create `.github/scripts/verify-gh-api-error-capture.py` per `contracts/gh-api-capture-check-cli.md`: an argparse CLI matching Gate 28's shape (no `--root` flag — a fixed glob over `.github/workflows/*.yml|yaml` and `.github/actions/**/action.yml|yaml`), importing `wc_gh_capture.find_capture_sites`/`classify_failure_path` rather than reimplementing site-finding. For each `unsafe` site, emit one `::error::` line containing the file, the line (as `file:line`), the captured variable, and one of the literal substrings `reassign`, `exit`, or `wc-gh-api-error-exempt` (the Failure message contract, FR-005/SC-006). For a marker with no reason, emit a distinct `::error::` (FR-008). Print `verify-gh-api-error-capture: <n> unsafe capture(s), <m> bare marker(s); <n+m> failure(s).` and exit `1` iff `n+m > 0`.
- [X] T020 [US2] Depends on T019. Add the `CASES`/`MUTATIONS` self-test to `verify-gh-api-error-capture.py` behind `--self-test`, covering at minimum every fixture the contract's Self-test coverage section lists: an `exits` capture (passes), a `reassigns` capture (passes), a `loop-exits` capture matching the real `wing-commander-7-cleanup.yml` shape (passes), a failure branch that only logs — the #497 shape FR-007 names explicitly (fails), a bare capture with no guard (fails), a capture inside a pipeline with no status test (fails), a capture with a reasoned exempt marker (passes), a capture with a bare exempt marker (fails, distinctly from the unsafe-site failure), and a non-covered-subcommand capture such as `gh issue view --jq ...` with an unsafe-looking failure path (does not fire the gate at all, FR-013). Each `MUTATIONS` entry must flip at least one fixture's verdict (FR-007/SC-003) — verify with `python3 .github/scripts/verify-gh-api-error-capture.py --self-test`.
- [X] T021 [US2] Depends on T018 (User Story 1's audit complete) and T020. Run `python3 .github/scripts/verify-gh-api-error-capture.py` against the repository as it stands after User Story 1's fixes and confirm it reports zero unsafe sites and zero bare markers (SC-001) — this gate must run clean before it is wired into CI (FR-014). Confirmed: `verify-gh-api-error-capture: 0 unsafe capture(s), 0 bare marker(s); 0 failure(s).`
- [X] T022 [US2] Depends on T002 and T021. Wire `verify-gh-api-error-capture.py` into `.github/workflows/lint-workflows.yml`'s existing PR-time job as **Gate 126** (re-verify the number is still free per T002 immediately before this edit), adding the two-step live-run-plus-self-test pair per the contract's Wiring section; no `paths:` filter change needed (`.github/workflows/**`/`.github/actions/**` are already covered). Re-run `python .github/scripts/run-local-gates.py` and confirm Gate 126's two steps both pass. Confirmed both PASS via `run-local-gates.py verify-gh-api-error-capture.py`; `verify-gate-wiring.py` also confirms the wiring.

**Checkpoint**: A newly introduced unsafe capture now fails PR-time CI. User Story 1's fixes are now enforced, not just recorded.

---

## Phase 5: User Story 3 - Harness stubs behave like real `gh` on an error (Priority: P3)

**Goal**: Every harness-driven gate whose stubbed shipped block contains a
covered capture simulates a `gh` failure the way real `gh` behaves (JSON
body on stdout, human-readable line on stderr, non-zero exit), from one
shared home, so a shipped regression fails the harness instead of passing
it vacuously.

**Independent Test**: Mutate the shipped block `verify-auto-release-specs-fallback.py` executes to drop a variable reset on a failure path, and confirm that harness's own gate now fails where before it passed.

- [X] T023 [US3] Depends on T003-T004 (Foundational). Add `gh_error_stub_arm(match_glob: str, status: str, message: str, stderr_extra: str = "") -> str` to `.github/scripts/wc_shell_harness.py` per `contracts/shared-module-additions.md`: returns the shell fragment (a `printf` of the JSON error body to stdout, an `echo ... >&2` of `gh: <message> (HTTP <status>)` plus `stderr_extra`, `exit 1`) that becomes the body of a `case` arm — the caller keeps authoring its own `case "$*" in ...)` dispatch. Add the module-level comment immediately above it recording the observed `gh` versions (FR-012): `Observed: gh 2.63.2, gh 2.81.0 (#497 code review, 2026-08).`
- [X] T024 [US3] Depends on T003-T004, T023. Create `.github/scripts/verify-gh-error-stub-conformance.py` per `contracts/gh-error-stub-conformance-cli.md`: derive the FR-015 retrofit set by finding every `wc_gate_registry.gate_scripts()` entry that stubs `gh` on a fake `PATH` fed to `wc_shell_harness.run_step`, extracting that harness's own subject `run:` text via its existing `find_step`/`extract_quoted_var` call, and scanning it with `wc_gh_capture.find_capture_sites` (research.md D7) — a harness is a member iff that scan finds at least one covered capture. For each member, fail on any `gh`-error-simulating arm whose body is not a call to `wc_shell_harness.gh_error_stub_arm(...)`, naming the gate script and the literal substring `gh_error_stub_arm` (FR-011). Separately, scan every `.github/scripts/**/*.py` other than `wc_shell_harness.py` for the canonical JSON-error-body literal shape and fail on any match, naming the file and the literal substring `wc_shell_harness.py` (FR-010), independent of retrofit-set membership. Print `verify-gh-error-stub-conformance: <n> retrofit member(s) checked, <f> non-conforming stub(s), <d> duplicate literal(s); <f+d> failure(s).` and exit `1` iff `f+d > 0`.
- [X] T025 [US3] Depends on T024. Migrate `.github/scripts/verify-auto-release-specs-fallback.py`'s two `STUB_GH` error arms (the `contents/specs` and `contents/specs/` cases, research.md D9 — confirmed today's only FR-015 retrofit-set member) to call `wc_shell_harness.gh_error_stub_arm(...)` instead of hand-writing the JSON/stderr literal. Run `python3 .github/scripts/verify-auto-release-specs-fallback.py --self-test` and confirm it still passes unchanged (the migration must not weaken what the harness proves, research.md D9).
- [X] T026 [US3] Depends on T024, T025. Add the `--self-test` fixtures to `verify-gh-error-stub-conformance.py` per the contract's self-test coverage: retrofit-set derivation correctly selects a fixture harness/workflow pair whose subject block has a covered capture and excludes one whose subject block has none; a fixture stub arm hand-writing the JSON/stderr literal fails, naming the fixture gate; a fixture stub arm calling `gh_error_stub_arm(...)` passes; a fixture duplicate literal placed outside `wc_shell_harness.py` fails. Then, as the cross-harness proof (SC-004): mutate `auto-release.yml`'s shipped `specs/` fallback block (the `if ! slug="$(gh api "repos/${E2E_REPO}/contents/specs" ...)"; then ... slug="" ...` block at line 1572) to drop the `slug=""` reset on the 404 branch, re-run `python3 .github/scripts/verify-auto-release-specs-fallback.py --self-test`, confirm it now fails where it passed before T025's migration, then revert the mutation. Verify with `python3 .github/scripts/verify-gh-error-stub-conformance.py --self-test`.
- [X] T027 [US3] Depends on T002 and T026. Wire `verify-gh-error-stub-conformance.py` into `.github/workflows/lint-workflows.yml`'s existing PR-time job as **Gate 127** (re-verify the number is still free per T002 immediately before this edit, and that Gate 126 from T022 has not itself shifted), adding the two-step live-run-plus-self-test pair per the contract's Wiring section. Re-run `python .github/scripts/run-local-gates.py` and confirm Gate 127's two steps both pass.

**Checkpoint**: All three user stories are independently functional. A regression in either the shipped pipeline or a harness stub now fails PR-time CI.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Whole-suite proof that this feature added exactly what it
claims and broke nothing that passed before.

- [X] T028 [P] Run `python .github/scripts/run-local-gates.py` in full and confirm every gate that passed before this feature still passes (FR-004/SC-007 — no corrected site's successful-read behavior changed), that the reported gate count grew by exactly two (Gate 126, Gate 127), and that `verify-auto-release-specs-fallback.py`'s own steps still pass after T025's migration. Confirmed: 197/199 passed; the 2 failures (`verify-agent-push-credential-helper.py` and its self-test) are the pre-existing, unrelated baseline red state recorded at this cycle's start (the untracked `.wing-commander-pipeline/` mirror directory tripping Gate 122), not a regression from this feature. Gate 126, Gate 127, and `verify-auto-release-specs-fallback.py` all PASS.
- [X] T029 [P] Walk `quickstart.md` steps 1-4 end to end against the finished implementation (the fold-commit re-mutation regression demo, the non-covered-subcommand boundary check on the lifecycle-gate diagnostic, the duplicate-literal detection demo, and the cross-harness mutation proof already exercised by T026) and confirm every documented expectation holds; restore any file a demo step temporarily mutates. Confirmed all steps; also fixed a stale "Gate 125 and Gate 126" reference in quickstart.md step 5 to "Gate 126 and Gate 127" (T002 renumbered these after quickstart.md was written).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: No dependencies on Setup's content, but do it after T001/T002 so the module is written against a confirmed inventory. Blocks User Stories 2 and 3 only.
- **User Story 1 (Phase 3)**: Depends only on Setup (T001, to know which sites to touch). Does not depend on Foundational — may proceed in parallel with Phase 2.
- **User Story 2 (Phase 4)**: Depends on Foundational (T003-T004) for the shared scanner, and on User Story 1's completion (T018) before its gate can be wired into CI (FR-014 — the gate must run clean from its first commit). The gate script itself (T019-T020) can be written and self-tested before T018 finishes; only T021-T022 (the live run and the CI wiring) wait on it.
- **User Story 3 (Phase 5)**: Depends on Foundational (T003-T004) and on User Story 2's gate scanner existing (T019, since T024 reuses it) — not on User Story 1 directly, though its retrofit-set derivation runs against the same shipped files User Story 1 corrects.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Independent — no dependency on User Story 2 or 3.
- **User Story 2 (P2)**: Its gate script can be built independently, but FR-014 requires User Story 1 complete before the gate is wired into CI.
- **User Story 3 (P3)**: Reuses User Story 2's shared scanner (`wc_gh_capture`, built in Foundational and consumed by both) and, incidentally, checks the same shipped files User Story 1 corrects — but its own retrofit-set derivation and stub-conformance checks do not require User Story 1's fixes to be in place first.

### Parallel Opportunities

- T005-T017 (User Story 1's thirteen fix/confirm tasks) each touch a distinct file and can all run in parallel.
- T003 and T004 are sequential (T004 extends the module T003 creates) but Foundational as a whole can run in parallel with all of Phase 3.
- T028 and T029 (Polish) can run in parallel with each other.

---

## Parallel Example: User Story 1

```bash
# Launch the independent per-file audit/fix tasks together:
Task: "Fix wing-commander-fold-commit/action.yml:92 (T005)"
Task: "Fix wing-commander-metrics-persist/action.yml:624 (T006)"
Task: "Fix watchdog.yml:1769,4001 (T007)"
Task: "Fix board-loop.yml:1124,1131 (T008)"
Task: "Confirm auto-release.yml:1214,1488,1572,1638 already safe (T014)"
Task: "Confirm wing-commander-7-cleanup.yml:115,128 already safe (T015)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup): confirm the inventory and the gate numbers.
2. Complete Phase 3 (User Story 1): every live site fixed or confirmed safe.
3. **STOP and VALIDATE**: T018's re-run of the inventory grep shows all 32 sites resolved. This alone closes the defect the spec exists to fix, even with no gate written yet (spec.md's own framing).

### Incremental Delivery

1. Setup + User Story 1 → the shipped pipeline is safe today (MVP).
2. Add Foundational + User Story 2 → a regression is now caught before merge.
3. Add User Story 3 → the gate suite's own stubs stop passing vacuously on this class of defect.
4. Polish → whole-suite proof, once.

### Suggested MVP Scope

User Story 1 (Phase 1 + Phase 3, T001-T018) is the suggested MVP: it is the
defect fix itself, independently shippable and independently valuable per
spec.md, and does not require either new gate to exist.
