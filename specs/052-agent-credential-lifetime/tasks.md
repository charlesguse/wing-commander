---

description: "Task list for feature 052: Bot Credential Lifetime Across Long Agent Cycles"
---

# Tasks: Bot Credential Lifetime Across Long Agent Cycles

**Input**: Design documents from `/specs/052-agent-credential-lifetime/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not explicitly requested as TDD. This feature's verification mechanism is the new gate script (`verify-post-agent-credential-refresh.py`, User Story 4) and the extension of an existing gate (`verify-implement-stall-notice-unchanged.py`, User Story 2) — both are first-class implementation tasks below, per this repository's convention that `verify-*.py` scripts and `wc_shell_harness.py`-driven fixtures ARE the tests (Constitution VIII), not an optional add-on.

**Organization**: Tasks are grouped by user story (spec.md priorities: US1/US2 = P1, US3/US4 = P2). US1 and US2 both touch every one of the 8 sweep-stage workflow files but add *different* steps at *different* points (the credential refresh vs. the agent-ran signal), so they are kept as separate phases even though they share files — this mirrors spec.md's own framing of them as independent, separately-testable defects (User Story 1 vs. User Story 2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1-US4, mapping to spec.md's priorities
- Line numbers cited below are today's (`main`, pre-change) positions, taken from the design documents and from inspecting the current tree. Each edit within a phase that touches a file more than once shifts later line numbers in that same file — locate steps by their `name:`/`id:` (the same way the new gate itself locates them, per contracts/post-agent-credential-refresh-gate.md: "by name pattern, not by line number"), not by line number alone, once a prior task in the same phase has landed on that file.

## Path Conventions

CI/CD pipeline infrastructure repository — no `src`/`tests` split. Paths below are repository-root-relative (`.github/actions/`, `.github/workflows/`, `.github/scripts/`, `docs/`), per plan.md's Project Structure.

---

## Phase 1: Setup

**Purpose**: Establish the baseline facts the gate's provisional numbering and this sweep's scope depend on, before any file changes.

- [X] T001 Confirm the working tree's baseline: run `python .github/scripts/run-local-gates.py` and record that it is green before this feature's changes; confirm the highest existing gate is Gate 66 (`.github/workflows/lint-workflows.yml:3567-3586`, `verify-auto-release-e2e-gate-decisions.py`), so this feature's new gate provisionally claims **Gate 67** — subject to renumbering at merge if a parallel-landed spec claims it first, per CLAUDE.md's documented norm (research.md D6, the Gate 62-66 collision comments already in `lint-workflows.yml`). No file changes.

**Checkpoint**: Baseline recorded; gate numbering claim is on record.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one shared mechanism every User Story 1 call site depends on.

**⚠️ CRITICAL**: No User Story 1 task can be written correctly until this phase is complete.

- [X] T002 Amend `.github/actions/wing-commander-context/action.yml`: add one new internal step to `runs.steps`, immediately after the existing `id: app-token` step (today lines 62-67) and before the existing `id: resolve` step (today lines 69-81):
  ```yaml
  - name: Relay bot token to the job environment
    shell: bash
    env:
      TOKEN: ${{ steps.app-token.outputs.token }}
    run: |
      echo "WC_BOT_TOKEN=$TOKEN" >> "$GITHUB_ENV"
  ```
  This step has no `id` and adds no new composite output. Do not touch the composite's `inputs:` (lines 31-43) or `outputs:` (lines 45-57) blocks — both stay byte-for-byte unchanged, so `token`/`bot-slug`/`spec-slug`/`spec-dir` are still emitted exactly as before for the one caller (the "Checkout spec branch as wing-commander-bot" step, User Story 1) that still needs the raw step-output form (contracts/wing-commander-context-relay.md, research.md D1, FR-002, FR-025).

**Checkpoint**: `env.WC_BOT_TOKEN` is available to every job that invokes `wing-commander-context`, on every invocation (both the pre-agent mint and any post-agent refresh). User Story 1's per-stage wiring can now begin.

---

## Phase 3: User Story 1 - A cycle that outruns the credential still completes its own bookkeeping (Priority: P1) 🎯 MVP

**Goal**: Every bot-acting step after an agent step, in all 8 sweep-stage workflows, uses a credential valid at the moment it runs — regardless of how long the preceding agent step ran.

**Independent Test**: Drive an agent stage whose agent step runs past the credential lifetime, and confirm every credential-bearing step after the agent completes normally — no credentials error anywhere in the job, no step skipped as a consequence of one.

### Implementation for User Story 1

- [X] T003 [P] [US1] In `.github/workflows/intake.yml`'s `intake` job: migrate every step between the "Wing Commander context" step (`id: ctx`, today lines 431-437) and after — including the "Re-checkout default branch as wing-commander-bot" step (today lines 452-459) and every other step in the job that reads `steps.ctx.outputs.token` — to `env.WC_BOT_TOKEN` instead. Immediately after the "Create spec from issue" agent step (`id: agent`, today lines 587-593), add the two-step post-agent refresh per contracts/wing-commander-context-relay.md: (1) `if: always()` step "Re-establish Wing Commander context (post-agent)" re-invoking `wing-commander-context` with the same inputs as the original call; (2) `if: always()` step "Refresh authenticated spec-branch remote (post-agent)" running `git remote set-url origin "https://x-access-token:${WC_BOT_TOKEN}@github.com/${{ github.repository }}.git"` in the job's existing checkout directory. Every step after the agent step already reads `env.WC_BOT_TOKEN` by construction once the migration above is done (FR-001, FR-002).
- [X] T004 [P] [US1] In `.github/workflows/clarify.yml`'s `clarify` job: same migration and refresh-pair insertion as T003, keyed off the "Wing Commander context" step (`id: ctx`, today lines 397-404), the "Checkout draft spec branch as wing-commander-bot" step (today lines 436-443), and the "Fold answers into the draft spec" agent step (`id: agent`, today lines 494-500).
- [X] T005 [P] [US1] In `.github/workflows/plan.yml`'s `plan` job: same migration, keyed off the "Wing Commander context" step (`id: ctx`, today lines 466-471) and the "Checkout spec branch as wing-commander-bot" step (today lines 616-623). This job has two agent steps on mutually exclusive branches — "Generate implementation plan (direct commit)" (`id: agent-auto`, today lines 646-652) and "Generate implementation plan" (`id: agent-pr`, today lines 803-807) — add the same post-agent refresh pair immediately after **each** of them (only one runs per dispatch, but each needs its own refresh for the steps that follow it). `plan.yml` has no `stalled` job (confirmed: `grep -n stalled .github/workflows/plan.yml` matches only prose at line 531) — no stall-path change applies here (research.md D4).
- [X] T006 [P] [US1] In `.github/workflows/tasks.yml`: apply the same migration and per-agent-step refresh pair in **both** entry jobs — the `tasks` job (`id: ctx` today lines 527-532, "Checkout spec branch as wing-commander-bot" today lines 536-542, and its agent step(s) on the auto/pr dispatch branches) and the `tasks-approved` job (`id: ctx` today lines 1232-1237, "Checkout spec branch as wing-commander-bot" today lines 1240-1246, and its own agent step). Locate each job's agent step(s) by `uses: anthropics/claude-code-action@v1` within that job's line range, not by a hardcoded line number, since both jobs share this file.
- [X] T007 [US1] In `.github/workflows/implement.yml`'s `implement` job: migrate every step reading `steps.ctx.outputs.token` (the single "Wing Commander context" call, `id: ctx`, today lines 465-471, and the "Checkout spec branch as wing-commander-bot" step, today lines 516-523) to `env.WC_BOT_TOKEN`. This job runs **three** sequential agent steps sharing that one pre-minted token today — "Implement and converge (cycle)" (today lines 782-786), "Implement and converge (retry at escalation model)" (today lines 1311-1320), and "Compose progress summary (haiku)" (today lines 1860-1864) — add an independent post-agent refresh pair (per contracts/wing-commander-context-relay.md) immediately after **each** of the three, so `WC_BOT_TOKEN` always names "the most recent mint" regardless of which agent step most recently ran (research.md D1, Edge Cases "two agent steps in one job"). No step between any two of the three needs to change which variable it reads — `env.WC_BOT_TOKEN` is correct throughout by construction.
- [X] T008 [P] [US1] In `.github/workflows/finalize.yml`'s `finalize` job: same migration and single refresh pair as T004, keyed off the "Wing Commander context" step (`id: ctx`, today lines 386-392), the "Checkout spec branch as wing-commander-bot" step (today lines 443-450), and the "Summarize change and extract remaining manual work" agent step (`id: summarize`, today lines 637-643). Add the FR-008 residual-risk short-form comment (pointing at `docs/architecture.md`, per T038) at this step's existing narration of the credential arrangement.
- [X] T009 [US1] In `.github/workflows/pr-conversation.yml`: apply the migration and refresh pair independently in **both** jobs with an agent step — `classify-and-announce` (`id: ctx` today lines 567-573, agent step "Classify the PR conversation request" `id: agent` today lines 818-824; this job resolves `spec-meta.json` via the contents API rather than a "Checkout spec branch" step, so there is no checkout-token migration here) and `act` (`id: ctx` today lines 1575-1581-ish, "Checkout working tree for this leg" step reading `steps.ctx.outputs.token` today around line 1822, agent step "Act on this classification" `id: agent` today lines 1872-1876).
- [X] T010 [US1] In `.github/workflows/auto-update-spec-kit.yml`'s `e2e-stage` job (today lines 1632-2115): (1) migrate steps reading `steps.ctx.outputs.token` (from the job's own "Wing Commander context" step, `id: ctx`, today lines 1695-1700) to `env.WC_BOT_TOKEN`, and add the standard post-agent refresh pair immediately after the "Run e2e agent-driven stage" agent step (`id: decide`, today lines 1913-1917); (2) independently, relay the job's separate "Mint a scratch-repository App token" step (`id: scratch-token`, today lines 1756-1763, `uses: ./.wing-commander-pipeline/.github/actions/_shared/scoped-app-token`) into its own job-scoped `WC_SCRATCH_TOKEN` env var via an inline "Relay scratch token to the job environment" step added at the call site immediately after it — do **not** amend `_shared/scoped-app-token/action.yml` itself, since that composite is also used by `auto-release.yml` (spec 049) for an unrelated purpose and has no reason to know about `WC_SCRATCH_TOKEN`; migrate the "Push agent-produced spec.md to the scratch repository (best-effort)" step (today lines 2094-2113) to read `env.WC_SCRATCH_TOKEN`, and add a second, independent post-agent refresh pair (re-invoking `scoped-app-token` + relay, then refreshing whichever remote it authenticates) immediately after the same agent step, scoped to `WC_SCRATCH_TOKEN` (research.md D8, contracts/wing-commander-context-relay.md "auto-update-spec-kit.yml's e2e-stage job"). This job's existing `continue-on-error: true` on the push step is a pre-existing, unrelated design choice (best-effort push) and is left as-is (research.md D8's own rationale) — the fix here is that the credential the push uses actually works, not a change to whether its failure is tolerated.
- [X] T011 [US1] Ran quickstart.md §4's shell-level verification using `wc_shell_harness.py`'s `run_step` pattern, shipped as `.github/scripts/verify-credential-relay-shell.py` (Gate 69) rather than a one-off: (1) extracts the relay step from T002 and runs it twice with different `TOKEN` values inside the same simulated `$GITHUB_ENV` file; asserts the file's last `WC_BOT_TOKEN=` line carries the *second* value (research.md D1's "later `$GITHUB_ENV` writes win" dependency). (2) Extracts `clarify.yml`'s "Refresh authenticated spec-branch remote (post-agent)" step (byte-identical across all 8 stages per Gate 68) and runs it inside a real git repository whose `origin` remote carries BOTH a stale URL-embedded credential AND a stale `http.https://github.com/.extraheader` config entry (mirroring what `actions/checkout@v5` actually leaves behind), with an untracked file present; asserts the extraheader is gone (not merely shadowed), the remote URL carries the fresh token, and the untracked file is untouched. Running this test is what SURFACED the T046 finding below — the original design (URL refresh only, no extraheader clearing) failed check (2) outright. Depends on: T002-T010.

**Checkpoint**: All 8 sweep stages complete every post-agent bot-acting step successfully regardless of agent-step duration (FR-001 through FR-009, User Story 1's own Independent Test). This is the MVP — the defect's root cause is fixed and independently demonstrable.

---

## Phase 4: User Story 2 - A stall notice never claims a stage that ran did not start (Priority: P1)

**Goal**: Every agent stage publishes a durable, prose-free record of whether its agent step ran and how it concluded; the six stages with an existing stall path read it and report accurately instead of "the stage failed before it could run its own steps."

**Independent Test**: Force a failure in a step after the agent has run to completion, and confirm the stall notice states that the agent ran and names the post-agent step that failed, rather than reporting that the stage never started.

### Publication (all 8 stages)

- [X] T012 [P] [US2] In `.github/workflows/intake.yml`'s `intake` job: immediately after the "Create spec from issue" agent step (`id: agent`) and **before** the credential-refresh pair added in T003, add an `if: always()` step `id: agent-ran` writing `ran=true` and `conclusion=${{ steps.agent.conclusion }}` to `$GITHUB_OUTPUT` (contracts/agent-ran-signal.md); add `agent-ran`/`agent-conclusion` to the `intake` job's `outputs:` block, mapped from `steps.agent-ran.outputs.ran`/`.conclusion`. No prose field (FR-014).
- [X] T013 [P] [US2] Same as T012 in `.github/workflows/clarify.yml`'s `clarify` job, keyed off the "Fold answers into the draft spec" agent step (`id: agent`) and the `clarify` job's `outputs:` block.
- [X] T014 [P] [US2] Same as T012 in `.github/workflows/plan.yml`'s `plan` job: add one `agent-ran`-shaped step after **each** of `agent-auto` and `agent-pr` (distinct step ids, e.g. `agent-ran-auto`/`agent-ran-pr`, per contracts/agent-ran-signal.md's "share neither id nor step name" convention), both writing to the same `$GITHUB_OUTPUT` keys the job's `outputs:` block maps from. `plan.yml` publishes with no reader (research.md D4) — no stall-path task follows for this file.
- [X] T015 [P] [US2] Same as T012 in `.github/workflows/tasks.yml`, in **both** the `tasks` job (after each of its auto/pr agent steps, same distinct-id convention as T014) and the `tasks-approved` job (after its own agent step); add `agent-ran`/`agent-conclusion` to both jobs' `outputs:` blocks independently.
- [X] T016 [US2] In `.github/workflows/implement.yml`'s `implement` job: add three `agent-ran`-shaped steps (distinct ids `agent-ran-cycle`/`agent-ran-retry`/`agent-ran-progress`), one immediately after each of "Implement and converge (cycle)", "Implement and converge (retry at escalation model)", and "Compose progress summary (haiku)" — all three writing to the same `$GITHUB_OUTPUT` keys, so the job's `agent-ran`/`agent-conclusion` outputs always describe the most recently reached agent step (research.md D3). Depends on: T007 (shares the same post-agent insertion points).
- [X] T017 [P] [US2] Same as T012 in `.github/workflows/finalize.yml`'s `finalize` job, keyed off the "Summarize change and extract remaining manual work" agent step (`id: summarize`).
- [X] T018 [US2] Same as T012 in `.github/workflows/pr-conversation.yml`, independently in both `classify-and-announce` (after "Classify the PR conversation request") and `act` (after "Act on this classification"), each job gaining its own `agent-ran`/`agent-conclusion` outputs.
- [X] T019 [P] [US2] Same as T012 in `.github/workflows/auto-update-spec-kit.yml`'s `e2e-stage` job, keyed off the "Run e2e agent-driven stage" agent step (`id: decide`). Publishes with no reader (research.md D4, same status as T014's plan.yml).

### Consumption (the six stages with an existing survivor job)

- [X] T020 [US2] In `.github/workflows/implement.yml`'s `stalled` job, inside the existing "Determine which dependency did not start" step (`id: reason`, today line 2707): add a new branch, evaluated ahead of the existing if/elif/else fallback, for `needs.implement.outputs.agent-ran == 'true'` — set `reason` to "the agent step ran (concluded: `<agent-conclusion>`) and a step after it did not complete" instead of falling through to today's "the implement stage failed before it could run its own steps" wording (contracts/agent-ran-signal.md, FR-011). Pass a resume-oriented `restart-command` sentence to `wing-commander-chain-stop-notice` in this branch instead of the existing restart-from-zero phrasing (FR-015); when `agent-ran` is unset, today's diagnosis and restart wording are unchanged (FR-012). Depends on: T016.
- [X] T021 [US2] Same branch-insertion pattern as T020 in `.github/workflows/finalize.yml`'s `stalled` job ("Determine which dependency did not start", today line 1345), reading `needs.finalize.outputs.agent-ran`/`.agent-conclusion`. Depends on: T017.
- [X] T022 [US2] Same as T020 in `.github/workflows/clarify.yml`'s `stalled` job (today line 1061), reading `needs.clarify.outputs.agent-ran`/`.agent-conclusion`. Depends on: T013.
- [X] T023 [US2] Same as T020 in `.github/workflows/intake.yml`'s `stalled` job (today line 1318), reading `needs.intake.outputs.agent-ran`/`.agent-conclusion`. Depends on: T012.
- [X] T024 [US2] Same as T020 in `.github/workflows/pr-conversation.yml`'s single `stalled` job (today line 3000, covering `classify-and-announce`), reading `needs.classify-and-announce.outputs.agent-ran`/`.agent-conclusion`. The `act` job's own agent-ran signal (T018) has no survivor job to consume it (no `stalled` job wraps `act`) — publish-only, same status as plan.yml (research.md D4). Depends on: T018.
- [X] T025 [US2] Same as T020 in **both** of `.github/workflows/tasks.yml`'s survivor jobs — `stalled` (today line 1418, reading `needs.tasks.outputs.agent-ran`/`.agent-conclusion`) and `stalled-approved` (today line 1545, reading `needs.tasks-approved.outputs.agent-ran`/`.agent-conclusion`). Depends on: T015.
- [X] T026 [US2] Extend `.github/scripts/verify-implement-stall-notice-unchanged.py`'s existing pinned-step fixture family with a new case for the `agent-ran == 'true'` branch (T020): model the "Determine which dependency did not start" step with `needs.implement.outputs.agent-ran` set to `'true'` and `.agent-conclusion` set to `failure`; assert the rendered reason names the post-agent step / states the agent ran and does **not** contain the literal phrase "the implement stage failed before it could run its own steps". Add a companion case with `agent-ran` unset asserting the literal phrase is byte-for-byte unchanged from today (regression pin — this feature's stall-wording change must land only on the new branch, never on the existing one). Depends on: T020.

**Checkpoint**: A maintainer reading any of the six existing survivor jobs' notices can tell whether the agent ran, even when the failure that triggered the notice has nothing to do with credentials (FR-010 through FR-015, User Story 2's own Independent Test).

---

## Phase 5: User Story 3 - An observability callout can never strand the pipeline below it (Priority: P2)

**Goal**: Every step between an agent step and its job's deterministic read-back that is documented in place as observability rather than failure is tolerated, so its own failure cannot skip the read-back or anything below it.

**Independent Test**: Make an observability callout between an agent step and its read-back fail, and confirm the read-back and every step below it still run and the job's reported outcome is decided by the read-back.

### Implementation for User Story 3

- [X] T027 [P] [US3] Add `continue-on-error: true` to `.github/workflows/clarify.yml`'s canonical "Report over-budget agent run" step (today lines 928-945, the `# (canonical copy; do not condense)` block). Do not touch the `#` comment prose itself here — its correction to describe enforcement is FR-024 (T035).
- [X] T028 [P] [US3] Add `continue-on-error: true` to `.github/workflows/intake.yml`'s "Report over-budget agent run" step (today line 1169, pointer copy of clarify.yml's canonical block).
- [X] T029 [P] [US3] Add `continue-on-error: true` to `.github/workflows/finalize.yml`'s "Report over-budget agent run" step (today line 785).
- [X] T030 [P] [US3] Add `continue-on-error: true` to both of `.github/workflows/tasks.yml`'s "Report over-budget agent run" steps — `(auto)` (today line 1096) and `(pr)` (today line 1111).
- [X] T031 [P] [US3] Add `continue-on-error: true` to both of `.github/workflows/plan.yml`'s "Report over-budget agent run" steps — `(auto)` (today line 1125) and `(pr)` (today line 1140).
- [X] T032 [P] [US3] Add `continue-on-error: true` to both of `.github/workflows/pr-conversation.yml`'s "Report over-budget agent run" steps — the `classify-and-announce` job's copy (today line 1042) and the `act` job's copy (today line 2141).
- [X] T033 [US3] Add `continue-on-error: true` to all three of `.github/workflows/implement.yml`'s "Report over-budget agent run" steps — `(cycle)` (today line 1010), `(retry)` (today line 1525), `(progress comment)` (today line 2047).
- [X] T034 [US3] Verify the population is closed: `git grep -n "Report over-budget agent run"` across `.github/workflows/` returns exactly the 12 sites touched by T027-T033, plus `rebase.yml:817` and `cleanup.yml:781` (confirmed out of scope — neither is one of FR-007's eight named stages, research.md D5) which are deliberately left untouched. Separately confirm the 22-site "Fail loud on non-healthy agent verdict" family (a different, already-enforced rationale — e.g. `implement.yml:943,1461,1975`, `clarify.yml:716`, `plan.yml:772,983`, `tasks.yml:755,892`, and others) is unchanged by this feature (research.md D5). This is FR-019's audit record, already captured in data-model.md's 12-row table; this task confirms the shipped tree matches it. Depends on: T027-T033.

**Checkpoint**: A failed observability callout between an agent step and its read-back can no longer strand the pipeline below it, in any of the 8 sweep stages that have one (FR-016 through FR-019).

---

## Phase 6: User Story 4 - A newly added post-agent step cannot silently reintroduce the exposure (Priority: P2)

**Goal**: A deterministic gate fails when a bot-acting step after an agent step does not follow the shipped remedy, naming the workflow, job, and step; the in-place documentation describes the mechanism that actually ships.

**Independent Test**: Add, in a fixture, a credential-bearing step after an agent step that does not follow the shipped remedy, and confirm the check fails and names the step; revert it and confirm the check passes.

### Documentation corrections (FR-024)

- [X] T035 [US4] In `.github/workflows/clarify.yml`, immediately above its "Wing Commander context" step, added a new `# (canonical copy; do not condense)` comment block describing the credential re-establishment mechanism (research.md D1/D2): the `WC_BOT_TOKEN` env-var relay, the post-agent re-mint, and the `git remote set-url` refresh. In the same file, corrected the existing "Report over-budget agent run" canonical comment to state that the tolerance is now enforced via `continue-on-error: true` (T027) rather than merely documented.
- [X] T036 [P] [US4] Added a one-line pointer comment (`-- see clarify.yml.`, in the form Gate 47 already parses) immediately above the "Wing Commander context" step in the other 7 sweep-stage workflows: `intake.yml`, `plan.yml`, `tasks.yml` (both entry jobs' ctx steps), `implement.yml`, `finalize.yml`, `pr-conversation.yml` (both jobs' ctx steps), `auto-update-spec-kit.yml`'s `e2e-stage` job. Depends on: T035 (the canonical block it points at must exist first, though Gate 47 checks the pointer text, not ordering).
- [X] T037 [US4] Rewrote `docs/architecture.md`'s "Identity & chaining: the wing-commander-bot App" section to state: the credential's one-hour lifetime, the `WC_BOT_TOKEN` env-var relay mechanism (T002), the `git remote set-url` remote refresh (T003-T010), and — per FR-008 — the residual risk that the agent's own push credential is not covered by this feature, with a forward reference to the follow-up issue (T039, filed as #402).
- [X] T038 [US4] In `.github/workflows/implement.yml`'s `implement` job, at the read-back step immediately after the cycle's post-agent refresh pair ("Read back cycle outcome"), added the FR-008 residual-risk sentence in short form, pointing at `docs/architecture.md`'s "Identity & chaining" section (T037) for the full statement (research.md D7 — one canonical statement plus one pointer, not the paragraph written twice). No pre-existing narration comment existed at this step to append to (contrary to research.md D7's premise, checked against origin/main), so the narration itself was authored here, matching the same short-form/pointer convention.
- [X] T039 [US4] Follow-up GitHub issue for FR-008 filed by the maintainer as [#402](https://github.com/charlesguse/wing-commander/issues/402) (the agent's own push credential remains exposed to the same one-hour lifetime; refreshing an authenticated remote underneath a running agent is a different mechanism from this feature's remedy), per the maintainer's restart-cycle note on #345 that the bot cannot create issues itself — checked off by reference, citing `docs/architecture.md`'s "Identity & chaining" section (T037) as the recorded residual risk (research.md D9).

### The durability gate

- [X] T040 [US4] Implement `.github/scripts/verify-post-agent-credential-refresh.py` (Gate 68 — renumbered from the provisional Gate 67 claimed at T001; #401 landed `verify-auto-release-credential-step.py` as Gate 67 first on the same base, per the maintainer's restart-cycle note on #345) per contracts/post-agent-credential-refresh-gate.md: static `yaml.safe_load` inspection over the 8 named workflow files' jobs containing at least one agent step (identified structurally by `uses:` resolving to `anthropics/claude-code-action@*`, never a hardcoded step-id list). Implements checks 1-4: (1) no step positioned after the first agent step in a job references `steps.<any-id>.outputs.*token*` directly (must resolve through `env.WC_BOT_TOKEN`/`env.WC_SCRATCH_TOKEN` instead, with the relay step itself exempted since its entire job is to read the raw mint) — steps before the first agent step are exempt; (2) every agent step in a job after the first is preceded, since the previous agent step, by a `wing-commander-context` (or, for `auto-update-spec-kit.yml`'s `e2e-stage`, the scratch-token mint) invocation; (3) every step named exactly "Report over-budget agent run" carries `continue-on-error: true`; (4) the gate exits non-zero, naming the unreachable file/job, if any of the 8 named files is missing, an expected job cannot be located, or zero agent steps are found across the named subject — never a silent pass over an empty result set. Depends on: T003-T010, T027-T033 (the gate's first successful run needs the shipped tree to check against).
- [X] T041 [US4] Add `self_test()`/`--self-test` to `.github/scripts/verify-post-agent-credential-refresh.py`, following `verify-plan-tasks-cost-line.py`'s `MUTATIONS`-over-the-live-tree convention (`copy.deepcopy` the real parsed tree per mutation, never a second synthetic YAML fixture file): assert the clean tree passes, then assert each of these five mutations fails with a message naming the workflow/job/step — (a) rewrite one post-agent step's credential reference back to `steps.ctx.outputs.token`; (b) delete the refresh step between `implement.yml`'s `retry` and `progress` agent steps; (c) strip `continue-on-error: true` from `clarify.yml`'s canonical "Report over-budget agent run" step; (d) point the subject list at a 9th, nonexistent workflow file; (e) point the subject list at zero workflow files. Depends on: T040.
- [X] T042 [US4] Wire Gate 68 into `.github/workflows/lint-workflows.yml`'s existing PR-time job, following Gate 66/67's two-step wiring pattern: a `"Gate 68 — <one-line summary>"` step running `python3 .github/scripts/verify-post-agent-credential-refresh.py`, and a `"Gate 68 self-test — <summary>"` step running the same script with `--self-test`, both `if: "!cancelled()"`. Confirmed `.github/scripts/wc_gate_registry.py`'s filename convention auto-discovers the new script (no registry file to hand-edit) and that Gate 10 (`verify-gate-wiring.py`) passes, confirming the wiring is complete in both directions (`python .github/scripts/run-local-gates.py`: 107/107 passed). Confirmed `lint-workflows.yml`'s existing `on.pull_request.paths` (`.github/workflows/**`, `.github/actions/**`) already covers this gate's subject — no new path entry required (FR-022). Depends on: T041.
- [X] T043 [US4] Run the `review-step-gating` skill over this feature's full diff (CLAUDE.md: any change touching `if:`, `continue-on-error:`, or a failing step gets a pass before merging — this feature touches both at more than a dozen call sites) and fix any findings; run the `container-shell-safety` skill as well per CLAUDE.md's blanket instruction for workflow changes of this size, noting that this feature adds no `container:` block so it is expected to surface no findings. Depends on: T002-T042.

**Checkpoint**: Gate 68 is reachable through the registry, runs identically locally and in CI, fails loudly on every care point FR-020/FR-021 name, and every failure branch is fixture-covered (FR-020 through FR-024, User Story 4's own Independent Test).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T044 Ran `python .github/scripts/run-local-gates.py` from the repository root repeatedly through this cycle; every gate passes, including Gate 68 and Gate 69 (renumbered from the provisional Gate 67, per T040) and their self-tests (quickstart.md §1-2, SC-006). Final confirmed state: 108/108 passed. Depends on: T001-T043.
- [X] T045 Confirmed, by construction, FR-005 (no behavioural change for a job whose agent step finishes well inside the credential lifetime — the refresh and signal steps run unconditionally on outcome, never on elapsed time; the `steps.<id>.outcome != 'skipped'` guard added during T046's step-gating fix only distinguishes "the agent step ran at all" from "the lifecycle gate was closed and it never ran," which is not a timing condition) and FR-009/SC-009 (no live credential outlives the job that established it — every refresh reuses the same App-installation-token mint mechanism with the same implicit expiry as today's single mint, so nothing new is left for teardown to revoke). No code change was needed for this confirmation itself. Depends on: T003-T010.
- [X] T046 Ran this PR's code review (CLAUDE.md: "every fix PR gets a code review before merge") and fixed its findings in this same PR: (1) **load-bearing correctness defect** — the post-agent remote refresh (D2) only rewrote the remote URL, never clearing the stale `http.https://github.com/.extraheader` entry `actions/checkout@v5` (default `persist-credentials: true`) actually authenticates with, so the refresh was a no-op that would have reproduced this feature's own target defect; fixed at all 11 call sites, documented in research.md D2's correction, and pinned by a new behavioral gate (`verify-credential-relay-shell.py`, Gate 69) that fails on the reverted form (confirmed by temporarily reverting the fix and observing Gate 69 fail, then restoring it and observing 108/108 pass again). (2) **minor efficiency waste** — the post-agent refresh/relay steps re-minted a token even when the agent step was skipped (closed lifecycle gate); added a `steps.<id>.outcome != 'skipped'` guard alongside the existing `if: always()` at all 26 call sites. Separately, `review-step-gating` (also required by CLAUDE.md for this diff's size) found none of the 26 post-agent refresh/relay steps carried `continue-on-error: true`, so their own transient failure could strand each stage's deterministic read-back below — fixed at all 26 sites. `container-shell-safety` surfaced no findings (no `container:` block added; both new `run:` step shapes already declare `shell: bash`). No finding fell outside this feature's scope.
- [ ] T047 Record, per CLAUDE.md's "a fix to behaviour that only runs in Actions is proven after merge by re-driving one run" rule: after merge, dispatch one stage (e.g. `clarify`) forced past the credential lifetime per quickstart.md §6 (a scratch adopter repository, specs/053's on-demand e2e provisioning), and post the run URL as this feature's post-merge proof on the lifecycle issue or the PR. This is a post-merge action, not a pre-merge blocker — left unchecked pending merge, which this implementation run does not perform.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS User Story 1 (T003-T011 all read `env.WC_BOT_TOKEN`, which T002 creates).
- **User Story 1 (Phase 3)**: Depends on Foundational (T002). The 8 stages' tasks (T003-T010) are file-disjoint except T007/T016 (implement.yml, shared with US2) and are otherwise independent of each other. No dependency on User Story 2, 3, or 4.
- **User Story 2 (Phase 4)**: Independent of User Story 1's mechanism (different steps — the agent-ran signal step is deliberately separate from the credential refresh, research.md D3, so a mint failure can never masquerade as "the agent never ran"). T012-T019 (publication) can proceed in parallel with, or even before, User Story 1. T020-T025 (consumption) each depend on their own stage's publication task (T012→T023, T013→T022, T014→none, T015→T025, T016→T020, T017→T021, T018→T024, T019→none). T026 depends on T020.
- **User Story 3 (Phase 5)**: Independent of User Story 1 and 2's mechanisms (a different set of steps — the existing "Report over-budget agent run" callouts). T027-T033 are fully file-disjoint and parallelizable. T034 depends on all seven.
- **User Story 4 (Phase 6)**: The gate (T040-T042) depends on User Story 1 (T003-T010) and User Story 3 (T027-T033) having landed, since it checks the shipped structure those stories produce. The documentation tasks (T035-T039) have no code dependency and could run earlier, but are sequenced last here to match spec.md's priority order and because T035/T038 reference mechanisms T002-T010 introduce.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Parallel Opportunities

- T003-T006, T008-T010 (User Story 1, 7 of the 8 stages) are file-disjoint and fully parallelizable once T002 lands; T007 (implement.yml) is its own task due to the three-agent-step complexity.
- T012-T015, T017, T019 (User Story 2 publication, 6 of the 8 stages) are file-disjoint and parallelizable; T016 (implement.yml) and T018 (pr-conversation.yml, two jobs) are their own tasks.
- T020-T025 (User Story 2 consumption) are file-disjoint and parallelizable once their respective publication task lands.
- T027-T032 (User Story 3, 6 of the 7 files with a single or double site) are file-disjoint and parallelizable; T033 (implement.yml, three sites) is its own task.
- T036 (pointer comments across 7 files) is independent of T037-T039 (different files).
- User Story 2 and User Story 3 have no dependency on each other and can be worked in parallel by different contributors once User Story 1's per-stage tasks that they share a file with are sequenced (same-file edits within one phase are sequential; edits in different phases to the same file should land as separate commits/passes to keep diffs reviewable).

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational — the composite amendment, T002).
2. Complete Phase 3 (User Story 1) — all 8 stages.
3. **STOP and VALIDATE**: quickstart.md §4 (T011) — the relay and remote-refresh shell logic behave as designed; manually confirm via quickstart.md §6 that a forced long-running cycle produces zero `HTTP 401` errors. This is the defect's root cause, fixed and independently demonstrable — spec.md's own framing of User Story 1 as "the defect's root."

### Incremental Delivery

1. Setup + Foundational → the shared relay mechanism exists.
2. User Story 1 → every post-agent step in all 8 stages holds a valid credential (MVP).
3. User Story 2 → a post-agent failure is reported as what it is, not as "never started."
4. User Story 3 → an observability callout's own failure can no longer strand the pipeline below it.
5. User Story 4 → the remedy is durable: a regression is caught by CI, not rediscovered the next time a cycle runs long.
6. Polish → full gate suite green, code review passed, post-merge proof recorded.

### Parallel Team Strategy

Per CLAUDE.md's own cap (concurrent local agents kept to two during this pipeline's implement stage):

1. Complete Setup + Foundational together (small, single-file phase).
2. Once Foundational is done: Contributor A takes User Story 1 (the MVP); Contributor B takes User Story 2's publication tasks (T012-T019, no dependency on User Story 1's mechanism) in parallel, then joins A for User Story 2's consumption tasks once each stage's own publication task lands.
3. Once User Story 1 and User Story 3 have both landed, either contributor takes User Story 4's gate (it needs both as its checked subject).
4. Phase 7 runs once all four stories are complete.

---

Lifecycle issue: #345.

## Maintainer Feedback

Code review of PR #407 at head bb064e9 (charlesguse) found the shipped remedy does not fully satisfy spec 052's requirements. Must-fix items block merge; should-fix items should be addressed in the same PR per CLAUDE.md's rule that every fix PR gets its review findings fixed in the same PR.

### Must fix

- [X] Record `.outcome` (not `.conclusion`) at every "Record agent-ran signal" step (15 sites: `clarify.yml:629`, `intake.yml:732`, `finalize.yml:708`, `implement.yml:943/1505/1990`, `plan.yml:764/940`, `tasks.yml:749/918`, `pr-conversation.yml:943/2006`, `auto-update-spec-kit.yml:2027`) — a `continue-on-error: true` step reports `conclusion=success` even on failure, so a failed agent is currently signaled as having run to completion. Fix `verify-implement-stall-notice-unchanged.py`'s self-test to only feed values production can emit. (FR-010, FR-011) — done via the new `wing-commander-agent-ran-signal` composite, which takes `steps.<id>.outcome` from every call site; `verify-implement-stall-notice-unchanged.py`'s self-test now feeds `failure` as a genuinely producible value and also exercises the new named-step/credential branches.
- [X] Update `.github/actions/wing-commander-chain-stop-notice/action.yml:152-159` to drop the "the stage did not start" / "no work was lost" wording when `agent-ran=true`, per `contracts/agent-ran-signal.md:59-66` and `data-model.md:57`; also stop the spec-meta commit message from saying "did not start" when the agent ran. (FR-011, FR-015) — done: new `agent-ran`/`agent-conclusion` composite inputs (default `false`/empty, so a caller that predates them keeps today's wording), threaded from all 6 consuming stall jobs; `verify-chain-stop-notice-body.py` gained a dedicated scenario and mutation.
- [X] Name the failed post-agent step in the stall reason, currently the generic "a step after it did not complete" in `clarify.yml:1126`, `finalize.yml:1384`, `implement.yml:2832`, `intake.yml:1357`, `pr-conversation.yml:3061`, `tasks.yml:1484`. (FR-011, SC-003) — done via a new per-job "Determine failed post-agent step" step (the job's last step, reading `toJSON(steps)`) publishing `failed-post-agent-step`, read by the stall-reason step ahead of the generic fallback.
- [X] Emit a distinct, named outcome from each re-establish step when the mint fails, and have the stall path and the next credential-bearing step report it naming the credential as cause and the step as site, instead of surfacing a bare 401 attributed to the wrong step. (FR-004) — done via the new `wing-commander-post-agent-credential-status` composite: fails loud (no `continue-on-error`) naming the credential as cause, and publishes `credential-refresh-ok`, read by the stall-reason step ahead of the generic agent-ran branch. Deferred to each job's last steps (review-step-gating self-review) so its hard exit cannot strand the business logic between it and the agent step.
- [X] Move the byte-identical "Refresh authenticated spec-branch remote" `run:` block (11 sites across 7 workflows) and the agent-ran-signal block (15 sites) into composite action(s) under `.github/actions/` (or `_shared/`), reducing each call site to a call; extend Gate 68 to assert the call exists at every site, since `verify-credential-relay-shell.py:46` currently claims byte-identity is enforced when it is not. (CLAUDE.md single-home rule) — done: `wing-commander-refresh-remote` and `wing-commander-agent-ran-signal` composites; Gate 68 check 5 asserts every "Record agent-ran signal"/"Refresh authenticated spec-branch remote (post-agent...)" step calls its composite; Gate 69 now drives the composite's own copy instead of a workflow-embedded `run:` block.
- [X] Close three Gate 68 self-test holes: (a) require re-establishment after the *last* agent step in a job, not only between consecutive ones — currently misses clarify's single-agent case and implement's `progress` agent; (b) match all step-name variants (`(cycle)`, `(retry)`, `(progress comment)`, `(auto)`, `(pr)`), not only the exact string `"Report over-budget agent run"`; (c) fail when a job that had an agent step stops having one, instead of silently skipping all of that job's checks. (FR-020, FR-021) — done: check 2 now uses a sentinel boundary at `len(steps)` so the last agent step is covered; `OVER_BUDGET_NAME_RE` matches every suffix variant; a per-job "must contain an agent step" check fires for every subject job outside the new `AGENTLESS_JOBS` (`tasks-approved`, which has none by design). Four new self-test mutations cover all three holes plus the single-home check.
- [X] Guard `auto-update-spec-kit.yml:2053-2060`'s `WC_SCRATCH_TOKEN` assignment with `steps.scratch-token-post-agent.outputs.ok == 'true'` so a failed mint cannot blank a still-valid token ahead of the step-21 push. (FR-005) — done, using `steps.scratch-token-post-agent.outcome == 'success'` (the composite's own step outcome already carries this; no new `ok` output needed).

### Should fix

- [ ] Add checked-in fixtures for FR-023: Gate 68's "job not found" branch and Gate 69 currently ship with no self-test/mutation coverage (the stall-notice sibling only asserts `"ran" in reason`). — partially done: Gate 68 gained a "job not found in an existing file" self-test mutation. Gate 69 still has no `--self-test` entry point; deferred (would need `lint-workflows.yml` wiring, out of proportion for this pass).
- [X] Harden the Gate 68/69 token-check beyond a single regex — `steps['ctx'].outputs['token']`, `fromJSON(steps.ctx.outputs.json).token`, and any `${{ env.X }}` spelling currently pass, and the relay exemption is by step name only. — `TOKEN_REF_RE` now also matches bracket notation and `fromJSON(...).token`, with a mutation proving it. The relay-step exemption remains name-based (an intentional, documented heuristic); Gate 69 has no token-check regex of its own (it drives shipped shell text directly).
- [X] Change `always()` to `!cancelled() && <agent>.outcome != 'skipped'` (or document in a comment why not) at the 13 sites of the three new steps — a cancelled run currently still performs a network mint and a remote rewrite inside the cancel window. — done at every new step's call site across all 8 workflows.
- [X] Record FR-013's cancellation gap explicitly in the spec's accepted-gap statement — every `stalled` job is `!cancelled()`, so cancellation after the agent ran currently posts no notice, leaving FR-013 apparently met when it isn't. — done, new Assumptions bullet in spec.md.
- [X] Record, per FR-005/SC-005, the reason `evaluate-path` and `comment-reply` in `auto-update-spec-kit.yml` are left reading `steps.ctx.outputs.token` after their agent steps (outside FR-007's eight stages, bounded by a 10-minute agent timeout, but currently undocumented). — done, in-place comments at both jobs' agent steps.
- [ ] Derive the gate's scanned job list from the workflow files instead of hard-coding it, so a new agent job added to the eight covered files, or to `rebase.yml`/`cleanup.yml`, is not silently left unscanned. — deferred: auto-discovering agent-bearing jobs risks pulling `rebase.yml`/`cleanup.yml` into scope by accident (both deliberately out of FR-007, research.md D5); the new per-job "must contain an agent step" check (must-fix item 6) covers the narrower, safer regression this was really guarding against (a covered job silently losing its agent step).
