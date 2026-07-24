# Phase 1 Data Model: Fix the Watchdog — Restore Reliable Run Inspection

This feature adds no new entity of its own — `specs/015-pipeline-watchdog/
data-model.md` remains authoritative for Run under inspection, Signals,
Finding, Fingerprint, Pipeline-defect issue, and Lifecycle issue. This
document records only the one shape this feature adds (a fourth report
variant) and the one behavioral clarification it makes to an existing shape
(Verdict).

## Verdict (existing entity, clarified)

`specs/015-pipeline-watchdog/` already defines the watchdog's terminal
outcome as one of three reports on the lifecycle issue: "run passed
inspection," "could not inspect this run" (all evidence collectors failed),
or one block per Finding. FR-002 of this feature makes explicit what was
previously only implicit: **every** invocation must reach exactly one of
these, and an invocation that produces none of them — because a job itself
hard-failed before it could compute an outcome — is the exact defect this
feature corrects. This feature does not change the three existing verdict
shapes; it adds a fourth report variant (below) for the one case none of
them previously covered, and a job that guarantees it fires.

## Unhandled-job-failure report (new)

Emitted only by the new `report-unhandled-failure` job
(contracts/watchdog-workflow-delta.md), and only when at least one of
`collect`/`diagnose`/`triage`/`act` ends with `result == 'failure'` or
`result == 'cancelled'` — i.e., precisely the case existing error handling
does not already cover (data-model.md's "could not inspect" covers all-
collectors-failed with `collect` itself still succeeding; this covers a job
itself not succeeding).

| Field | Source | Notes |
|---|---|---|
| Failed job name(s) | `needs.<job>.result` read by the safety-net job | One or more of `collect`, `diagnose`, `triage`, `act` |
| Run URL | Re-resolved by the safety-net job itself (does not trust `collect`'s output, which may not exist if `collect` is the job that failed) | Always included so a human can open the raw run if they choose to, even though the point of this report is that they shouldn't need to for the verdict itself |
| Lifecycle issue (if resolvable) | Re-resolved by the safety-net job itself, independently of `collect`'s own resolution | Best-effort; if it cannot be resolved (e.g. because the very step that would have resolved it is what failed), the report falls back to the run's own summary, same fallback rule as every existing verdict path |
| Report text | Deterministic template, not model-generated | `"🐕 **Wing Commander · watchdog** — could not inspect this run: the <job> job ended <result> unexpectedly. <link to job logs>. This is a pipeline defect, not a finding about the inspected run itself."` |

This report is distinguished from the existing "could not inspect this run:
every evidence collector failed outright" message (data-model.md, FR-005) by
wording ("ended `<result>` unexpectedly" vs. "every evidence collector failed
outright") so a maintainer reading either can immediately tell which failure
shape occurred — a collection-evidence gap (expected, handled, benign) versus
a genuine pipeline break (this feature's target).

## State transition (extends `specs/015-pipeline-watchdog/data-model.md`'s diagram)

```
(any stage's run completes, success or failure) ──workflow_run──▶ collect → diagnose → triage → act
                                                                          │
                          [existing, unchanged] every path above completes normally
                          ─────────────────────────────────────────────────────────▶ one of: passed inspection /
                                                                                       could not inspect (evidence) /
                                                                                       finding report(s)
                          [new] collect OR diagnose OR triage OR act ends failure/cancelled
                          ─────────────────────────────────────────────────────────▶ report-unhandled-failure (always())
                                                                                       └─▶ could not inspect (job failure)
```

No new persisted entity, no new external write surface — the safety-net job
writes to the same two destinations (lifecycle issue comment, or run
summary) every other verdict path already uses.
