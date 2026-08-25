---

description: "Task list template for feature implementation"
---

# Tasks: Durable Agent Run Metrics — Emit, Persist, and Roll Up What the Pipeline Spends

**Input**: Design documents from `/specs/043-durable-metrics-record/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md,
contracts/emission-contract.md, contracts/metrics-record-schema.md,
contracts/persist-workflow.md, contracts/wrapper-contract.md,
contracts/gate-coverage-043.md

**Tests**: This feature's own User Story 5 *is* its test/gate coverage
(FR-039/FR-040) — no separate "Tests for User Story N" subsections are
generated for Stories 1-4; their independent tests (spec.md) are exercised
by User Story 5's fixture-backed gates plus quickstart.md's manual walkthrough.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Include exact file paths in descriptions

## Site inventory used throughout this document (measured in this checkout, not assumed)

`wing-commander-metrics-summary` call sites (13, across 10 workflow files —
not the plan's approximate "~14"; grounded by `grep -rn "uses:
./.wing-commander-pipeline/.github/actions/wing-commander-metrics-summary"
.github/workflows/*.yml`):

| File | Sites | Existing transcript artifact name(s) |
|---|---|---|
| `clarify.yml` | 1 | `claude-execution-output` |
| `cleanup.yml` | 1 | `claude-execution-output` |
| `finalize.yml` | 1 | `claude-execution-output` |
| `implement.yml` | 3 | `claude-execution-output-cycle`, `-retry`, `-progress` |
| `intake.yml` | 1 | `claude-execution-output` |
| `plan.yml` | 1 | `claude-execution-output` |
| `pr-conversation.yml` | 2 | `claude-execution-output-classify`, `-act-${{ strategy.job-index }}` |
| `rebase.yml` | 1 | `claude-execution-output-${{ matrix.slug }}` |
| `tasks.yml` | 1 | `claude-execution-output` |
| `watchdog.yml` | 1 (diagnose) | `claude-execution-output-diagnose` |

Transcript `upload-artifact` sites with **no** declared `retention-days`
today (16, across 11 workflow files — grounded by `grep -c "name:
claude-execution-output" .github/workflows/*.yml`): the 10 files above,
each at the same site count, **plus** `auto-update-spec-kit.yml` (3 sites:
`claude-execution-output-evaluate-path`, `-e2e-stage`, `-comment-reply`;
not a `wing-commander-metrics-summary` call site, so it is out of scope for
US1/US3 but in scope for US4).

## Phase 1: Setup

No setup tasks. This feature adds no new language, dependency, or toolchain —
every piece is Bash/YAML/`jq`/`git`/`gh` this repository's runners and gate
scripts already use (plan.md Technical Context). Existing conventions
(`.github/scripts/verify-*.py`/`.sh`, `run-local-gates.py`,
`stage-invariant-waivers.json`) are reused, not re-created.

---

## Phase 2: Foundational

No separate foundational phase. User Story 1 (Phase 3) *is* the shared
foundation every other story depends on (plan.md Summary: "the foundation
both remaining tiers stand on") — there is no cross-story infrastructure to
build ahead of it. Proceed directly to Phase 3.

---

## Phase 3: User Story 1 - Every agent run emits a machine-readable record of what it cost (Priority: P1) 🎯 MVP

**Goal**: `wing-commander-metrics-summary` emits a normalized, versioned
JSON record from the same extraction it already does for the rendered
summary, at every existing call site, uploaded alongside the transcript.

**Independent Test**: Run any pipeline stage that invokes an agent, confirm
a structured record is produced alongside the existing transcript, carries
every schema field, agrees numerically with the rendered summary, and that
a missing/unparseable-transcript run still produces a record marked
unavailable rather than nothing (quickstart.md Story 1).

### Implementation for User Story 1

- [X] T001 [US1] In `.github/actions/wing-commander-metrics-summary/action.yml`, add the `record-path` (default `${{ runner.temp }}/wing-commander-metrics-record.json`), `stage`, `spec-dir`, `spec-issue` inputs and `record-json`, `record-key` outputs per contracts/emission-contract.md, leaving every existing input/output unchanged (FR-036).
- [X] T002 [US1] In the same file's "Render agent run metrics summary" step, after the existing per-field extraction (`result_json`, `main_turns`/`reported_turns`, `usage_json`, `model_usage_json`, `subtype`, `duration_ms`, `cost_usd`), build the schema-version-1 JSON object (contracts/metrics-record-schema.md shape) — `schema_version: 1`, `run.workflow_run_id` (`github.run_id`), `run.job_key` (`github.job`), `run.job_id: null`, `run.step_index` (literal per call site, wired in T006-T015), `run.record_key = "<run_id>:<job_key>:<step_index>"`, `stage`/`spec.spec_dir`/`spec.issue` from the new T001 inputs with their `*_available` flags, `model`/`model_available`, `turns.*` from `main_turns`/`reported_turns`/`MAX_TURNS`/`CEILING`, `tokens.*` from `usage_json`, `cost_usd`/`cost_available`, `duration_ms`/`duration_available`, `outcome` (map `subtype`/verdict vocabulary to `healthy`\|`exhausted`\|`failed`\|`unclassifiable`) — and write it to `record-path`. Added a `step-index` input (not explicit in contracts/emission-contract.md's table but required by this task's own `run.step_index` field and T006-T015's per-site wiring) — default `'0'`, correct for every single-agent-step job.
- [X] T003 [US1] In the same step, implement the degraded-record branch (the existing `availability != ok` case, contracts/metrics-record-schema.md "Degraded record"): still write a full record with `record_available: false`, every transcript-derived field `null` with its `*_available: false`, while `run.*`, `stage`/`stage_available`, `spec.*`, `model`/`model_available`, `turns.intended_budget`, `turns.enforced_ceiling` stay populated from the job environment inputs (never from the transcript) — the step must still `exit 0`.
- [X] T004 [US1] In the same step, implement the `per_model` array builder from `model_usage_json` — one `{model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_usd}` entry per model in `.modelUsage` (a single-model run yields one entry, never zero), `per_model_available: false` and `per_model: []` when `.modelUsage` is absent/unparseable (FR-005a), and confirm `sum(per_model[].*) == tokens.*`/`cost_usd` when both are available (contracts/metrics-record-schema.md Invariant).
- [X] T005 [US1] In the same file, set the `record-json` (file contents as a string) and `record-key` (`run.record_key`) step outputs from the record written in T002-T004.
- [X] T006 [P] [US1] In `.github/workflows/clarify.yml`: pass `stage`/`spec-dir`/`spec-issue` to its existing `wing-commander-metrics-summary` call, then add an "Upload metrics record" step immediately after it using `actions/upload-artifact@v6`, `name: metrics-record`, `path: ${{ runner.temp }}/wing-commander-metrics-record.json`, `if-no-files-found: ignore`, `retention-days: 90` (contracts/emission-contract.md's call-site snippet).
- [X] T007 [P] [US1] Same change as T006 in `.github/workflows/cleanup.yml` (`name: metrics-record`).
- [X] T008 [P] [US1] Same change as T006 in `.github/workflows/finalize.yml` (`name: metrics-record`).
- [X] T009 [P] [US1] Same change as T006 in `.github/workflows/implement.yml`, at all three sites, each with `step_index` 0/1/2 respectively and artifact names `metrics-record-cycle`, `metrics-record-retry`, `metrics-record-progress` mirroring the existing transcript suffixes; place each upload step before any later agent step in the same job overwrites the shared `runner.temp` record path (same ordering constraint the transcript upload already observes).
- [X] T010 [P] [US1] Same change as T006 in `.github/workflows/intake.yml` (`name: metrics-record`).
- [X] T011 [P] [US1] Same change as T006 in `.github/workflows/plan.yml` (`name: metrics-record`).
- [X] T012 [P] [US1] Same change as T006 in `.github/workflows/pr-conversation.yml`, at both sites, artifact names `metrics-record-classify` and `metrics-record-act-${{ strategy.job-index }}` mirroring the existing transcript suffixes.
- [X] T013 [P] [US1] Same change as T006 in `.github/workflows/rebase.yml`, artifact name `metrics-record-${{ matrix.slug }}` mirroring the existing transcript suffix.
- [X] T014 [P] [US1] Same change as T006 in `.github/workflows/tasks.yml` (`name: metrics-record`).
- [X] T015 [P] [US1] Same change as T006 in `.github/workflows/watchdog.yml`'s diagnose site, artifact name `metrics-record-diagnose` mirroring the existing transcript suffix; this site has no spec lifecycle issue to pass as `spec-issue` (it posts to a findings issue) — pass `stage`/`spec-dir` only, leaving `spec.identity_available: false`.

**Checkpoint**: User Story 1 is fully functional and independently testable — trigger any stage, download `metrics-record*`, confirm it matches contracts/metrics-record-schema.md and agrees with the rendered `$GITHUB_STEP_SUMMARY` table (quickstart.md Story 1).

---

## Phase 4: User Story 2 - The record outlives the artifact that carried it (Priority: P1)

**Goal**: A published `wing-commander-metrics-persist` composite and
`metrics-persist.yml` workflow fetch a concluded run's records and append
them, with bounded retry-on-contention, to a wrapper-supplied destination
branch/path — never touching any branch the pipeline builds from.

**Independent Test**: Drive several concurrent pipeline runs, persist them,
read `records.jsonl` directly without downloading an artifact, and confirm
one entry per agent run with none lost, overwritten, or duplicated on a
repeat pass (quickstart.md Story 2).

### Implementation for User Story 2

- [X] T016 [US2] Create `.github/actions/wing-commander-metrics-persist/action.yml` with inputs `run-id`, `destination-branch`, `destination-path` (all required, no literal default — FR-013). First step: discover this run's jobs and `metrics-record*` artifacts via `gh api repos/{owner}/{repo}/actions/runs/{run-id}/jobs` then `.../artifacts` (mirroring `watchdog.yml`'s existing cross-run artifact discovery pattern), resolving each job's `job_key`→numeric `job_id` from the same jobs list for T020's `record_key` rewrite; when discovery finds zero matching artifacts, exit successfully with zero records (FR-021). `pipeline-repo`/`pipeline-repo-ref` were placed on T021's workflow instead of this composite — contracts/persist-workflow.md's own declared `metrics-persist.yml` YAML shows them as workflow_call inputs, not composite inputs, and this composite doesn't check out the pipeline repo itself (that already happened one layer up, before this composite is invoked).
- [X] T017 [US2] In the same composite, implement retrieval: `gh run download {run-id} -p 'metrics-record*' -D <dir>` (same tool/auth `watchdog.yml` uses); any artifact matched at T016 but not retrievable here (expired, never uploaded) is reported by name as **not retrieved**, never silently skipped or persisted as if complete (FR-022).
- [X] T018 [US2] In the same composite, implement validation of every retrieved record against contracts/metrics-record-schema.md's shape and the `per_model` sum invariant: a record whose `schema_version` is not `1` is retained as-is and excluded from further validation (FR-025d, "retain and skip"); a record declaring `schema_version: 1` that fails validation is rejected and reported by `record_key` (FR-041); rewrite each valid record's `run.record_key` to use the numeric `run.job_id` resolved in T016 (data-model.md's job_key→job_id rewrite, R6). Known limitation, documented inline: the job_key→job_id map is an exact-name match, unambiguous only for the 11 single-instance-job call sites — the 2 matrix-strategy sites (rebase.yml, pr-conversation's act job) share one job_key across every matrix instance in a run, so those records keep `job_id: null` and their emission-time `record_key` form rather than risk a wrong rewrite.
- [X] T019 [US2] In the same composite, implement destination branch creation (research.md R8): `git ls-remote --exit-code origin refs/heads/<destination-branch>`; if it exits non-zero, `git checkout --orphan`, commit the first batch of validated records against an empty tree, and push it as the branch's first commit — no human preparation required (FR-020).
- [X] T020 [US2] In the same composite, implement the append-with-retry loop (research.md R7): up to 8 attempts — fetch `destination-branch` fresh, parse existing `record_key`s out of `destination-path`, compute this run's records not already present, append only those, commit, `git push`; on non-fast-forward rejection, sleep `min(attempt, 5)` seconds and retry from the fetch step; on the 8th consecutive rejection, fail the step naming every still-unwritten `record_key` (FR-016/FR-017); a repeat invocation for the same `run-id` computes zero new records to append and leaves the file unchanged (FR-018 idempotency).
- [X] T021 [US2] Create `.github/workflows/metrics-persist.yml`, `workflow_call`-only, declaring the interface in contracts/persist-workflow.md (`run-id`/`destination-branch`/`destination-path` required with no default, optional `pipeline-repo`/`pipeline-repo-ref` inputs and `pipeline-repo-token` secret, `persisted-count`/`unpersisted-record-keys` outputs), self-checking-out the pipeline repo via the same trusted-ref pattern every stage uses, and calling the T016-T020 composite; a failure at any step fails only this workflow's own run — it never modifies the origin pipeline run's branch, checks, or comments (FR-015/FR-019/FR-019a).
- [X] T022 [US2] Create `.github/workflows/wing-commander-metrics-persist.yml` wrapper (contracts/wrapper-contract.md): `resolve` job (no checkout, `permissions: actions: read` only, `if: vars.WING_COMMANDER_METRICS_PAUSED != 'true'`, mirroring `wing-commander-8-watchdog.yml`'s `resolve` shape) producing one `run-id` from either the `workflow_run` event (`on.workflow_run.workflows`, matching each stage's exact `name:` field per this repo's own workflow_run-resolves-by-display-name convention) or a `workflow_dispatch` `run-id` input; `persist` job calling `metrics-persist.yml` with `destination-branch: ${{ vars.WING_COMMANDER_METRICS_BRANCH || 'metrics' }}`, `destination-path: ${{ vars.WING_COMMANDER_METRICS_PATH || 'records.jsonl' }}`, `secrets: inherit`.

**Checkpoint**: User Stories 1 AND 2 both work independently — persist a run, `git fetch origin metrics && git show origin/metrics:records.jsonl`, confirm one line per agent run, no other branch touched, and a repeat dispatch leaves the line count unchanged (quickstart.md Story 2).

---

## Phase 5: User Story 3 - A specification's total spend is legible from its lifecycle issue (Priority: P2)

**Goal**: Each stage's status comment carries a compact per-run cost line;
one rolling cumulative summary in a machine-owned issue-comment region
stays current, derived from the same persisted records.

**Independent Test**: Take one specification through several stages,
confirm each stage's status comment carries a cost line, one rolling
summary shows the cumulative total, the two agree, and a repeat rollup
update produces no duplicate line or second summary (quickstart.md Story 3).

### Implementation for User Story 3

- [ ] T023 [US3] Define the per-run cost-line Markdown fragment (data-model.md "Rollup — per-run cost line"), e.g. `**Cost**: $0.42 · 38/60 turns · claude-sonnet-5`, built from the same `wing-commander-metrics-summary` outputs each call site already has in hand, degrading to naming which figures are unavailable rather than omitting the line.
- [ ] T024 [P] [US3] In `.github/workflows/clarify.yml`, append the T023 cost line to the body of the status comment this stage already posts (no new comment — FR-031c). Depends on T006 (same file, same job).
- [ ] T025 [P] [US3] Same change as T024 in `.github/workflows/cleanup.yml`. Depends on T007.
- [ ] T026 [P] [US3] Same change as T024 in `.github/workflows/finalize.yml`. Depends on T008.
- [ ] T027 [P] [US3] Same change as T024 in `.github/workflows/implement.yml`, at each of its three status-comment sites. Depends on T009.
- [ ] T028 [P] [US3] Same change as T024 in `.github/workflows/intake.yml`. Depends on T010.
- [ ] T029 [P] [US3] Same change as T024 in `.github/workflows/plan.yml`. Depends on T011.
- [ ] T030 [P] [US3] Same change as T024 in `.github/workflows/pr-conversation.yml`, at both sites. Depends on T012.
- [ ] T031 [P] [US3] Same change as T024 in `.github/workflows/rebase.yml`. Depends on T013.
- [ ] T032 [P] [US3] Same change as T024 in `.github/workflows/tasks.yml`. Depends on T014. (`watchdog.yml`'s diagnose site is excluded — contracts/emission-contract.md: it posts to a findings issue, not a spec lifecycle issue.)
- [ ] T033 [US3] In the T016-T020 composite/T021 workflow, after a successful append, implement the rollup computation (research.md R9): resolve this run's `spec_dir` from the just-appended records' `spec.spec_dir`/`identity_available`, re-read `destination-path` filtered to that `spec_dir`, and recompute cumulative totals (cost/tokens summed by stage, run count) — skip this step entirely when no persisted record from this run carries spec identity.
- [ ] T034 [US3] In the same place, implement the machine-owned comment region (research.md R10, data-model.md "Rollup — cumulative summary"): search the lifecycle issue's comments via `gh api repos/{owner}/{repo}/issues/{issue}/comments` (paginated) for the `<!-- wing-commander-metrics-rollup:begin -->` marker; PATCH it in place (`gh api --method PATCH .../issues/comments/{id}`) if found, else create a new comment; regenerate the full region every update — totals table by stage, an "Incomplete: N of M runs..." notice when any contributing record has an unavailable cost/token field (FR-030), and the per-run `<details>` history list.
- [ ] T035 [US3] In the same region-builder, implement per-run history de-dup: parse the existing region's history list back out of the previous comment body before regenerating, keep every line whose `record_key` token is already present untouched, and append exactly one new line per `record_key` this update introduces — matching `finalize.yml`'s structured-field dedup discipline (never string-matching rendered Markdown), so a repeated rollup update for the same agent run leaves one cost line and one rolling summary (FR-031b).

**Checkpoint**: All three of Stories 1-3 work together — a spec's lifecycle issue shows per-run cost lines and one rolling cumulative summary that agree, updating without duplication as further stages complete (quickstart.md Story 3).

---

## Phase 6: User Story 4 - Future transcripts stop expiring on a ninety-day clock (Priority: P2)

**Goal**: Every existing transcript `upload-artifact` step declares
`retention-days: 90` explicitly instead of inheriting the repository
default.

**Independent Test**: Inspect every transcript upload site and confirm each
declares a retention period; confirm a new undeclared site fails a check
(quickstart.md Story 4 — the check itself ships in Phase 7/T055).

### Implementation for User Story 4

- [ ] T036 [P] [US4] In `.github/workflows/auto-update-spec-kit.yml`, add `retention-days: 90` to all three `claude-execution-output-*` (`-evaluate-path`, `-e2e-stage`, `-comment-reply`) `upload-artifact` steps.
- [ ] T037 [P] [US4] In `.github/workflows/clarify.yml`, add `retention-days: 90` to its `claude-execution-output` `upload-artifact` step. Depends on T006 (same file).
- [ ] T038 [P] [US4] Same change as T037 in `.github/workflows/cleanup.yml`. Depends on T007.
- [ ] T039 [P] [US4] Same change as T037 in `.github/workflows/finalize.yml`. Depends on T008.
- [ ] T040 [P] [US4] In `.github/workflows/implement.yml`, add `retention-days: 90` to all three `claude-execution-output-cycle`/`-retry`/`-progress` steps. Depends on T009.
- [ ] T041 [P] [US4] Same change as T037 in `.github/workflows/intake.yml`. Depends on T010.
- [ ] T042 [P] [US4] Same change as T037 in `.github/workflows/plan.yml`. Depends on T011.
- [ ] T043 [P] [US4] In `.github/workflows/pr-conversation.yml`, add `retention-days: 90` to both `claude-execution-output-classify` and `claude-execution-output-act-${{ strategy.job-index }}` steps. Depends on T012.
- [ ] T044 [P] [US4] Same change as T037 in `.github/workflows/rebase.yml` (`claude-execution-output-${{ matrix.slug }}`). Depends on T013.
- [ ] T045 [P] [US4] Same change as T037 in `.github/workflows/tasks.yml`. Depends on T014.
- [ ] T046 [P] [US4] Same change as T037 in `.github/workflows/watchdog.yml`'s `claude-execution-output-diagnose` step. Depends on T015.

**Checkpoint**: All 16 discovered transcript upload sites (T036-T046) declare `retention-days: 90`; none of the 453 pre-existing artifacts are claimed to be rescued (FR-035).

---

## Phase 7: User Story 5 - The layer split and every failure branch are enforced by checks, not by review (Priority: P2)

**Goal**: Five new fixture-backed gates close the `.github/actions/**`
layer-split gap, assert schema conformance and unknown-version tolerance,
drive the contention-retry loop, and assert every discovered transcript
upload site declares retention — each wired into the existing gate
registry, none suppressible by an unrelated gate's failure.

**Independent Test**: Reintroduce each defect (ambient state, a decided
destination, a non-conforming record, an undeclared retention) in turn and
confirm each turns its gate red; confirm all five pass against the correct
tree (quickstart.md Story 5).

### Implementation for User Story 5

- [ ] T047 [P] [US5] Create `.github/scripts/verify-actions-layer-invariants.py`: scan every `action.yml` under `.github/actions/**` for `github.event.*`/`vars.*` reads (mirroring `verify-stage-invariants.py`'s existing regex approach, extended to the actions directory it doesn't cover today — issue #149) and for `uses: anthropics/claude-code-action` (FR-040a); support a waiver file for pre-existing, unrelated violations (same shape as `stage-invariant-waivers.json`: exact file/pattern match, exact count, staleness-checked) but require zero violations, waived or not, in this feature's own new/changed files (`wing-commander-metrics-summary/action.yml`'s additions, `wing-commander-metrics-persist/action.yml`).
- [ ] T048 [P] [US5] Add fixtures for T047 under `.github/scripts/fixtures/actions-layer-invariants/`: an `action.yml` snippet reading `vars.SOMETHING`, and one invoking `claude-code-action`; assert the gate fails and names both.
- [ ] T049 [P] [US5] Create `.github/scripts/verify-metrics-record-schema.py`: validate a JSON file against contracts/metrics-record-schema.md's field table (types, presence, the `*_available` convention) and the `per_model` sum invariant, rejecting and naming the failing field(s).
- [ ] T050 [P] [US5] Add fixtures for T049 under `.github/scripts/fixtures/metrics-record-schema/`: a well-formed schema-version-1 record (positive case); a record missing a required field, one with a wrong-typed field, and one with a renamed field (negative cases); a multi-model record whose `per_model` sums correctly and one whose sums are wrong (invariant case).
- [ ] T051 [P] [US5] Create `.github/scripts/verify-metrics-schema-version-tolerance.py`: run a fixture record declaring `schema_version: 2` through the same retain-and-skip logic T018's persistence composite implements (a harness driving equivalent logic, since the composite itself is bash) and assert it is retained in a fixture store and excluded from a fixture rollup computation — never dropped, rewritten, or erroring.
- [ ] T052 [P] [US5] Add a fixture for T051 under `.github/scripts/fixtures/metrics-schema-version-tolerance/`: a `schema_version: 2` record plus the small fixture store/rollup computation it is run against.
- [ ] T053 [P] [US5] Create `.github/scripts/verify-metrics-persist-retry.sh`: drive T020's append-with-retry composite logic against a local bare git repository fixture with two simulated concurrent writers (one push accepted, the second's initial push rejected then retried), asserting both writers' records survive; a second fixture engineered to reject every attempt asserts the step fails loudly, naming every unwritten `record_key`, rather than hanging or succeeding silently.
- [ ] T054 [P] [US5] Add fixtures for T053 under `.github/scripts/fixtures/metrics-persist-retry/`: the local bare-repo setup for the eventually-successful race and for the sustained-contention exhaustion case.
- [ ] T055 [P] [US5] Create `.github/scripts/verify-transcript-retention-declared.py`: discover every `upload-artifact` step across `.github/workflows/*.yml` whose `path` matches the transcript or metrics-record filename pattern (glob + parse — not the hardcoded "16," which itself must not recur as a silent gap) and assert `retention-days: 90` is present at each, failing and naming the exact file/step when absent (FR-032/FR-033/SC-010).
- [ ] T056 [P] [US5] Add a fixture for T055 under `.github/scripts/fixtures/transcript-retention/`: a workflow snippet with a transcript-pattern `upload-artifact` step and no `retention-days`, asserting the gate fails and names the file/step.
- [ ] T057 [US5] Wire all five gates (T047, T049, T051, T053, T055) into `.github/workflows/lint-workflows.yml`: one `run:` line each inside a PR-triggered job, gated `if: !cancelled()` (not bare `always()`, matching this repository's step-gating convention) and not conditional on any other gate's outcome, so `verify-gate-wiring.py` and `run-local-gates.py` pick each up automatically with no separate registration. Depends on T047-T056.
- [ ] T058 [US5] In the same file's `pull_request.paths` list, add `specs/043-durable-metrics-record/contracts/metrics-record-schema.md` (alongside the existing per-spec contract entries) so an edit to the schema document alone triggers T049's gate (FR-040's explicit callout that the literal path list doesn't cover contract/schema documents by default). Depends on T057 (same file).

**Checkpoint**: All five user stories are independently functional and enforced. `python3 .github/scripts/run-local-gates.py` passes against the correct tree and each gate's own negative fixture turns that one gate red (quickstart.md Story 5).

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T059 [P] Run quickstart.md's five story validations end-to-end against a disposable test repository (or this repository with cleanup per its "Cleanup" section) — confirm no leftover `metrics` branch or rollup comments remain from the exercise.
- [ ] T060 [P] Confirm FR-036 non-regression across every changed published action/workflow (`wing-commander-metrics-summary`, and every file touched in T006-T046): no existing input, output, or secret was removed or renamed; a caller passing none of the new optional inputs still gets a valid record degraded only in those fields, and the rendered `$GITHUB_STEP_SUMMARY` table is byte-for-byte unchanged (FR-011).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** and **Foundational (Phase 2)**: no tasks — proceed directly to Phase 3.
- **User Story 1 (Phase 3)**: no dependencies on other stories. Must complete before Stories 2, 3, and (for the per-file tasks) before the matching Story 4 file edits, since several tasks touch the same files.
- **User Story 2 (Phase 4)**: depends on User Story 1 existing (persists the records US1 emits) but is independently testable once T001-T005 (the action's record-writing logic) land, even before every call site in T006-T015 is updated.
- **User Story 3 (Phase 5)**: depends on User Story 1 (the per-run cost line needs US1's outputs, T024-T032 depend on their matching T006-T015 file edit) and User Story 2 (the cumulative summary is computed inside the persistence workflow, T033-T035 depend on T016-T022).
- **User Story 4 (Phase 6)**: independent of Stories 1-3's *behavior*, but several of its tasks (T037-T046) share files with User Story 1's tasks (T006-T015) and should land after them to avoid overlapping edits to the same steps.
- **User Story 5 (Phase 7)**: its gate scripts and fixtures (T047-T056) can be written in parallel with Stories 1-4 since they test against contracts/fixtures, not against the call-site edits directly — but wiring (T057-T058) and a meaningful "passes against the correct tree" run depend on Stories 1-4's code existing.
- **Polish (Phase 8)**: depends on all five stories being complete.

### Parallel Opportunities

- T002-T005 are sequential (same file, same step block) — no [P].
- T006-T015 (10 files) are fully parallel — different files.
- T016-T020 are sequential (same new composite file, one behavior builds on the last).
- T024-T032 (9 files) are parallel with each other; each depends on its matching T006-T015 task in the same file.
- T036-T046 (11 files) are parallel with each other; each (except T036, a file no other story touches) depends on its matching T006-T015 task in the same file.
- T047-T056 (5 gate scripts + their fixtures) are fully parallel with each other and with Stories 1-4.
- T057-T058 are sequential (same file, `lint-workflows.yml`).

---

## Parallel Example: User Story 1 call-site rollout

```bash
# After T001-T005 land (the action's own new inputs/outputs/logic), launch
# all ten file edits together:
Task: "Wire stage/spec-dir/spec-issue inputs + upload metrics-record in clarify.yml"
Task: "...in cleanup.yml"
Task: "...in finalize.yml"
Task: "...in implement.yml (3 sites)"
Task: "...in intake.yml"
Task: "...in plan.yml"
Task: "...in pr-conversation.yml (2 sites)"
Task: "...in rebase.yml"
Task: "...in tasks.yml"
Task: "...in watchdog.yml (diagnose site)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 3 (T001-T015): every agent step emits a structured
   record alongside its transcript.
2. **STOP and VALIDATE**: quickstart.md Story 1 — download a `metrics-record*`
   artifact, confirm it matches contracts/metrics-record-schema.md and
   agrees with the rendered summary.
3. This alone is deployable: no consuming repository's behavior changes,
   nothing is persisted yet, and FR-002/FR-008 hold with zero configuration.

### Incremental Delivery

1. Story 1 (Phase 3) → records exist, nothing is durable yet.
2. Story 2 (Phase 4) → records survive artifact retention (the tier the
   requester said matters most if only one ships).
3. Story 3 (Phase 5) → a spec's spend is legible from its lifecycle issue.
4. Story 4 (Phase 6) → the retention mitigation ships independently of the
   above three (can be sequenced anytime after Story 1's per-file edits to
   avoid file conflicts, or before them, or in parallel by a different
   implementer working from a fresh checkout).
5. Story 5 (Phase 7) → the whole feature is enforced by gates, not review.
6. Phase 8 → end-to-end validation and non-regression check.

### Parallel Team Strategy

With multiple implementers: one completes Phase 3 first (it is the shared
foundation); once T001-T005 land, the ten Phase 3 file tasks, the Phase 6
retention tasks, and all five Phase 7 gate/fixture tasks can proceed in
parallel across different people. Phase 4 (the new composite/workflow/wrapper)
and Phase 5 (the rollup, which builds on Phase 4) are best kept to one
implementer each, since their tasks are mostly sequential within a small
set of new files.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- Every task above names its exact file path(s); none is a placeholder.
- The 13-site (`metrics-summary` call sites) vs. 16-site (transcript
  uploads) counts are measured in this checkout, not the plan's approximate
  figures — re-measure with the greps at the top of this document if this
  branch has since diverged from `main`.
- Commit after each task or logical group; stop at any checkpoint to
  validate a story independently.
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that
  break independence beyond what is explicitly noted above.
