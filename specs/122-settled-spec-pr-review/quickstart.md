# Quickstart: Validating the Settled Spec PR Review

## Prerequisites

- Checkout of this branch; Python 3; `gh` authenticated for the live steps.

## 1. Decision logic (runs locally and in CI)

```bash
python .github/scripts/verify-spec-pr-review.py
python .github/scripts/verify-spec-pr-review-wiring.py
python .github/scripts/run-local-gates.py
```

Expected: every fixture in `contracts/decision-module.md` passes; the wiring
verifier confirms no `APPROVE`/`REQUEST_CHANGES`/merge call, no published-surface
change, composites consumed (not pasted), and the kill switch read first.

## 2. Live: settled PR is reviewed once

1. Take a spec PR at `stage:spec`, no open marker, App ready announcement newer than head.
2. `gh workflow run spec-pr-review.yml -f pr=<N>` (or wait for the schedule).
3. Expect one `COMMENT` review naming round, head SHA, verdict, findings, round record last; a commit status under the new context; one outcome line on the lifecycle issue.
4. Re-run: expect skip reason `already-reviewed`.

## 3. Live: unsettled / controls

- Put `stage:clarify` on the issue, or add a marker, or push a new commit: expect a recorded skip, no review.
- Set `WING_COMMANDER_SPEC_REVIEW_PAUSED=true`: expect a stand-down record and no round.

## 4. Replay (SC-004, one-off)

Run the review against the heads of #1078 and #1086 as the manual reviews saw
them; expect `not ready` with findings naming spec 119 FR-022 and spec 120 FR-002.
