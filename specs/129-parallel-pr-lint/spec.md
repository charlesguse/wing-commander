# Feature Specification: Faster PR Lint — Parallelise the Gate Suite in CI

**Feature Branch**: `spec-draft/129-parallel-pr-lint`

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "Faster PR lint: parallelise the gate suite in CI (#1198). `lint-workflows.yml`'s pull-request run takes 21 to 31 minutes because the whole gate suite (~296 steps) runs sequentially in one `lint` job on one runner, while `run-local-gates.py` runs the same gates in parallel in ~10 minutes wall-clock against ~38 minutes summed. A dozen slow gates (mostly self-tests) take ~13 minutes between them; the rest is a long tail of ~280 short gates. Options: shard the job, run the suite through `run-local-gates.py` in CI, speed up the slowest gates, or a combination."

Today the PR-time suite is two jobs of `lint-workflows.yml`: the `lint` job (291 steps) and the `harness tests` job (Gate 4 and the E2E provisioning tests, ~70s). Both are in the gate set `run-local-gates.py` derives.

*Layer*: this spec describes the **consuming instrument** (constitution VII) — this repository's own PR-time gate suite in `lint-workflows.yml` and its local mirror `run-local-gates.py`. It changes no input, secret or output of the published `workflow_call` stage workflows.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A PR's lint verdict arrives in a fraction of today's time (Priority: P1)

A maintainer (or a pipeline stage) opens or pushes a pull request that touches workflows or scripts. Today the gate-suite check takes 21–31 minutes to report. After this feature, the same check reports a verdict within 10 minutes, and every gate that ran before still runs, against the same subject, with the same arguments.

**Why this priority**: The wait is the problem the issue names. Every PR that touches workflows or scripts, and every readiness decision that depends on the check (the review gate, the board loop), is blocked for the full duration.

**Independent Test**: Push a PR that touches a workflow; measure, as SC-001 defines it, the time from the run starting to the aggregate `lint` check completing across several runs and compare it with the 21–31 minute baseline; confirm the set of gates executed equals the set executed before the change.

**Acceptance Scenarios**:

1. **Given** a PR touching `.github/workflows/`, **When** the gate-suite check runs, **Then** its final verdict is reported within 10 minutes of wall-clock time (owner decision, 2026-11-24).
2. **Given** the gate suite before and after this change, **When** the executed gate identities are compared, **Then** no gate is dropped, duplicated, or run with different arguments.
3. **Given** any single gate fails, **When** the check completes, **Then** the overall check is red and the failing gate is identifiable by name.

---

### User Story 2 - Downstream consumers of the lint verdict keep working (Priority: P1)

Two kinds of consumer depend on the lint run today.

- **Verdict readers** read the `lint` check-run's conclusion for the PR head, through the two `_gate_suite_green` copies. Each copy tests that the check-run's name equals `lint` and that its workflow name contains "workflow". The copies are `board_readiness.gate_suite_green`, which the board loop's readiness check and the merge-evidence audit (spec 125) call; and `lifecycle_readiness`'s copy, which feeds the review gate's `select_prefilter`, the lifecycle merge preconditions (`evaluate_from_snapshot`, the "gate suite ran green on that SHA" gate in constitution X), and, for lifecycle merges, the merge-evidence audit as well, through `lifecycle_merge_preconditions.gate_suite_green_in_rollup`. Any branch-protection required check on `lint` is a verdict reader too.
- **The board-status report** (`wc_board_status.py`) must keep working but reports no readiness. It finds main's CI by the workflow file `lint-workflows.yml`, reading the latest run on main whose event is not `pull_request` and calling main green when that run concluded success. Its "no run found" message names the workflow `lint · workflows`.

After the split, each verdict reader still receives one unambiguous, correct verdict for the PR head — green only when every gate passed — and the board-status report still reads main's run.

**Why this priority**: A faster check that a readiness consumer can no longer find, or that reads green while a shard is still running or has failed, would break Principle VIII ("a green check means what it says") and stall or wrongly advance lifecycles.

**Independent Test**: On a test PR, make one gate in one partition fail; confirm every verdict reader reports "not ready"/red. Make all pass; confirm every verdict reader reports ready. Confirm no verdict reader reports ready while any partition is still in progress. Confirm the board-status report still reads main's run, and that main's push or scheduled run concludes success when its own jobs pass.

**Acceptance Scenarios**:

1. **Given** the suite is split across parallel units, **When** all units pass, **Then** a single aggregate verdict — the check-run named `lint` in the workflow named `lint · workflows` — is green, and every verdict reader recognises it.
2. **Given** a `pull_request` run in which one unit fails, is cancelled, or is skipped, **When** the aggregate is computed, **Then** the aggregate concludes failure (never success, skipped or neutral, so never green by omission).
3. **Given** one unit is still running, **When** a consumer polls readiness, **Then** it sees "not ready", not "green".
4. **Given** a `push`, `schedule` or `workflow_dispatch` run of `lint-workflows.yml`, **When** it completes, **Then** the PR-time units and the aggregate are skipped, as `lint` is today, and do not change the run's conclusion: the run concludes success when its own jobs pass.

---

### User Story 3 - Local and CI suites stay the same suite (Priority: P2)

A maintainer runs `python .github/scripts/run-local-gates.py` before pushing. It must still derive exactly the gate set CI runs, from the workflow itself, so that "green locally" continues to predict "green in CI".

**Why this priority**: CLAUDE.md and constitution VIII both require local and CI to run the same subject with the same arguments; the derivation from `lint-workflows.yml` is the mechanism, and any restructuring of the workflow can silently break it.

**Independent Test**: Compare the gate list `run-local-gates.py` derives after the change with the list CI executes on the same commit; they must be identical. Add a new gate to one partition and confirm the local runner picks it up with no extra edit.

**Acceptance Scenarios**:

1. **Given** the restructured workflow, **When** the local runner derives its gate list, **Then** it equals the union of gates across all CI units.
2. **Given** a gate is added to, moved between, or removed from a unit, **When** the local runner runs, **Then** its list reflects the change without a second edit elsewhere.

---

### User Story 4 - A failing gate is still easy to find (Priority: P2)

When the check is red, a maintainer or agent opens the run and finds which gate failed and its output without reading a 296-step log end to end.

**Why this priority**: Diagnosis speed matters; the owner chose (2026-11-24) that every gate stays its own step in the Actions UI (see FR-006).

**Independent Test**: Break one gate on a test PR; confirm that gate's step is the one marked failed in its unit's job, with its output in that step's log, and that the aggregate `lint` check names the failed unit.

**Acceptance Scenarios**:

1. **Given** a red run, **When** the maintainer opens it, **Then** the aggregate `lint` check names the failed unit, and the failing gate appears as its own failed step, by name, in that unit's job, with its output in that step's log.

---

### Edge Cases

- In a `pull_request` run, a partition is skipped because its `if:` is false or a needed job failed: the aggregate must treat "skipped" as not-passed, with no exception. The `paths:` filter decides whether the PR run exists at all; there is no in-run path filter, so a skipped unit inside a PR run is never a legitimate no-op.
- On `push`, `schedule` and `workflow_dispatch` runs, the PR-time units and the aggregate are skipped, as `lint` and `harness tests` are today. That is the intended outcome on those events and must not make the run conclude failure, because the board-status report reads exactly that conclusion for main's CI.
- In a `pull_request` run, the aggregate itself would be skipped by default when a unit it needs fails: it must still run and conclude failure, because both verdict readers count a skipped or neutral `lint` check as green.
- A newer push cancels the older head's run (#1196): cancelled units must not leave a stale green aggregate on either head.
- A gate depends on state produced by an earlier step in the same job (setup, a shared checkout, a built fixture): splitting must keep that dependency satisfied in every unit that needs it.
- Gates that read `lint-workflows.yml`'s own structure (step names, comments, order, byte-compared text): they must still find their subject after the restructure, or be updated in the same change; none may pass vacuously because its subject moved (constitution VIII).
- A gate is added later in a job the aggregate does not cover: it must fail loudly rather than silently never run or never count toward the verdict.
- Runner concurrency limits delay some units: the aggregate must wait, not time out to green.
- The slowest single gate (Gate 97 self-test, ~156s) sets a floor on any partition containing it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The PR-time gate suite MUST execute every gate it executes today, each against the same subject with the same arguments, after the change.
- **FR-002**: The suite MUST run with parallelism in CI such that a PR's final lint verdict arrives within 10 minutes of wall-clock time (owner decision, 2026-11-24; see User Story 1, scenario 1). The parallelism MUST come from sharding the suite into several jobs, each gate remaining its own step (FR-006).
- **FR-003**: The suite MUST expose exactly one aggregate verdict per PR head. Three identifiers MUST be kept. The job-level check-run name `lint` is what both `_gate_suite_green` copies match exactly. The workflow name `lint · workflows` is kept because both copies require the workflow name to contain "workflow", and because the board-status report's "no run found" message and the docs use that name. The workflow file `lint-workflows.yml` is the key the board-status report resolves main's runs by, so the aggregate verdict and every unit MUST stay in that one workflow file. The aggregate MUST be the only check-run in the run named `lint`; no unit may carry that name. Every verdict reader MUST recognise it unchanged. They are `board_readiness.gate_suite_green` and its callers (the board loop's readiness check, the merge-evidence audit of spec 125); `lifecycle_readiness`'s copy and its callers (the review gate's `select_prefilter`, the lifecycle merge preconditions in `evaluate_from_snapshot`, and the merge-evidence audit for lifecycle merges via `lifecycle_merge_preconditions.gate_suite_green_in_rollup`); and any branch-protection required check. The board-status report MUST keep reading main's run. If the plan finds any of these identifiers cannot be kept, every reader of it MUST be changed in the same PR.
- **FR-004**: In a `pull_request` run, the aggregate verdict MUST be green only if every gate passed; a failed, cancelled, timed-out or skipped unit MUST make it red, and an in-progress unit MUST make it not-yet-green. In a `pull_request` run the aggregate check itself MUST NOT conclude skipped or neutral when any unit did not succeed; it concludes failure. On `push`, `schedule` and `workflow_dispatch` runs, the PR-time units and the aggregate are skipped, as `lint` is today, and MUST NOT change the run's conclusion, so the board-status report's read of main's CI stays green when the run's own jobs pass.
- **FR-004a**: The `harness tests` job (Gate 4 and the E2E provisioning tests) is one of the units under the aggregate: in a `pull_request` run its failure, cancellation or skip makes the aggregate red, so the `lint` verdict covers the whole PR-time suite on its own and does not rely on a separate all-checks condition.
- **FR-005**: `run-local-gates.py` MUST continue to derive its gate list from the workflow, and the derived list MUST equal the set of gates CI runs on the same commit; a deterministic check MUST fail if they diverge.
- **FR-006**: A failing gate MUST be identifiable by name, with its output reachable, from the run. Every gate MUST remain its own step in the Actions UI (owner decision, 2026-11-24); an aggregated step with a per-gate report is not sufficient. `run-local-gates.py`'s derivation from the workflow's steps, the gate registry and the step-name checks MUST keep working against the sharded jobs.
- **FR-007**: Every gate MUST be in exactly one parallel unit. The workflow's job layout — which job a gate's step sits in — MUST be the single record of that assignment (CLAUDE.md's single-home rule; constitution VIII's "derived, not listed"); no separate assignment table or list may exist. A deterministic check, derived from that layout the way `pr_time_gates` is, MUST fail if a PR-time job is not a unit under the aggregate or a gate appears in more than one unit. The aggregate job itself is exempt by name from "every PR-time job is a unit": it is not a gate and not a unit, and it is not in the gate set FR-005 compares.
- **FR-008**: Gates that read `lint-workflows.yml`'s own structure (step names, comments, order) MUST keep reaching their subject after the restructure and MUST NOT pass vacuously; each such gate MUST be identified and adapted in the same change.
- **FR-009**: A failure in one gate MUST NOT suppress another unrelated gate from running and reporting (constitution VIII). This is a change from today, not a preservation of it: 70 of the `lint` job's 291 steps (starting with Gates 2, 3, 5, 6, 7, 8 and 9) carry no `!cancelled()` guard and are skipped by any earlier failure in the job. After the change, every step in every unit except setup (checkout) MUST run after an unrelated failure in its own unit or any other. This covers unnumbered steps such as "Parse YAML and bash -n every run block" as well as numbered gates. The one allowed exception is a self-test step, which MAY be skipped when the gate step it tests failed; it MUST still run after the failure of any other step. A self-test is paired with its gate step by step name, not by gate number, since gate numbers repeat (there are two Gate 22 and two Gate 23 steps). FR-001's "every gate it executes today" names the gate set, not today's skip behaviour.
- **FR-010**: The change MUST NOT alter the published `workflow_call` contract of any stage workflow.
- **FR-011**: `docs/reference.md` MUST be updated where it describes the lint job, its check name(s), or its limits.
- **FR-012**: Speeding up individual slow gates (Gate 97/155/41 self-tests, Gates 22, 9, 36, 79…) is out of scope for this spec; each such speed-up is a separate line on the Maintenance backlog (owner decision, 2026-11-24). The FR-002 target MUST be met by sharding alone.

### Key Entities

- **Gate**: one check in the PR-time suite, identified by its step name, which is unique (gate numbers are not); has a subject, arguments, and a measured duration.
- **Parallel unit**: a shard — a PR-time job of `lint-workflows.yml` that runs a group of gates, each as its own step, on its own runner; every gate belongs to exactly one, and the job it sits in is the only record of which. `harness tests` is one.
- **Aggregate verdict**: the single pass/fail result per PR head, the check-run named `lint` in the workflow named `lint · workflows` (file `lint-workflows.yml`). It is a job but neither a gate nor a unit.
- **Verdict reader**: a script or setting that reads the aggregate's conclusion: both `_gate_suite_green` copies and their callers (board-loop readiness, the merge-evidence audit of spec 125, which reads both copies, the review gate's `select_prefilter`, the lifecycle merge preconditions), and any branch-protection required check.
- **Board-status report**: `wc_board_status.py`, which reports main's CI from the latest non-`pull_request` run of `lint-workflows.yml` on main, found by file name, and reports no readiness.
- **Gate registry / derivation**: the mechanism by which `run-local-gates.py` lists the gates from the workflow.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each of the first ten successful first-attempt (`run_attempt == 1`) `pull_request` runs of `lint · workflows` after merge, the time from the run's `run_started_at` to the aggregate `lint` check-run's `completed_at`, both read from the GitHub Actions API, is 10 minutes or less (FR-002; owner decision, 2026-11-24). Runs that conclude red or cancelled, and re-run attempts, are not counted.
- **SC-002**: The set of gates executed per run is identical before and after the change (0 gates dropped, 0 duplicated), verified by comparing gate identities (unique step names) on the same commit.
- **SC-003**: In a deliberate-failure drill (one gate broken per unit, one unit cancelled), 100% of verdict readers report not-ready/red; in an all-pass run, 100% report ready. In both runs, the board-status report still reads main's run: main's push or scheduled run concludes success when its own jobs pass.
- **SC-004**: The local runner's derived gate list matches CI's executed set on every commit, enforced by a gate that fails on divergence.
- **SC-005**: In a red run with one gate broken, that gate's step is the one marked failed in its unit's job, with its output in that step's log, and the aggregate `lint` check names the failed unit.

## Assumptions

- More parallel runner time is acceptable: this repository is public and its GitHub Actions minutes are free (issue's open question 6 is settled by this default; the owner can override in clarify).
- The aggregate verdict keeps the identifiers consumers resolve today: the check-run name `lint` (both `_gate_suite_green` copies match it), the workflow name `lint · workflows` (both copies require "workflow" in it; the board-status message and the docs use it) and the workflow file `lint-workflows.yml` (the board-status report's key). Metrics persistence does not read the lint run. Any other consumer that reads job- or step-level structure is updated in the same change (FR-003).
- The mechanism is sharding into several jobs (owner decision, 2026-11-24); running the suite through the local runner's parallelism inside one job is not chosen, since it would collapse gates into one step. The assignment of gates to shards (fixed lists, by gate number, or balanced by measured duration) and the shard count are plan-level choices bounded by FR-002 and FR-005–FR-008.
- The slowest single gate (~156s) is well under the 10-minute target, so the target is reachable by sharding without slow-gate work (FR-012).
- #1196 (cancel the older head's lint run on a newer push) is complementary and remains in place.
- Measured durations (2026-11-24: 294 gates, 2262.7s summed, ~10 min wall-clock locally; twelve slowest steps ~13 min) are the baseline for sizing.
