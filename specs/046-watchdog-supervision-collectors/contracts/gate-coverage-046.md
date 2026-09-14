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
| `verify-turn-budget-collector.sh` | `collect-turn-budget`'s band computation and per-run signal gating | Climbing history → `critical`; consecutive-only history → `watch`; climb-only history → `elevated` | Under-both-thresholds history → no cross-run signal; `turns.available: false` → no per-run signal, outcome `ok`; a `skipped`/`cancelled` run → no signal (attribution invariant) |
| `verify-turn-budget-suppression.sh` | The closed-fingerprint pre-check (`contracts/turn-budget-trend.md`) | Same band as a closed issue → suppressed; escalated band vs. a closed lower-band issue → emits | Same band as an *open* issue → still emits (accumulation is `Dedup search`'s job, not the collector's); collector's copied hash/fingerprint formula diffed byte-for-byte against the live `Stamp signal ids`/`Compute fingerprint` steps (mirrors gate 5's drift guard) |
| `verify-cost-report-collector.sh` | `collect-cost-report`'s missing/malformed detection | `cost_available: true` + no attributable comment → `cost-line-missing`; a literal `$COST_LINE` leak → `cost-line-malformed` | `cost_available: false` → no signal; well-formed `$0.42` → no signal; well-formed sub-$1 `$0.0042` (4dp) → no signal (research.md R8's magnitude-aware pattern) |
| `verify-final-pr-claims-collector.sh` | `collect-final-pr-claims`'s three claim-shape parsers and ground-truth derivation | A task-count mismatch; a commit-count mismatch; a test-count (fixture-file-count) mismatch | An unparseable claim shape → no signal; all three claims matching → no signal; a non-finalize run → no signal (scope guard) |
| `verify-narrative-drift-routing.sh` | The new `Determine issue-filing eligibility` step | A `narrative-drift` Finding → `issueless: true`, `Ensure pipeline-defect issue` skipped, `Report finding to lifecycle issue` still runs and posts | Any other class → `issueless` unset/false, normal issue-filing path unaffected |
| `verify-spec-collision-collector.sh` | `collect-spec-collision`'s claimant enumeration and dedup-by-identity | Two open PRs sharing a number → collision; an open PR matching a `main` directory → collision | Every open PR distinct → no signal; a PR observed twice (same run re-inspected) → not a self-collision (FR-028); a non-intake run → no signal (scope guard) |

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
