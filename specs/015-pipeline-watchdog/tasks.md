---

description: "Task list for Pipeline Watchdog — Run Validation & Triage"
---

# Tasks: Pipeline Watchdog — Run Validation & Triage

**Input**: Design documents from `/specs/015-pipeline-watchdog/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/watchdog-workflow.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for any pipeline stage in this repository (plan.md's Testing section). Validation is manual, via `quickstart.md`'s fourteen scenarios, folded into each user-story phase's checkpoint and the Polish phase below.

**Organization**: This feature's primary artifacts are two new workflow files, `.github/workflows/watchdog.yml` (the reusable four-job stage: `collect` → `diagnose` → `triage` → `act`) and its wrapper `.github/workflows/wing-commander-8-watchdog.yml`, plus one new consuming-repo-owned config file, `.specify/memory/watchdog-guardrails.json`. Because almost every task edits `watchdog.yml`, `[P]` is used sparingly — only for tasks that touch genuinely different files (the guardrails config, docs, and the stage-interfaces contract).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split (per plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the guardrail config and the two new workflow files as empty, correctly-wired skeletons — the scaffold every story's logic attaches to.

- [X] T001 [P] Create `.specify/memory/watchdog-guardrails.json` with the FR-011/FR-017 v1 seed allowlist from `data-model.md`/`research.md`: `maxDiffLines: 5` and `changeClasses` entries `allowlist-grant` (`pathGlobs: [".github/workflows/**", ".github/actions/**"]`, `maxDiffLines: 3`), `path-or-typo-correction` (`pathGlobs: [".github/workflows/**", ".github/actions/**", "docs/**"]`, `maxDiffLines: 3`), `syntax-fix` (`pathGlobs: [".github/workflows/**", ".github/actions/**"]`, `maxDiffLines: 5`).
- [X] T002 Create `.github/workflows/watchdog.yml` as a `workflow_call`-only reusable stage skeleton, matching `cleanup.yml`/`rebase.yml`'s shape: typed inputs `run-id` (required) and `run-name` (required), plus `model`/`max-turns` inputs per agent step following the tiering convention every other stage uses; top-level `permissions:` (`contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`); `concurrency: { group: wing-commander-watchdog-${{ inputs.run-id }}, cancel-in-progress: false }`; four empty job skeletons in dependency order — `collect`, `diagnose` (`needs: collect`), `triage` (`needs: diagnose`), `act` (`needs: triage`) — each `runs-on: ubuntu-latest`.
- [X] T003 Create `.github/workflows/wing-commander-8-watchdog.yml` as the thin wrapper: `on.workflow_run.workflows` listing all nine stage display names verbatim from `contracts/watchdog-workflow.md` (`"1 - Intake"`, `"1b - Clarify"`, `"3 - Plan"`, `"4 - Tasks"`, `"5 - Implement"`, `"6 - Finalize"`, `"7 - Cleanup"`, `"Rebase"`, `"8 - Watchdog"` — including itself, for self-inspection) with `types: [completed]`; `on.workflow_dispatch.inputs.run-id` (required, description "The run ID to (re-)inspect"); one job resolving `run-id`/`run-name` (event path: `github.event.workflow_run.id`/`.name`; dispatch path: `inputs.run-id` plus `gh run view $run-id --json name --jq .name` to resolve the name) and calling `./.github/workflows/watchdog.yml` (`uses:` local path, matching every other wrapper's local-path-calls-published-stage convention) with those two inputs.

**Checkpoint**: Both workflow files parse and are wired end-to-end with empty job bodies; the guardrail config exists — ready for Foundational steps.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Give the `collect` job the common boilerplate and identity resolution every collector needs, and wire the job-to-job conditional chain the contract requires.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 In the `collect` job of `.github/workflows/watchdog.yml`, add the bootstrap opener: preflight (`./.github/actions/wing-commander-preflight` composite, same fail-fast as every other stage), `actions/checkout@v4` (`persist-credentials: false`), and `./.github/actions/wing-commander-context` (`id: ctx`, App-token auth) — the same self-checkout dance every other stage performs.
- [X] T005 In the `collect` job, add a "Resolve inspected run's spec slug" step: derive `slug` from the inspected run's `head_branch` by stripping known prefixes (`spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/*-iterN`); on a `main`-based run (e.g. cleanup) where no prefix matches, treat resolution as best-effort and set an output recording "no lifecycle issue destination" rather than failing the job — a run the watchdog can't tie to a spec is still inspected and reported against its own run URL (contract's `collect` job step 2).
- [X] T006 Wire the job-to-job conditional chain in `.github/workflows/watchdog.yml` per `contracts/watchdog-workflow.md`: `collect` emits an `evidence-available` job output (defaulted `true`, flipped `false` only per T012's failure mode); `diagnose` is `if: needs.collect.outputs.evidence-available != 'false'`; `triage` and `act` each run as a `strategy.matrix` fanning out one entry per Finding in `diagnose`'s structured output, gated `if: needs.diagnose.outputs.outcome != 'passed-inspection' && needs.collect.outputs.evidence-available != 'false'`.

**Checkpoint**: `collect` can authenticate, resolve run identity, and the four-job chain's skip/fan-out conditions are wired — user story work can begin.

---

## Phase 3: User Story 1 - Detect a run's problems and report them (Priority: P1) 🎯 MVP

**Goal**: The watchdog inspects a completed run via five deterministic collectors, synthesizes findings with a haiku-tier diagnose step, and reports every outcome (finding, "passed inspection," or "could not inspect") to the run's lifecycle issue — with zero repository writes.

**Independent Test**: Point the watchdog at a completed run exhibiting a known problem pattern (repeated auto-denied tool calls, or an interrupted implement run with zero commits) and confirm it produces a finding citing the specific evidence and posts it to the lifecycle issue, without modifying any repository file — `quickstart.md` Scenarios 1–4.

### Implementation for User Story 1

- [X] T007 [US1] In the `collect` job of `.github/workflows/watchdog.yml`, implement the `execution-output` collector (FR-003a, FR-006, research.md's collector table): `gh run download <run-id> -n 'claude-execution-output-*'`; `jq` over the array for tool-invocation/denial records (not just the terminal `"result"` record `wing-commander-metrics-summary` already reads), counting denials grouped by tool name; append `{"source":"execution-output","class-hint":"denied-tool","facts":{tool,denials,turns}}` entries to the running signals array for any tool with repeated denials; treat "no such artifact" as a successful empty contribution, never a step failure.
- [X] T008 [US1] In the `collect` job, implement the `branch-drift` collector (FR-003b, FR-006): `git fetch origin` the inspected run's branch, compare `before-sha` (the run's triggering commit) against `origin/<branch>` via `git log <before-sha>..origin/<branch>` commit count; append `{"source":"branch-drift","class-hint":"lost-progress","facts":{branch,before-sha,after-sha,commits}}` when the count is zero after a run that should have pushed. Fold in the coexistence check (research.md's signal-suppression decision, FR-024): if `spec-meta.json.stage == "stalled"` or a `stage:stalled` label is already present on the lifecycle issue as of a time at or before this run started, set `alreadyHandledBy` on the emitted signal instead of a bare `lost-progress` class-hint.
- [X] T009 [US1] In the `collect` job, implement the `spec-meta` collector (FR-006): `git show origin/<branch>:<spec_dir>/spec-meta.json` compared against the stage the just-completed workflow should have advanced it to; append `{"source":"spec-meta","class-hint":"stage-mismatch","facts":{expected-stage,actual-stage}}` on a mismatch, nothing when it matches.
- [X] T010 [US1] In the `collect` job, implement the `step-summary` collector (FR-006): `gh api repos/{owner}/{repo}/actions/jobs/{job_id}` per job in the inspected run, grepping this pipeline's own known sentinel phrases (e.g. "stalled", "rejected", the metrics action's turn-budget warning); append `{"source":"step-summary","class-hint":null,"facts":{job,matched-sentinel}}` per match.
- [X] T011 [US1] In the `collect` job, implement the `annotations` collector (FR-006): `gh api repos/{owner}/{repo}/check-runs/{id}/annotations` (or `gh run view --json` if it exposes annotations) filtered to `warning`/`failure` level entries; append `{"source":"annotations","class-hint":null,"facts":{level,message}}` per entry.
- [X] T012 [US1] In the `collect` job, add the aggregation step that merges T007–T011's emitted entries into one `signals.json` array and uploads/exposes it as `diagnose`'s input (job artifact or output, implementation's choice); implement the failure mode (contract): only when every one of the five collector steps outright errored (not merely "produced nothing") does this step set `evidence-available: false`; an empty array with all collectors succeeding is a valid "no signal" result and proceeds to `diagnose` normally (data-model.md: "the collect job still runs diagnose... rather than skipping it").
- [X] T013 [US1] Implement the `diagnose` job's agent step in `.github/workflows/watchdog.yml`: `anthropics/claude-code-action@v1`, `model: claude-haiku-4-5`, bounded `max-turns`, `--allowedTools "Read,Grep,Bash(gh:*),Bash(git log:*),Bash(git diff:*)"`, `--disallowedTools "WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*)"`, structured output via `--json-schema` matching `data-model.md`'s Finding array shape (`class`, `description`, `evidence`, `normalizedFacts`, `severityHint`, `alreadyHandledBy`); prompt explicitly frames `signals.json` and anything read via `Read`/`Grep`/`gh` as untrusted data, never instructions to itself (FR-023, same framing convention every comment-triggered stage already uses); zero Findings in the output sets a job output `outcome: passed-inspection`.
- [X] T014 [US1] In `.github/workflows/watchdog.yml`, implement the "could not inspect" report path: a deterministic step, `if: needs.collect.outputs.evidence-available == 'false'`, posts "Could not inspect this run: \<reason\>." to the lifecycle issue resolved in T005 (or, when no lifecycle issue destination exists, to the run's own `$GITHUB_STEP_SUMMARY`) — FR-005, never fabricating a finding.
- [X] T015 [US1] In `.github/workflows/watchdog.yml`, implement the "passed inspection" report path: a deterministic step, `if: needs.diagnose.outputs.outcome == 'passed-inspection'`, posts "Run passed inspection." to the resolved lifecycle issue — FR-004.
- [X] T016 [US1] In the `act` job of `.github/workflows/watchdog.yml`, implement the findings-report step: for each Finding in `diagnose`'s structured output, format one block naming the problem class, the human-readable description, and the cited evidence (run identifier, offending turns/tools/branch state — FR-002); post one comment covering all of this run's findings to the resolved lifecycle issue (FR-022). This is the terminal write for User Story 1 alone — no fingerprint, dedup, issue, or PR yet (Phase 4 extends this same step with rung/dedup information per finding).

**Checkpoint**: User Story 1 is fully functional — `quickstart.md` Scenarios 1–4 pass independently of every other phase below, with no repository file ever modified.

---

## Phase 4: User Story 2 - Triage a finding to the right rung, without duplicating (Priority: P2)

**Goal**: Each finding is fingerprinted, checked against both open and closed issues, and routed to a PR-plus-issue (when a fix is attempted) or a bare issue (when no fix is attempted) — never duplicating an existing item, and reopening a closed one on recurrence.

**Independent Test**: Feed the watchdog a finding tied to an existing open pipeline-defect issue and confirm it opens a PR referencing that issue; feed the same finding again and confirm it comments rather than duplicating; feed a matching closed issue and confirm it reopens — `quickstart.md` Scenarios 10–12.

### Implementation for User Story 2

- [X] T017 [US2] In the `triage` job of `.github/workflows/watchdog.yml` (one matrix entry per Finding, per T006), implement the fingerprint step: `fingerprint = sha256(finding.class + "|" + canonical(finding.normalizedFacts))`, where `canonical()` sorts object keys, lowercases string values, and drops any field a per-class schema marks volatile (run IDs, timestamps, turn numbers) — data-model.md's Fingerprint section, never model-generated.
- [X] T018 [US2] In the `triage` job, implement the coexistence-suppression step (research.md): when a Finding's `alreadyHandledBy` field is set (from T008's collector), mark this matrix entry `suppressed` — skip T017's fingerprint and every dedup/act step for it — but still carry it into the final report as "already reported by \<job\>" (FR-024).
- [X] T019 [US2] In the `triage` job, implement the dedup-search step (non-suppressed entries only): `gh search issues --repo <repo> "wing-commander-watchdog: fingerprint=$FP in:body" --state all --json number,state`; zero results ⇒ `dedup: none`; exactly one `OPEN` result ⇒ `dedup: match-open` (its number); exactly one `CLOSED` result ⇒ `dedup: match-closed` (its number); more than one result ⇒ emit a data-integrity finding of its own (reported, no auto action) per FR-012–FR-016.
- [X] T020 [US2] In the `triage` job, implement the propose-fix step (non-suppressed entries only, invoked only when `finding.class` matches a `changeClasses[].id` in `.specify/memory/watchdog-guardrails.json`, read in T004's checkout): `anthropics/claude-code-action@v1`, `model: claude-sonnet-5`, bounded `max-turns`, `--allowedTools "Read,Grep,Glob,Edit,Write"` with the prompt scoping edits to `.github/workflows/**`, `.github/actions/**`, `docs/**` only, no `git`/`gh` write access declared; the step writes a diff to the job's own worktree, or makes no changes if it can't confidently produce one — checked afterward via `git diff --stat` (empty ⇒ declined).
- [X] T021 [US2] In the `triage` job, implement the rung-gate step's User-Story-2 slice (data-model.md's Triage decision table, the pre-guardrail-allowlist behavior Phase 6 later extends): no diff attempted or declined, and T019's dedup found nothing ⇒ `rung: 3`; no diff, dedup found a match ⇒ `rung: dedup-only` (comment/reopen, not a new item); a diff exists (regardless of size/path, since the FR-011 allowlist gate is not yet wired) ⇒ `rung: 2`, ensuring a pipeline-defect issue exists (T019's match reused/reopened, or created fresh) for the PR to reference.
- [X] T022 [US2] In the `act` job of `.github/workflows/watchdog.yml` (one matrix entry per non-suppressed Finding), implement the `rung: 3` write path: create (T019 found nothing) or reuse/reopen (T019 found a match) the pipeline-defect issue — on create, body includes `<!-- wing-commander-watchdog: fingerprint=<sha256> -->` (FR-016) plus the Finding's description/evidence; comment the fresh evidence + this run's `html_url` on the resolved lifecycle issue, linking the pipeline-defect issue (FR-009, FR-013–FR-015).
- [X] T023 [US2] In the `act` job, implement the `rung: 2` write path: commit T020's diff to a fresh branch `watchdog-fix/<short-fingerprint>`, open a PR to `main` whose body references the pipeline-defect issue via `Refs #N` (never an auto-closing keyword — a human decides the issue is resolved, not the merge, per data-model.md); comment the PR link on both the pipeline-defect issue and the resolved lifecycle issue (FR-008).
- [X] T024 [US2] In the `act` job, implement the `rung: dedup-only` write path: when T019 found an `OPEN` match, comment the fresh evidence there and file nothing new (FR-013); when it found a `CLOSED` match, reopen it and comment the fresh evidence (FR-014); either way, comment on the resolved lifecycle issue linking the pipeline-defect issue.
- [X] T025 [US2] Extend T016's findings-report step so each Finding's lifecycle-issue block additionally states the rung taken and the dedup outcome (create / reuse-open / reopen-closed / suppressed), per data-model.md's Lifecycle issue report shape ("One block per Finding: description + evidence + rung taken + dedup outcome").

**Checkpoint**: User Stories 1 AND 2 both work independently — `quickstart.md` Scenarios 1–4 and 10–12 all pass.

---

## Phase 5: User Story 4 - Hold itself to the same ladder (Priority: P2)

**Goal**: The watchdog inspects its own prior runs with the identical detection/triage/dedup rules, and a hard cap on consecutive self-inspection prevents an unbounded chain of watchdog runs.

**Independent Test**: Trigger the watchdog against a prior watchdog run exhibiting a problem and confirm it produces/triages a finding using the same rules with no special-case exemption, and that the self-dispatch cap bounds any resulting chain — `quickstart.md` Scenarios 8–9.

### Implementation for User Story 4

- [X] T026 [US4] In the `act` job of `.github/workflows/watchdog.yml`, implement the self-dispatch-depth step (FR-018, research.md): `if: github.event.workflow_run.name == '8 - Watchdog'` (self-inspection), walk `gh run list --workflow "8 - Watchdog" --json databaseId,event,createdAt --limit <cap + 5>` backward from the inspected run, counting a consecutive chain of entries whose `event == "workflow_run"` (each itself sourced from the watchdog wrapper); compare the resulting depth against `vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`).
- [X] T027 [US4] Wire T026's depth output as a write-suppression gate over every `act` write path built in Phase 4 (T022–T024): depth `>= cap` ⇒ skip every write for every Finding this run produced (collect/diagnose/triage still ran and are still reported); the lifecycle-issue report states "Self-dispatch cap reached — reporting only, no autonomous action taken." (data-model.md's report-shape table, FR-018).
- [X] T028 [US4] Desk-check `.github/workflows/watchdog.yml` end-to-end against FR-021: confirm no step across `collect`/`diagnose`/`triage`/`act` special-cases `workflow_run.name == "8 - Watchdog"` for anything other than T026's depth computation — detection, fingerprinting, dedup, and reporting must apply identically whether the inspected run is a watchdog run or any other stage; the lifecycle issue a self-inspection report lands on is whichever spec the *inspected* watchdog run itself was checking (T005's resolution, unchanged), never a separate "watchdog's own issue" concept.

**Checkpoint**: User Stories 1, 2, AND 4 all work independently — `quickstart.md` Scenarios 1–4, 8–12 all pass.

---

## Phase 6: User Story 3 - Fix a truly minor problem on sight (Priority: P3)

**Goal**: A fix diff that satisfies all three FR-011 guardrail conditions — allowlisted change-class, allowlisted paths, under the line cap — is opened as a PR without requiring a prior issue (rung 1); anything short of that, or while paused, falls back to rung 2 / report-only.

**Independent Test**: Configure the guardrail allowlist to permit a specific change-class, feed a finding of that exact class, and confirm the fix lands via the lightest permitted path with the action recorded on the lifecycle issue; feed a finding just outside the boundary and confirm it falls back to rung 2; confirm the pause switch suppresses all autonomous writes — `quickstart.md` Scenarios 5–7.

### Implementation for User Story 3

- [X] T029 [US3] In the `triage` job's rung-gate step (extends T021), implement the FR-011 three-condition guardrail check for any Finding with an attempted diff (T020): (a) `finding.class` is present in `.specify/memory/watchdog-guardrails.json`'s `changeClasses[].id`; (b) every path touched in `git diff --stat` matches that class's `pathGlobs`; (c) the diff's changed-line count is `<= min(class.maxDiffLines, config.maxDiffLines)`. All three pass ⇒ candidate `rung: 1` (subject to T030/T031's remaining gates); any single failure ⇒ stays `rung: 2` (T021/T023's existing path) — FR-011, FR-017.
- [X] T030 [US3] In the `triage` job's rung-gate step, implement the pause-switch check (FR-019): `vars.WING_COMMANDER_WATCHDOG_PAUSED == 'true'` produces the identical short-circuit as T027's self-dispatch-cap suppression — `act` performs no write for any Finding at any rung, and the lifecycle-issue report states "Autonomous fixes are paused (`WING_COMMANDER_WATCHDOG_PAUSED`) — reporting only."
- [X] T031 [US3] Finalize the rung-gate step (extends T021/T029/T030): a candidate `rung: 1` from T029 is confirmed only when also not paused (T030) and under the self-dispatch cap (T026/T027); any single failure among all of these demotes it to `rung: 2` — data-model.md's Triage decision table; any remaining ambiguity in severity/rung resolves to the higher (more human-involved) rung by default (FR-007, FR-010).
- [X] T032 [US3] In the `act` job, implement the `rung: 1` write path: commit T020's diff to `watchdog-fix/<short-fingerprint>`, open a PR to `main` with a short "here's exactly what changed and why" body — no prior pipeline-defect issue created or referenced, since dedup found nothing and this is the finding's first occurrence (research.md's rung-1 decision); comment the PR link on the resolved lifecycle issue (FR-020).
- [X] T033 [US3] Desk-check `.specify/memory/watchdog-guardrails.json` (T001) is read-only from every step in `.github/workflows/watchdog.yml` — no step ever writes to it — and confirm a change-class absent from the file (or the file itself missing) simply fails guardrail condition (a) in T029, never inventing a default allowlist entry (data-model.md's Guardrail configuration note).

**Checkpoint**: All four user stories are independently functional — the full `quickstart.md` scenario set (1–13) passes.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation consistency and end-to-end validation across the whole feature.

- [X] T034 [P] Add a "Stage 9 — Watchdog" section to `docs/architecture.md` (per plan.md's Project Structure note) documenting the four-job shape (`collect` → `diagnose` → `triage` → `act`), the two triggers (`workflow_run` across all nine stages including itself, plus `workflow_dispatch`), the triage ladder (rung 1/2/3 plus dedup-only), the fingerprint/marker dedup convention (reusing `rebase.yml`'s pattern), and the guardrail/pause/self-dispatch-cap knobs — mirroring the existing per-stage section format.
- [X] T035 [P] Add `.specify/memory/watchdog-guardrails.json`'s purpose and the two new repo variables (`WING_COMMANDER_WATCHDOG_PAUSED`, default unset/not-paused; `WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP`, default `3`) to `docs/setup.md`'s repository-variables/config tables, mirroring the `WING_COMMANDER_PLAN_REVIEW`/`WING_COMMANDER_TASKS_REVIEW` precedent from `specs/014-configurable-gates/`.
- [X] T036 [P] Add a `watchdog.yml` row to `specs/010-reusable-pipeline/contracts/stage-interfaces.md` (inputs: `run-id`, `run-name`, `model`, `max-turns`; outputs/side effects: lifecycle-issue comment, pipeline-defect issue, PR to `main`), mirroring the other nine stages' rows in that table.
- [X] T037 Validate `.github/workflows/watchdog.yml` and `.github/workflows/wing-commander-8-watchdog.yml` end-to-end on paper: YAML parses (e.g. `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` or actionlint if available) and every embedded `run:` script passes `bash -n` (matching `lint-workflows.yml`'s CI checks); cross-check every job/step against `contracts/watchdog-workflow.md`'s trigger, job, self-dispatch-cap, and pause contracts.
- [X] T038 Walk `specs/015-pipeline-watchdog/quickstart.md`'s full scenario set (1–14) end-to-end against the finished workflow files, recording in the PR body which were exercised live (via scratch spec runs / `workflow_dispatch`) versus desk-checked only — including Scenario 14 (untrusted content never treated as instructions, FR-023), which has no dedicated implementation task above since it is a property of T013's prompt framing rather than a separate code path.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (job skeletons must exist before adding steps to them) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on other stories.
- **User Story 2 (Phase 4)**: Depends on Foundational AND User Story 1 (T025 extends T016's report step; T017's fingerprint step consumes Findings T013 produces).
- **User Story 4 (Phase 5)**: Depends on User Story 2 (T027 wraps the `act` write paths T022–T024 build).
- **User Story 3 (Phase 6)**: Depends on User Story 2 (T029/T031 extend T021's rung gate and reuse T020's diff) AND User Story 4 (T031 reuses T026/T027's self-dispatch-cap output).
- **Polish (Phase 7)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: Independently implementable and testable after Foundational — the only story with no dependency on another story's write paths.
- **User Story 2 (P2)**: Builds on User Story 1's Findings and report step; independently testable once its own phase completes (Scenarios 10–12 don't require Phases 5–6).
- **User Story 4 (P2)**: Builds on User Story 2's `act` write paths (it wraps them in a suppression gate); independently testable once its own phase completes (Scenario 8's self-dispatch cap, Scenario 9's self-inspection).
- **User Story 3 (P3)**: The highest-trust rung, sequenced last because it both extends User Story 2's rung gate and reuses User Story 4's self-dispatch-cap output — matches spec.md's own stated sequencing rationale ("Autonomous writes... must be earned on top of reliable detection and triage").

### Within Each Story

- Collectors (US1) before diagnose before report (each depends on the prior step's output existing).
- Fingerprint before dedup-search before propose-fix before rung-gate before act-writes (US2's internal order, per `contracts/watchdog-workflow.md`'s `triage` job step sequence).
- Self-dispatch-depth computation before its write-suppression wiring (US4's T026 before T027).
- Guardrail check before pause check before the finalized rung decision (US3's T029 before T030 before T031).

### Parallel Opportunities

- T001 (guardrails config) is parallel-safe against T002/T003 (different files).
- Within Phase 1, T002 and T003 touch different files but T003 calls T002 by path — sequence T002 before T003 for correctness even though they're technically different files.
- Within Phases 2–6, almost every task edits the same `watchdog.yml` file (different steps within the same job or across dependent jobs) — treat as sequential, not `[P]`, per this feature's file-concentration.
- T034, T035, and T036 (Polish, three different doc files) are parallel-safe with each other and with T037/T038.

---

## Parallel Example: Setup

```bash
# Launch together — different files, no shared state:
Task: "Create .specify/memory/watchdog-guardrails.json with the FR-011/FR-017 v1 seed allowlist"
Task: "Create .github/workflows/watchdog.yml as a workflow_call-only reusable stage skeleton"
```

## Parallel Example: Polish Documentation

```bash
# Launch together — three different doc files:
Task: "Add a 'Stage 9 — Watchdog' section to docs/architecture.md"
Task: "Add the guardrail file and two new repo variables to docs/setup.md"
Task: "Add a watchdog.yml row to specs/010-reusable-pipeline/contracts/stage-interfaces.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `quickstart.md` Scenarios 1–4 independently
5. This alone delivers SC-001 and SC-007 — every pipeline run's post-mortem is automated and posted to the lifecycle issue, with zero autonomous writes, replacing the manual first-responder step entirely

### Incremental Delivery

1. Setup + Foundational → scaffold ready
2. Add User Story 1 → validate Scenarios 1–4 → mergeable increment (MVP)
3. Add User Story 2 → validate Scenarios 10–12 → mergeable increment (findings now route to PRs/issues without duplicating)
4. Add User Story 4 → validate Scenarios 8–9 → mergeable increment (self-inspection with the same rules, loop-bounded)
5. Add User Story 3 → validate Scenarios 5–7 → mergeable increment (the highest-trust rung, fully guardrailed)
6. Polish → validate the full Scenario 1–14 sweep together

### Why User Story 3 depends on both User Story 2 and User Story 4

Rung 1 is defined entirely as a *tightening* of User Story 2's rung-2 path (the same diff, the same rung-gate step, just an additional three-condition guardrail check that promotes it) plus reuse of User Story 4's self-dispatch-cap output as one of its three additional preconditions (not-paused, under-cap). There is no independent "rung 1 only" code path to build first — attempting to sequence it before Phase 4/5 would mean either duplicating the diff-generation and rung-gate machinery those phases already build, or leaving the self-dispatch-cap precondition unimplemented, silently weakening FR-018's loop-prevention guarantee exactly where it matters most (autonomous, unattended writes).
