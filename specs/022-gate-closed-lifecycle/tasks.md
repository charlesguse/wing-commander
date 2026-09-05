---

description: "Task list for A Closed Lifecycle Is Inert — Gate Comment-/Label-Triggered Stages on Issue State"

---

# Tasks: A Closed Lifecycle Is Inert — Gate Comment-/Label-Triggered Stages on Issue State

**Input**: Design documents from `/specs/022-gate-closed-lifecycle/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/wing-commander-lifecycle-gate.md, contracts/lifecycle-gate-points.md, contracts/denied-tool-collector-delta.md, quickstart.md

**Tests**: Not generically requested — no unit-test framework exists for workflow YAML in this repository (plan.md's Testing note, consistent with specs 014/016/017/018/019/020). Two things plan.md *does* explicitly request are included as implementation tasks rather than a separate test phase: (1) a small deterministic `jq` fixture check for the collector fix (T012), following the existing pattern of `.github/scripts/verify-watchdog-run.sh`; (2) `quickstart.md`'s nine scenarios, run at each phase's checkpoint and as a final sweep in Polish (T017).

**Organization**: Tasks are grouped by user story. US1 and US2 are both P1 and share one new composite action (Foundational, T002) that every wiring task builds on. US1 covers the two entry points that are genuine raw comment/label events — `clarify.yml` and `intake.yml` — which alone reproduce all four of US1's acceptance scenarios (a comment-shaped trigger, the closing-comment race, branch-resurrection prevention, and a label-shaped trigger) and is therefore the MVP: the reported defect (issue #109) is fixed as soon as US1 lands. US2 extends the identical gate to the three remaining FR-004-named entry points that are not raw comment/label events (`tasks-approved`, `finalize`, `implement`/converge) and adds the audit that confirms no named entry point was missed and no out-of-scope workflow (`plan`, `cleanup`, `claude`) was touched. US3 (P2) is the independent collector-accuracy fix — it shares no code with US1/US2 and can proceed in parallel with either.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project GitHub Actions pipeline repository, no `src`/`tests` split (plan.md's Structure Decision). One new composite action, five existing reusable workflows gain one new step plus `if:` guards each, one existing `jq` filter is corrected, and one documentation file is updated. All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm research.md R1's entry-point audit still matches the live repository before any file is edited, since research.md was authored in a separate planning session and this repository's workflows could have drifted since.

- [X] T001 Re-run research.md R1's audit against the current tree: `grep -rn "issue_comment" .github/workflows/` plus inspection of every workflow's `on:` block. Confirm `wing-commander-2-clarify.yml` → `clarify.yml` and `wing-commander-1-intake.yml` → `intake.yml` remain the only two raw `issue_comment`/`issues.labeled` entry points; confirm `wing-commander-4-tasks.yml`'s `tasks-approved` job in `tasks.yml` remains `pull_request: [closed]`-triggered; confirm `finalize.yml` and `implement.yml` remain dispatch-only (`workflow_dispatch`/`workflow_call`, no comment trigger of their own); confirm `claude.yml` remains fully disabled (`if: false`). If any workflow's shape has changed since research.md was written, note the discrepancy before proceeding to Phase 2 — the wiring tasks below assume the step names and line numbers research.md and this file recorded are still accurate.

**Checkpoint**: The FR-004 entry-point map this feature's tasks are built against is confirmed current.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the one new shared composite every user story wires into a workflow. No wiring task in US1 or US2 can start before this exists.

- [X] T002 Create `.github/actions/wing-commander-lifecycle-gate/action.yml` per contracts/wing-commander-lifecycle-gate.md, following the authoring pattern of `.github/actions/wing-commander-preflight/action.yml` (header comment noting it is resolved from the pipeline repository's own checkout at `github.job_workflow_sha`, never assumed to live in the workspace-root repository; single responsibility; no hidden state). Inputs: `issue-number` (required), `token` (required, at least `issues: read`). Single composite step: run `gh issue view "$ISSUE_NUMBER" --json state --jq .state` using the supplied token; on failure (e.g. issue does not exist), fail loudly with `::error::` and a non-zero exit — do not default to either open or closed. Outputs: `state` (`OPEN`/`CLOSED`, the raw value — `gh --json` reads through GraphQL, which returns uppercase) and `is-open` (`"true"` iff `state` is `OPEN`, `"false"` iff `CLOSED`, matched case-insensitively; any other value fails loudly rather than defaulting to closed) — the value every downstream step's `if:` reads. No other issue field (labels, comments, assignees) is read, and no write of any kind occurs in this composite.

**Checkpoint**: `wing-commander-lifecycle-gate` exists and is independently invocable — every wiring task below can now reference `./.wing-commander-pipeline/.github/actions/wing-commander-lifecycle-gate`.

---

## Phase 3: User Story 1 - A closed lifecycle issue is inert to further activity (Priority: P1) 🎯 MVP

**Goal**: Closing a lifecycle issue reliably ends its activity — a later comment (clarify-shaped) or label (intake-shaped) on the closed issue, including the very comment that closed it, causes no branch checkout-as-bot, no commit, no push, no PR edit, and no comment beyond the single FR-012 decline note.

**Independent Test**: Close a lifecycle issue that has an open draft/spec PR, then post a comment in the shape that would normally trigger `clarify` and apply a label in the shape that would normally trigger `intake`. Confirm neither stage does any write, and confirm exactly one `kind: info` decline comment appears per triggering event (quickstart.md Scenarios 1-4).

### Implementation for User Story 1

- [X] T003 [P] [US1] Wire the lifecycle gate into `.github/workflows/clarify.yml` per contracts/lifecycle-gate-points.md row 1: add a "Check lifecycle issue state" step (`id: lifecycle-gate`, `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-lifecycle-gate`, `issue-number: ${{ inputs.issue-number }}`, `token: ${{ github.token }}`) immediately after "Checkout pipeline repository" (~line 147) and before "Preflight" (~line 159). Immediately after it, add a "Note closed lifecycle and stop" step (`if: steps.lifecycle-gate.outputs.is-open != 'true'`, `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-callout`, `kind: info`, `summary: "This lifecycle issue is closed — no action was taken."`, `issue-number: ${{ inputs.issue-number }}`, `token: ${{ github.token }}`). Add `if: steps.lifecycle-gate.outputs.is-open == 'true'` (ANDed with any existing `if:`) to every remaining step: Preflight, Configure AWS credentials for Bedrock, Fetch issue labels, Wing Commander context, Verify spec identity, Checkout draft spec branch as wing-commander-bot, React to the triggering comment, Stage the answer as a data file, Fold answers into the draft spec, Determine clarification follow-up outcome, Announce remaining clarification questions, Resolve spec PR URL, Announce spec PR ready for review, Upload Claude execution log, Agent run metrics summary, Fail on agent API error.
- [X] T004 [P] [US1] Wire the lifecycle gate into `.github/workflows/intake.yml` per contracts/lifecycle-gate-points.md row 2: add the same "Check lifecycle issue state" + "Note closed lifecycle and stop" step pair immediately after "Checkout pipeline repository" (~line 192) and before "Preflight" (~line 204). Add `if: steps.lifecycle-gate.outputs.is-open == 'true'` (ANDed with any existing `if:`) to every remaining step: Preflight, Configure AWS credentials for Bedrock, Wing Commander context, Resolve default branch, Re-checkout default branch as wing-commander-bot, Allocate feature number, Report run started on issue, Create spec from issue, Resolve created spec, Check whether the spec still needs clarification, Announce clarification needed, Resolve spec PR URL, Announce spec PR ready for review, Label spec PR to match the issue, Upload Claude execution log, Agent run metrics summary, Fail on agent API error. Leave the wrapper `wing-commander-1-intake.yml`'s existing `spec-request` label who/what gate untouched (spec.md Assumptions; contracts/lifecycle-gate-points.md row 2).
- [X] T005 [US1] Validate quickstart.md Scenarios 1-4 against the finished `clarify.yml`/`intake.yml` wiring: a comment on a closed issue (Scenario 1), the exact closing-comment race (Scenario 2, reproducing issue #109), a comment on a closed issue whose branch was already torn down by cleanup (Scenario 3, confirming no re-creation via `git ls-remote`), and a label applied to a closed issue (Scenario 4). Confirm in each case the job's step list shows "Check lifecycle issue state" running and every subsequent step `Skipped`, and exactly one `kind: info` decline comment posted. Record whether each scenario was exercised via a live triggered run or desk-checked by inspection only.

**Checkpoint**: User Story 1 is independently satisfied — the reported defect (issue #109) no longer reproduces. This alone is mergeable as the MVP.

---

## Phase 4: User Story 2 - The state gate is enforced at the trigger, consistently across every entry point (Priority: P1)

**Goal**: The identical gate, at the identical layer (before any agent runs or any write can occur), is applied to the three remaining FR-004-named entry points that are not raw comment/label events — `tasks-approved`, `finalize`, and `implement`/converge — and the full FR-004 list is confirmed gated with no unnamed workflow swept in by mistake.

**Independent Test**: Trigger `tasks-approved` (merge a `tasks/**` PR against a closed lifecycle issue), `finalize`, and `implement`/converge (manual `workflow_dispatch` against a closed lifecycle issue's `issue-number`) and confirm each declines at its gate step before any write. Then grep-audit that exactly the five named workflows carry the gate and `plan.yml`/`cleanup.yml`/`claude.yml` do not (quickstart.md Scenario 5). (`claude.yml` was removed by PR #277 — re-running this audit now checks `plan.yml`/`cleanup.yml` only.)

### Implementation for User Story 2

- [X] T006 [P] [US2] Wire the lifecycle gate into `.github/workflows/tasks.yml`'s `tasks-approved` job per contracts/lifecycle-gate-points.md row 3: add the "Check lifecycle issue state" step after "Checkout spec branch as wing-commander-bot" (~line 727) and before "Verify stage and dispatch implement stage" (~line 738) — this job derives `issue-number` from that branch's `spec-meta.json` `.issue` field (`jq -r '.issue' "$SPEC_DIR/spec-meta.json"`), not a `workflow_call` input, so it cannot run any earlier. Add the "Note closed lifecycle and stop" decline step immediately after it. Add `if: steps.lifecycle-gate.outputs.is-open == 'true'` to "Verify stage and dispatch implement stage" only — the job's sole write step (checking out the already-long-lived spec branch beforehand is not itself the resurrection risk FR-003 forbids).
- [X] T007 [P] [US2] Wire the lifecycle gate into `.github/workflows/finalize.yml` per contracts/lifecycle-gate-points.md row 4: add the gate step pair immediately after "Checkout pipeline repository" (~line 155) and before "Preflight" (~line 167). Add `if: steps.lifecycle-gate.outputs.is-open == 'true'` (ANDed with any existing `if:`) to every remaining step: Preflight, Configure AWS credentials for Bedrock, Wing Commander context, Resolve default branch, Resolve and validate spec identity, Checkout spec branch as wing-commander-bot, Verify spec artifacts match the dispatch, Check for an existing final pull request, Check for a diff and compute "how to see it", Announce finalize anomaly (no diff), Summarize change and extract remaining manual work, Upload Claude execution log, Agent run metrics summary, Verify agent output, Announce finalize failure (agent output), Assemble PR body, Determine feature title, Open the final pull request, Verify the final pull request was created, Announce finalize failure (PR verification), Announce the implementation PR for review, Commit metadata (stage -> review), Check for remaining manual work, Announce remaining manual work on the lifecycle issue, Announce no remaining manual work on the lifecycle issue, Flip stage label.
- [X] T008 [P] [US2] Wire the lifecycle gate into `.github/workflows/implement.yml`'s `implement` job per contracts/lifecycle-gate-points.md row 5: add the gate step pair immediately after "Checkout pipeline repository" (~line 212) and before "Preflight" (~line 224). Add `if: steps.lifecycle-gate.outputs.is-open == 'true'` (ANDed with any existing `if:`) to every remaining step in the `implement` job: Preflight, Configure AWS credentials for Bedrock, Wing Commander context, Resolve and validate spec identity, Checkout spec branch as wing-commander-bot, Verify spec artifacts match the dispatch, Idempotency guard, Resolve iteration cap, Report run started on lifecycle issue, Record base SHA, Install actionlint for the agent, Implement and converge (cycle), Upload Claude execution log (cycle), Agent run metrics summary (cycle), Read back cycle outcome, Implement and converge (retry at escalation model), Upload Claude execution log (retry), Agent run metrics summary (retry), Read back retry outcome, Consolidate final outcome, Extract agent final message, Post progress comment (haiku), Agent run metrics summary (progress comment), Flip stage label (first cycle), Dispatch next step. The separate `stalled` job in the same file is not a comment-/label-triggered entry point named by FR-004 (research.md R1) — leave it unmodified.
- [X] T009 [US2] Confirm full FR-004 coverage per contracts/lifecycle-gate-points.md's audit clause: run `grep -rln "wing-commander-lifecycle-gate" .github/workflows/{clarify,intake,tasks,finalize,implement}.yml` and confirm exactly those five files list (SC-003 — zero ungated named entry points). Run `grep -rLn "wing-commander-lifecycle-gate" .github/workflows/{wing-commander-3-plan,wing-commander-7-cleanup,claude}.yml` and confirm all three list (i.e. contain no gate reference), confirming research.md R1/R2's scope boundary — `plan`'s PR-merge trigger and `cleanup`'s teardown mechanism — was not swept in by mistake.
- [X] T010 [US2] Validate quickstart.md Scenario 5 (every one of the five named entry points declines uniformly, visible as the gate step running and every subsequent step skipping — not merely a side effect of a denied tool call) and Scenario 7 (SC-004 — re-run each stage's previously-passing behavior against an *open* lifecycle issue and confirm zero regression, with one extra visible "Check lifecycle issue state" step adding no material latency).

**Checkpoint**: User Stories 1 and 2 both hold — every FR-004-named entry point declines uniformly at the trigger layer, and the scope boundary around `plan`/`cleanup`/`claude` is confirmed intact.

---

## Phase 5: User Story 3 - The watchdog's denied-tool report describes what actually happened (Priority: P2)

**Goal**: The watchdog's denied-tool collector reports a denial count that matches true occurrences (no silent single-tool drop, no inflation) and never labels a result-record array position as a "turn" number.

**Independent Test**: Feed the corrected `jq` filter a synthetic execution-output fixture with a known denial count (including a singleton-tool denial) and known `num_turns`; confirm `facts.denials` matches exactly and no `record-index` is presented as a turn (quickstart.md Scenario 8).

### Implementation for User Story 3

- [X] T011 [P] [US3] Apply the corrected `jq` filter to `.github/workflows/watchdog.yml`'s "Collect: execution-output artifacts" step (`id: collect-execution-output`, lines ~314-357) per contracts/denied-tool-collector-delta.md: rename the per-entry `turn` field to `record-index` (same zero-based array-position value, honest name — never compared against or presented alongside `num_turns` as if it were a turn count); remove the `map(select(length > 1))` step so every tool with at least one denial-shaped `tool_result` entry is reported, with `denials` (the post-`group_by` array length) now equal to the true occurrence count for that tool; change the `source` literal to `"execution-output (log-scan fallback — not authoritative)"`; add the forward-compatible branch that prefers a terminal result record's own permission-denial count when present (`.[] | select(.type=="result") | has("permission_denials")`), falling back to the corrected log-scan when absent — this branch is currently dead code per research.md R4 (no such field exists in the SDK's result record today) but must be present so no further collector change is needed if a future SDK version adds one.
- [X] T012 [US3] Add a small deterministic fixture check at `.github/scripts/verify-denied-tool-collector.sh`, following `.github/scripts/verify-watchdog-run.sh`'s pattern (plain bash/jq assertions, no test framework): feed the corrected filter a synthetic `claude-execution-output.json`-shaped array with a known number of denial-shaped `tool_result` entries (including at least one tool with exactly one denial, to prove the size-1 drop is gone) and a known `num_turns` on a `result`-type record, and assert (1) `facts.denials` equals the injected count exactly — no drop, no inflation (SC-005); (2) no `facts.record-index` value is presented as, or could be mistaken for, a turn number exceeding the injected `num_turns` (SC-006); (3) a second fixture with no `result`-type record at all still produces fallback output rather than crashing or fabricating a count (spec.md's "Collector with no terminal result record" edge case).

**Checkpoint**: User Story 3 holds independently — the collector's denial count and per-denial labeling are accurate, verifiable by the fixture script alone with no watchdog run required.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Perform the one-time remediation this defect's investigation identified, document the changes, and validate the complete feature end-to-end.

- [ ] T013 [P] Delete the orphaned resurrected branch `spec-draft/021-rebase-discover-stall` on `origin` (research.md R5, FR-011, SC-007): `git push origin --delete spec-draft/021-rebase-discover-stall`. This is a destructive, hard-to-reverse remote-branch deletion — it MUST be performed with GitHub App write credentials at implement-stage time (or directly by a maintainer), never during spec/plan/tasks generation. Verify via `git ls-remote --heads origin spec-draft/021-rebase-discover-stall` returning empty output (quickstart.md Scenario 9). **Deferred to a maintainer:** this implement run is constrained to push only to `spec/022-gate-closed-lifecycle`; deleting a different remote ref is out of that scope, and the network `git ls-remote`/`git push --delete` operations are not permitted in this headless environment. Left unchecked so a maintainer performs the one-time remote-branch remediation with GitHub App write credentials, per this task's own note that it may be "performed … directly by a maintainer."
- [X] T014 [P] Add a note to `specs/015-pipeline-watchdog/data-model.md` documenting that its `facts.turns` field (line 28's shape) is renamed to `facts.record-index` by this feature (FR-010) as a deliberate, spec-022-sanctioned deviation from that spec's original contract, cross-referencing `specs/022-gate-closed-lifecycle/contracts/denied-tool-collector-delta.md` for the full delta.
- [X] T015 [P] Update `docs/architecture.md` to document: (a) the new `wing-commander-lifecycle-gate` composite and its "Check lifecycle issue state" step, now the first billable step (after checkout, before preflight) of `clarify.yml`, `intake.yml`, `finalize.yml`, and `implement.yml`, and inserted before the sole write step of `tasks.yml`'s `tasks-approved` job — gating every subsequent step on `is-open == 'true'` and posting the single `kind: info` decline note on close; (b) the watchdog collector's corrected field name (`record-index`, not `turn`) and its now-accurate denial count.
- [X] T016 Validate every edited workflow file (`clarify.yml`, `intake.yml`, `tasks.yml`, `finalize.yml`, `implement.yml`, `watchdog.yml`) parses as valid YAML and passes this repository's own `lint-workflows.yml` checks (actionlint/yamllint), matching specs/019's and specs/020's precedent — run locally or trigger `lint-workflows.yml` itself.
- [X] T017 Run the full quickstart.md scenario sweep (Scenarios 1-9) against the finished implementation, including Scenario 6 (a reopened issue becomes actionable again, FR-005 — not exercised by any earlier phase's checkpoint). Record in the PR body which scenarios were exercised via a live dogfooded run versus desk-checked only, consistent with specs/020's validation-record precedent, since this repository has no unit-test harness for workflow YAML (constitution I; plan.md Testing).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Independent of Setup's outcome but should follow it in sequence (T001 confirms the assumptions T002's caller contract and every wiring task rely on) — BLOCKS every wiring task in US1 and US2 (T003-T004, T006-T008 all reference the composite T002 creates).
- **User Story 1 (Phase 3)**: Depends on Foundational (T002).
- **User Story 2 (Phase 4)**: Depends on Foundational (T002). Independent of User Story 1's own tasks (different files) but shares the same composite and audit scope, so T009's grep audit is most meaningful once both phases have landed.
- **User Story 3 (Phase 5)**: Depends on nothing from Phases 2-4 — touches a completely different job (`watchdog.yml`'s `collect`) and can proceed at any point, in parallel with Foundational/US1/US2.
- **Polish (Phase 6)**: T013/T014 depend on nothing but each other's absence of conflict (different repositories of concern — a remote branch vs. a spec doc) and can start immediately; T015 depends on US1/US2/US3 all being complete (it documents the finished wiring and the finished collector fix); T016 depends on all workflow-editing tasks (T003-T004, T006-T008, T011) being complete; T017 depends on every prior phase.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency beyond Foundational — independently testable and deployable as the MVP; fixes the exact reported defect (issue #109) on its own.
- **User Story 2 (P1)**: No dependency beyond Foundational; not dependent on User Story 1's specific files, but is the natural next increment since it completes the same audit US1 started (FR-004's full named list).
- **User Story 3 (P2)**: No dependency on User Story 1 or 2 at all — a fully independent fix to a different workflow (`watchdog.yml`) and a different concern (report accuracy, not authorization).

### Same-file ordering (not story dependencies, but real ordering constraints)

- T003 and T005 both edit `clarify.yml`-related concerns but only T003 edits the file; T005 is a validation task that must run after T003 completes.
- T004 (intake.yml) has no file overlap with T003/T005 (clarify.yml) — fully parallel.
- T006, T007, T008 each edit a distinct file (`tasks.yml`, `finalize.yml`, `implement.yml`) — fully parallel with each other and with T003/T004.
- T009 and T010 depend on T006-T008 (and, for the full five-workflow grep, on T003-T004 too) having landed.
- T011 (watchdog.yml jq filter) and T012 (new fixture script) are sequential — T012 tests the filter T011 produces.
- T013 and T014 touch unrelated repositories of concern (a remote git ref vs. a markdown file) and are mutually parallel-safe.

### Parallel Opportunities

- T003, T004, T006, T007, T008 can all run in parallel (five distinct workflow files, all depending only on T002).
- T011 (US3) can run in parallel with any/all of T003-T010 (US1/US2) — no shared file.
- T013, T014, T015 (once their own prerequisites are met) can run in parallel with each other.
- T001 (Setup) has no hard dependency on T002 starting, though in practice T001 should complete first since T002's contract review benefits from a confirmed baseline.

---

## Parallel Example: Phase 3 + Phase 4 together (once T002 is done)

```bash
# Launch every workflow-wiring task in parallel — five distinct files, one shared dependency (T002):
Task: "Wire the lifecycle gate into .github/workflows/clarify.yml (T003)"
Task: "Wire the lifecycle gate into .github/workflows/intake.yml (T004)"
Task: "Wire the lifecycle gate into .github/workflows/tasks.yml's tasks-approved job (T006)"
Task: "Wire the lifecycle gate into .github/workflows/finalize.yml (T007)"
Task: "Wire the lifecycle gate into .github/workflows/implement.yml (T008)"

# In parallel with all of the above — a different job in a different workflow:
Task: "Apply the corrected jq filter to watchdog.yml's collect-execution-output step (T011)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the entry-point map is still current)
2. Complete Phase 2: Foundational (the `wing-commander-lifecycle-gate` composite)
3. Complete Phase 3: User Story 1 (`clarify.yml` + `intake.yml` wiring)
4. **STOP and VALIDATE**: Run quickstart.md Scenarios 1-4 — confirm the exact reported defect (issue #109) no longer reproduces
5. This alone is mergeable: a closed lifecycle issue is now inert to the two entry points that are genuine raw comment/label triggers

### Incremental Delivery

1. Setup + Foundational → composite ready, baseline confirmed
2. Add User Story 1 → validate Scenarios 1-4 → mergeable increment (MVP: the reported defect is fixed)
3. Add User Story 2 → validate Scenarios 5 and 7 → mergeable increment (every FR-004-named entry point is now gated, with the scope boundary confirmed intact)
4. Add User Story 3 → validate Scenario 8 → mergeable increment (the watchdog's denied-tool reports are now accurate) — independent of Users Story 1/2 and could equally land first or in parallel
5. Polish → branch remediation, doc updates, full Scenario 1-9 sweep including the reopened-issue case (Scenario 6)

### Why User Story 1 alone is the MVP

FR-007 names the exact scenario this feature must eliminate: a comment-triggered stage firing on the closing comment of an already-closed lifecycle, resurrecting a torn-down branch, editing a closed PR, and posting a callout on the closed issue. That scenario runs through `clarify.yml` specifically (the entry point issue #109 observed), and User Story 1's wiring of `clarify.yml` and `intake.yml` — the only two genuine raw comment/label triggers — is sufficient on its own to make that scenario no longer reproduce. User Story 2's remaining three entry points (`tasks-approved`, `finalize`, `implement`) close the same hole defensively where it has not yet been observed to fire; User Story 3 is an unrelated reporting-accuracy fix. Both are important for completeness (SC-003, SC-005, SC-006) but neither is required for the reported defect itself to be fixed.
