# Contract: Watchdog diagnose outcome, the `rate-limited` report, and the `usage-limit` issue

`.github/workflows/watchdog.yml`, `diagnose` job. Builds on the existing
"Compute agent run verdict" / "Read back diagnose outcome" / "Report ...
to lifecycle issue" steps documented in `data-model.md`'s "Diagnose
outcome" table; `research.md` R5 explains the dedup rule.

## "Read back diagnose outcome" (EXTENDED)

Existing step, `id: diagnose-outcome`. Gains one new branch, checked
**before** the existing `diagnose-failed` test (a rate-limited rejection
also fails that test's `agent_ok` condition today, so ordering is
load-bearing):

```
if steps.diagnose-verdict.outputs.verdict == 'rate-limited':
    outcome = rate-limited
elif steps.diagnose.outcome != 'success' OR agent_ok != 'true':
    outcome = diagnose-failed          # unchanged
elif count == 0:
    outcome = passed-inspection        # unchanged
else:
    outcome = findings                 # unchanged
```

`findings` stays `[]` and `finding-count`/`finding-indexes` stay empty
for the `rate-limited` branch — no matrix entry is scheduled, matching
`diagnose-failed`'s existing behavior (triage/act are already skipped
whenever `finding-count == 0`; no change needed there).

## "Report 'rate-limited' to lifecycle issue" (NEW)

Sibling of the existing "Report 'diagnose failed'..." and "Report
'passed inspection'..." steps — same `if` shape
(`steps.diagnose-outcome.outputs.outcome == 'rate-limited'`), same two
delivery paths (comment on `needs.collect.outputs.lifecycle-issue` when
set, else `$GITHUB_STEP_SUMMARY`).

**Body contract** (FR-007/FR-008/FR-009):

- States plainly that the usage window was exhausted.
- Names the reset time from `steps.diagnose-verdict.outputs.rate-limit-reset`
  (already `"unknown"` when absent — never re-derived here).
- States the run was therefore **not inspected** — same "not a clean
  bill of health" framing as the existing diagnose-failed report, so a
  reader scanning past headlines doesn't mistake it for a pass.
- Does **not** use the words "failed" or "crashed," and is visually
  distinguishable at a glance from the "diagnose failed" report — a
  different leading emoji/heading (e.g. "⏳" rather than the bare "🐕"
  failure framing) and different prose, not a shared string with one
  word swapped.
- Links the inspected run, same as the existing two report steps.

Example shape (final wording is implementation's call, not fixed here):

> 🐕⏳ **Wing Commander · watchdog** — the usage window was exhausted
> during this run, so it was **not inspected**. This is not a clean bill
> of health: problems may be present and undetected. Resets at
> `2026-09-14T18:00:00Z`. _[Inspected run](...)_

## "Ensure usage-limit issue" (NEW)

Same `if` gate as the report step above. Distinct from the existing
`pipeline-defect` filing machinery in `triage`/`act` — this step lives
in the `diagnose` job itself, because `triage`/`act` are skipped
whenever `finding-count == 0` (which a rate-limited run always is).

**Behavior** (FR-012/FR-013, dedup rule per research.md R5):

1. `gh label create usage-limit --color ... --description "Watchdog: a run went uninspected because the usage window was exhausted" --force` (idempotent, mirrors the existing `pipeline-defect` bootstrap).
2. `gh issue list --label usage-limit --state open --json number --jq '.[0].number // empty'` — the ENTIRE dedup key is "does an open `usage-limit` issue currently exist," no fingerprint.
3. If found: `gh issue comment <number>` appending one bullet (run URL,
   reset time, "went uninspected").
4. If not found: `gh issue create --label usage-limit --title "watchdog: usage window exhausted" --body <first bullet>`.
5. On a failed `gh issue list` (network/API error): do **not** create a
   new issue — same "a failed search is not evidence of absence, skip
   filing rather than risk a duplicate" discipline the existing
   `pipeline-defect` dedup already follows (watchdog.yml's existing
   `dedup` step, and `verify-watchdog-run.sh`'s own CREATE_ISSUE arm,
   both cite #167/#169 for this exact failure mode). The rate-limited
   report step above still posts regardless — the fact is on the
   record even if this accumulation step could not run.

This step never touches the `pipeline-defect` label and never runs the
existing fingerprint/dedup machinery in `triage`/`act` — it is a
narrower, standalone accumulator.

## What does NOT change

- `steps.diagnose-verdict.outputs.verdict != 'healthy'`'s existing "Fail
  loud on non-healthy agent verdict" step: unchanged, still fires for
  `rate-limited` (FR-015) — this keeps the diagnose *step* visibly red
  in its own job view even though the *job* (and the run) stays green
  by the same `continue-on-error: true` design already in place.
- The existing "Report 'diagnose failed'..." and "Report 'passed
  inspection'..." steps: unchanged conditions, now simply never true at
  the same time as the new branch (mutual exclusion, data-model.md).
- `wing-commander-metrics-summary`'s invocation in this job: unchanged
  wiring, now rendering `rate-limited` per
  contracts/agent-verdict-extension.md.
