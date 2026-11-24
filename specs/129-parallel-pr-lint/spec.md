# Feature Specification: Faster PR Lint — Parallelise the Gate Suite in CI

**Feature Branch**: `spec-draft/129-parallel-pr-lint`

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "Faster PR lint: parallelise the gate suite in CI (#1198). `lint-workflows.yml`'s pull-request run takes 21 to 31 minutes because the whole gate suite (~296 steps) runs sequentially in one `lint` job on one runner, while `run-local-gates.py` runs the same gates in parallel in ~10 minutes wall-clock against ~38 minutes summed. A dozen slow gates (mostly self-tests) take ~13 minutes between them; the rest is a long tail of ~280 short gates. Options: shard the job, run the suite through `run-local-gates.py` in CI, speed up the slowest gates, or a combination."

*Layer*: this spec describes the **consuming instrument** (constitution VII) — this repository's own PR-time gate suite in `lint-workflows.yml` and its local mirror `run-local-gates.py`. It changes no input, secret or output of the published `workflow_call` stage workflows.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A PR's lint verdict arrives in a fraction of today's time (Priority: P1)

A maintainer (or a pipeline stage) opens or pushes a pull request that touches workflows or scripts. Today the gate-suite check takes 21–31 minutes to report. After this feature, the same check reports a verdict within 10 minutes, and every gate that ran before still runs, against the same subject, with the same arguments.

**Why this priority**: The wait is the problem the issue names. Every PR that touches workflows or scripts, and every readiness decision that depends on the check (the review gate, the board loop), is blocked for the full duration.

**Independent Test**: Push a PR that touches a workflow; measure the time from the check starting to its final verdict across several runs and compare it with the 21–31 minute baseline; confirm the set of gates executed equals the set executed before the change.

**Acceptance Scenarios**:

1. **Given** a PR touching `.github/workflows/`, **When** the gate-suite check runs, **Then** its final verdict is reported within 10 minutes of wall-clock time (owner decision, 2026-11-24).
2. **Given** the gate suite before and after this change, **When** the executed gate identities are compared, **Then** no gate is dropped, duplicated, or run with different arguments.
3. **Given** any single gate fails, **When** the check completes, **Then** the overall check is red and the failing gate is identifiable by name.

---

### User Story 2 - Downstream consumers of the lint verdict keep working (Priority: P1)

The review gate's "gate suite green" readiness, the board loop's readiness check, the watchdog, metrics persistence (which resolves the workflow by display name) and any branch-protection required check all read the lint run's result today. After the split, each of them still receives one unambiguous, correct verdict for the PR head — green only when every gate passed.

**Why this priority**: A faster check that a readiness consumer can no longer find, or that reads green while a shard is still running or has failed, would break Principle VIII ("a green check means what it says") and stall or wrongly advance lifecycles.

**Independent Test**: On a test PR, make one gate in one partition fail; confirm every consumer reports "not ready"/red. Make all pass; confirm every consumer reports ready. Confirm no consumer reports ready while any partition is still in progress.

**Acceptance Scenarios**:

1. **Given** the suite is split across parallel units, **When** all units pass, **Then** a single aggregate verdict under a stable, documented name is green, and every existing consumer recognises it.
2. **Given** one unit fails, is cancelled, or is skipped unexpectedly, **When** the aggregate is computed, **Then** the aggregate is red (never green by omission).
3. **Given** one unit is still running, **When** a consumer polls readiness, **Then** it sees "not ready", not "green".

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

**Independent Test**: Break one gate on a test PR and time how long it takes to locate the failing gate's name and output from the run page.

**Acceptance Scenarios**:

1. **Given** a red run, **When** the maintainer opens it, **Then** the failing gate appears as its own failed step, by name, in the failing unit, with its output in that step's log.

---

### Edge Cases

- A partition is skipped because its `if:` is false or a needed job failed: the aggregate must treat "skipped" as not-passed unless the skip is the documented no-op case (e.g. path filters say nothing relevant changed).
- A newer push cancels the older head's run (#1196): cancelled units must not leave a stale green aggregate on either head.
- A gate depends on state produced by an earlier step in the same job (setup, a shared checkout, a built fixture): splitting must keep that dependency satisfied in every unit that needs it.
- Gates that read `lint-workflows.yml`'s own structure (step names, comments, order, byte-compared text): they must still find their subject after the restructure, or be updated in the same change; none may pass vacuously because its subject moved (constitution VIII).
- A gate is added later without being assigned to any unit: it must fail loudly rather than silently never run.
- Runner concurrency limits delay some units: the aggregate must wait, not time out to green.
- The slowest single gate (Gate 97 self-test, ~156s) sets a floor on any partition containing it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The PR-time gate suite MUST execute every gate it executes today, each against the same subject with the same arguments, after the change.
- **FR-002**: The suite MUST run with parallelism in CI such that a PR's final lint verdict arrives within 10 minutes of wall-clock time (owner decision, 2026-11-24; see User Story 1, scenario 1). The parallelism MUST come from sharding the suite into several jobs, each gate remaining its own step (FR-006).
- **FR-003**: The suite MUST expose exactly one aggregate verdict per PR head under a stable name that every current consumer (review-gate readiness, board-loop readiness, watchdog, metrics persistence, any branch-protection required check) recognises; any consumer that reads a name or structure that changes MUST be updated in the same change.
- **FR-004**: The aggregate verdict MUST be green only if every gate passed; a failed, cancelled, timed-out or unexpectedly skipped unit MUST make it red, and an in-progress unit MUST make it not-yet-green.
- **FR-005**: `run-local-gates.py` MUST continue to derive its gate list from the workflow, and the derived list MUST equal the set of gates CI runs on the same commit; a deterministic check MUST fail if they diverge.
- **FR-006**: A failing gate MUST be identifiable by name, with its output reachable, from the run. Every gate MUST remain its own step in the Actions UI (owner decision, 2026-11-24); an aggregated step with a per-gate report is not sufficient. `run-local-gates.py`'s derivation from the workflow's steps, the gate registry and the step-name checks MUST keep working against the sharded jobs.
- **FR-007**: Every gate MUST be assigned to exactly one parallel unit; a deterministic check MUST fail if any gate is unassigned or assigned twice.
- **FR-008**: Gates that read `lint-workflows.yml`'s own structure (step names, comments, order) MUST keep reaching their subject after the restructure and MUST NOT pass vacuously; each such gate MUST be identified and adapted in the same change.
- **FR-009**: A failure in one gate MUST NOT suppress another unrelated gate from running and reporting (constitution VIII).
- **FR-010**: The change MUST NOT alter the published `workflow_call` contract of any stage workflow.
- **FR-011**: `docs/reference.md` MUST be updated where it describes the lint job, its check name(s), or its limits.
- **FR-012**: Speeding up individual slow gates (Gate 97/155/41 self-tests, Gates 22, 9, 36, 79…) is out of scope for this spec; each such speed-up is a separate line on the Maintenance backlog (owner decision, 2026-11-24). The FR-002 target MUST be met by sharding alone.

### Key Entities

- **Gate**: one check in the PR-time suite, identified by its step name/number; has a subject, arguments, and a measured duration.
- **Parallel unit**: a shard — a job of `lint-workflows.yml` that runs a group of gates, each as its own step, on its own runner; every gate belongs to exactly one.
- **Aggregate verdict**: the single, stably named pass/fail result per PR head that consumers read.
- **Consumer**: any workflow, script or setting that reads the lint verdict (review gate, board loop, watchdog, metrics persistence, branch protection).
- **Gate registry / derivation**: the mechanism by which `run-local-gates.py` lists the gates from the workflow.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Over the first ten successful PR lint runs after merge, the median time to final verdict is 10 minutes or less (FR-002) and the maximum is no worse than 15 minutes (1.5× that target).
- **SC-002**: The set of gates executed per run is identical before and after the change (0 gates dropped, 0 duplicated), verified by comparing gate identities on the same commit.
- **SC-003**: In a deliberate-failure drill (one gate broken per unit, one unit cancelled), 100% of consumers report not-ready/red; in an all-pass run, 100% report ready.
- **SC-004**: The local runner's derived gate list matches CI's executed set on every commit, enforced by a gate that fails on divergence.
- **SC-005**: From a red run's page, the failing gate's name and output can be located in under one minute.

## Assumptions

- More parallel runner time is acceptable: this repository is public and its GitHub Actions minutes are free (issue's open question 6 is settled by this default; the owner can override in clarify).
- The aggregate verdict keeps the existing workflow display name `lint · workflows` as its stable name, so consumers that resolve by name (e.g. metrics persistence) keep working; any consumer that reads job- or step-level structure is updated in the same change.
- The mechanism is sharding into several jobs (owner decision, 2026-11-24); running the suite through the local runner's parallelism inside one job is not chosen, since it would collapse gates into one step. The assignment of gates to shards (fixed lists, by gate number, or balanced by measured duration) and the shard count are plan-level choices bounded by FR-002 and FR-005–FR-008.
- The slowest single gate (~156s) is well under the 10-minute target, so the target is reachable by sharding without slow-gate work (FR-012).
- #1196 (cancel the older head's lint run on a newer push) is complementary and remains in place.
- Measured durations (2026-11-24: 294 gates, 2262.7s summed, ~10 min wall-clock locally; twelve slowest steps ~13 min) are the baseline for sizing.
