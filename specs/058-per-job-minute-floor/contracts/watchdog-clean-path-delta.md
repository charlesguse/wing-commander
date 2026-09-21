# Contract Delta: The Watchdog's Clean Path (`watchdog.yml` and its wrapper)

This is a delta against `specs/010-reusable-pipeline/contracts/
stage-interfaces.md`'s `## reusable-watchdog.yml` section (as already
amended by `specs/020-fix-watchdog/contracts/watchdog-workflow-delta.md`
and `specs/024-watchdog-precision-hardening/contracts/watchdog-spec-
amendments-delta.md`, both of which remain the base contract for
`collect`'s five collectors, `triage`'s dedup/fingerprint mechanism, and
`act`'s single remediation branch — none of that changes here). Only the
clauses below change.

## Inputs — `run-name` becomes optional

**Current contract**: `run-name` (string, required) — "inspected run's
display name," supplied by the wrapper's `resolve` job.

**Amended contract**: `run-name` (string, optional, default `''`). When
empty, the stage resolves it itself inside `collect`'s existing
inspected-run lookup, via the same `gh run view --json workflowName`
call the wrapper's `resolve` job made today (research.md R-B4,
data-model.md). This is additive and non-breaking: a caller that still
supplies `run-name` explicitly sees no behavior change.

## `diagnose` — agent-skip condition widens from "all collectors failed" to "empty signal set"

**Current contract** (024): `diagnose` runs unless
`needs.collect.outputs.evidence-available == 'false'` (every collector
failed).

**Amended contract**: `diagnose` runs only when
`evidence-available != 'false'` **and** the aggregate signal set is
non-empty (research.md R-B1). A run where at least one collector
reported, one or more collectors failed, and the signal set is empty now
skips `diagnose` and reaches the new deterministic partial-pass path
below, rather than invoking the agent to weigh nothing (FR-019). The
all-failed case is unchanged — it still skips `diagnose` and still
reaches the pre-existing "could not inspect" path (FR-013), which this
delta does not touch.

## `collect` — gains a deterministic passed-inspection step

**Current contract**: `collect` computes the aggregate and, when
`evidence-available == 'false'`, posts the "could not inspect" comment.
It posts nothing on any other outcome; a zero-Finding but
evidence-available run relied on `diagnose` running and computing
`outcome: passed-inspection` itself.

**Amended contract**: immediately after the `aggregate` step, a new
deterministic step runs when `steps.aggregate.outcome == 'success'`,
`evidence-available != 'false'`, and the signal set is empty. It posts
the passed-inspection comment — full wording when
`collectors-failed == 0`, partial wording (naming how many collectors
reported and how many errored) otherwise (FR-011) — using the same two
wording strings the `diagnose`-job version of this comment already uses,
relocated rather than reworded. No issue is filed or updated (FR-009).
No agent step executes anywhere in the run on this path (FR-009,
FR-013's constitution-IX framing: this judgment is deterministic code,
not a prompt).

The pre-existing "Report 'passed inspection'" step inside `diagnose`
(the agent ran, found zero actionable Findings after weighing real
signals) is unchanged — a different event, reached only when `diagnose`
actually ran, keeping its own code path and wording (FR-012).

## `diagnose`'s run-summary call site — no record on the no-finding path

**Current contract**: `diagnose`'s agent step is the only
`wing-commander-metrics-summary` call site in `watchdog.yml`; it always
runs when `diagnose` runs.

**Amended contract**: unchanged in code — the effect is a consequence of
the `diagnose`-skip clause above, not a new suppression. When
`diagnose` skips (the no-finding path), no metrics record is emitted for
that run at all (FR-031). The lifecycle rollup's "every agent run
appears exactly once" invariant is unaffected: a run that emits no
record was never counted as an agent run by that invariant's own
definition (records-store-derived, not run-count-derived — research.md
R-B3).

## Wrapper (`wing-commander-8-watchdog.yml`) — `resolve` job removed

**Current contract**: two jobs — `resolve` (a runner-allocating job that
resolves `run-id`/`run-name` from the triggering event) and `watchdog`
(the `uses:` call, forwarding both).

**Amended contract**: one job — `watchdog`, a bare `uses:
./.github/workflows/watchdog.yml` with `run-id:
${{ format('{0}', inputs.run-id || github.event.workflow_run.id) }}`
and no `run-name:` supplied (the stage resolves it, per the amended
input above). The pause kill-switch (`vars.
WING_COMMANDER_WATCHDOG_PAUSED`) and the self-dispatch cap remain exactly
where they are today — this delta touches only run-name resolution, not
any gating condition (FR-015 — the watchdog's own runs stay unexempted,
unchanged by this delta).

## Self-verifier (`wing-commander-8b-watchdog-self.yml`) — new healthy shape accepted, floor re-scaled

**Current contract**: `verify-watchdog-run.sh` treats a healthy run as
one where `diagnose` ran within its ceiling, an execution-output
artifact and metrics record exist, and the whole-run duration clears a
floor of `max(40, median(recent successful durations) * 2/5)` seconds.

**Amended contract**: a run where `diagnose` is `skipped`, the
passed-inspection comment was posted, no execution-output artifact and
no metrics record exist, and the whole-run duration may fall under
today's `40`-second absolute floor is now also a passing, healthy shape
(FR-032). The absolute floor constant is lowered (research.md R-B5 — the
exact value is an implementation-time measurement, not fixed by this
plan) to sit under the new shape's real duration with headroom; the
median-based term is unchanged code, and self-adjusts as new-shape runs
populate its history window. Every failure branch the self-verifier
catches today — the crashed or stalled agent, the could-not-inspect
degradation, the fired safety net, the fabricated verdict — is
unchanged and must still fail after this delta (FR-032's second
clause); the checked-in failure-path fixture harness gains the new
healthy shape as one more passing case, alongside its existing failing
ones.

## What does not change

- The five collectors, their attribution invariant, and `signals.json`'s
  shape (specs 015/024, untouched).
- `triage`'s fingerprint/dedup mechanism and `act`'s single remediation
  branch (spec 024, untouched).
- `findings-dropped` and `report-unhandled-failure`'s own conditions —
  the latter still runs on every watchdog run, including one where every
  other job died (FR-017), and this delta adds nothing to its `if:`.
- The self-dispatch cap and the pause kill-switch.

## Versioning

Additive and non-breaking: `run-name` both gains a default AND loses
`required: true` — GitHub still demands a value for a `required: true`
input even when a default is declared, so dropping `required` is what
actually lets the wrapper omit it; no output or secret changes. A caller
still passing `run-name` explicitly sees no behavior change (Gate 75).
Per `contracts/versioning.md`, this ships as part of this feature's
overall minor release.
