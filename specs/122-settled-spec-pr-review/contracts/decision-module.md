# Contract: `spec_pr_review.py` decision module

Pure, deterministic; JSON on stdin, JSON on stdout, non-zero exit on
unreadable input (VIII: fail loud, never a pass it did not earn).

| Subcommand | Input | Output |
|---|---|---|
| `select` | list of `SpecPrSnapshot` | `{selected: {pr, head_sha}\|null, skips: [{pr, reason}]}` |
| `eligible` | one snapshot (fresh) | `EligibilityDecision` |
| `verdict` | findings[] | `{verdict, in_scope_count}`; any in-scope finding ⇒ `not ready` (a finding whose `in_scope` is not readable counts as in scope) |
| `check-fixes` | per-fix paths, line counts and precedent resolutions, spec dir, caps | `{pushable: [..], blocked: [{finding, reason, title}]}` (`finding` is the join key, `title` the text the review shows); marker lines checked for path/size only |
| `plan-actions` | verified findings (each with `in_scope`), push results, snapshot freshness, whether the round stopped | `ActionPlan`, acting on in-scope findings only, plus `record_out_of_scope` |
| `failed-cap` | per-head failure count | `{stop: bool}` at 2 |

## Scope (owner decision 2026-11-27, Roadmap #890)

A finding is in scope when it is a spec defect under the review's three
checks: buildability, a conflict, or a contradictory, untestable or
undecided requirement. A plan-level finding (one that only names a file, a
literal, a regex or a step's shape) is out of scope: it is listed in the
review as report-only, gets no fix and no marker, moves no label, does not
affect the status or the "not ready (N findings)" line, and is recorded once
per round on the lifecycle issue for the plan stage.

## Stopped round (owner decision 2026-11-26, Roadmap #890)

A budget or convergence stop withholds the ready announcement; owner-decision
markers the round pushed still move the issue to clarify. The stop note names
the commit the round pushed (the reviewed head when it pushed nothing), so
that push does not re-arm the stop.

## Invariants checked by fixtures (FR-025)

- Settled: each of the four unsettled conditions, plus the settled case; lookalike non-App announcement ignored; bare phrase in prose is not a marker.
- Dispatch: valid maintainer; bot actor rejected; wrong stage rejected; open marker rejected; announcement/unchanged-head skipped.
- One review per head; new head re-eligible; budget exhausted; convergence stop (the stop note, re-armed through `wc_convergence.py rearmed`, not re-implemented); failed-cap hand-off; kill switch.
- Fix checks: path outside spec dir, over size cap, missing/unresolvable precedent each block a push and become a report-only finding; markers exempt from citation only.
- Label move only after markers pushed; announcement only when every fix pushed and never from a stopped round, whose pushed markers still move the label; stale/closed PR yields no writes.
- Scope: out-of-scope findings alone yield `ready for the owner`; only in-scope findings are counted, fixed, marked or announced; an unreadable `in_scope` counts as in scope; out-of-scope findings are recorded for the plan stage only when the result is writable.
- SC-004 replays: spec 119 FR-022 (ninth merge condition vs. constitution X) and spec 120 FR-002 (`Actions: write` vs. `docs/setup.md` permissions) each produce `not ready` with a finding naming that requirement.

Registered in the gate registry (`wc_gate_registry.py`) so `run-local-gates.py` and CI run the same subject.
