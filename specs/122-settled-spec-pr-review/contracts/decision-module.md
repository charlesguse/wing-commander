# Contract: `spec_pr_review.py` decision module

Pure, deterministic; JSON on stdin, JSON on stdout, non-zero exit on
unreadable input (VIII: fail loud, never a pass it did not earn).

| Subcommand | Input | Output |
|---|---|---|
| `select` | list of `SpecPrSnapshot` | `{selected: {pr, head_sha}\|null, skips: [{pr, reason}]}` |
| `eligible` | one snapshot (fresh) | `EligibilityDecision` |
| `verdict` | findings[] | `{verdict}`; non-empty ⇒ `not ready` |
| `check-fixes` | diff stat, per-fix precedent resolutions, spec dir, caps | `{pushable: [..], blocked: [{finding, reason}]}`; marker lines checked for path/size only |
| `plan-actions` | verified findings, push results, snapshot freshness | `ActionPlan` |
| `failed-cap` | per-head failure count | `{stop: bool}` at 2 |

## Invariants checked by fixtures (FR-025)

- Settled: each of the four unsettled conditions, plus the settled case; lookalike non-App announcement ignored; bare phrase in prose is not a marker.
- Dispatch: valid maintainer; bot actor rejected; wrong stage rejected; open marker rejected; announcement/unchanged-head skipped.
- One review per head; new head re-eligible; budget exhausted; convergence stop (via `wc_convergence`, not re-implemented); failed-cap hand-off; kill switch.
- Fix checks: path outside spec dir, over size cap, missing/unresolvable precedent each block a push and become a report-only finding; markers exempt from citation only.
- Label move only after markers pushed; announcement only when every fix pushed; stale/closed PR yields no writes.
- SC-004 replays: spec 119 FR-022 (ninth merge condition vs. constitution X) and spec 120 FR-002 (`Actions: write` vs. `docs/setup.md` permissions) each produce `not ready` with a finding naming that requirement.

Registered in the gate registry (`wc_gate_registry.py`) so `run-local-gates.py` and CI run the same subject.
