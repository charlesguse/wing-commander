---

description: "Task list for Clear Next-Step Callouts in the Lifecycle Issue"
---

# Tasks: Clear Next-Step Callouts in the Lifecycle Issue

**Input**: Design documents from `/specs/019-next-step-callouts/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/callout-format.md, contracts/callout-points.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for workflow YAML in this repository (plan.md's Testing note; consistent with specs 014/016/017/018). Validation is `quickstart.md`'s seven scenarios, folded into each phase's checkpoint below.

**Organization**: FR-001–FR-012 require every human-action moment the pipeline can reach to post through one new shared composite action, `wing-commander-callout` (research.md), so the action-required/informational distinction is enforced in one place instead of drifting per-workflow. User Story 1 (P1) is the composite action's first three call sites — the two PR review gates (spec-phase, reached from both `intake.yml` and, after clarification, `clarify.yml`) and the previously-missing implementation-phase review gate in `finalize.yml` — because a spec PR announced but an implementation PR silently opened is exactly the core gap `spec.md` reports, and both gates share the identical `pr-label` template (Acceptance Scenario 2), so they belong to one story. User Story 2 (P2) extends the same convention to every other action-required moment FR-011 names — clarification-needed prompts (delivered as the other branch of User Story 1's own `intake.yml`/`clarify.yml` conditions, verified here rather than re-implemented) and the failure/stall/blocked moments in `finalize.yml`, `implement.yml`, `rebase.yml`, and `cleanup.yml` that don't yet exist. User Story 3 (P3) is `finalize.yml`'s remaining-manual-work callout specifically, since it is the one call site with its own entity (a task list) and its own extra field (`timing`) beyond the generic action/info split. Phase 2 (Foundational) exists because the composite action itself is a genuine shared blocking prerequisite every story's call sites invoke — no story can complete without it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (one new GitHub Actions composite action + targeted edits to six existing reusable workflow files + one documentation file), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the exact current step names, line numbers, and step `id`s at each of the ten call sites `contracts/callout-points.md` enumerates, since `research.md`'s audit was captured during planning and the six workflow files may have shifted since.

- [X] T001 Re-read `.github/workflows/intake.yml` (step 7's agent prompt, "Resolve created spec", "Label spec PR to match the issue"), `.github/workflows/clarify.yml` (step 6's agent prompt, "Update the draft PR description" — confirm its exact name), `.github/workflows/finalize.yml` ("Check for a diff and compute...", "Summarize change and extract remaining manual work", "Verify agent output", "Open the final pull request", "Verify the final pull request was created", "Commit metadata (stage -> review)", "Comment remaining manual work on the lifecycle issue"), `.github/workflows/implement.yml` ("Report stalled on lifecycle issue"), `.github/workflows/rebase.yml` ("Abandon and escalate"), and `.github/workflows/cleanup.yml` ("Comment rejection and remove labels"), and confirm every step name/line still matches `contracts/callout-points.md`'s table. If any step has moved, been renamed, or gained/lost a step `id`, update the working inventory before T003 begins — every task below assumes this list is exhaustive and current.

**Checkpoint**: The step-level inventory is confirmed current — editing can proceed without re-deriving it mid-task.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `wing-commander-callout` (research.md's single decision this whole feature hangs on) is the one new file every story's call sites invoke via `uses:`. No user story task can run before it exists.

- [X] T002 Create `.github/actions/wing-commander-callout/action.yml` as a new composite action, following the self-checkout-compatible shape of `.github/actions/wing-commander-preflight/action.yml` (same repo, resolved cross-repo at `github.job_workflow_sha` per the header comment in `.github/actions/wing-commander-context/action.yml` — this new composite needs no such header itself since it touches no workspace paths, but must not assume it lives in the workspace-root repository). Implement exactly `contracts/callout-format.md`'s contract: inputs `token` (required), `issue-number` (required), `kind` (required, `action`|`info`), `summary` (required), `body` (optional), `body-file` (optional, mutually exclusive with `body` — fail via `::error::` + non-zero exit if both are set), `pr-url` (optional), `pr-label` (optional, default `"the pull request"` when `pr-url` is set), `timing` (optional). In a single `run:` step: assemble the full rendered comment into a temp file (`${{ runner.temp }}/wing-commander-callout-body.md` or equivalent) — for `kind: action`, the `> [!IMPORTANT]` / `> **Action needed: <summary>**` block with every line prefixed `>`, the `body`/`body-file` content quoted into the block if given, a `> **PR:** [<pr-label>](<pr-url>)` line only when `pr-url` is set, and a `> **When:** <timing>` line only when `timing` is set; for `kind: info`, `<summary>` followed by `<body>`/`<body-file>` content if given, no wrapper, no PR/timing lines even if those inputs happen to be set (silently ignored per contract). Post via `gh issue comment <issue-number> --body-file <temp file>` (`GH_TOKEN: ${{ inputs.token }}`) — never `--body "$(cat ...)"` (research.md injection-safety decision). Never edit or delete a prior comment (FR-012).

**Checkpoint**: `wing-commander-callout` renders both templates correctly against a scratch issue (a manual `workflow_dispatch` smoke test, or desk-check against `contracts/callout-format.md`'s two example blocks) — every story below can now invoke it.

---

## Phase 3: User Story 1 - See "you need to review this PR" at every review gate (Priority: P1) 🎯 MVP

**Goal**: Both PR review gates — the spec-phase PR (`intake.yml`, and again from `clarify.yml` once clarification answers resolve all questions) and, for the first time, the implementation/finalize-phase PR — post an unmistakable `wing-commander-callout` `kind: action` comment naming the PR and linking it, using the identical `pr-label` shape for both gates.

**Independent Test**: Drive a spec through to the point the final implementation PR is opened. Confirm the lifecycle issue receives a clearly-marked "action needed: review this PR" callout that names and links the PR (quickstart.md Scenario 1); confirm the spec-phase callout (from either `intake.yml` or, after clarification, `clarify.yml`) uses the same `pr-label` template shape (quickstart.md Scenario 2).

### Implementation for User Story 1

- [X] T003 [US1] In `.github/workflows/finalize.yml`, add a new step immediately after "Verify the final pull request was created" (`id: verify-pr`) and before "Commit metadata (stage -> review)", gated `if: steps.diff.outputs.skip != 'true'` (job semantics already skip it if `verify-pr` itself failed — no extra guard needed), invoking `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-callout` with `token: ${{ steps.ctx.outputs.token }}`, `issue-number: ${{ inputs.issue-number }}`, `kind: action`, `summary: "Review the implementation PR"`, `pr-url:` built from `steps.verify-pr.outputs.pr-number` (e.g. `${{ steps.defbranch... }}`-free — construct via a small preceding `env:`/shell expression or add a `pr-url` output to the existing `verify-pr` step using `gh pr view "$pr" --json url --jq .url`), `pr-label: "the implementation PR"` — this is the core fix for User Story 1 (contracts/callout-points.md row 5): today this moment posts no comment at all.
- [X] T004 [P] [US1] In `.github/workflows/intake.yml`, narrow step 7's agent prompt ("Create spec from issue") so its final bullet no longer instructs `gh issue comment`: when `[NEEDS CLARIFICATION]` markers remain, the agent writes the questions (identical content/format to today's `"## 🔍 Clarification needed"` comment, minus the heading and reply-instructions boilerplate the deterministic template now supplies) to `${{ runner.temp }}/intake-clarification.md`; when none remain, the agent writes nothing (the "ready for review" callout needs no freeform body). Keep the label-creation/`--add-label` instructions unchanged. Remove `Bash(gh issue comment:*)` from step 7's own responsibility only if step 2's "could not produce a spec" early-exit still needs it in `--allowedTools` (it does — leave the tool available). Then add a new deterministic step after "Resolve created spec" (`id: created`) and before "Label spec PR to match the issue": if `steps.created.outputs.spec-dir` is empty, do nothing (step 2's agent-authored comment already covered this case); else if `<spec-dir>/spec.md` still contains `[NEEDS CLARIFICATION]`, invoke `wing-commander-callout` with `kind: action`, `summary: "Answer the open clarification questions"`, `body-file: ${{ runner.temp }}/intake-clarification.md`, no `pr-url` (contracts/callout-points.md row 2); else resolve the draft PR via `gh pr list --head "${SPEC_DRAFT_PREFIX}${NUM}-*" --state open --json url --jq '.[0].url // empty'` (mirrors the existing "Label spec PR to match the issue" step's own `gh pr list --head` lookup) and invoke `wing-commander-callout` with `kind: action`, `summary: "Review the spec PR"`, `pr-url:` the resolved URL, `pr-label: "the spec PR"` (contracts/callout-points.md row 1 — same `pr-label` as T003's implementation-PR callout, per Acceptance Scenario 2).
- [X] T005 [P] [US1] In `.github/workflows/clarify.yml`, narrow step 6's agent prompt ("Fold answers into the draft spec") so its final bullet no longer instructs `gh issue comment`: the agent always writes "which questions were resolved and with what" to `${{ runner.temp }}/clarify-followup.md`, additionally appending the still-open questions (if any remain) to the same file — content equivalent to today's comment, minus the "ready for review"/"still-open" framing sentence the deterministic template now supplies. Then add a new deterministic step after the agent step and after "Update the draft PR description" (which already resolves the PR via `gh pr list --head <branch>`): re-check `${{ steps.ctx.outputs.spec-dir }}/spec.md` for `[NEEDS CLARIFICATION]` markers (post-edit, same check shape `intake.yml`'s T004 uses); if markers remain, invoke `wing-commander-callout` with `kind: action`, `summary: "Answer the remaining clarification questions"`, `body-file: ${{ runner.temp }}/clarify-followup.md`, no `pr-url` (contracts/callout-points.md row 3); else resolve the draft PR's URL the same way "Update the draft PR description" already located it and invoke `wing-commander-callout` with `kind: action`, `summary: "Review the spec PR"`, `pr-url:` the resolved URL, `body-file: ${{ runner.temp }}/clarify-followup.md`, `pr-label: "the spec PR"` (contracts/callout-points.md row 4 — identical template to T004's "ready" branch).

**Checkpoint**: User Story 1 is fully functional — quickstart.md Scenario 1 (implementation PR announced, the core fix) and Scenario 2 (both review gates share one recognizable format) both pass.

---

## Phase 4: User Story 2 - Tell information apart from action (Priority: P2)

**Goal**: Every remaining human-action moment FR-011 names — failures, stalls, blocked states, and a rejected draft — posts through `wing-commander-callout` with `kind: action`, so a reader can classify every pipeline comment as informational or action-required with no ambiguous cases (SC-003). (The clarification-needed callouts from User Story 1's `intake.yml`/`clarify.yml` work already satisfy this convention for their moments — this phase covers the sites User Story 1 doesn't touch.)

**Independent Test**: Review the set of comments a spec accumulates across a lifecycle that includes at least one stall/failure/blocked/rejected moment. Confirm every comment is recognizably either informational or action-required by the same `[!IMPORTANT]`-box convention (quickstart.md Scenario 3).

### Implementation for User Story 2

- [X] T006 [P] [US2] In `.github/workflows/finalize.yml`, migrate its three flat failure/anomaly comments to `wing-commander-callout`: (1) "Check for a diff and compute..." (`id: diff`) — replace its inline `gh issue comment ... "⚠️ **Finalize anomaly** — ..."` line with an `anomaly=true` step output alongside the existing `skip=true`, and add a new step immediately after, `if: steps.diff.outputs.anomaly == 'true'`, invoking `wing-commander-callout` with `kind: action`, `summary:` the existing anomaly sentence verbatim (minus its `⚠️ **Finalize anomaly** —` prefix, which the alert box now supplies), no `pr-url` (contracts/callout-points.md row 7a); (2) "Verify agent output" — give it `id: verify-agent-output`, replace its inline `gh issue comment ... "❌ **Finalize failed** — ..."` line with a `failed=true` output written just before its existing `exit 1`, and add a new step immediately after, `if: steps.verify-agent-output.outputs.failed == 'true'`, invoking `wing-commander-callout` with `kind: action`, `summary:` the existing failure sentence verbatim (contracts/callout-points.md row 7b); (3) "Verify the final pull request was created" (`id: verify-pr`, already used by T003) — apply the identical transformation to its own `❌ **Finalize failed** — ...` early-exit branch (a `failed=true` output before that branch's `exit 1`, a new step `if: steps.verify-pr.outputs.failed == 'true'` invoking `wing-commander-callout` the same way) — this must be ordered before T003's new step so both read `steps.verify-pr`'s outputs correctly.
- [X] T007 [P] [US2] In `.github/workflows/implement.yml`, in "Report stalled on lifecycle issue", keep every existing line that assembles `/tmp/stall-comment.md` (banner, failing-run link, reason, collapsible agent transcript, restart runbook — all unchanged) and the `stage:stalled` label mutation, but remove the trailing `gh issue comment "$ISSUE" --body-file /tmp/stall-comment.md` line; add a new step immediately after invoking `wing-commander-callout` with `token: ${{ steps.ctx.outputs.token }}`, `issue-number: ${{ inputs.issue-number }}`, `kind: action`, `summary: "Restart the implement stage"`, `body-file: /tmp/stall-comment.md`, no `pr-url` (contracts/callout-points.md row 8 — the richest existing pattern, content otherwise untouched).
- [X] T008 [P] [US2] In `.github/workflows/rebase.yml`, in "Abandon and escalate", keep the existing marker (`<!-- wing-commander-rebase: blocked ... -->`) and escalation-file assembly unchanged, and keep the `rebase:blocked` label mutation in this same step; export the resolved `issue` as a step output (`id: escalate`, `echo "issue=$issue" >> "$GITHUB_OUTPUT"`, set only on the path that reaches `$RUNNER_TEMP/escalation.md`, i.e. not on the early `exit 0` "cannot resolve a trustworthy lifecycle issue" path) and remove the `gh issue comment "$issue" --body-file "$RUNNER_TEMP/escalation.md"` line; add a new step immediately after, `if: always() && steps.escalate.outputs.issue != ''`, invoking `wing-commander-callout` with `token: ${{ steps.ctx.outputs.token }}`, `issue-number: ${{ steps.escalate.outputs.issue }}`, `kind: action`, `summary: "Manually rebase this branch"`, `body-file: "$RUNNER_TEMP/escalation.md"`, no `pr-url` (contracts/callout-points.md row 9).
- [X] T009 [P] [US2] In `.github/workflows/cleanup.yml`, in "Comment rejection and remove labels", replace the inline `gh issue comment "$ISSUE" --body "🚫 **Draft rejected** — ..."` line with an invocation of `wing-commander-callout` (`token: ${{ steps.ctx.outputs.token }}`, `issue-number: ${{ steps.meta.outputs.issue }}`, `kind: action`, `summary: "Decide whether to revise and resubmit"`, `body:` the existing sentence verbatim minus its `🚫 **Draft rejected** —` prefix, no `pr-url` — the draft PR is already closed) as a new step immediately after this one (label-removal lines in this step stay exactly as they are); keep the `if: steps.idempotency.outputs.skip != 'true'` guard on both (contracts/callout-points.md row 10).

**Checkpoint**: User Stories 1 AND 2 both hold — quickstart.md Scenario 3 (no ambiguous cases across the full comment set) passes.

---

## Phase 5: User Story 3 - Flag remaining manual/implementation tasks as post-merge to-dos (Priority: P3)

**Goal**: `finalize.yml`'s remaining-manual-work comment is framed as a human to-do with explicit "after this PR merges" timing when work remains, and as an informational message when none remains.

**Independent Test**: Drive a spec whose finalize phase leaves residual manual work to the lifecycle issue. Confirm the surfaced tasks are labelled as human tasks with the stated timing (quickstart.md Scenario 4, non-empty case); confirm a spec with zero remaining items instead gets a plain informational message with no alert wrapper (quickstart.md Scenario 4, empty case).

### Implementation for User Story 3

- [X] T010 [US3] In `.github/workflows/finalize.yml`, replace "Comment remaining manual work on the lifecycle issue"'s two-branch `gh issue comment` body with `wing-commander-callout` invocations, keeping its existing `[ -s remaining_file ] && [ -n "$(tr -d '[:space:]' < remaining_file)" ]` condition unchanged (contracts/callout-points.md row 6/6b): non-empty branch invokes `kind: action`, `summary: "Complete the remaining manual work"`, `body-file: ${{ runner.temp }}/finalize-remaining.md`, `timing: "after this PR merges"`, no `pr-url`; empty branch invokes `kind: info`, `summary: "No manual work remains."`, no `body`.

**Checkpoint**: All three user stories are independently functional — the full quickstart.md scenario set (1–5) passes.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Document the new convention and validate the whole feature end to end.

- [X] T011 [P] Add a new bullet to `docs/architecture.md`'s "Mechanics worth knowing" list (after the existing "Preflight" bullet, ~line 57), naming the `wing-commander-callout` composite action: action-required moments render inside a GitHub `[!IMPORTANT]` alert box, informational messages don't, and `contracts/callout-format.md` (specs/019) is the source of truth for the template.
- [X] T012 [P] Validate `.github/actions/wing-commander-callout/action.yml` and every workflow file touched by T003–T010 parses as valid YAML and passes `bash -n` on embedded `run:` scripts, matching `.github/workflows/lint-workflows.yml`'s own CI checks — run locally or trigger `lint-workflows.yml` itself. Validated headlessly with the allowlisted tooling: `yamllint` passes on `action.yml`; `actionlint` (which runs `shellcheck` over every `run:` block) parses all six touched workflows and reports no syntax errors in any callout-related step — its only notes are pre-existing style/info items (`SC2012`/`SC2129`) in steps this feature did not add and false-positive `job_workflow_sha` expression warnings present identically across all pipeline workflows. `python3`/`bash -n` are not allowlisted in this headless run; `lint-workflows.yml`'s CI (YAML parse + `bash -n`) still runs on the PR and shellcheck already covers run-block syntax.
- [X] T013 Run quickstart.md's full scenario set (1–7) against the finished workflow files: Scenarios 1–2 (User Story 1, T003–T005), Scenario 3 (User Story 2, T006–T009 plus the clarification branches from T004–T005), Scenario 4 (User Story 3, T010), Scenario 5 (no-PR edge case, T004/T005's clarification branch), Scenario 6 (a full dogfooded live run — do this at least once before merging), and Scenario 7's maintainer-audit greps (`grep -Lrn "wing-commander-callout" .github/workflows/{intake,clarify,finalize,implement,rebase,cleanup}.yml` returns nothing; `grep -rLn "wing-commander-callout" .github/workflows/{plan,tasks,watchdog}.yml` lists all three, confirming no unintended migration). Record in the PR body which scenarios were exercised via a live run versus desk-checked only. **Headless status:** Scenario 7's audit greps verified — all six of `intake`/`clarify`/`finalize`/`implement`/`rebase`/`cleanup` invoke `wing-commander-callout`, and `plan`/`tasks`/`watchdog` do not (no unintended migration). Scenarios 1–5 desk-checked against the finished wiring (each call site posts the contract-correct `kind`/`summary`/`pr-url`/`body-file`/`timing`; `finalize.yml`'s `verify-pr` step emits the `pr-url` output T003 consumes; the empty/non-empty and clarification-remaining branches select `info` vs `action` correctly). Scenario 6 (full dogfooded live run) requires a real pipeline dispatch and must be exercised by a maintainer before merge — it cannot run in this headless implement stage; note this in the PR body.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001 confirms the exact step names/ids T002's callers will reference) — BLOCKS every user story (T003–T010 all invoke the composite action T002 creates).
- **User Story 1 (Phase 3)**: Depends on Foundational.
- **User Story 2 (Phase 4)**: Depends on Foundational. Independent of User Story 1's tasks (different files, except T006 which touches `finalize.yml` alongside T003 — see below).
- **User Story 3 (Phase 5)**: Depends on Foundational. Independent of User Stories 1 and 2's tasks (T010 touches a different step of `finalize.yml` than T003/T006).
- **Polish (Phase 6)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on User Story 2 or 3's tasks beyond the Foundational phase.
- **User Story 2 (P2)**: No dependency on User Story 1 or 3's tasks beyond the Foundational phase — independently testable once its own phase completes.
- **User Story 3 (P3)**: No dependency on User Story 1 or 2's tasks beyond the Foundational phase — independently testable once its own phase completes.

### Same-file ordering (not story dependencies, but real ordering constraints)

- `.github/workflows/finalize.yml` is edited by T003 (US1), T006 (US2), and T010 (US3) — three different steps, safe to implement in any order relative to each other's *content*, but since they are literal edits to one file they cannot be applied as truly concurrent patches; apply them in T003 → T006 → T010 order (phase order) to avoid merge friction. T006's third transformation (the `verify-pr` step) must land before or alongside T003, since both add a new step reading `steps.verify-pr`'s outputs.
- `.github/workflows/intake.yml` (T004) and `.github/workflows/clarify.yml` (T005) are independent files and may proceed in parallel with each other and with T003.
- T007 (`implement.yml`), T008 (`rebase.yml`), and T009 (`cleanup.yml`) each touch a distinct file with no cross-dependency and may proceed in parallel with each other and with T006.

### Parallel Opportunities

- T004 and T005 (User Story 1) can run in parallel with each other; T003 (also User Story 1) touches a different file and can run in parallel with both.
- T007, T008, T009 (User Story 2) can run in parallel with each other; T006 (also User Story 2, `finalize.yml`) should follow or accompany T003 per the same-file note above.
- T011 (docs) and T012 (lint) are parallel-safe with each other since T012 only reads the finished files.

---

## Parallel Example: User Story 1

```bash
# Launch together — three different files, same "wire the composite action" pattern:
Task: "Add the implementation-PR-ready callout step to .github/workflows/finalize.yml"
Task: "Narrow intake.yml step 7 to write-file-then-callout for both its branches"
Task: "Narrow clarify.yml step 6 to write-file-then-callout for both its branches"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the step-level inventory)
2. Complete Phase 2: Foundational (`wing-commander-callout` composite action)
3. Complete Phase 3: User Story 1 (both review gates announced, same template)
4. **STOP and VALIDATE**: Run quickstart.md Scenarios 1 and 2 against the finished wiring
5. This alone fixes the core gap `spec.md` reports — every remaining phase extends the same convention to moments that already had *some* comment, just not a consistently-shaped one

### Incremental Delivery

1. Setup + Foundational → composite action ready, step inventory confirmed
2. Add User Story 1 → validate Scenarios 1/2 → mergeable increment (MVP: the previously-silent implementation-PR gate is now announced)
3. Add User Story 2 → validate Scenario 3 → mergeable increment (every failure/stall/blocked/rejected moment is now visually consistent with the review-gate callouts)
4. Add User Story 3 → validate Scenario 4 → mergeable increment (remaining manual work reads as a timed human to-do, or is explicitly ruled out)
5. Polish → validate the full Scenario 1–7 sweep, plus lint and the docs note

### Why User Story 1 alone is the MVP

FR-002/FR-003/SC-001 together name the implementation-phase review gate as the confirmed, currently-unannounced core gap — a customer-visible silent stall today. User Story 2 and User Story 3 make the *existing* comments at other moments consistently shaped and correctly timed, which is valuable but does not, on its own, fix a moment where the pipeline currently posts nothing at all.
