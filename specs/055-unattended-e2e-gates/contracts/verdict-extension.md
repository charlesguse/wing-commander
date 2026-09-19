# Contract: FR-016–FR-024 — the verdict schema is unchanged; one outcome value and one report branch are added

research.md D11/D12 explain why no field is added to
`.github/actions/_shared/auto-release-verdict.sh`'s six-field shape
(`specs/049-single-home-release-idioms/contracts/verdict-helper.md`) and why
new gate evidence lives in the `report` job's summary text rather than in
that JSON.

## `auto-release-verdict.sh` (UNCHANGED)

Same five positional args (`outcome`, `head`, `failing_check`, `expected`,
`observed`) plus `evidence_url`, same `jq -n` program, same output shape.
New call sites in the `poll` step use the existing script exactly as every
current `fail-*` site does, supplying `outcome="fail-gate-stall"` and the
gate name / expectation / observation described in
`data-model.md`'s End-to-end verdict section.

## New `poll`-step call sites (in `auto-release.yml`, inside the existing loop)

| Trigger | `outcome` | `failing_check` | `expected` | `observed` |
|---|---|---|---|---|
| Clarify decision = `exhausted` | `fail-gate-stall` | `"clarification"` | `"a reply from the harness resolves the open clarification question within 3 rounds"` | `"still asking after 3 rounds"` |
| Merge decision = `conflicting` | `fail-gate-stall` | `"<gate name>"` | `"gh pr merge succeeds"` | `"PR #<n>: CONFLICTING"` |
| Merge decision = `blocked` | `fail-gate-stall` | `"<gate name>"` | `"gh pr merge succeeds"` | `"PR #<n>: required check blocked"` |
| Merge decision = `wrong-attempt` | `fail-gate-stall` | `"<gate name>"` | `"the PR at this branch belongs to the current attempt"` | `"PR #<n> belongs to a previous attempt"` |
| Merge decision = `wrong-base` (maintainer feedback on PR #389) | `fail-gate-stall` | `"<gate name>"` | `"the PR at this branch targets <expected base>"` | `"PR #<n> targets a different base branch"` |
| A gate-driving read or write fails `MAX_GATE_FAILURES` (3) times running (maintainer feedback) | `fail-gate-stall` | `"<gate name>"` | `"reading/deciding/writing each succeed within 3 attempts"` | the failed command's own captured stderr, or a generic reason |
| Clarification gate opened, no QUALIFYING reply (the harness's own, or a human's, per FR-010) exists by `stage:done` | `fail-wrong-output` | `"clarification gate answered before stage:done"` | `"a qualifying reply after every open question"` | `"question opened, never answered"` |
| A merge-gate PR exists but is missing or not attributed to the harness login by `stage:done` (maintainer feedback, FR-016/FR-018) | `fail-wrong-output` | `"<gate name> merged by the harness before stage:done"` | `"the PR merged, attributed to <harness login>"` | `"no merged PR found"`, or `"merged by '<login>'"` |

`<gate name>` is one of `"spec-draft PR merge"`, `"plan PR merge"`,
`"finalize PR merge"`, matching the Lifecycle gate table in
`data-model.md`.

## `report` job classification (`auto-release.yml`, the `outcome` step
around today's line 1013–1014)

```bash
# before (spec 045, two-way):
if [ "$OUTCOME" = "fail-infra" ]; then CLASS="infrastructure"; else CLASS="pipeline defect"; fi

# after (this feature, three-way):
case "$OUTCOME" in
  fail-infra) CLASS="infrastructure" ;;
  fail-gate-stall) CLASS="gate stall" ;;
  *) CLASS="pipeline defect" ;;
esac
```

Every outcome other than `fail-infra` and `fail-gate-stall` keeps its
current classification (`fail-timeout`, `fail-incomplete`,
`fail-wrong-output` → "pipeline defect", unchanged) — Edge Cases requires
this explicitly ("the lifecycle reaches `stage:stalled` for a non-gate
reason: reported as a pipeline defect, unchanged by this feature").

## Durable failure-issue body (`_shared/durable-failure-issue`, consumed
unchanged; body text built by the `report` job gains one branch)

For `CLASS = "gate stall"`, the body states, per FR-022: the gate name
(`failing_check`), what the pipeline was waiting for (`expected`), and
what was observed instead (`observed`) — the same three fields every other
classification already renders, so the body-building code needs no new
field, only a label change from "pipeline defect" to "gate stall" text and
(optionally) a short "the harness attempted to drive this gate and could
not" sentence distinguishing it from an infra failure or a code defect.

## Gate coverage

`.github/scripts/verify-auto-release-report.py` (the existing gate over
this report/classification logic) gains fixtures for: a `fail-gate-stall`
verdict at each of the four gate names, the exhausted-rounds case, each of
the three merge-decision stall reasons, and the pass-path clarification
assertion (research.md D12) both with and without a clarification question
having opened. No new gate script — one home, extended (CLAUDE.md).
