# Research: Parallel PR Lint

## R1 — Shard count and assignment
- **Decision**: 8 shard jobs (`lint-shard-1`…`lint-shard-8`), assigned once, at implement time, by greedy balancing on the 2026-11-24 measured per-gate durations (`run-local-gates.py` timing output), then frozen as step placement in the workflow. Keep gates that share a fixture or read each other's output in the same shard.
- **Rationale**: 2263 s / 8 ≈ 283 s per shard + ~60 s checkout/setup ≈ 6 min, leaving headroom under 10 min for runner queueing; the 156 s floor (Gate 97 self-test) fits. Fewer shards (4) ≈ 10 min with no margin; more adds setup overhead with little gain.
- **Alternatives**: run `run-local-gates.py` in one job (rejected by owner: collapses gates into one step); assign by gate number (rejected: numbers repeat and durations are uneven); a separate assignment table (forbidden by FR-007).

## R2 — Aggregate job
- **Decision**: job id `lint`, `name: lint`, `needs: [lint-shard-1…8, harness-tests]`, `if: always() && github.event_name == 'pull_request'`, one step that fails unless every `needs.<job>.result == 'success'`, printing each non-success job by name (FR-004, SC-005).
- **Rationale**: `always()` stops GitHub skipping the aggregate when a need fails or is skipped (readers count a skipped `lint` as green). On push/schedule/dispatch the event test skips it, as today. Units keep `if: github.event_name == 'pull_request'`, so main's run concludes success on its own jobs (`names-and-tags`).
- **Alternatives**: `!cancelled()` (rejected: a cancelled run would leave a skipped `lint`, which readers treat as green); matrix job (rejected: matrix check names carry suffixes, and per-job assignment would live in a list, not the layout).
- **Risk to prove**: when a newer push cancels a run (#1196), the `always()` aggregate must conclude cancelled or failure, never success/skipped. Covered by the aggregate gate's simulation and the post-merge `prove-after-merge` drill (SC-003). Pass through `review-step-gating` skill.

## R3 — FR-009 failure isolation
- **Decision**: every step except checkout and the aggregate's own gets `if: ${{ !cancelled() }}` (or the existing guard). A self-test step MAY additionally be guarded `steps.<gate id>.outcome != 'failure'`, paired by unique step name (FR-009 and contract item 7 make this optional). The shipped workflow adds no pair guards: a self-test runs fixtures, not the repository's state, so it still passes when its gate finds a real defect. Both steps go red only when the gate script itself is broken, and then both are accurate. `verify-lint-shard-layout.py` enforces the `!cancelled()` guard, and checks that any pair guard present names its own gate's id in the same unit.
- **Rationale**: 70 steps today are skipped by an earlier failure; sharding does not fix that alone.

## R4 — Step-name uniqueness
- **Decision**: rename the second `Gate 23 self-test — the detector actually detects`; update every gate that reads step names (found by grepping `lint-workflows.yml` consumers: `verify-gate-wiring.py`, `verify-gate-22/23*.py`, `wc_lint_gate_source.py`-based gates, `verify-lint-supersedes-pr-runs.py` which reads the single `lint` job's `if`).
- `wc_lint_gate_source.extract_gate_step` already iterates all jobs, so it needs no change; gates addressing `jobs["lint"]["steps"]` directly do.

## R5 — Per-shard setup
- **Decision**: any step in the old `lint` job that installs tools or builds a fixture used by later gates is moved into a shared composite under `.github/actions/` (internal) and called from each shard that needs it; the task list begins with an inventory of such steps.
- **Rationale**: single-home rule (CLAUDE.md).

## R6 — Local/CI equality (FR-005)
- **Decision**: `pr_time_gates` derives from `run:` text across all jobs whose `if:` admits pull_request; the aggregate job runs no gate script, so it adds nothing. New gate compares the derived list with the union of units' gate invocations by step name and fails on divergence; aggregate exempt by name.

## R7 — Decisions made without clarification
- Shard count 8 and balancing method (R1), `always()` aggregate (R2), and the rename in R4 were chosen here as plan-level choices; the spec bounds them (FR-002, FR-005–FR-008) but names none.
