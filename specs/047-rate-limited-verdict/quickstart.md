# Quickstart: Validating the Rate-limited Agent Verdict

Prerequisites: a repo checkout with `jq`/`bash`/`python3` (matches
`ubuntu-latest`'s preinstalled toolchain) for the fixture-driven
scenarios, and `gh` authenticated against a scratch spec/issue for the
live-run scenarios. See `contracts/agent-verdict-extension.md` for the
classifier's exact new output, `contracts/watchdog-reporting.md` for the
new report/issue steps, `contracts/verifier-suppression.md` for the
verifier, and `contracts/exemption-gate.md` for Gate 51.

## Scenario 1 — A terminal 429 classifies as `rate-limited`, not `failed` (US1, FR-001/FR-002/FR-003, SC-004)

1. Pull the real execution-output artifacts named in issue #306/#300 (the
   three 2026-09-12 runs and the 2026-08-28 run) and use them as the
   primary fixtures — not a hand-authored approximation (research.md R1
   flags this as the load-bearing ground truth this plan could not
   verify directly).
2. Invoke `wing-commander-agent-verdict` directly against each.
3. Expected: `verdict: rate-limited`, `reason` names the window and the
   reset time, `rate-limit-reset` carries the same reset time (or
   `"unknown"` if any of the four lack `resetsAt`) — never empty, never
   epoch-zero.
4. Replay the 2026-09-08 binary-not-found runs from #278 through the
   same composite. Expected: `verdict: failed`, unchanged from today
   (SC-004's negative half).

## Scenario 2 — A 429 the runtime recovered from stays `healthy` (spec.md edge case, US1)

1. Fixture: a `rate_limit_event` record mid-transcript, followed by
   further turns and a terminal `result` record with
   `subtype: "success"`, `is_error: false`.
2. Expected: `verdict: healthy` — the presence of a `rate_limit_event`
   anywhere in the transcript must never demote an otherwise-successful
   run.

## Scenario 3 — A non-429 API error keeps filing exactly as today (spec.md edge case, FR-016 negative case)

1. Fixture: a terminal `result` record with `is_error: true`,
   `terminal_reason: "api_error"`, `api_error_status: 500` (or any
   non-429 value), no `rate_limit_event` record anywhere.
2. Expected: `verdict: failed`, unchanged reason text from today — the
   429-specific corroboration must not accidentally widen to any API
   error.

## Scenario 4 — The watchdog's diagnose reporter names the outage, not a crash (US1 AS2, FR-007/FR-008/FR-009)

1. Wire Scenario 1's fixture through `watchdog.yml`'s `diagnose` job
   (locally against the composite, or by replacing a scratch dispatched
   run's uploaded transcript artifact before the read-back step runs).
2. Expected: "Read back diagnose outcome" produces `outcome:
   rate-limited`; the new "Report 'rate-limited'..." step posts (not the
   "diagnose failed" step); the posted body names the usage window and
   reset time, states the run was not inspected, and contains neither
   "failed" nor "crashed"; the diagnose *step* itself still shows red in
   its own job view (the unchanged "Fail loud" step, FR-015) while the
   *job* and the *run* stay green.

## Scenario 5 — Stage-8b stays green for a purely rate-limited run (US1 AS1/AS3, FR-010/FR-012a, SC-001)

1. Take Scenario 4's run. Run `verify-watchdog-run.sh` against it with
   `CREATE_ISSUE=true`.
2. Expected: exit code 0, "verified healthy" summary, **no**
   `pipeline-defect` issue created or commented on.

## Scenario 6 — An unrelated defect alongside a rate-limited run still files (US1 AS4, FR-011)

1. Take Scenario 4's run, but synthetically mark an unrelated job (e.g.
   `report-unhandled-failure`'s safety net) as having fired, or extend
   the run's duration past the stall ceiling.
2. Expected: `verify-watchdog-run.sh` exits 1, `fail_reasons` names only
   the unrelated defect (not "no successful terminal result," not "under
   the floor"), and the existing `pipeline-defect` filing/dedup fires
   exactly as it does today for that unrelated reason.

## Scenario 7 — The `usage-limit` issue accumulates, never duplicates (US2, FR-012/FR-013, SC-003)

1. Drive two rate-limited diagnose runs against the same scratch repo
   state (no existing open `usage-limit` issue).
2. Expected: run 1 creates one issue labelled `usage-limit` (never
   `pipeline-defect`) naming the run and reset time; run 2 appends a
   second bullet to the *same* issue number — `gh issue list` confirms
   exactly one open `usage-limit`-labelled issue exists.
3. Filter the scratch repo's issue board for `pipeline-defect`. Expected:
   the `usage-limit` issue does not appear (US2 AS3).

## Scenario 8 — Every other stage still fails loud, and only the issue-writer is exempt (US3, FR-014/FR-015/FR-015a)

1. Feed Scenario 1's fixture through a non-watchdog stage's metrics
   summary (e.g. `clarify.yml`'s `agent`/`agent-verdict`/metrics-summary
   trio, run against the fixture transcript).
2. Expected: the run summary and the durable metrics record both name
   `rate-limited` (not degraded to `unclassifiable`/`failed` — FR-014);
   that stage's own "Fail loud on non-healthy agent verdict" step still
   fires and the job still ends failed (FR-015); and, wherever that
   stage's failure path would otherwise post a comment or file an issue
   about the outcome, it does neither for this verdict (FR-015a) —
   confirm no issue/comment lands beyond the run's own log and step
   summary.

## Scenario 9 — Gate 22's new cases (FR-016)

1. Run Gate 22 (`verify-agent-verdict.py`) against the repository as it
   stands after this feature lands. Expected: the three new cases
   (Scenarios 1-3 above, as synthetic transcripts) all pass, and the
   existing mutation phase still catches every existing mutation
   unchanged.

## Scenario 10 — Gate 36's new fixtures (constitution VIII)

1. Run Gate 36 (`verify-watchdog-run-failure-paths.sh`). Expected: the
   four new fixtures from `contracts/verifier-suppression.md` (pure
   rate-limited pass, rate-limited-plus-unrelated-defect fail, stall
   arm unaffected, `gh`-stub-failure fails safe) all behave as
   documented, with mutation coverage proving each is load-bearing.

## Scenario 11 — Gate 51 enumerates and can fail its own subject (FR-015b)

1. Run the new gate
   (`.github/scripts/verify-rate-limited-exemption.py`) against the
   repository as it stands after this feature lands. Expected: zero
   failures — every discovered verdict-gated issue/comment-writing step
   either excludes `rate-limited` or is in `EXEMPT_SITES`.
2. Add a scratch step to any workflow: `if:
   steps.x-verdict.outputs.verdict != 'healthy'` guarding a `run:` that
   calls `gh issue create`, with no exclusion and no registration.
   Re-run the gate. Expected: failure, naming the new file and step.
3. Run the gate's self-test fixture (its own PASS/PASS/FAIL synthetic
   cases). Expected: all three resolve as documented, proving the gate
   itself can fail (constitution VIII).

## Scenario 12 — Documentation names the fifth value (FR-017)

1. Open `docs/architecture.md`'s verdict-vocabulary paragraph. Expected:
   `rate-limited` appears in the enumeration alongside the existing
   four, and the sentence naming Gate 22 also names its three new cases
   and Gate 51.
