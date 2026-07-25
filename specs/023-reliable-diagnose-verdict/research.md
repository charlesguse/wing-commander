# Phase 0 Research: Restore Reliable Watchdog Diagnosis

Both `[NEEDS CLARIFICATION]` markers spec.md originally carried were already
resolved by the maintainer on issue #117 before planning started (Q1:C,
Q2:C — see `checklists/requirements.md`'s Notes and FR-009/FR-010). Phase 0
research below is about the *technical* unknowns planning still had to
resolve: what, exactly, issue #117 still leaves broken given the code already
in `watchdog.yml`, how to classify a crashed diagnose attempt for a bounded
retry using only signals available inside the running job, and how to scope
the issue-#117-specific root cause the spec also requires (FR-005).

## R1 — What issue #117 shows is *still* broken, given the current code

**Decision**: `specs/020-fix-watchdog/`'s fix (the `report-unhandled-failure`
safety net) and a second, later hardening pass — visible directly in
`watchdog.yml`'s `diagnose` job as of this writing, dated 2026-07-24 in its
own comments — already closed the *honesty* gap this spec's US1/US2 describe:

- The "Read back diagnose outcome" step already computes `agent_ok` from the
  execution-output file's terminal `result` record (`is_error == false` and
  `subtype == "success"`), not from the step's post-`continue-on-error`
  conclusion alone, and already treats an empty array, a missing record, an
  `is_error` result, or an error subtype as `diagnose-failed`, never as
  `passed-inspection` (a comment there cites the exact incident this fixed:
  "run 30134852122 posted 'passed inspection' over an artifact that was
  literally `[]`").
- The "Report 'diagnose failed' to lifecycle issue" step already posts an
  honest failure, explicitly worded "not a clean bill of health," whenever
  that happens.
- `verify-watchdog-run.sh` already fails a run whose diagnose crashed this
  way (its checks 3, 4, and 7), and issue #117 is proof this works: its body
  states the "diagnose failed" reporter *ran* — i.e., the crash was surfaced,
  not masked. Issue #117 is stage-8b correctly reporting "the watchdog did
  not do its job," not a case of a crash presenting as healthy.

So FR-001 through FR-004 (the "never a masked pass" guarantee) are already
satisfied by the current code for the general case. What issue #117 actually
demonstrates is the piece those honesty guarantees were never meant to
provide on their own: **reliability**. An honestly-reported crash still means
the inspected run went uninspected, still auto-files a `pipeline-defect`
issue, and still needs a human to notice and re-dispatch. FR-005 and FR-010 —
root-causing the specific issue-#117 signature and adding a bounded retry for
recognized transient/infrastructure signatures — are the parts of this spec
with no existing implementation, and are this plan's actual scope.

**Rationale**: Confirmed by direct reading of the current `diagnose` job
(lines ~811-902 of `watchdog.yml` at planning time) rather than by inference
from the spec text alone — the code is more current than the spec's own
"Overview" framing, which describes the pre-020 defect for narrative context
but does not assert today's code still has it.

**Alternatives considered**: Re-implementing the `agent_ok`/honest-reporting
logic from scratch on the assumption it was still missing — rejected once
static reading showed it already exists; doing so would duplicate working
code and risk regressing the exact mechanism FR-007 requires stay intact.

## R2 — Classifying a crashed attempt for retry, without live job-log access

**Decision**: Classification is computed entirely from the same
`${{ runner.temp }}/claude-execution-output.json` file the existing read-back
step already parses, immediately after the first `Diagnose` attempt, in a new
`always()` step:

- **Not retryable — already healthy**: `agent_ok == true` (the existing
  check). No retry; proceeds exactly as today.
- **Retryable (recognized transient/infrastructure)**: the file exists and
  contains at least one `type=="result"` entry (the SDK reached *some*
  terminal state) whose `is_error == true` or `subtype != "success"`. This is
  the shape of an execution-layer failure — the agent started, the SDK ran,
  and something failed mid-run (rate limiting, a transient tool error, a
  dropped connection) — which is exactly the class a second attempt can
  plausibly avoid.
- **Not retryable (deterministic)**: the file is missing, empty, or contains
  no `type=="result"` record at all — the SDK never reached a terminal state.
  This is the shape of a failure that happens *before* execution begins (the
  action declining to run at all, or a CLI argument the SDK rejects outright)
  — retrying with byte-identical inputs would reproduce it identically, so a
  retry only doubles the wasted job time before the same honest failure.
  `verify-watchdog-run.sh`'s own known crash-signature list (`Action failed
  with error`, `SDK execution error`, `Workflow initiated by non-human
  actor`, `json-schema is not valid JSON`) maps onto this split: the first
  two are plausible execution-layer/transient shapes; the latter two are
  both "declined or rejected before the SDK ran" shapes, matching the
  not-retryable branch.

The bound is **one retry (two attempts total)** — the smallest bound that
satisfies FR-010 and matches the clarification's own suggested example ("e.g.
once"). A retried diagnosis that still fails proceeds through the unchanged
existing "diagnose failed" path — never a masked pass (FR-010's own
requirement).

**Rationale**: The obvious alternative — classifying by grepping the
*diagnose job's own raw log* for the same signatures `verify-watchdog-run.sh`
already greps for — is not available to a step running inside that same
still-in-progress job: the Actions API's job-logs endpoint only serves a
job's log after the job has finished (R3 below hit the same access boundary
from the outside), and there is no supported way for one step to read
another step's raw console output as a file mid-job. The execution-output
artifact, by contrast, is written to disk by the SDK itself before the
`Diagnose` step's `continue-on-error` step conclusion is even determined, so
it is available for immediate, in-job jq inspection — the same source of
truth the existing read-back step already trusts over step conclusions
alone.

**Alternatives considered**:
- *Grep the raw step log via `gh api .../jobs/<id>/logs` from inside the same
  job* — rejected: the log is not finalized until the job completes (this
  step runs before that), so the endpoint would 404 or return a truncated,
  unreliable log for the very job it's part of.
- *Retry unconditionally whenever `agent_ok != true`* (Q1's option B) —
  rejected per the maintainer's Q1:C answer: this would also retry
  deterministic failures that cannot be fixed by retrying, wasting job time
  on every occurrence of a bug that actually needs a code fix (FR-005),
  and delays the honest failure report for a run that was never going to
  recover.
- *Classify using the diagnose step's exit code / `steps.diagnose.outcome`
  alone* — rejected: `continue-on-error` normalizes every non-zero exit to
  the same `outcome: failure`, with no distinction between "SDK ran and
  errored" and "SDK never started" — exactly the distinction retry
  eligibility depends on. The execution-output file preserves that
  distinction; the step outcome alone does not.

## R3 — Root-causing the specific issue-#117 crash signature (FR-005)

**Decision**: This plan does not assert which of the four already-known
crash signatures (`Action failed with error`, `SDK execution error`,
`Workflow initiated by non-human actor`, `json-schema is not valid JSON`)
fired in run 30161188955 — `gh run view`/`gh api .../jobs/.../logs` against
that run were not reachable from this planning stage's sandbox (`gh issue
view` succeeded; every `gh run`/`gh api` invocation attempted required
interactive approval this headless stage does not have — the identical
boundary `specs/020-fix-watchdog/`'s own research.md R3 hit and documented).
The implement stage, which needs that same access to write and verify the
fix regardless, must fetch the job log for run 30161188955 (or, if it has
aged out of retention, fault-inject the same signature per quickstart.md
Scenario 3) and follow this decision tree:

| Confirmed signature | Root cause action |
|---|---|
| `SDK execution error` or `##[error]Action failed with error` | Already covered structurally: R2's retryable branch now gives this class a second attempt. Confirm the retry fires for it (quickstart.md Scenario 2); no further code change required unless the log reveals a more specific, fixable cause underneath the generic message. |
| `Workflow initiated by non-human actor` | Not retryable under R2 (declines before the SDK runs) — the actual fix is to widen or correct `allowed_bots` (currently `"github-actions,${{ steps.ctx.outputs.bot-slug }}"`) for whatever actor triggered run 30161188955; confirm what `steps.ctx.outputs.bot-slug` resolved to for that run's trigger context and whether it matched the real actor. |
| `json-schema is not valid JSON` | Not retryable under R2 — the actual fix is correcting the inline `--json-schema` string in the `Diagnose` step's `claude_args`, most likely a shell-quoting or escaping regression; diff the schema string as sent against what the CLI actually received. |

Whichever branch applies, the fix must not weaken the crash-signature
detection `verify-watchdog-run.sh` already performs (FR-007) — the targeted
fix corrects the underlying cause so the signature stops firing; it does not
touch the verifier's ability to still catch it if it recurs.

**Rationale**: `specs/020-fix-watchdog/`'s planning hit the identical
tool-access boundary and resolved it the same way — proceeding on a
static-analysis-grounded decision tree rather than blocking planning, with
exact confirmation deferred to the stage that has the access to act on it.
The general retry/honesty mechanism (R1, R2) is correct regardless of which
specific signature matches, since the classification split in R2 already
covers all four known signatures by shape, not by name — only the *targeted*
half of FR-005 (fixing the specific underlying cause so it stops recurring)
needs the confirmed identity.

**Alternatives considered**: Blocking planning until log access is
available — rejected for the same reason `specs/020-fix-watchdog/` rejected
it: the fix design here does not depend on which branch of the decision
table applies, and the spec's own Assumptions anticipate this class of
follow-up confirmation.

## R4 — Diagnose job timeout with a bounded retry

**Decision**: Raise the `diagnose` job's `timeout-minutes` from 20 to 35.
Each `Diagnose` step attempt keeps its existing 10-minute step-level timeout
unchanged; two attempts back-to-back is a 20-minute worst case for the agent
steps alone, plus the job's existing checkout/preflight/context/read-back/
report overhead (well under a minute in the common case, per
`specs/020-fix-watchdog/`'s own SC-006 timing note). 35 minutes gives
comfortable headroom above the 20-minute agent-step worst case without
materially loosening the ceiling `verify-watchdog-run.sh`'s own runtime-
anomaly band (check 2) polices — that band derives its ceiling from this
workflow's *observed* history, so a job that only occasionally uses its
second attempt does not itself change what "normal" looks like for a run
that didn't retry.

**Rationale**: The job timeout must not fire between a legitimate retryable
crash and its retry attempt completing — 20 minutes was sized for exactly
one attempt (research.md context: `specs/015-pipeline-watchdog/`'s original
diagnose job) and does not leave room for a second.

**Alternatives considered**: Shortening the retry attempt's own step timeout
(e.g. 5 minutes) instead of raising the job timeout — rejected: a retry is
meant to be a second genuine attempt at the same task under the same
`--max-turns` budget, not a degraded one; shortening it risks the retry
itself becoming the next crash-with-no-terminal-result case R2 is designed
to stop masking.
