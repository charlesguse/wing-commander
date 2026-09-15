# Contract: Gate coverage for the four new collectors (SC-002)

Six new deterministic gates, each following constitution VIII's
requirements (reachable through the gate registry, same subject/arguments
locally and in CI, triggered by the tree it checks, fails loudly rather
than passing vacuously, not suppressible by an unrelated gate, every
failure branch fixture-backed). Gate numbers are assigned sequentially at
implementation time (research.md R12) — this contract names each gate by
script, not number, to stay stable regardless of what other in-flight
specs claim first.

| Script | Subject | Positive fixture(s) | Negative / failure-branch fixture(s) |
|---|---|---|---|
| `verify-turn-budget-collector.sh` | `collect-turn-budget`'s band computation and per-run signal gating (FILTER extracted live from watchdog.yml, not a hand copy) | Climbing history → `critical`; consecutive-only history → `watch`; climb-only history → `elevated` | Under-both-thresholds history → no cross-run signal; `turns.available: false` → no per-run signal, outcome `ok`; a `skipped`/`cancelled` run → no signal (attribution invariant); boundary: `counted-turns` exactly equal to `intended-budget` → still emits a per-run signal; boundary: window's max consumed-ceiling-fraction exactly equal to `climb_fraction` (0.6) → still produces band `elevated` |
| `verify-turn-budget-suppression.sh` | The closed-fingerprint pre-check (`contracts/turn-budget-trend.md`) | Same band as a closed issue → suppressed; escalated band vs. a closed lower-band issue → emits | Same band as an *open* issue → still emits (accumulation is `Dedup search`'s job, not the collector's); collector's copied hash/fingerprint formula, and its `gh issue list --state` flag, diffed against the live `Stamp signal ids`/`Compute fingerprint`/suppression-precheck text (mirrors gate 5's drift guard) |
| `verify-cost-report-collector.sh` | `collect-cost-report`'s missing/malformed detection (FILTER extracted live from watchdog.yml, not a hand copy) | `cost_available: true` + no attributable comment → `cost-line-missing`; a literal `$COST_LINE` leak → `cost-line-malformed` | `cost_available: false` → no signal; well-formed `$1.42` → no signal; well-formed sub-$1 `$0.0042` (4dp) → no signal (research.md R8's magnitude-aware pattern); boundary: exactly `$1.00`, the 2dp/4dp magnitude crossover → no signal |
| `verify-final-pr-claims-collector.sh` | `collect-final-pr-claims`'s full shipped step, executed directly with `gh` stubbed (`wc_shell_harness.find_step`/`run_step`), not fixtured via copies of its parsers | A task-count mismatch; a commit-count mismatch; a test-count (fixture-file-count) mismatch | An unparseable claim shape → no signal; all three claims matching → no signal; a non-finalize run → no signal before any write (scope guard); no PR resolvable → outcome `ok`, no signal; `gh pr view` failure → outcome `failed`, collector-outcomes record still written; a `tasks.md` with zero checked boxes → does not abort the step (#274 fold leg-0) and still compares against the real actual value; an empty PR body → no claims parsed, no signal regardless of actual values |
| `verify-narrative-drift-routing.sh` | The new `Determine issue-filing eligibility` step, executed directly (`wc_shell_harness.find_step`/`run_step`), not a hand copy of its if/else | A `narrative-drift` Finding → `issueless: true`, `Ensure pipeline-defect issue` skipped, `Report finding to lifecycle issue` still runs and posts | Any other class → `issueless` unset/false, normal issue-filing path unaffected |
| `verify-spec-collision-collector.sh` | `collect-spec-collision`'s claimant enumeration and dedup-by-identity (FILTER extracted live from watchdog.yml, not a hand copy) | Two open PRs sharing a number → collision; an open PR matching a `main` directory → collision | Every open PR distinct → no signal; a PR observed twice (same run re-inspected) → not a self-collision (FR-028); a non-intake run → no signal (scope guard) |

## Registration

Each script is wired into `lint-workflows.yml` with exactly one `run:`
line, discoverable via `wc_gate_registry.py`'s existing derivation — no
second registration point, matching every existing gate's convention.
Each gate is re-runnable locally via `run-local-gates.py`, satisfying
this repository's "before pushing" CLAUDE.md requirement without any new
tooling.

## What is explicitly not covered by a fixture

`diagnose`'s own judgment (whether a `class-hint: null` per-run
turn-budget signal, cited alongside a trend signal, is described
accurately in a Finding's prose) is not fixture-tested, matching every
existing collector's boundary — these gates validate the deterministic
code this feature adds, not the model's output. `quickstart.md` covers
end-to-end validation of the full path including a real `diagnose` run.
