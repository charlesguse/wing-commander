---

description: "Task list for feature 078: A plan or tasks agent can write a multi-line commit message"
---

# Tasks: A Plan or Tasks Agent Can Write a Multi-Line Commit Message

**Input**: Design documents from `/specs/078-plan-tasks-commit-scratch-path/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not explicitly requested. This feature's acceptance mechanism is the new gate's own `--self-test` (Constitution VIII) plus the quickstart.md validation runs, not a separate opt-in TDD pass — matching every other `verify-*.py` gate in this repository.

**Organization**: Tasks are grouped by user story (spec.md priorities P1-P3). The one shared artifact — the canonical guidance composite action — is Foundational rather than part of User Story 1, because all nine User Story 1 call-site edits render from it from the moment they're wired; see Dependencies & Execution Order below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US3)
- Line numbers cited below are today's (`main`, post-#585) positions, confirmed by reading the live files during task generation. Each edit within a phase that touches a file more than once shifts later line numbers in that same file, so locate sites by the step `id`/`name` in quotes, not by line number alone, once a prior task in the same phase has landed on that file.

## Path Conventions

CI/CD pipeline infrastructure repository — no `src`/`tests` split. Paths below are repository-root-relative (`.github/`, `specs/`), per plan.md's Project Structure.

---

## Phase 1: Setup

**Purpose**: Confirm the two facts later phases depend on before any file is edited.

- [ ] T001 Confirm the next unused gate number: run `grep -rhoE "Gate [0-9]+" .github/scripts/*.py .github/workflows/*.yml | grep -oE "[0-9]+" | sort -n | uniq | tail -1`. As of this task list's generation the highest in-use number is 98 (`.github/workflows/lint-workflows.yml`'s Gate 98 block, ~line 4118), so the new gate in T016-T018 is **Gate 99** — but re-run the check immediately before creating the gate script in case another spec's gate landed on `main` first (research.md D3). No file changes — this is a verification gate before Phase 2 begins.

**Checkpoint**: The gate number for Phase 5 is confirmed (or re-derived if it drifted).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one canonical guidance source every User Story 1 call site renders from.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 Create `.github/actions/wing-commander-commit-message-guidance/action.yml` per contracts/commit-message-guidance-action.md: a composite action, `using: composite`, one `shell: bash` step (no network, no agent — mirroring `wing-commander-tool-args/action.yml`'s fail-fast-before-credentials position and its inputs→output shape). Inputs: `scratch-filename` (required, a bare filename with no directory component — the action itself prefixes `${{ runner.temp }}/`), `extra-note` (optional, default `""`). Output `guidance`: a single string built from `${{ runner.temp }}/<scratch-filename>`, containing, in order: (1) that a commit message longer than one line goes through the `Write` tool to exactly that path and the commit is then made with `git commit -F` from it (FR-001, FR-002); (2) that the path lies outside the repository and why a path under the repository is unusable — refused inside `.git/`, swept into the commit anywhere else (FR-003); (3) that a heredoc or `$(cat ...)` on the command line is refused by the permission layer, named explicitly (FR-004); (4) that this only applies to messages longer than one line — an inline `-m` one-liner remains available (FR-005); (5) `extra-note`'s text, appended verbatim as a trailing sentence, only when non-empty. The rendered text MUST be byte-identical across two calls with the same `(scratch-filename, extra-note)` pair, and MUST differ between two calls only in the substituted `scratch-filename` and `extra-note` (FR-009, "Behavioral guarantees" in the contract). Seed the wording from `implement.yml`'s existing hand-written paragraph (today at `implement.yml:938-945` and `implement.yml:1530-1539`, read below) so the meaning those two sites' agents receive does not change (FR-013, research.md Assumptions).

**Checkpoint**: The canonical guidance source exists and can be invoked with a per-site filename. User story work can begin.

---

## Phase 3: User Story 1 - A committing agent writes a multi-line message on the first attempt (Priority: P1) 🎯 MVP

**Goal**: Every one of the nine agent-prompt sites that instructs a commit renders the canonical guidance (T002) with its own scratch filename, so an agent composing a multi-line commit message at any of them succeeds on the first attempt.

**Independent Test**: Drive a plan run (either mode) and a tasks run (either mode) whose agent composes a commit message with a body; the commit succeeds with no denied tool call and `git log -1 --format=%B` shows subject and body. For `board-loop.yml`'s two fix agents and `pr-conversation.yml`'s fold agent, read the rendered prompt and confirm it names a path and `git commit -F`.

### Implementation for User Story 1

- [ ] T003 [P] [US1] In `.github/workflows/plan.yml`'s `plan` job, add a step "Compose commit-message guidance (plan.direct-commit)", `id: commit-guidance-plan-direct`, `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-commit-message-guidance` with `scratch-filename: plan-commit-message-direct.txt`, placed immediately before the "Compose tool args (plan.direct-commit)" step (`id: tool-args-plan-direct-commit`, today `plan.yml:677-687`) so it is available before the "Generate implementation plan (direct commit)" agent step (`id: agent-auto`). In that agent step's `prompt:` block, append `${{ steps.commit-guidance-plan-direct.outputs.guidance }}` on its own paragraph immediately after step 3's existing text ("...directly on ... (no new branch) and push. Open no PR.", today `plan.yml:748-752`) — contracts/commit-message-guidance-action.md's "Consumption pattern" example is this exact site.
- [ ] T004 [US1] In `.github/workflows/plan.yml`'s `plan` job, add a step "Compose commit-message guidance (plan.pr)", `id: commit-guidance-plan-pr`, same action, `scratch-filename: plan-commit-message-pr.txt`, placed immediately before the "Compose tool args (plan.pr)" step (`id: tool-args-plan-pr`, today `plan.yml:879-889`) so it is available before the "Generate implementation plan" agent step (`id: agent-pr`). Append `${{ steps.commit-guidance-plan-pr.outputs.guidance }}` immediately after step 4's existing text ("...and push ${{ inputs.plan-prefix }}...", today `plan.yml:941-944`). Sequential with T003 (same file).
- [ ] T005 [P] [US1] In `.github/workflows/tasks.yml`'s `tasks` job, add a step "Compose commit-message guidance (tasks.direct-commit)", `id: commit-guidance-tasks-direct`, same action, `scratch-filename: tasks-commit-message-direct.txt`, placed immediately before the "Compose tool args (tasks.direct-commit)" step (`id: tool-args-tasks-direct-commit`, today `tasks.yml:680-690`) so it precedes the `id: agent-auto` agent step. Append `${{ steps.commit-guidance-tasks-direct.outputs.guidance }}` immediately after step 3's existing text ("...on the current branch (...) and push.", today `tasks.yml:740-743`).
- [ ] T006 [US1] In `.github/workflows/tasks.yml`'s `tasks` job, add a step "Compose commit-message guidance (tasks.pr)", `id: commit-guidance-tasks-pr`, same action, `scratch-filename: tasks-commit-message-pr.txt`, placed immediately before the "Compose tool args (tasks.pr)" step (`id: tool-args-tasks-pr`, today `tasks.yml:867-878`) so it precedes the `id: agent-pr` agent step. Append `${{ steps.commit-guidance-tasks-pr.outputs.guidance }}` immediately after step 4's existing text ("...and push ${{ inputs.tasks-prefix }}...", today `tasks.yml:928-930`). Sequential with T005 (same file).
- [ ] T007 [P] [US1] In `.github/workflows/board-loop.yml`'s `fix` job, add a step "Compose commit-message guidance (board-loop.fixer)", `id: commit-guidance-fixer`, same action, `scratch-filename: board-loop-commit-message-fixer.txt`, placed immediately before the "Compute agent turn ceiling (fixer)" step (today `board-loop.yml:1848-1852`) so it precedes the "Fixer" step (`id: fixer`). Append `${{ steps.commit-guidance-fixer.outputs.guidance }}` immediately after the existing sentence "Commit your work with `git commit` as you go (never `git push` -- you do not have that tool, and a deterministic step after you runs the full local gate suite and pushes only if it is green). Do not open a PR yourself." (today `board-loop.yml:1885-1888`). The job's existing `default-allowed-tools` (`board-loop.yml:1844`) already grants `Write` and `Bash(git commit:*)` — confirmed during research (research.md D5); no allowlist change needed (FR-007).
- [ ] T008 [US1] In `.github/workflows/board-loop.yml`'s `review` job, add a step "Compose commit-message guidance (board-loop.review-fixup)", `id: commit-guidance-review-fixup`, same action, `scratch-filename: board-loop-commit-message-review-fixup.txt`, placed immediately before the "Compute agent turn ceiling (review-fixup)" step (`id: review-fixup-ceiling`, today `board-loop.yml:2982-2986`) so it precedes the "Review-fixup" step (`id: review-fixup`). Append `${{ steps.commit-guidance-review-fixup.outputs.guidance }}` immediately after the existing sentence "Commit your work with `git commit` as you go (never `git push` -- a deterministic step after you runs the full local gate suite and pushes only if it is green). Do not open or edit any PR yourself." (today `board-loop.yml:3015-3018`). Same allowlist confirmation as T007 (`board-loop.yml:2978`). Sequential with T007 (same file, different jobs).
- [ ] T009 [P] [US1] In `.github/workflows/pr-conversation.yml`'s `act` job, add a step "Compose commit-message guidance (pr-conversation.fold)", `id: commit-guidance-fold`, same action, `scratch-filename: pr-conversation-commit-message-fold.txt`, placed immediately before the "Compose tool args (act)"-equivalent step preceding "Act on this classification" (`id: agent`, today `pr-conversation.yml:1959-1960`; confirm the exact preceding tool-args step id by reading the live file, since only the agent step's own id was confirmed during research). Append `${{ steps.commit-guidance-fold.outputs.guidance }}` immediately after the existing sentence "Commit BOTH files together in one commit whose message starts with \"fold(${{ matrix.id }}): ${{ steps.leg.outputs.summary }}\" and push to the current branch." (today `pr-conversation.yml:2009-2011`), before the following "Do NOT run `gh workflow run` yourself..." sentence. The job's existing `default-allowed-tools` (`pr-conversation.yml:1940`) already grants `Write` and `Bash(git commit:*)` (research.md D5); no allowlist change needed.
- [ ] T010 [P] [US1] In `.github/workflows/implement.yml`'s `implement` job, add a step "Compose commit-message guidance (implement.cycle)", `id: commit-guidance-cycle`, same action, `scratch-filename: implement-commit-message-cycle.txt` (unchanged from #440 — FR-013), placed immediately before the "Compose tool args (cycle)"-equivalent step preceding `id: tool-args-cycle` (today `implement.yml:823`) so it precedes the "Implement and converge (cycle)" step (`id: cycle`). Replace the hand-written paragraph "A commit message longer than one line goes through the Write tool to exactly ${{ runner.temp }}/implement-commit-message-cycle.txt and then git commit -F with that path; never a heredoc or $(cat ...) on the command line, which the permission layer denies, and never a file under the repository (a path inside .git/ is denied outright, and any other path there would be swept into the commit)." (today `implement.yml:938-945`) in place with `${{ steps.commit-guidance-cycle.outputs.guidance }}` — the surrounding "Constraints: commit and push ONLY to..." sentence before it and the blank line/"Tooling:" paragraph after it are unchanged.
- [ ] T011 [US1] In `.github/workflows/implement.yml`'s `implement` job, add a step "Compose commit-message guidance (implement.retry)", `id: commit-guidance-retry`, same action, `scratch-filename: implement-commit-message-retry.txt` (unchanged from #440), `extra-note: >-` followed by the exact sentence "Use a name distinct from the cycle step's scratch file above -- the cycle attempt may have left one behind, and this is a fresh session that never read it." (contracts/commit-message-guidance-action.md's literal example), placed immediately before the "Compose tool args (retry)"-equivalent step preceding `id: tool-args-retry` (today `implement.yml:1396`) so it precedes the "Implement and converge (retry at escalation model)" step (`id: retry`). Replace the hand-written paragraph at `implement.yml:1530-1539` (same shape as T010's, plus the trailing "Use a name distinct from the cycle step's scratch file above..." sentence) in place with `${{ steps.commit-guidance-retry.outputs.guidance }}`. Sequential with T010 (same file, same job).
- [ ] T012 [US1] Run the `review-step-gating` skill (CLAUDE.md) against T003-T011's changes to confirm the nine new guidance-composing steps introduce no `if:`/`continue-on-error:` regression — each new step is unconditional pure bash preceding its job's existing agent step (mirroring `tool-args-*` steps' own unconditional placement), so none should need a guard, but the skill pass is the deterministic check rather than an assumption. Fix any findings it surfaces.
- [ ] T013 [US1] Run quickstart.md §5 across all nine sites (not just the two it names): read each rendered `prompt:` block and confirm the interpolated `guidance` text differs from every other site's only in the substituted filename (and, at `implement.yml`'s retry site only, the trailing `extra-note` sentence) — Acceptance Scenario 6. Also confirm quickstart.md §3's manual-read check for `board-loop.yml`'s two fix-agent sites and `pr-conversation.yml`'s fold agent (each names a path and `git commit -F`). Depends on: T003-T011.

**Checkpoint**: User Story 1 complete — every in-scope site renders the canonical guidance with its own path (FR-001 through FR-006, FR-009, FR-013). Independently testable and shippable as the MVP.

---

## Phase 4: User Story 2 - The scratch file never becomes part of the repository (Priority: P2)

**Goal**: The commit-message scratch file is workspace debris that never reaches the tree, the commit's file list, or a stray `git status` entry, and a repeated commit at one site overwrites rather than appends.

**Independent Test**: After a plan run and a tasks run that each used the scratch path, `git status --porcelain` on the branch is clean and `git show --stat HEAD` lists only the stage's own artifacts.

### Implementation for User Story 2

- [ ] T014 [US2] Structural check across T002's action and T003-T011's nine call sites: confirm every `scratch-filename` value passed is a bare filename with no `/` or path separator (`grep -n "scratch-filename:" .github/workflows/plan.yml .github/workflows/tasks.yml .github/workflows/board-loop.yml .github/workflows/pr-conversation.yml .github/workflows/implement.yml`), confirm the composite action's own `run:` step (T002) never issues a `git add`/`git commit` itself — it only computes and outputs a string — and confirm no two sites in the same job share a `scratch-filename` value (FR-006; trivially true here since T003-T011 each assign a distinct filename per research.md D2). Record that the Write tool's overwrite (not append) semantics, already relied on by `implement.yml` since #440, satisfy the "repeated commits at one site" edge case without further code (data-model.md's Commit-message scratch file entity).
- [ ] T015 [US2] Run quickstart.md §4: after driving a plan run and a tasks run that each compose a commit through the scratch path (the same runs T013/User Story 1 validation uses), run `git status --porcelain` (expect clean) and `git show --stat HEAD` (expect only the stage's own artifacts — `plan.md`, `research.md`, etc. — never a `*-commit-message-*.txt` file) on each resulting branch. This step requires an actual dispatched run (CLAUDE.md: "a fix to behaviour that only runs in Actions is proven after merge by re-driving one run... and recording the evidence on the PR or the issue") — record the evidence there rather than only locally. Depends on: T013.

**Checkpoint**: User Story 2 complete — no commit-message file ever reaches the tree or the commit's file list (FR-003, User Story 2 acceptance scenarios).

---

## Phase 5: User Story 3 - The convention cannot silently regress (Priority: P3)

**Goal**: A future prompt edit that drops the scratch-path guidance, or adds a tenth commit-instructing prompt without it, fails the PR-time gate suite by name.

**Independent Test**: Delete the scratch-path sentence from one agent prompt in the working tree and run the repository's PR-time gate suite; the suite fails and names the site.

### Implementation for User Story 3

- [ ] T016 [US3] Create `.github/scripts/verify-commit-message-scratch-path.py` (Gate 99, or the number T001 re-confirms) per contracts/commit-scratch-path-gate.md, mirroring `verify-rate-limited-exemption.py`'s (Gate 51) structural shape: (1) **Discovery** — YAML-parse every `.github/workflows/*.yml` file (never grep, per Gate 7/23/51's stated rationale) and find every step, in any job, whose `prompt:` value contains the literal substring `git commit`. (2) **Pass condition per discovered site** — (a) *Covered*: a step in the same job, ordered before the discovered step, invokes `./.github/actions/wing-commander-commit-message-guidance` (or the pipeline-repo-relative equivalent) under some step id `X`, and the discovered step's `prompt:` contains the literal substring `steps.X.outputs.guidance`; or (b) *Exempt*: `(os.path.basename(path), step_name)` is a literal entry in this script's own `EXEMPT_SITES` constant (a Python set of tuples, each preceded by a comment stating why that site's commits are always deterministic one-liners — ships **empty**, research.md D6). A site satisfying neither fails, emitting `::error file=<path>::Gate 99: job {job!r} step {step!r}: {msg}` (Gate 51's format). Fail loudly (non-zero exit) if zero `.github/workflows/*.yml` files are discovered or zero sites are found at all (Constitution VIII). (3) **Deeper check for `implement.yml`'s `cycle` and `retry` steps specifically**: confirm each site's guidance-composing step passes `scratch-filename: implement-commit-message-cycle.txt` / `implement-commit-message-retry.txt` respectively; confirm `retry`'s guidance-composing step sets a non-empty `extra-note` whose rendered text still names "a name distinct from the cycle step's scratch file"; execute the composite action's shipped `run:` step for both filenames (with and without the retry `extra-note`) via `wc_shell_harness.run_step` (never a Python re-implementation of the render — matching `verify-tooling-statement.py`/`verify-plan-tasks-cost-line.py`) and assert the two rendered `guidance` strings are identical except for the substituted filename and the trailing `extra-note` sentence (FR-009, FR-013).
- [ ] T017 [US3] Add a `--self-test` mode to `.github/scripts/verify-commit-message-scratch-path.py` reintroducing, and asserting each one is caught: (1) a discovered site's `prompt:` with the `steps.X.outputs.guidance` substring removed; (2) a discovered site whose preceding guidance-composing step is deleted from the job while the `prompt:` still references its output; (3) an `EXEMPT_SITES` entry naming a `(basename, step_name)` pair that does not exist in any workflow (a stale exemption); (4) for `implement.yml`: the `cycle` site's `scratch-filename` changed to collide with `retry`'s (must fail, FR-006) and the `retry` site's `extra-note` blanked (must fail, FR-013); (5) zero sites discovered at all (must fail loudly). Use synthetic fixtures (tempdir-based, Gate 47/51 style) rather than mutating the real workflow files in place. Same file as T016, sequential.
- [ ] T018 [US3] Register two steps in `.github/workflows/lint-workflows.yml`, immediately after the Gate 98 block (today ending `lint-workflows.yml:4136`), matching every existing gate's exact registration shape (each `if: "!cancelled()"`, no `continue-on-error:`): `- name: "Gate 99 — commit-message scratch path is named at every in-scope site"` running `python3 .github/scripts/verify-commit-message-scratch-path.py`, and `- name: "Gate 99 self-test — a stripped render, an orphaned reference, a stale exemption, an implement.yml collision, and zero discovered sites each fail"` running `python3 .github/scripts/verify-commit-message-scratch-path.py --self-test`. Confirm the job's existing trigger path filters already cover `.github/workflows/**` and `.github/actions/**` (they do, matching every other gate in this job) — no filter widening needed. No separate `run-local-gates.py` registration — it derives the new gate automatically via `wc_gate_registry.pr_time_invocations`, matching every other gate. Depends on: T016, T017.
- [ ] T019 [US3] Run the `review-step-gating` skill (CLAUDE.md) against T018's two new `if:`-gated steps and fix any findings it surfaces.
- [ ] T020 [US3] Run quickstart.md §2: pick one in-scope site (e.g. `plan.yml`'s direct-commit step) and delete its `${{ steps.commit-guidance-plan-direct.outputs.guidance }}` interpolation from the `prompt:` block in the working tree; re-run `python3 .github/scripts/verify-commit-message-scratch-path.py` and confirm non-zero exit with an `::error file=.github/workflows/plan.yml::...` line naming the job and step; restore the file afterward (a manual drill, not a committed change). Then run `python3 .github/scripts/verify-commit-message-scratch-path.py --self-test` and confirm exit 0. Depends on: T016-T018.

**Checkpoint**: User Story 3 complete — a dropped guidance sentence or an unrecorded new site fails the gate suite by name (FR-010 through FR-012, SC-006, SC-008).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Whole-tree validation once every story has landed.

- [ ] T021 Run `python .github/scripts/run-local-gates.py` from the repository root and confirm every gate passes, including Gate 99 and its self-test step, with Gate 99 listed among the gates the script ran (confirming registry reachability — Constitution VIII, SC-005) — quickstart.md §1.
- [ ] T022 [P] Run quickstart.md §5's `cat .github/actions/wing-commander-commit-message-guidance/action.yml` and confirm the guidance wording exists in exactly that one file (`git grep` for a distinctive phrase like "never a heredoc or" across `.github/workflows/` and `.github/actions/` should return zero hits outside this one action.yml) — SC-007, SC-009.
- [ ] T023 Run this PR's code review (CLAUDE.md's "every fix PR gets a code review before merge") and fix its findings in this same PR; if the review surfaces a bug outside this feature's scope, file it as a new issue carrying the line "Found by the code review of #585" rather than widening this PR.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories. T002 (the composite action) is pulled forward from User Story 1 because every one of that story's nine call-site edits renders from it from the moment they're wired — without T002 landing first, T003-T011 would have nothing to call.
- **User Story 1 (Phase 3)**: Depends on Foundational (T002). No dependency on User Story 2 or 3.
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T003-T011) — its validation (T015) drives the same plan/tasks runs User Story 1's own validation (T013) uses, and its structural check (T014) reads the nine call sites User Story 1 creates.
- **User Story 3 (Phase 5)**: Depends on Foundational (T002) and User Story 1 (T003-T011) — the gate's discovery and its `implement.yml` deeper check need real sites to scan and the real composite action to execute via `wc_shell_harness.run_step`. Also depends on Setup (T001) for the gate number.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Each User Story

- User Story 1: the five files' first edits (T003, T005, T007, T009, T010) touch five different files and are mutually parallel; each file's second edit (T004, T006, T008, T011) is sequential with its file's first edit (same file, and for `board-loop.yml`/`implement.yml`, the two edits are close together in the same job or adjacent jobs). T012 and T013 depend on all nine edits landing.
- User Story 2: T014 and T015 both depend on User Story 1's completed edits; T015 additionally depends on T013's runs.
- User Story 3: T016 and T017 grow the same new file and are sequential; T018 depends on both; T019 depends on T018; T020 depends on T016-T018.

### Parallel Opportunities

- T003, T005, T007, T009, T010 (User Story 1, five different files) can run in parallel.
- T022 (Polish) can run alongside T021.
- User Story 2 (Phase 4) has no code dependency on User Story 3 (Phase 5) beyond both depending on User Story 1 — the two could be worked in parallel by different contributors once Phase 3 lands, despite being sequenced by priority here.

---

## Parallel Example: User Story 1

```bash
# Once T002 (the composite action) lands, wire all five files' first sites together:
Task: "Wire plan.yml's direct-commit site (T003)"
Task: "Wire tasks.yml's direct-commit site (T005)"
Task: "Wire board-loop.yml's fixer site (T007)"
Task: "Wire pr-conversation.yml's fold site (T009)"
Task: "Convert implement.yml's cycle site (T010)"

# Then each file's second site follows its own file's first:
Task: "Wire plan.yml's pr site (T004)"
Task: "Wire tasks.yml's pr site (T006)"
Task: "Wire board-loop.yml's review-fixup site (T008)"
Task: "Convert implement.yml's retry site (T011)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (the canonical guidance composite action — CRITICAL, blocks all stories).
3. Complete Phase 3: User Story 1 — all nine sites render the canonical guidance.
4. **STOP and VALIDATE**: run quickstart.md §3/§5 (T013) — a plan and tasks run compose multi-line commits successfully, and two sites' rendered text differs only in the substituted fields.
5. This is CLAUDE.md's own stated cost the issue exists to remove, delivered and independently checkable without the residue check or the enforcement gate.

### Incremental Delivery

1. Setup + Foundational → canonical guidance source ready.
2. Add User Story 1 → validate independently (quickstart §3, §5) → this is the MVP.
3. Add User Story 2 → validate independently (quickstart §4) → the scratch file's absence from the tree is confirmed, not assumed.
4. Add User Story 3 → validate independently (quickstart §2) → the convention has a shelf life beyond the next session.
5. Phase 6 (Polish) → whole-tree validation: `run-local-gates.py` green, single canonical source confirmed, code review passed.

### Parallel Team Strategy

With two contributors (CLAUDE.md's own stated cap on concurrent local agents during this pipeline's implement stage):

1. Both complete Setup + Foundational together (small, sequential-dependency-heavy phase).
2. Once Foundational is done: Contributor A takes `plan.yml` + `tasks.yml` (T003-T006); Contributor B takes `board-loop.yml` + `pr-conversation.yml` + `implement.yml` (T007-T011) in parallel; both converge for T012-T013.
3. Once User Story 1 lands, Contributor A takes User Story 2 (T014-T015) while Contributor B takes User Story 3 (T016-T020) in parallel.
4. Phase 6 runs once both have merged their stories' work.

---

Lifecycle issue: #585.
