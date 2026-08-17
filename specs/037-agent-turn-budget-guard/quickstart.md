# Quickstart: Validating the Agent Turn Budget Guard

Prerequisites: a repo checkout with `jq`/`awk`/`bash` (matches
`ubuntu-latest`'s preinstalled toolchain) for the fixture-driven
scenarios, and `gh` authenticated against a scratch spec for the
live-run scenarios. See `contracts/agent-verdict-composite.md` for the
two new composites' exact inputs/outputs and
`contracts/coverage-gate.md` for Gates 22/23.

## Scenario 1 — Healthy-but-post-hoc-rejected run still completes the stage (US1, FR-001/FR-002, SC-001/SC-003)

1. Craft a fixture transcript matching run 31918153816's shape: last
   record `{"type": "result", "subtype": "success", "is_error": false,
   "num_turns": 47, ...}`, with 36 distinct main-loop assistant message
   ids and a declared `intended-turns: 40` (so counted turns, 36, sit
   comfortably below the intended budget of 40, exactly like the real
   run — this is not an over-budget case).
2. Invoke `wing-commander-agent-verdict` directly against it.
3. Expected: `verdict: healthy`, `counted-turns: 36`, `reported-turns:
   47`, `over-budget: "false"`.
4. Wire the same fixture through `clarify.yml`'s rewired `agent` step
   locally (or dispatch a scratch `clarify` run and replace its uploaded
   transcript artifact before the verdict step runs, if testing against
   a live run) and confirm every downstream step — the shape check, the
   spec-PR-ready callout, the label transition — still executes, and the
   job concludes successfully (US1 Acceptance Scenarios 1-3).

## Scenario 2 — Genuine failure still fails loud (US1 Acceptance Scenario 4, FR-003)

1. Three fixtures: (a) `is_error: true`, `subtype: success`; (b) no
   `.type=="result"` record at all; (c) a `subtype` that is neither
   `success` nor `error_max_turns`.
2. Expected for all three: `verdict: failed`, a non-empty `reason`
   naming what's wrong, and — wired through any rewired call site — the
   "Fail loud on non-healthy agent verdict" step fires, the job ends
   failed, and no downstream step (callout, label flip, PR creation)
   runs.

## Scenario 3 — Declared-schema site with valid healthy verdict but malformed structured output (US1 Acceptance Scenario 5, FR-004)

1. Use `clarify.yml`'s fixture shape (Scenario 1) but give the result
   record a `result` field that is valid JSON yet missing the
   `clarifications` key the schema requires.
2. Expected: `wing-commander-agent-verdict` alone still reports
   `verdict: healthy` (it has no schema opinion — research.md R2); the
   call site's own existing shape-check step, now gated on
   `verdict == 'healthy'`, is what fails the job — confirm it does, with
   a message naming the missing/malformed field, not a generic verdict
   error.

## Scenario 4 — Unreadable transcript fails closed (spec.md edge case, FR-005)

1. Three fixtures: missing file, empty file, `not valid json`.
2. Expected for all three: `verdict: unclassifiable`,
   `counted-turns`/`reported-turns` empty, and — wired through a call
   site — the job fails loud (same "Fail loud" step, since it gates on
   `!= 'healthy'`, not specifically on `failed`).

## Scenario 5 — Exhaustion is real, not spurious (spec.md edge case, FR-009)

1. Fixture: `subtype: error_max_turns`, `num_turns` at the configured
   ceiling.
2. Expected: `verdict: exhausted`, distinguishable in `reason` from a
   generic `failed`. Wired through `implement.yml`'s `cycle` site,
   confirm the existing git-state stall-detection path is unaffected
   (research.md R13) — the new wiring adds a clear failure reason on top,
   it does not change whether the cycle is judged stalled.

## Scenario 6 — Over-budget-but-healthy is reported, not failed (US2, FR-017, SC-009)

1. Fixture: `subtype: success`, `is_error: false`, counted turns >=
   `intended-turns` (e.g. 42 counted against an intended budget of 40),
   `reported-turns` higher still (consistent with the divergence
   sample).
2. Expected: `verdict: healthy`, `over-budget: "true"`. Wired through a
   lifecycle-issue-posting site (e.g. `clarify.yml`), confirm the job
   still concludes successfully AND the "Report over-budget agent run"
   callout posts to the lifecycle issue, stating both turn totals (US2
   Acceptance Scenario 1).
3. Contrast fixture: counted turns below intended, reported turns above
   the intended cap (the actual defect shape). Expected: `over-budget:
   "false"`, no callout — reported-turns crossing the cap must never by
   itself trigger the over-budget report (US2 Acceptance Scenario 2).

## Scenario 7 — Subagent turns excluded, records-vs-ids counted correctly (US2 Acceptance Scenario 3)

1. Reuse Gate 11's own two fixture shapes — 87 responses streamed as 3
   records each (expect 87, never 261 or `num_turns`'s value), and 94
   main + 86 subagent responses (expect 94, subagent count reported
   separately, never folded into `counted-turns`) — against
   `wing-commander-agent-verdict` instead of `wing-commander-metrics-summary`.
2. Expected: identical counting behavior in both actions, proving the
   shared `count-turns.sh` extraction (research.md R5) didn't change
   behavior for either caller.

## Scenario 8 — A genuinely runaway agent is still stopped (US2 Acceptance Scenario 5, SC-008)

1. Confirm `wing-commander-turn-ceiling` invoked with `intended-turns:
   40` (a typical site) produces `ceiling: 100` (40 * 2.5), and that
   this literal value — not `40`, not unbounded — is what reaches the
   agent step's `claude_args` at that site.
2. Confirm `wing-commander-turn-ceiling` invoked with `intended-turns:
   ""` (or `0`, or `-1`) exits non-zero with an `::error::` naming the
   bad value, and that this failure happens *before* the agent step runs
   (no cost spent).

## Scenario 9 — Coverage is enforced mechanically (US3, FR-010/FR-011, SC-002/SC-005)

1. Run Gate 23 against the repository as it stands after this feature
   lands. Expected: 19 sites enumerated by name (the table in
   `data-model.md`), zero failures.
2. Add a scratch agent step with `--max-turns` set to a literal number
   (no `wing-commander-turn-ceiling` step) and re-run Gate 23. Expected:
   failure, naming the new site specifically.
3. Take an existing rewired site and change its `--max-turns` back to a
   raw `${{ inputs.max-turns }}` (simulating "lowers a ceiling back to
   its intended budget"). Expected: Gate 23 fails, naming that exact
   site (US3 Acceptance Scenario 3).
4. Run Gate 23's own self-test
   (`.github/scripts/verify-gate-23-selftest.py`). Expected: every
   synthetic known-bad fixture is caught by name, proving Gate 23 itself
   can fail (US3 Acceptance Scenario 2, and the "detector actually
   detects" precedent every enumeration gate in this repository carries).

## Scenario 10 — A maintainer can audit the verdict from the run alone (US4, FR-012, SC-007)

1. Take Scenario 1's healthy-but-rejected run and Scenario 2's genuine
   failure. Open each run's own job summary (no artifact download, no
   transcript inspection).
2. Expected: Scenario 1's summary states the verdict (`healthy`), the
   reason (post-hoc rejection ignored — healthy transcript), and both
   `counted-turns`/`reported-turns`. Scenario 2's summary states the
   failure verdict and reason, and does not read as an ambiguous or
   ignorable annotation next to a green run (US4 Acceptance Scenarios 1-2,
   and the spec's edge case about the action's own error annotation
   possibly remaining visible even when the stage continues).

## Scenario 11 — Read-only: the guard never changes a healthy stage's real-world outcome (mirrors 009-agent-metrics Scenario 9)

1. Compare a Scenario-1-style healthy-but-rejected run's actual
   repository-facing outcome (commit pushed, PR body updated, label
   flipped) against what that same stage would have produced before this
   feature existed, had the upstream rejection simply not occurred.
2. Expected: identical outcome — this feature changes what happens
   *after* a post-hoc rejection, not what the agent step itself commits
   or how any other step behaves.

## Scenario 12 — The drafted upstream report exists and is complete (FR-018, SC-010)

1. Open `specs/037-agent-turn-budget-guard/upstream-report.md`.
2. Expected: it names `anthropics/claude-code-action#1607`, cites both
   observed occurrences with their real numbers, states the 1.0x-2.3x
   divergence sample, and states explicitly that filing it is optional
   and at the maintainers' discretion.
