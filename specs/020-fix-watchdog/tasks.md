---

description: "Task list for Fix the Watchdog — Restore Reliable Run Inspection"

---

# Tasks: Fix the Watchdog — Restore Reliable Run Inspection

**Input**: Design documents from `/specs/020-fix-watchdog/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/watchdog-workflow-delta.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for workflow YAML in this repository (plan.md's Testing note; consistent with specs 014/016/017/018/019). Validation is `quickstart.md`'s five scenarios, run at the end of each relevant phase's checkpoint and as a final sweep in Polish.

**Organization**: All three user stories are served by one new job, `report-unhandled-failure`, added to `.github/workflows/watchdog.yml` (contracts/watchdog-workflow-delta.md) — so this feature's phases split that single job's steps by which acceptance behavior they satisfy rather than by file. User Story 1 (P1) is the job's failure-detection gate plus a baseline report that always lands somewhere (the run summary at minimum) — this alone eliminates FR-002's "no verdict at all" failure and is therefore the MVP: a maintainer stops seeing a silent red X, even before routing is polished. User Story 2 (P1) adds the job's own independent re-resolution of the GitHub App token and the lifecycle issue (it cannot trust `collect`'s outputs, since `collect` may be the job that failed) so the verdict lands on the lifecycle issue when one resolves, matching every other verdict path's destination rule. User Story 3 (P2) is the report's exact wording — naming the failed job, its result, and a link to its logs, phrased so it reads as a distinct case from the existing "every evidence collector failed" message (data-model.md R2) — making a future recurrence self-diagnosing. Phase 1 (Setup) confirms the root-cause hypothesis research.md R1 derived from static analysis against the actual reported run (or a fresh reproduction), since the plan was authored without `gh` log access (research.md R3) and the fix's regression test (FR-005) needs a confirmed, not merely hypothesized, failure shape.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD bug fix (one new job and no structural change to four existing jobs in one reusable workflow file, plus one documentation section), no `src`/`tests` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm which step actually failed in the reported run (or in a fresh reproduction of the same failure class), so the fix targets a confirmed cause and quickstart.md Scenario 3 has real evidence to check against, per research.md R3's open item.

- [ ] T001 Attempt `gh run view 30118703536 --repo charlesguse/wing-commander --json jobs,conclusion` (or `gh api repos/charlesguse/wing-commander/actions/runs/30118703536/jobs`) to read the `collect` job's step-level conclusions for the run linked from issue #96. If the run is still inspectable, identify the exact failing step (research.md R1's leading candidate is "Fetch inspected run metadata"'s `gh run view` call, but "Checkout consumer repository", "Resolve pipeline ref", "Checkout pipeline repository", "Preflight", and "Wing Commander context" are also unguarded and possible). If the run has aged out of retention (spec.md's Assumptions anticipate this), instead reproduce the same failure class by temporarily forcing one of those steps to fail on a throwaway branch via manual `workflow_dispatch` (quickstart.md Scenario 2's method), then revert the deliberate breakage. Append a short confirmation note to `specs/020-fix-watchdog/research.md` under R3 recording which step was confirmed to fail (or which reproduction was used), so the Polish-phase validation (T009) has a concrete, not merely hypothesized, failure to re-run against.

**Checkpoint**: The failure this feature fixes is confirmed against real evidence, not only static analysis — implementation and final validation can proceed with a concrete repro in hand.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the `report-unhandled-failure` job's skeleton and the scaffolding every story's steps append to — the job declaration itself, and the best-effort checkout/context steps needed to reach the shared `wing-commander-context` composite action for its own GitHub App token (contracts/watchdog-workflow-delta.md). No story's steps can be added before this job exists in `.github/workflows/watchdog.yml`.

- [ ] T002 In `.github/workflows/watchdog.yml`, after the `act` job (ends ~line 1643) and before/alongside the concurrency/permissions block that already applies workflow-wide, add a new job `report-unhandled-failure` with `needs: [collect, diagnose, triage, act]`, `if: always()`, `runs-on: ubuntu-latest`. Give it the same best-effort checkout scaffolding `collect` uses to reach the shared composite actions — "Checkout consumer repository" (`actions/checkout@v4`, `persist-credentials: false`), "Resolve pipeline ref" (identical logic to `collect`'s step at line 158, since `github.job_workflow_sha`/OIDC resolution is job-scoped and cannot be inherited from `collect`), "Checkout pipeline repository" (`path: .wing-commander-pipeline`) — but mark each of these three steps `continue-on-error: true` (contract point 3: "this job's own steps tolerate their own failure gracefully... it is the last line of defense and must not itself become a new single point of failure"), unlike `collect`'s identical-looking but hard-failing versions. Then add a "Wing Commander context" step (`uses: ./.wing-commander-pipeline/.github/actions/wing-commander-context`, `app-id`/`private-key` from the same secrets `collect` uses), also `continue-on-error: true`, producing `steps.ctx.outputs.token` (empty string if minting failed, e.g. because the preceding checkout also failed).

**Checkpoint**: `report-unhandled-failure` exists in the workflow graph, always runs (`if: always()`), and has best-effort access to a GitHub App token when it can reach one — no report is posted yet, but every story below can now add its steps to this job.

---

## Phase 3: User Story 1 - The watchdog reaches a verdict for every inspected run (Priority: P1) 🎯 MVP

**Goal**: When `collect`, `diagnose`, `triage`, or `act` ends `failure` or `cancelled` for any reason — including a cause no existing per-step error handling anticipated — the watchdog run still produces exactly one verdict instead of ending as a bare red X with nothing posted anywhere.

**Independent Test**: Reproduce (or use T001's confirmed reproduction of) a hard failure in one of `collect`'s unguarded pre-collector steps via manual `workflow_dispatch` on a throwaway branch. Confirm `collect` fails, `diagnose`/`triage`/`act` are skipped (unchanged Actions semantics), and the watchdog run nonetheless ends with a written verdict rather than silence (quickstart.md Scenario 2, steps 1-3).

### Implementation for User Story 1

- [ ] T003 [US1] In `.github/workflows/watchdog.yml`'s `report-unhandled-failure` job (after T002's context steps), add a step "Determine failed jobs" (`id: gate`) that reads `needs.collect.result`, `needs.diagnose.result`, `needs.triage.result`, and `needs.act.result`, and sets two outputs: `any-failed` (`true` if one or more of the four is `failure` or `cancelled`, else `false`) and `failed-jobs` (a newline- or space-separated list of `"<job>:<result>"` pairs for every job that qualifies, e.g. `collect:failure`). This step must not use `set -e`/`set -o pipefail` — it only reads workflow-engine-computed `needs.*.result` strings (never user-influenced text, Constitution V), so there is nothing here that should ever fail, but it must not become one either.
- [ ] T004 [US1] Add a step "Report unhandled job failure to run summary" (`id: report-baseline`, `if: steps.gate.outputs.any-failed == 'true'`) that always appends one line per entry in `steps.gate.outputs.failed-jobs` to `$GITHUB_STEP_SUMMARY` using the deterministic template from data-model.md ("🐕 **Wing Commander · watchdog** — could not inspect this run: the `<job>` job ended `<result>` unexpectedly... This is a pipeline defect, not a finding about the inspected run itself."), with a placeholder run-URL reference (`inputs.run-id`) since this step must not depend on any of T002's best-effort steps having succeeded. This step alone guarantees FR-002 holds — a verdict now always exists in the run's own summary even in the worst case where the App token mint and lifecycle-issue resolution (User Story 2) both also fail.

**Checkpoint**: User Story 1 is independently satisfied — quickstart.md Scenario 2's core claim (the safety net fires and a verdict is never silently absent) holds, even before verdicts are routed to the lifecycle issue.

---

## Phase 4: User Story 2 - The watchdog's verdict is delivered where the maintainer looks (Priority: P1)

**Goal**: When at least one job hard-failed, the "could not inspect" report from User Story 1 lands as a comment on the inspected run's lifecycle issue (when one can be resolved) instead of only the run summary — matching the destination rule every other verdict path in `specs/015-pipeline-watchdog/` already follows.

**Independent Test**: Force the same fault-injection failure as User Story 1's test, once against a run whose head branch resolves to a lifecycle issue and once against one that doesn't. Confirm the report lands as an issue comment in the first case and in the run summary in the second (quickstart.md Scenario 2, step 3's "to the lifecycle issue if one resolves, else the run summary").

### Implementation for User Story 2

- [ ] T005 [US2] Add a step "Resolve inspected run's lifecycle issue" (`id: issue`, `if: steps.gate.outputs.any-failed == 'true'`, `continue-on-error: true`) that independently re-derives the lifecycle issue the same way `collect`'s "Resolve inspected run's spec slug and lifecycle issue" step does (lines 232-292: parse `inputs.run-id`'s head branch via `gh run view` using `steps.ctx.outputs.token`, match it against the four branch-prefix `vars.WING_COMMANDER_*_PREFIX` variables, fetch `spec-meta.json` off the resolved spec branch, read its `.issue` field) — it must not read `needs.collect.outputs.lifecycle-issue`, since `collect` may be the job that failed before computing that output. Output `issue-number` (empty if resolution fails at any point, including because `steps.ctx.outputs.token` from T002 is itself empty).
- [ ] T006 [US2] Replace T004's run-summary-only report with a two-branch step "Report unhandled job failure" (`id: report`, `if: steps.gate.outputs.any-failed == 'true'`, `continue-on-error: true`): when `steps.issue.outputs.issue-number` is non-empty, post the per-job report lines as a `gh issue comment` using `steps.ctx.outputs.token`; otherwise (empty issue number, for any reason — no resolvable spec, or the resolution step itself failed) fall back to appending to `$GITHUB_STEP_SUMMARY`, identical to every other verdict path's fallback rule (data-model.md, contracts/watchdog-workflow-delta.md). Keep T004's run-summary write as a final `if: always() && steps.report.outcome == 'failure'` fallback step so that even this step's own failure (e.g. `gh issue comment` erroring) still leaves a written verdict in the run summary — the safety net must not itself have a silent failure mode.

**Checkpoint**: User Stories 1 and 2 both hold — quickstart.md Scenario 2 passes end to end, with the verdict routed correctly in both the resolvable- and unresolvable-lifecycle-issue cases.

---

## Phase 5: User Story 3 - A failing watchdog explains itself rather than failing silently (Priority: P2)

**Goal**: The report T006 posts is worded so a maintainer can immediately tell, without opening any logs, which job failed, how it failed, and where to look — and can immediately distinguish this "a job itself hard-failed" case from the pre-existing "every evidence collector failed but `collect` itself succeeded" case (data-model.md R2).

**Independent Test**: Read the posted report from User Story 2's test without opening the Actions tab. Confirm it names the specific failed job(s) and result(s), links to that job's logs, and uses wording ("ended `<result>` unexpectedly") distinct from the existing "could not inspect — every evidence collector failed outright" message (quickstart.md Scenario 2, step 3; data-model.md's report-variant table).

### Implementation for User Story 3

- [ ] T007 [US3] Add a step "Resolve failed job log URLs" (`id: job-urls`, `if: steps.gate.outputs.any-failed == 'true'`, `continue-on-error: true`) that calls `gh api repos/${{ github.repository }}/actions/runs/${{ inputs.run-id }}/jobs --jq '.jobs[] | select(.name==... ) | .html_url'` (using the default `GITHUB_TOKEN`, which already has `actions: read` from the workflow-level `permissions:` block — no App token needed for this read) to look up each failed job's own log URL by name, for every job named in `steps.gate.outputs.failed-jobs`. Output one URL per failed job (empty for any that can't be resolved, e.g. if the API call itself fails — the report template must tolerate a missing link).
- [ ] T008 [US3] Update T006's report template to the exact contract wording per job — `"🐕 **Wing Commander · watchdog** — could not inspect this run: the <job> job ended <result> unexpectedly. [Job logs](<url>). This is a pipeline defect, not a finding about the inspected run itself."` — one line per entry in `steps.gate.outputs.failed-jobs`, using T007's resolved URL for `<url>` (or omitting the link if T007 couldn't resolve it, rather than posting a broken link). Confirm by inspection that this wording ("ended `<result>` unexpectedly") reads as clearly distinct from the existing "could not inspect this run: every evidence collector failed outright" message at line 521 of `.github/workflows/watchdog.yml` — a maintainer reading either must be able to tell which failure shape occurred without cross-referencing anything else.

**Checkpoint**: All three user stories hold — quickstart.md Scenario 2 passes in full, including the exact wording check, and a maintainer can self-diagnose a future recurrence from the report alone.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Document the new safety net as regression protection (FR-008/research.md R4) and validate the whole feature against every quickstart scenario, including the no-regression contexts this feature must not touch.

- [ ] T009 [P] Add a fifth bullet to `docs/architecture.md`'s Stage 9 — Watchdog Design list (after the existing `act` bullet, ~line 363), documenting `report-unhandled-failure`: `needs: [collect, diagnose, triage, act]`, `if: always()`, no-ops when every job succeeded, otherwise posts a "could not inspect this run: the `<job>` job ended `<result>` unexpectedly" report (to the lifecycle issue if one resolves, else the run summary) — the structural safety net that makes a hard job failure in any of the four preceding jobs still end in a truthful verdict instead of silence (research.md R1/R4).
- [ ] T010 [P] Validate the edited `.github/workflows/watchdog.yml` parses as valid YAML and passes `bash -n` on its embedded `run:` scripts, matching `.github/workflows/lint-workflows.yml`'s own CI checks — run locally or trigger `lint-workflows.yml` itself (`actionlint`/`yamllint` per specs/019's precedent, if `python3`/`bash -n` aren't available in this environment).
- [ ] T011 Run quickstart.md's full scenario set against the finished workflow: Scenario 1 (automatic per-stage trigger still reaches a verdict on a normal, non-failing run — confirms no regression in the common path), Scenario 2 (User Stories 1-3, T003-T008, fault injection proves the safety net), Scenario 3 (reproduces T001's confirmed failure class and confirms the fix yields a valid verdict where the original symptom occurred), Scenario 4 (manual `workflow_dispatch` and self-inspection both still reach a verdict exactly as before — confirms FR-006's no-regression requirement across all three invocation contexts), and Scenario 5 (median time from stage completion to verdict stays under 10 minutes, confirming the new job's `if:`-guarded no-op path adds no material latency on the common case). Record in the PR body which scenarios were exercised via a live dogfooded run versus desk-checked only.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Independent of Setup's outcome (T002 is structural scaffolding, not dependent on which step T001 confirms failed) but should follow it in sequence since both edit context this feature reasons about — BLOCKS every user story (T003-T008 all add steps to the job T002 creates).
- **User Story 1 (Phase 3)**: Depends on Foundational (T002).
- **User Story 2 (Phase 4)**: Depends on Foundational (T002) and on User Story 1 (T005/T006 replace T004's report step and reuse `steps.gate` from T003).
- **User Story 3 (Phase 5)**: Depends on Foundational (T002) and User Story 2 (T007/T008 refine T006's report step and reuse `steps.issue`/`steps.ctx`).
- **Polish (Phase 6)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency beyond the Foundational phase — independently testable and deployable as-is (a maintainer stops seeing silent no-verdict failures, even with reports landing only in the run summary).
- **User Story 2 (P2)**: Builds on User Story 1's `steps.gate` output and replaces its report step; not independently implementable in isolation (there is nothing to route until User Story 1's detection exists), but independently *testable* once both are in place — its acceptance scenario is a distinct behavior (destination) from User Story 1's (existence).
- **User Story 3 (P2)**: Builds on User Story 2's `steps.issue`/`steps.ctx` outputs and refines its report wording; same relationship — independently testable as a wording/evidence check once User Story 2's routing exists.

### Same-file ordering (not story dependencies, but real ordering constraints)

- All of T002-T008 edit the same new job in the same file (`.github/workflows/watchdog.yml`) and must be applied in ID order (T002 -> T003 -> ... -> T008) since each step depends on outputs (`steps.ctx`, `steps.gate`, `steps.issue`) an earlier task introduces — this feature has no cross-file parallelism within its core fix, unlike specs/019's multi-file callout migration.
- T009 (docs) and T010 (lint) are parallel-safe with each other and can start as soon as T008 lands, since both only read the finished workflow file.

### Parallel Opportunities

- T009 and T010 can run in parallel with each other.
- T001 (Setup) can run in parallel with T002 (Foundational) since neither's outcome gates the other's start, though T001's confirmed failure step should be known before T011's final validation.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the reported failure's exact step)
2. Complete Phase 2: Foundational (job skeleton + best-effort context steps)
3. Complete Phase 3: User Story 1 (failure-detection gate + guaranteed run-summary report)
4. **STOP and VALIDATE**: Run quickstart.md Scenario 2 against the finished MVP wiring — confirm a hard job failure now ends with a written verdict, even if only in the run summary
5. This alone fixes FR-002's core defect — every remaining phase makes the verdict land in the *right* place (User Story 2) and read clearly (User Story 3), not merely exist

### Incremental Delivery

1. Setup + Foundational -> job skeleton ready, root cause confirmed
2. Add User Story 1 -> validate Scenario 2's "a verdict now exists" claim -> mergeable increment (MVP: the reported "isn't working" symptom is gone)
3. Add User Story 2 -> validate Scenario 2's destination routing -> mergeable increment (verdict now lands on the lifecycle issue like every other verdict path)
4. Add User Story 3 -> validate Scenario 2's wording check -> mergeable increment (a future recurrence is self-diagnosing)
5. Polish -> validate the full Scenario 1-5 sweep, plus docs and lint

### Why User Story 1 alone is the MVP

FR-002 names "ends without a verdict" as the exact failure this feature must eliminate, and that is what User Story 1's gate-plus-baseline-report delivers on its own, even before routing (User Story 2) or wording (User Story 3) are polished. A verdict sitting only in the run summary instead of the lifecycle issue is a rough edge; a watchdog run that ends with nothing anywhere is the reported bug.
