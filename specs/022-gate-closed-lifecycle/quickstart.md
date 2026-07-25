# Quickstart: Validating the Closed-Lifecycle Gate and the Collector Fix

Prerequisites: maintainer access to this repository (or a throwaway test
repository configured the same way, per docs/adoption.md), and `gh` CLI
access equivalent to the repo's own automation. All scenarios below run
against real triggered workflow runs — this repo dogfoods itself
(constitution I) and has no separate unit-test harness for workflow YAML.

## Scenario 1 — A closed lifecycle is inert to a comment (US1; FR-001–FR-003, FR-012)

1. Take a lifecycle issue through intake so it has a spec-identity label
   and an open draft/spec PR, then close the issue (do not merge the PR).
2. Post a comment on the closed issue in the same shape that would
   normally trigger `clarify` (i.e., as a maintainer, on an issue carrying
   `stage:clarify`).
3. Confirm: no `clarify` run does any write — no branch checkout-as-bot, no
   commit, no push, no PR edit. Confirm exactly one comment appears on the
   issue: the `kind: info` "This lifecycle issue is closed — no action was
   taken." note, and nothing else.

**Expected**: SC-001, SC-003 (partial — clarify) hold; Acceptance Scenario
1 (US1) reproduced with the opposite outcome from the reported defect.

## Scenario 2 — Reproducing the exact reported race: closing comment itself (US1; FR-007, SC-002)

1. On an open lifecycle issue with an open draft PR, close the issue and,
   in the same close action (or immediately after), leave a comment in the
   shape that would trigger `clarify` — reproducing issue #109's reported
   sequence.
2. Confirm the triggered run's gate re-fetches state live and finds it
   closed (research.md R3) — no stage action results, and the single
   decline note is the only output.

**Expected**: SC-002 holds — the specific reported scenario, reproduced,
now results in no stage action.

## Scenario 3 — No branch resurrection after cleanup has run (US1; FR-003)

1. Let a lifecycle issue's PR close/get rejected so `cleanup.yml` tears
   down its draft branch and closes the issue.
2. Comment on the now-closed issue in a shape that would normally trigger
   a stage that commits and pushes (e.g. `clarify`).
3. Confirm `git ls-remote` shows no re-creation of the torn-down branch —
   the gate declines before the "checkout draft branch as bot" step ever
   runs (contracts/lifecycle-gate-points.md, row 1).

**Expected**: SC-001 holds — zero branch resurrection.

## Scenario 4 — Label trigger on a closed issue (US1; FR-001, Acceptance Scenario 4)

1. Close a lifecycle issue (or use one that was never opened through
   intake — an ordinary closed issue).
2. Apply the `spec-request` label to it.
3. Confirm `intake` declines: no spec branch/PR is created, and the single
   decline note is posted.

**Expected**: SC-001 holds for the label-triggered entry point.

## Scenario 5 — Every named entry point declines uniformly (US2; FR-004, SC-003)

For each row in `contracts/lifecycle-gate-points.md` — `clarify`, `intake`,
`tasks-approved` (merge a `tasks/**` PR against a closed lifecycle issue),
`finalize`, `implement`/converge (manually `workflow_dispatch` one against
a closed lifecycle issue's `issue-number`) — trigger it against a closed
lifecycle issue and confirm it declines at the gate step specifically
(visible in the job's step list: "Check lifecycle issue state" runs, then
every subsequent step shows `Skipped`), not merely as a side effect of a
denied tool call. Cross-check with:

```
grep -rln "wing-commander-lifecycle-gate" .github/workflows/{clarify,intake,tasks,finalize,implement}.yml
```

**Expected**: SC-003 — all five list, confirming zero ungated named entry
points; Acceptance Scenario 2 (US2) confirmed — the decision is visibly
made at the gate step, before any agent/write step runs.

## Scenario 6 — Reopened issue is actionable again (Edge Case: Reopened issue; FR-005)

1. Close a lifecycle issue, confirm Scenario 1's decline behavior.
2. Reopen the issue.
3. Repeat the same comment that was declined in step 1.

**Expected**: The stage now proceeds exactly as it would have before this
feature (SC-004) — the gate reflects current state, not history.

## Scenario 7 — Open lifecycle is unaffected (FR-006, SC-004)

Re-run every existing acceptance scenario from the stages this feature
touches (`clarify.yml`, `intake.yml`, `tasks.yml`, `finalize.yml`,
`implement.yml`'s own contracts/tests) against an **open** lifecycle issue.

**Expected**: 100% of previously-passing behavior still passes, with one
extra step ("Check lifecycle issue state") visible in each job's log,
adding no material latency (plan.md Performance Goals).

## Scenario 8 — Denied-tool collector accuracy (US3; FR-008–FR-010, SC-005, SC-006)

1. Using the fixture described in
   `contracts/denied-tool-collector-delta.md`'s "Fixture verification"
   section, feed a synthetic `claude-execution-output.json` with a known
   `num_turns` and a known number of denial-shaped `tool_result` entries
   (including at least one singleton-tool denial) through the corrected
   `jq` filter.
2. Confirm the reported `facts.denials` equals the injected count exactly
   (no drop, no inflation).
3. Confirm every `facts.record-index` value is labeled as a record index,
   never as a "turn," and that the finding's `source` reads as a
   non-authoritative fallback when no `result`-record denial count is
   present.
4. Run a second fixture with no `result`-type record at all; confirm the
   collector still degrades to the log-scan fallback rather than failing
   or fabricating a count (spec.md's "Collector with no terminal result
   record" edge case).

**Expected**: SC-005, SC-006 hold.

## Scenario 9 — Orphaned branch removed (FR-011, SC-007)

```
git ls-remote --heads origin spec-draft/021-rebase-discover-stall
```

**Expected**: empty output — the branch identified in research.md R5 no
longer exists after this feature's implement stage (or a maintainer)
performs the deletion research.md R5 flags.
