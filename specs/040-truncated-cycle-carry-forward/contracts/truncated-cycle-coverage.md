# Contract: `.github/scripts/verify-truncated-cycle-carry-forward.py` (new, Gate 26)

Follows the calling convention every other `verify-*.py` gate script in
`.github/scripts/` already establishes: standalone, invoked with no
arguments as `python3 .github/scripts/verify-truncated-cycle-carry-forward.py`
from a `lint-workflows.yml` step, exit 0 on pass / non-zero on any
assertion failure, built on `wc_shell_harness.py`'s `resolve_bash`,
`ensure_jq`, `find_step`, `run_step`, `parse_github_output`,
`use_utf8_stdout` — unmodified, per the module's own module-level
docstring convention (`wc_gate_registry.py`).

## Purpose

Prove, by executing the shipped `run:` text of "Read back cycle outcome",
"Consolidate final outcome", "Record truncated-cycle count", and "Dispatch
next step" (`.github/workflows/implement.yml`) against synthetic git
history and a stubbed upstream verdict, that: a turn-exhausted cycle with
progress is classified truncated and forced not-converged (FR-005, US2); a
turn-exhausted cycle with no progress takes today's failed path (US3); the
consecutive-truncation count increments and resets correctly (FR-011); and
that removing the forced-not-converged rule, the no-progress guard, either
arm of the progress test, or widening truncation to ordinary failures each
independently breaks this proof (FR-019), with the gate's own presence in
`lint-workflows.yml` checked reflexively (FR-020).

## Harness shape (research.md D8)

A real git repository with a local bare remote, per scenario — mirroring
`verify-stall-restart-runbook.py`'s (Gate 14) `make_workspace` pattern —
so the counter-write commit/push path (`spec-meta.json`'s
`truncated_count`, data-model.md) executes for real rather than being
asserted against a mocked git. `find_step` extracts each named step's
`run:` text directly from `implement.yml`; `run_step` executes it with
`VERDICT`/`CYCLE_RESULT`/`BASE_SHA`/etc. supplied as env vars standing in
for what the upstream steps in the real job would have produced —
`wc_shell_harness.py`'s existing model for testing one named step without
re-running the whole job (Gate 14 already does this for `RECORDED`/
`ISSUE`/etc.).

## Scenarios asserted (each against the real, unmutated step text)

| # | Scenario | Synthetic history (relative to `BASE_SHA`) | `VERDICT` | Expected `ok`/`truncated`/`converged` | FR/US |
|---|---|---|---|---|---|
| 1 | Exhausted, Arm-A progress, no converge commit | One commit ticking a `tasks.md` checkbox + the lifecycle-record advance commit | `exhausted` | `true`/`true`/`false` | FR-004 Arm A, FR-005, US1, US2 |
| 2 | Exhausted, only the lifecycle-record advance landed | Just the `spec-meta.json` advance commit, nothing else | `exhausted` | `false`/`false`/empty (today's failed path) | FR-004a, spec Edge Case "only commit is bookkeeping" |
| 3 | Exhausted, Arm-A-only progress | Same as #1 | `exhausted` | `true`/`true`/`false` | FR-004 (Arm A alone sufficient) |
| 4 | Exhausted, Arm-B-only progress | A file changed outside `$SPEC_DIR` + the advance commit, `tasks.md` unchanged | `exhausted` | `true`/`true`/`false` | FR-004 (Arm B alone sufficient) |
| 5 | Ordinary failure | No relevant commits beyond `BASE_SHA` (or the advance never lands) | `failed` (or `CYCLE_RESULT=failure`) | `false`/`false`/empty (today's failed path, unchanged) | FR-002, FR-017 |
| 6 | Normal successful cycle | Progress commits + a `converge:` commit touching `tasks.md` | `healthy` | `true`/`false`/`true` or `false` per the existing converge-commit scan, exactly as today | FR-017 |

## Additional assertions

- **Counter (FR-011)**: starting `spec-meta.json` with `truncated_count: 1`,
  scenario 1 (truncated) must leave it at `2`; scenario 5 or 6 (failed or
  completed) must reset it to `0`. A second consecutive truncated scenario
  run against the resulting state must show `3`.
- **At-cap reporting (FR-014)**: "Dispatch next step" run with
  `ITERATION == MAX` and `TRUNCATED=='true'` must produce a body containing
  the "ran out of turns before it could assess what remained" wording and
  must NOT contain an empty fenced `remaining` block.
- **Below-cap reporting (FR-013, FR-015)**: "Dispatch next step" run with
  `TRUNCATED=='true'`, below cap, must produce a body that does not contain
  the word "failed" and does contain the consecutive-truncation count.
- **Retry-truncation (FR-016)**: one scenario drives "Read back retry
  outcome" the same way as scenario 1, confirming the retry path reaches
  `ok=true, truncated=true` too, and that "Consolidate final outcome"
  selects the retry's `truncated` value when the retry ran.

## Required mutations (FR-019) — each must turn at least one passing scenario failing

| Mutation | Expected effect |
|---|---|
| Remove the forced `converged=false` on the truncated path (let the converge-commit scan run and set its result unconditionally) | Scenario 1 now reports `converged=true` where it must be `false` |
| Remove the no-progress guard (classify any `exhausted` + advanced run as `truncated` without checking either arm) | Scenario 2 now reports `truncated=true` where it must be `false` |
| Drop Arm A (task-checkbox count) from the progress test | Scenario 3 now reports `truncated=false` where it must be `true` |
| Drop Arm B (outside-spec-dir file change) from the progress test | Scenario 4 now reports `truncated=false` where it must be `true` |
| Count the lifecycle-record advance itself as progress (e.g. treat "branch tip moved" as sufficient) | Scenario 2 now reports `truncated=true` where it must be `false` — the same failure mode the FR-004a exclusion prevents, from a different mutation |
| Widen `VERDICT=="exhausted"` to also match `VERDICT=="failed"` | Scenario 5 now reports `ok=true`/`truncated=true` where it must be `false`/`false` |

Each mutation uses the `if mutated == steps: raise` self-check
`verify-stall-restart-runbook.py:345` already establishes, so a mutation
helper that silently fails to apply is itself caught.

**Reflexive check (FR-020)**: a lightweight assertion, inside this same
script, that "Gate 26" appears as an enabled step in
`.github/workflows/lint-workflows.yml` invoking this script by path —
mirroring Gate 25's own D7 reflexive check, so disabling or removing Gate
26 is itself a failure `verify-gate-wiring.py` (the general form) and this
script's own reflexive assertion (the specific form) both catch.

## Non-goals

- Does not re-test `wing-commander-agent-verdict`'s own transcript
  classification (`error_max_turns` → `exhausted`) — that is Gate 22's
  job, reused as a trusted input here via a stubbed `VERDICT` env var
  (research.md D1, D8).
- Does not modify `wc_shell_harness.py`.
- Does not exercise the real `gh workflow run` self-dispatch call in
  "Dispatch next step" — asserts on the composed message body and the
  branch taken, not on an actual GitHub Actions dispatch (no live API
  call in any gate script, per the existing convention every other
  `verify-*.py` script already follows).
