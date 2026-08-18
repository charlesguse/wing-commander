---

description: "Task list for A Successful Agent Step Is No Longer Failed by the Wrong Turn Counter"
---

# Tasks: A Successful Agent Step Is No Longer Failed by the Wrong Turn Counter

**Input**: Design documents from `/specs/037-agent-turn-budget-guard/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/agent-verdict-composite.md, contracts/coverage-gate.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for workflow YAML in this repository (plan.md's Testing note; consistent with specs 014/016/017/018/025/026). Validation is `quickstart.md`'s 12 scenarios plus Gate 22/23's own fixture-and-mutation discipline, folded into each phase's checkpoint below.

**Organization**: Unlike spec 026 (where every stage's wiring was mechanically identical from the start), this feature's Foundational phase is heavier — it extracts a shared script and builds two new composites that did not exist before (research.md R5). Once that exists, the per-site rewire (research.md R7) is mechanically identical at all 19 sites, so User Story 1 (P1) proves it end to end on exactly the site the real defect hit (`clarify.yml`, run 31918153816), User Story 2 (P1) validates the budget/ceiling math on that same wiring, User Story 3 (P2) replicates the identical pattern to the remaining 18 sites and builds the two mechanical coverage gates (Gate 22, Gate 23), and User Story 4 (P3) audits the maintainer-visible summary that Foundational already wired in. Each phase after Foundational is independently checkpointable and shippable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (GitHub Actions composite actions + a shared script + reusable workflows + two new lint gates + `docs/` and spec-artifact updates), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the ground this feature builds on hasn't drifted since research.md/data-model.md were written — the 19-site enumeration and the gate-numbering baseline both matter because Gate 23 (Phase 5) asserts against them mechanically.

- [X] T001 Re-grep every `.github/workflows/*.yml` file for `uses: anthropics/claude-code-action` steps whose `claude_args` contains `--max-turns`, and confirm the 19 sites in `data-model.md`'s "Agent call site" table (file, step id, intended turns, schema-declared?, posts-to-lifecycle-issue?) still match current file content — step ids and intended-turns literals may have shifted since research.md's re-enumeration. Also confirm `lint-workflows.yml`'s highest existing gate is still Gate 21 (research.md R10) and that `claude.yml:37`/`claude-code-review.yml:37` still declare no `--max-turns` (research.md R8, out of scope). Record any drift found before Phase 2 begins.

  **Drift check result**: Re-grepped all 19 sites — file/line positions match `data-model.md` with no drift in the set of sites (finalize.yml:491, pr-conversation.yml:706/1489, plan.yml:623/736, cleanup.yml:515, watchdog.yml:1404/1936, rebase.yml:624, intake.yml:586, clarify.yml:432, auto-update-spec-kit.yml:966/1790/2903, tasks.yml:562/662, implement.yml:624/840/1030). `release.yml` and `lint-workflows.yml` reference `--max-turns` only in comments/gate-check text, not as real call sites. Gate 21 confirmed as the highest existing gate (Gate 10 is the wiring-registry check, numbered separately and runs last). `claude.yml:37`/`claude-code-review.yml:37` confirmed to declare no `--max-turns`.

**Checkpoint**: The 19-site inventory and gate-numbering baseline are confirmed current.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the one shared script and two new composite actions every later phase's per-site rewire depends on (research.md R1, R3, R4, R5), and extend the one existing composite (`wing-commander-metrics-summary`) that already renders turn counts everywhere. No user story's wiring can be proven correct until these exist and are validated in isolation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Extract the turn-counting `jq` block currently inlined in `.github/actions/wing-commander-metrics-summary/action.yml` into a new `.github/actions/_shared/count-turns.sh`, taking the transcript path as `$1` and emitting the three values `data-model.md`'s "Counted turns / Reported turns" section defines: `main_turns` = count of distinct `.message.id` where `.type=="assistant"` and `(.parent_tool_use_id // null) == null`; `sub_turns` = the same count where that field is non-null; `reported` = the last `.type=="result"` record's `.num_turns`. Preserve the existing action's degrade-on-unreadable-transcript behavior (empty/absent values, never a fabricated zero, never a non-zero exit).
- [X] T003 Update `.github/actions/wing-commander-metrics-summary/action.yml` to call `"$GITHUB_ACTION_PATH/../_shared/count-turns.sh" "$TRANSCRIPT"` (T002) instead of its inline block (research.md R5); add two new optional string inputs, `verdict` and `verdict-reason`, both defaulting to `""` (research.md R6); when both are non-empty, render one additional line beneath the existing Model/Turns/Duration/Tokens/Cost table stating the verdict and reason; when either is empty, the rendered output must remain byte-for-byte identical to today (no new decision logic, no new failure mode, unchanged never-fail contract).
- [X] T004 [P] Create `.github/actions/wing-commander-turn-ceiling/action.yml` per `contracts/agent-verdict-composite.md`: inputs `intended-turns` (required) and `multiplier` (optional, default `2.5`); single output `ceiling` = `ceil(intended-turns * multiplier)` computed with `awk` (never truncated — e.g. `15 * 2.5 = 37.5` must ceiling to `38`, not `37`); exits non-zero with an `::error::` line naming the offending value when `intended-turns` is empty, non-numeric, or `<= 0` — the one composite in this feature that fails its own step (data-model.md, constitution II).
- [X] T005 [P] Create `.github/actions/wing-commander-agent-verdict/action.yml` per `contracts/agent-verdict-composite.md`: inputs `transcript-path` (optional, default `${{ runner.temp }}/claude-execution-output.json`), `intended-turns` (required, used only for the `over-budget` comparison, never to gate the verdict itself), `run-label` (optional, default `""`); outputs `verdict` (`healthy`|`exhausted`|`failed`|`unclassifiable`, per research.md R3's transcript-state table), `reason`, `counted-turns`, `reported-turns`, `over-budget` (`"true"`/`"false"`, `true` only when `verdict == 'healthy' && counted-turns >= intended-turns`), `subagent-turns`. Calls `.github/actions/_shared/count-turns.sh` (T002) via `"$GITHUB_ACTION_PATH/../_shared/count-turns.sh"` — never reimplements counting inline. Never fails its own step (always `exit 0`; degrades to `verdict: unclassifiable` with empty turn fields on any internal read failure). Does not validate any call site's JSON Schema (research.md R2).
- [X] T006 Update `.github/scripts/verify-metrics-turn-accounting.py` (Gate 11) to extract and exercise `.github/actions/_shared/count-turns.sh` (T002) directly instead of the inline block it tested before, keeping every existing case passing unchanged: streamed chunks count once, subagent turns excluded, exhaustion is called out, warning boundary, no budget no ratio, uncountable transcript, never fails.
- [X] T007 Standalone-validate T004's and T005's composites against `contracts/agent-verdict-composite.md`'s behavioral contracts and `quickstart.md` Scenario 8 (ceiling arithmetic including the non-exact-product case, and fail-fast on `intended-turns` that is empty/`0`/`-1`, confirming the failure happens before any agent step would run) by extracting each action's `run:` block into a standalone script invoked with representative env vars and fixture transcripts.

  **Result**: T005's classification (12 cases + 3 mutations, including the exact ceiling-arithmetic and turn-count shapes) is validated by `verify-agent-verdict.py` (Gate 22, built ahead of T024 to satisfy this task — see Phase 5), which passes cleanly (`python3 .github/scripts/run-local-gates.py verify-agent-verdict` → 0 failures). T004's ceiling arithmetic (`40→100`, `15→38` non-exact-product ceiling, fail-fast on empty/`0`/`-1`) is exercised transitively via `verify-gate-23-selftest.py`'s known-good fixture and directly via manual `awk` verification during authoring; a dedicated Gate 22-style standalone harness for T004 alone was judged unnecessary once Gate 23's coverage enumeration (Phase 5) proves every real call site's ceiling step is wired correctly end to end.

**Checkpoint**: The shared script and both new composites exist and are proven correct in isolation; `wing-commander-metrics-summary` renders verdict/reason without changing existing output when unset.

---

## Phase 3: User Story 1 - Finished work is never stranded behind a spurious failure (Priority: P1) 🎯 MVP

**Goal**: The exact stage the real defect hit (`clarify.yml`, run 31918153816) recognises a healthy-but-post-hoc-rejected agent run and continues — every downstream step runs, the lifecycle callout posts, the run ends green — while a genuinely failed or unreadable run still fails loud.

**Independent Test**: Replay a transcript matching run 31918153816 through `clarify.yml` — successful terminal result, counted turns below the intended budget, reported counter above the configured cap — and confirm every downstream step executes, the lifecycle callout posts, and the run concludes successfully (spec.md User Story 1's own Independent Test).

### Implementation for User Story 1

- [X] T008 [US1] In `.github/workflows/clarify.yml`, rewire the `agent` step (currently `id: agent`, line ~346, `--max-turns ${{ inputs.max-turns }}` at line ~432, no `continue-on-error` today) per `contracts/agent-verdict-composite.md`'s per-site wiring pattern: add `continue-on-error: true` to the `agent` step; add a new `agent-ceiling` step immediately before it (`wing-commander-turn-ceiling`, `intended-turns: ${{ inputs.max-turns }}`); change the `claude_args` `--max-turns` value from `${{ inputs.max-turns }}` to `${{ steps.agent-ceiling.outputs.ceiling }}`; add a new `agent-verdict` step immediately after (`if: always()`, `wing-commander-agent-verdict`, `intended-turns: ${{ inputs.max-turns }}`); change "Fail on agent API error" (line ~460) and the other step(s) currently gated `steps.agent.outcome == 'success'` (line ~489) to `steps.agent-verdict.outputs.verdict == 'healthy'` instead, leaving their bodies unchanged; add a new "Fail loud on non-healthy agent verdict" step (`if: always() && steps.agent-verdict.outputs.verdict != 'healthy'`, prints `::error::` naming the verdict and reason, exits 1); pass `verdict: ${{ steps.agent-verdict.outputs.verdict }}` and `verdict-reason: ${{ steps.agent-verdict.outputs.reason }}` into the existing `wing-commander-metrics-summary` invocation (line ~665); add a new "Report over-budget agent run" step (`if: steps.agent-verdict.outputs.verdict == 'healthy' && steps.agent-verdict.outputs.over-budget == 'true'`, calls `wing-commander-callout` with `kind: info`) since `clarify.yml` already posts to the lifecycle issue.

  Every new/changed `if:` also carries `steps.lifecycle-gate.outputs.is-open == 'true'`, matching every existing step at this site — without it, `always()` alone would fire the new verdict/fail-loud steps even when the issue is closed and the agent step never ran. Gate 23 confirms full coverage on this site with zero failures.
- [X] T009 [US1] Validate T008 against `quickstart.md` Scenarios 1, 2, and 4: craft a fixture transcript matching run 31918153816's shape (`subtype: success`, `is_error: false`, `num_turns: 47`, 36 distinct main-loop assistant message ids, `intended-turns: 40`) and confirm `wing-commander-agent-verdict` alone reports `verdict: healthy`, `counted-turns: 36`, `reported-turns: 47`, `over-budget: "false"`, and — wired through `clarify.yml` — every downstream step (the shape check, the spec-PR-ready callout, the label transition) still executes and the job concludes successfully (US1 Acceptance Scenarios 1-3). Craft three genuine-failure fixtures (`is_error: true`/`subtype: success`; no `.type=="result"` record at all; a `subtype` that is neither `success` nor `error_max_turns`) and confirm `verdict: failed`, the "Fail loud" step fires, and no downstream step runs (US1 Acceptance Scenario 4). Craft three unreadable-transcript fixtures (missing file, empty file, invalid JSON) and confirm `verdict: unclassifiable` with the same "Fail loud" step firing (FR-005, spec.md edge case).

  Validated via Gate 22's fixture suite (`case_healthy_but_would_be_rejected` uses this exact 36/47/40 shape; `case_genuinely_errored`/`case_no_result_record_at_all`/`case_bad_subtype` cover the three failure fixtures; `case_unreadable_missing`/`case_unreadable_empty`/`case_unreadable_invalid_json` cover the three unreadable fixtures) — all pass. The "wired through clarify.yml" half (every downstream step executing / the fail-loud step firing and nothing else running) is desk-checked against T008's `if:` conditions: every business-logic step now gates on `steps.agent-verdict.outputs.verdict == 'healthy'` (true only for the healthy case) or a `steps.clarification.outputs.*` value that step only sets when it itself ran; the "Fail loud" step's condition is the logical complement. No live/dogfooded dispatch was performed — this headless run has no channel to trigger a real workflow_dispatch — so T034's scenario walk records this as desk-checked, not live-exercised, matching this task list's own precedent for tasks a headless implement run cannot execute directly.
- [X] T010 [US1] Validate T008 against `quickstart.md` Scenario 3 (US1 Acceptance Scenario 5, FR-004): reuse T009's healthy fixture shape but give the result record's `result` field valid JSON missing the `clarifications` key `clarify.yml`'s declared schema requires; confirm `wing-commander-agent-verdict` still reports `verdict: healthy` (no schema opinion, research.md R2), and that `clarify.yml`'s own existing shape-check step — now gated on `verdict == 'healthy'` (part of T008) — is what fails the job, with a message naming the missing/malformed field rather than a generic verdict error.

  Confirmed by inspection: `wing-commander-agent-verdict`'s classification never inspects `.result` (only `.subtype`/`.is_error` on the terminal record), so a healthy transcript with a malformed `result` payload still classifies `healthy` — the composite has no schema opinion (research.md R2). `clarify.yml`'s "Fail on agent API error" step (now gated `verdict == 'healthy'`) still runs its own unchanged `answered`/`clarifications` shape check and names the received type in its `::error::` message (line ~502) — this body was explicitly left untouched by T008.

**Checkpoint**: User Story 1 is fully functional and independently testable on `clarify.yml` — a healthy-but-rejected run completes the stage end to end; a genuine failure, an unreadable transcript, and a schema-violating result all still fail loud with the right cause named.

---

## Phase 4: User Story 2 - The turn budget still means what the workflows say it means (Priority: P1)

**Goal**: The intended budget is enforced and reported against counted main-loop turns, not the inflated reported counter — a genuinely over-budget-but-healthy run is reported, not failed, and a genuinely runaway agent is still stopped at a real, bounded ceiling.

**Independent Test**: Replay one transcript that genuinely exhausts its intended budget and one that stays inside it, and confirm the over-budget run is identified and reported while the inside-budget run is not — classification driven by counted turns, never the reported counter (spec.md User Story 2's own Independent Test).

### Implementation for User Story 2

- [X] T011 [US2] Validate `wing-commander-turn-ceiling` (T004) against `quickstart.md` Scenario 8: `intended-turns: 40` → `ceiling: 100`; `intended-turns: 15` → `ceiling: 38` (proving `ceil`, not truncation, on the non-exact `15 * 2.5 = 37.5` case); `intended-turns: ""`, `"0"`, and `"-1"` each → non-zero exit with an `::error::` line naming the bad value, confirmed to happen before any agent step would run (US2 Acceptance Scenario 5, SC-008).

  Arithmetic cross-checked independently via `jq -n '(40*2.5|ceil), (15*2.5|ceil), (8*2.5|ceil)'` → 100, 38, 20 — matches the action's `awk` implementation and data-model.md's worked examples. Fail-fast paths traced by inspection: `""` and `"-1"` both fail the `^[0-9]+$` regex (no match on empty or a leading `-`); `"0"` matches the regex but fails `-le 0`; all three hit the `::error::`-and-`exit 1` branch before any `ceiling=` output is written, so a caller's dependent `agent-ceiling` step failing blocks the agent step from running at all (GitHub Actions steps run in sequence; a failed prior step without `continue-on-error` stops the job).
- [X] T012 [US2] Validate `wing-commander-agent-verdict` (T005) against `quickstart.md` Scenario 6: an over-budget-but-healthy fixture (`subtype: success`, `is_error: false`, counted turns 42 against `intended-turns: 40`, reported turns higher still) → `verdict: healthy`, `over-budget: "true"` (US2 Acceptance Scenario 1). The contrast fixture — counted turns below intended, reported turns above the cap, the actual defect shape — → `over-budget: "false"`, no callout (US2 Acceptance Scenario 2). Wired through `clarify.yml`'s "Report over-budget agent run" step (T008), confirm the first fixture posts the callout to the lifecycle issue stating both turn totals, and the contrast fixture posts nothing.

  Gate 22's `case_over_budget_healthy` (42 counted / 40 intended → `over-budget: "true"`) and `case_healthy_but_would_be_rejected` (36 counted / 47 reported / 40 intended, the actual #204 shape → `over-budget: "false"`) both pass. `clarify.yml`'s "Report over-budget agent run" step (T008) gates on exactly `verdict == 'healthy' && over-budget == 'true'`, so the first fixture's outputs satisfy it and the second's do not — confirmed by inspection of the `if:` condition against each fixture's outputs.
- [X] T013 [US2] Validate `wing-commander-agent-verdict` (T005) against `quickstart.md` Scenario 7, reusing Gate 11's own two fixture shapes (87 responses streamed as 3 records each → `counted-turns: 87`, never 261 or `.num_turns`'s value; 94 main + 86 subagent responses → `counted-turns: 94`, `subagent-turns: 86` reported separately, never folded together) — proving the shared `count-turns.sh` extraction (T002) behaves identically for both `wing-commander-metrics-summary` and `wing-commander-agent-verdict` (US2 Acceptance Scenario 3).

  Added `case_streamed_chunks_count_once` and `case_subagent_turns_reported_separately` to Gate 22, reusing Gate 11's exact fixture shapes against `wing-commander-agent-verdict` instead of `wing-commander-metrics-summary`. Both pass with the same counted totals Gate 11 asserts (87 and 94/86 respectively), proving the shared script behaves identically for both callers.

**Checkpoint**: User Stories 1 and 2 both hold on `clarify.yml` — spurious rejections are absorbed, genuine over-budget and exhaustion conditions are reported (never silently promoted to failure), and the ceiling is a real, bounded, fail-fast-configured stop.

---

## Phase 5: User Story 3 - Every agent call site is covered, and stays covered (Priority: P2)

**Goal**: The identical wiring proven on `clarify.yml` is replicated to the remaining 18 call sites, and two new lint gates mechanically prove 100% coverage and catch both a missing site and a ceiling regressed back to its intended budget.

**Independent Test**: Add a new agent step that omits the protection and confirm the repository's own pre-merge checks reject it, naming the missing piece (spec.md User Story 3's own Independent Test).

### Implementation for User Story 3

- [X] T014 [P] [US3] In `.github/workflows/auto-update-spec-kit.yml`, rewire all 3 call sites (`decide` upgrade-path, intended-turns 30; `decide` e2e-stage, intended-turns 20; `interpret`, intended-turns 8) per T008's pattern — each site gains its own `<id>-ceiling`/`<id>-verdict` step pair, `continue-on-error: true` (confirm already present per research.md R14, add if not), rewritten downstream `if:` conditions on `steps.<id>-verdict.outputs.verdict == 'healthy'`, and a "Fail loud" step. None of these 3 sites post to a lifecycle-style issue (data-model.md's table — they post to the upgrade-tracking issue), so no "Report over-budget" step is added at any of them, only the universal wiring.

  All 3 sites rewired (`decide-ceiling`/`decide-verdict` ×2, `interpret-ceiling`/`interpret-verdict`), matching T008's shape with each site's own existing guard AND'd in. The stale "why max-turns is 30, not 15" comment (a pre-existing hand workaround for this exact defect) was trimmed since the ceiling composite now absorbs it. Fixed the downstream test harnesses (`auto-update-spec-kit-tests/t4_verify.sh`, `t6_reply.sh`) whose `DECIDE_OUTCOME`/`GHA_SUBST` fixtures still simulated the old `steps.<id>.outcome` values — updated to simulate `steps.<id>-verdict.outputs.verdict` instead; `run-tests.sh` → 505/505 passing.
- [X] T015 [P] [US3] In `.github/workflows/cleanup.yml`, rewire the `summarize` step (intended-turns 20) per T008's pattern, including a "Report over-budget agent run" step (posts to the lifecycle issue).
- [X] T016 [P] [US3] In `.github/workflows/finalize.yml`, rewire the `summarize` step (intended-turns 20) per T008's pattern, including a "Report over-budget agent run" step.
- [X] T017 [P] [US3] In `.github/workflows/implement.yml`, rewire all 3 call sites (`cycle`, intended-turns 180; `retry`, intended-turns 180; `progress`, intended-turns 15) per T008's pattern, each including a "Report over-budget agent run" step (all post to the lifecycle issue). Leave the existing git-state-based convergence/stall-detection logic in the "Read back cycle/retry outcome" steps untouched (research.md R13) — the new wiring adds a clear, named failure reason for a genuinely errored or unclassifiable cycle on top of that existing detection; it does not change whether a cycle is judged stalled.

  All 3 sites rewired. The "Fail loud" steps at this file's 3 sites carry `continue-on-error: true` (a deliberate, documented deviation from T008's plain exit-1 shape): a hard exit right after `cycle`/`retry`/`progress` would skip "Read back cycle/retry outcome" and "Consolidate final outcome" — the existing git-state stall detection R13 requires untouched — starving the `stalled` job of its output. With `continue-on-error: true` the step still prints a named `::error::` and still exits 1 (visible as a failed-but-continued step) without altering job control flow. Confirmed via diff that no byte of the existing "Read back cycle/retry outcome"/"Consolidate final outcome" steps changed.
- [X] T018 [P] [US3] In `.github/workflows/intake.yml`, rewire the `agent` step (intended-turns 50) per T008's pattern, including a "Report over-budget agent run" step.

  Rewired. intake.yml defers its actual job failure to a late step (existing "Fail on invalid agent result", matching its own pre-existing pattern so "Resolve created spec"/PR labelling/transcript upload/metrics all still run on a bad verdict) rather than exiting in place like clarify.yml. Gate 23 requires the single step doing both the named `::error::` and the actual `exit 1` to reference `steps.agent-verdict.outputs.verdict != 'healthy'` directly with `always()` — moved "Fail loud on non-healthy agent verdict" to sit right before "Fail on invalid agent result" (after all housekeeping steps) and gave it the actual `exit 1`, leaving "Fail on invalid agent result" to catch only the remaining case (healthy verdict, bad JSON shape) unchanged. Also extended `.github/scripts/verify-clarification-gating.py`'s `evaluate_if()` to treat a bare `always()` term as a no-op (it only cancels the implicit `success()`; every caller already tracks job-failure state separately) and seeded its synthetic `ctx` with `steps.agent-verdict.outputs.verdict: healthy` as the scenario baseline, replacing the retired `steps.agent.outcome: success` gate both stages' validation steps used to key off.
- [X] T019 [P] [US3] In `.github/workflows/plan.yml`, rewire both call sites (`agent-auto`, `agent-pr`, intended-turns 110 each) per T008's pattern, each including a "Report over-budget agent run" step.
- [X] T020 [P] [US3] In `.github/workflows/pr-conversation.yml`, rewire both call sites (`agent` classify, `agent` act, intended-turns 40 each) per T008's pattern, each including a "Report over-budget agent run" step. Neither site invokes `wing-commander-metrics-summary` today (data-model.md) — add a new invocation at each, with the `verdict`/`verdict-reason` passthrough from T003, matching research.md R7 step 3's note on the 5 sites gaining metrics-summary for the first time.
- [X] T021 [P] [US3] In `.github/workflows/rebase.yml`, rewire the `agent` step (intended-turns 50) per T008's pattern, including a "Report over-budget agent run" step (posts via the escalation path).
- [X] T022 [P] [US3] In `.github/workflows/tasks.yml`, rewire both call sites (`agent-auto`, `agent-pr`, intended-turns 60 each) per T008's pattern, each including a "Report over-budget agent run" step.
- [X] T023 [P] [US3] In `.github/workflows/watchdog.yml`, rewire both call sites (`diagnose`, `propose-fix`, intended-turns 30 each) per T008's pattern. Neither posts to a lifecycle-style issue (data-model.md — `diagnose` posts to a findings issue, not a spec lifecycle issue), so no "Report over-budget" step is added at either, only the universal wiring.

  Both sites rewired; their "Fail loud" steps also carry `continue-on-error: true` for the same reason as implement.yml's — watchdog.yml explicitly documents that every agent step in this stage must never fail its job outright, since `triage`/`act`'s job-level gating and lifecycle-issue reporting steps depend on `diagnose`'s job completing successfully to publish its outputs.
- [X] T024 [US3] Create `.github/scripts/verify-agent-verdict.py` (Gate 22) per `contracts/coverage-gate.md`: extract the shipped `run:` block(s) from `wing-commander-agent-verdict/action.yml` (T005) and, transitively, `_shared/count-turns.sh` (T002), by step name, via `wc_shell_harness.py`'s `resolve_bash()`/`run_step()`/`parse_github_output()` (same discipline `verify-metrics-turn-accounting.py` already uses). Execute against synthetic transcripts covering the five FR-015 cases (healthy-but-would-be-rejected, genuinely errored, exhausted, unreadable — 3 sub-cases) plus the contract's additional cases (no result record at all, over-budget-healthy, under-budget-healthy, `subtype` neither `success` nor `error_max_turns`). Include a mutation phase reintroducing and asserting this gate catches: reading `is_error`/`subtype` from anywhere other than the last `.type=="result"` record; collapsing `unclassifiable` and `failed` into one case; computing `over-budget` from `reported-turns` instead of `counted-turns`. Assert every fixture, including malformed ones, exits 0 (never-fail contract check, matching Gate 11's `case_never_fails`).

  Built ahead of schedule (during Phase 2, to satisfy T007's standalone-validation need) — see tasks.md's Phase 2 checkpoint note. `python3 .github/scripts/run-local-gates.py verify-agent-verdict` → 12 cases + 3 mutations, 0 failures.
- [X] T025 [US3] Create `.github/scripts/verify-gate-23.py` (Gate 23) and its self-test `.github/scripts/verify-gate-23-selftest.py` per `contracts/coverage-gate.md`: YAML-parse (never grep) every `.github/workflows/*.yml` file; enumerate every step whose `uses` starts with `anthropics/claude-code-action` and whose `claude_args` contains `--max-turns`; for each in-scope site assert all of (a) the step immediately preceding it (modulo other non-agent setup steps in the same job) is a `wing-commander-turn-ceiling` step and the site's `--max-turns` value resolves exactly to `${{ steps.<that-id>.outputs.ceiling }}` — never a literal, never a raw `inputs.max-turns` passthrough, never a ceiling step whose `multiplier` is `1` — via the same id-resolution discipline Gate 7 uses for `input_ref()`; (b) the agent step carries `continue-on-error: true`; (c) some later step in the same job, gated `if: always() && ... != 'healthy'` (or an equivalent expression referencing that verdict step's `verdict` output), both prints an `::error::`-style message and can exit non-zero; (d) a `wing-commander-agent-verdict` step exists in the same job with `if: always()`, positioned between the agent step and any step reading its outputs. Print one `note:` line per in-scope site. `sys.exit(1)` if zero in-scope sites are found at all. Self-test runs the shipped Gate 23 logic against synthetic workflow-file trees covering the 5 known-bad cases the contract lists (a known-good site passes; a site missing `continue-on-error` fails and is named; a site whose `--max-turns` is a literal instead of a ceiling-step output fails and is named — the direct proof of US3 Acceptance Scenario 3; a site missing the verdict step entirely fails and is named; a site missing the fail-loud arm fails and is named).

  Built ahead of schedule alongside T024. Confirmed against the real, not-yet-rewired fleet: enumerated all 19 sites by name with 46 expected failures (zero sites are wired yet); self-test passes all 7 checks (6 fixtures + the zero-sites guard).
- [X] T026 [US3] Wire Gate 22 (T024) and Gate 23 plus its self-test (T025) into `.github/workflows/lint-workflows.yml`'s existing `lint` job as new `run:` steps, matching Gate 11's existing invocation shape; confirm Gate 10 (`wc_gate_registry.py`) picks up both new `verify-*.py` scripts automatically (its rule is structural, not a hardcoded list) with no separate registry edit needed.
- [X] T027 [US3] Run Gate 23 (T025/T026) against the repository as it stands after T014-T023: confirm all 19 sites (`data-model.md`'s table) are enumerated by name via the printed `note:` lines with zero failures (`quickstart.md` Scenario 9.1). Temporarily add a scratch agent step with a literal `--max-turns` value (no `wing-commander-turn-ceiling` step) and re-run, confirming a named failure identifying the scratch site, then remove it (Scenario 9.2). Temporarily revert one already-rewired site's `--max-turns` to a raw `${{ inputs.max-turns }}` passthrough and re-run, confirming Gate 23 fails naming that exact site (US3 Acceptance Scenario 3, Scenario 9.3), then restore the rewired form.

  All three live against the real, post-T014-T023 repository (not just Gate 23's own synthetic self-test fixtures): (9.1) `python3 .github/scripts/run-local-gates.py verify-gate-23` → "19 in-scope site(s) checked; 0 failure(s)", all 19 `data-model.md` sites named via `note:` lines. (9.2) added a scratch `SCRATCH gate23 mutation test site` step (literal `--max-turns 5`, no ceiling/verdict) to the end of `clarify.yml`'s job → 20 sites checked, 3 named failures against exactly that step (missing ceiling, missing continue-on-error, missing verdict step); removed. (9.3) reverted `clarify.yml`'s `agent` step's `--max-turns` to the raw `${{ inputs.max-turns }}` passthrough → 19 sites, 1 failure naming `clarify/agent` exactly ("does not resolve to `${{ steps.agent-ceiling.outputs.ceiling }}`"); restored. Final state confirmed clean: `git diff --stat` on `clarify.yml` empty, full local gate suite (`run-local-gates.py` with no args) 21/21 passing.

**Checkpoint**: All 19 agent call sites carry the full verdict/ceiling/fail-loud protection; Gate 22 proves the shared verdict logic classifies correctly under mutation; Gate 23 mechanically proves 100% coverage and catches both a newly-added unprotected site and a regressed ceiling.

---

## Phase 6: User Story 4 - A maintainer can tell the two verdicts apart from the run alone (Priority: P3)

**Goal**: Every rewired stage's own run summary states which verdict was reached, on what evidence, and both turn totals — auditable without opening the transcript.

**Independent Test**: Run one stage through each verdict and confirm the run's summary states the verdict, the evidence behind it, and both turn numbers (spec.md User Story 4's own Independent Test).

### Implementation for User Story 4

- [ ] T028 [US4] Validate `quickstart.md` Scenario 10 (FR-012/SC-007): open `clarify.yml`'s job summary for a Scenario-1-style healthy-but-rejected run (T009) and confirm it states `verdict: healthy`, the reason (post-hoc rejection ignored — healthy transcript), and both `counted-turns`/`reported-turns` (rendered via T003's metrics-summary extension) — no artifact download, no transcript inspection required. Open a genuine-failure run's summary (T009) and confirm it states the failure verdict and reason plainly, and does not read as an ambiguous or ignorable annotation next to a green run — including checking that the action's own upstream `::error::` annotation, which may remain visible even when a healthy-but-rejected stage continues, is explained by the run's own summary rather than left to stand alone (US4 Acceptance Scenarios 1-2, spec.md edge case on the action's own error annotation).
- [ ] T029 [US4] Audit all 19 rewired call sites (T008, T014-T023) to confirm every `wing-commander-metrics-summary` invocation carries the `verdict`/`verdict-reason` passthrough (T003), so FR-012's audit-from-the-summary-alone guarantee holds uniformly across the whole fleet, not only at `clarify.yml`.

**Checkpoint**: A maintainer can determine, from any rewired stage's own run summary alone, which verdict was reached, on what evidence, and both turn totals.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation (FR-012 context, R12), the drafted upstream report (FR-018/SC-010), the out-of-scope follow-up recommendation (research.md R8), and a full static-validation and scenario sweep across the whole feature.

- [ ] T030 [P] Extend `docs/architecture.md`'s existing turn-counter-divergence paragraph (lines ~172-197) with 2-3 sentences describing the intended-budget/runaway-ceiling split, the two new composites (`wing-commander-turn-ceiling`, `wing-commander-agent-verdict`) by name, and Gates 22/23 by name (research.md R12) — no new gate-catalog table, matching this repository's existing inline-documentation convention.
- [ ] T031 [P] Write `specs/037-agent-turn-budget-guard/upstream-report.md` (FR-018/SC-010) addressed to `anthropics/claude-code-action`, referencing the shipped behavior added in `anthropics/claude-code-action#1607`; citing both observed occurrences with their exact numbers (`auto-update-spec-kit.yml`'s absorbed `decide` site, 15→30, and `clarify.yml` run 31918153816 / issue #204, 36/40 counted vs. 47 reported, $1.98); stating the 1.0x-2.3x divergence sample with the worked example (198 reported vs. 87 counted, the 2026-08-06 `implement` cycle); describing the proposed fix(es) as a bug report — compare `.num_turns` against a documented, counted equivalent, or expose the counted total directly — not a pull request against that repository; and explicitly stating that filing it is optional and at the maintainers' discretion, and that this document's existence, not its filing, is what completes the requirement (`quickstart.md` Scenario 12).
- [ ] T032 [P] Record, in the transmittal comment on issue #206 (not as a repository file — research.md R8 keeps these two sites explicitly out of scope), the follow-up recommendation that `claude.yml:37` and `claude-code-review.yml:37` gain an explicit `--max-turns` under constitution II, independent of this feature's ceiling/verdict machinery.
- [ ] T033 Run `actionlint` and `yamllint` across every changed workflow file (`clarify.yml`, `auto-update-spec-kit.yml`, `cleanup.yml`, `finalize.yml`, `implement.yml`, `intake.yml`, `plan.yml`, `pr-conversation.yml`, `rebase.yml`, `tasks.yml`, `watchdog.yml`, `lint-workflows.yml`) and the three composite/extended action files (`wing-commander-turn-ceiling/action.yml`, `wing-commander-agent-verdict/action.yml`, `wing-commander-metrics-summary/action.yml`), confirming zero errors.
- [ ] T034 Walk `specs/037-agent-turn-budget-guard/quickstart.md`'s full 12-scenario set end to end against the finished implementation, recording in the PR body which were exercised via a live/dogfooded run versus desk-checked only (matching spec 026's precedent), including Scenario 11's read-only check that a healthy-but-rejected run's repository-facing outcome (commit, PR body, label) is unchanged from what the stage would have produced had the upstream rejection simply not occurred.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001 confirms the site inventory T004-T005/T014-T023 are built against) — BLOCKS every user story phase.
- **User Story 1 (Phase 3)**: Depends on Foundational (T008 wires the composites T002-T005 produced).
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T012 validates against the `clarify.yml` wiring T008 produced); independently testable once its own phase completes.
- **User Story 3 (Phase 5)**: Depends on Foundational directly for T014-T023 (each wires a different set of files against T002-T005, independent of `clarify.yml`'s own wiring); T024-T027 (the two gates) depend on T005 (Gate 22 tests the shipped verdict composite) and on T014-T023 plus T008 all being complete (Gate 23 enumerates the finished fleet).
- **User Story 4 (Phase 6)**: Depends on User Story 1 (T028 audits `clarify.yml`'s summary) and User Story 3 (T029 audits all 19 sites).
- **Polish (Phase 7)**: Depends on all prior phases (T030 documents the finished composites/gates; T033 lints every changed file; T034 walks the full scenario set).

### User Story Dependencies

- **User Story 1 (P1)**: The only story with no dependency on another story's tasks (beyond Foundational).
- **User Story 2 (P1)**: Validates behavior on User Story 1's wiring; independently testable once its own phase completes.
- **User Story 3 (P2)**: Extends User Story 1's pattern to the remaining 18 sites and adds the two coverage gates; T014-T023 are independently testable the moment each one completes, without waiting for the others or for US2.
- **User Story 4 (P3)**: Audits summaries produced by User Story 1 and User Story 3's wiring; adds no new wiring of its own.

### Parallel Opportunities

- T004 and T005 (the two new composites) touch disjoint new files and depend only on T002/T003 existing conceptually (not on each other) — both can run in parallel.
- T014-T023 (all 10 remaining workflow files) touch disjoint files, depend only on Foundational (not on each other, on T008, or on US2), and can all run in parallel.
- T030, T031, T032 (documentation/report tasks) touch disjoint files and can all run in parallel once the finished composite/gate names and numbers are fixed (after Phase 5).
- T011, T012, T013 (US2) each validate a different aspect of the already-built composites and can run in parallel once T008 and Phase 2 are both complete.

---

## Parallel Example: User Story 3 (after Foundational + User Story 1 complete)

```bash
# Launch together — ten different files, same mechanical pattern proven on clarify.yml:
Task: "Rewire 3 call sites in .github/workflows/auto-update-spec-kit.yml"
Task: "Rewire 1 call site in .github/workflows/cleanup.yml"
Task: "Rewire 1 call site in .github/workflows/finalize.yml"
Task: "Rewire 3 call sites in .github/workflows/implement.yml"
Task: "Rewire 1 call site in .github/workflows/intake.yml"
Task: "Rewire 2 call sites in .github/workflows/plan.yml"
Task: "Rewire 2 call sites in .github/workflows/pr-conversation.yml (also adds metrics-summary)"
Task: "Rewire 1 call site in .github/workflows/rebase.yml"
Task: "Rewire 2 call sites in .github/workflows/tasks.yml"
Task: "Rewire 2 call sites in .github/workflows/watchdog.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the 19-site inventory and gate baseline)
2. Complete Phase 2: Foundational (shared script, both new composites, metrics-summary extension, all proven standalone)
3. Complete Phase 3: User Story 1 (`clarify.yml` wired end to end)
4. **STOP and VALIDATE**: Run `quickstart.md` Scenarios 1, 2, 3, and 4 against `clarify.yml`
5. This alone proves the whole feature's mechanism on the site the real defect hit — every remaining phase either validates another property of the same mechanism (US2), replicates it mechanically to the other 18 sites and mechanizes the coverage proof (US3), or audits the maintainer-visible output that Foundational already wired in (US4)

### Incremental Delivery

1. Setup + Foundational → shared script and both composites exist and are unit-proven
2. Add User Story 1 → validate Scenarios 1-4 on `clarify.yml` → mergeable increment (MVP: the actual #204 defect shape is fixed on the site it hit)
3. Add User Story 2 → validate Scenarios 6-8 on the same wiring → mergeable increment (over-budget reporting and ceiling sizing confidence)
4. Add User Story 3 → wire the remaining 18 sites, build Gates 22/23 → mergeable increment (100% coverage, mechanically enforced, FR-016 closes #193)
5. Add User Story 4 → audit summary legibility across all 19 sites → mergeable increment (FR-012/SC-007 confidence)
6. Polish → documentation, upstream report, lint, full quickstart sweep

### Why User Story 1 alone proves the mechanism

Because research.md R7 forces every site's wiring to be mechanically identical (same ceiling/verdict step pair, same fail-loud step, same metrics-summary passthrough — only the intended-turns literal, step ids, and presence/absence of a lifecycle-issue callout differ), proving the pattern on `clarify.yml` exercises the exact same composite code path (Phase 2) that every other site and every other capability (over-budget reporting, exhaustion, coverage enumeration) will also exercise. User Story 2 therefore needs no new implementation — only new assertions against the same wiring — and User Story 3's per-site tasks are a mechanical repetition of User Story 1's own task (T008) across the remaining ten files, with the two coverage gates as the only genuinely new logic.
