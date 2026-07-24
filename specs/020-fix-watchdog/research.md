# Phase 0 Research: Fix the Watchdog — Restore Reliable Run Inspection

All three `[NEEDS CLARIFICATION]` markers in spec.md were already resolved by
the requester on issue #96 before planning started (Q1:A, Q2:A, Q3:C — see
spec-meta.json/checklist notes). Phase 0 research below is about the
*technical* unknown planning still had to resolve: **what in the codebase
actually causes the reported "job/step failed, no verdict" symptom**, and how
to fix it in a way that satisfies FR-008's broader-hardening scope.

## R1 — Root cause of the reported failure

**Decision**: The failure mechanism is a missing failure boundary in the
`collect` job of `.github/workflows/watchdog.yml`. Steps that run before the
five (already `continue-on-error: true`) evidence collectors —
"Checkout consumer repository", "Resolve pipeline ref", "Checkout pipeline
repository", "Preflight", "Wing Commander context", and especially "Fetch
inspected run metadata" (`gh run view "$RUN_ID" ...` under `set -euo
pipefail`, no `continue-on-error`) — have no error handling at all. If any of
them fails (a transient `gh run view` error, GitHub API eventual-consistency
right after the triggering `workflow_run` event fires, a token-minting hiccup,
etc.), the whole `collect` job fails. Because `diagnose` (`needs: collect`),
`triage` (`needs: [collect, diagnose]`), and `act` (`needs: [collect,
diagnose, triage]`) all implicitly require their `needs` to have *succeeded*
(GitHub Actions ANDs a job's `if:` with `success()` unless the `if:` itself
starts with `always()`/`failure()`/etc.), a `collect` failure skips every
downstream job. The run ends as a single failed job with no comment posted to
the lifecycle issue and nothing written to the run summary — precisely
FR-002's forbidden outcome, and precisely Q1:A's "the watchdog workflow
errored/failed (a job/step failed) so the run never reached a verdict."

**Rationale**: This is derived from static reading of
`.github/workflows/watchdog.yml` (research done during planning) rather than
from the original run's logs — see R3 below for why, and what the implement
stage must still confirm. The hypothesis fits every constraint the
clarification answers impose: it explains a hard job/step failure (Q1:A), it
is reachable from the automatic per-stage trigger the same as any other
trigger since `collect` runs identically regardless of caller (Q2:A), and
fixing it structurally (one safety-net job) rather than patching one flaky
call addresses the broader class of "some step somewhere hard-fails" instead
of only today's specific culprit (Q3:C).

**Alternatives considered**:
- *Patch only the one likely flaky call* (add a retry/backoff around `gh run
  view` in "Fetch inspected run metadata"). Rejected as the sole fix: it
  would plausibly resolve today's specific occurrence but leaves every other
  un-guarded step (token minting, pipeline-repo checkout, preflight) equally
  capable of producing the same silent no-verdict failure, which FR-008
  explicitly asks this feature to also cover.
- *Wrap every step in `continue-on-error: true`*. Rejected: several of these
  steps produce outputs later steps and jobs hard-depend on (e.g. `run-id`
  metadata, the GitHub App token); silently continuing past their failure
  would let subsequent steps fail confusingly or, worse, run with stale/empty
  values and produce a wrong verdict rather than an honest "could not
  inspect." A verdict must be truthful (FR-002), not merely present.
- **Chosen**: add one workflow-level safety-net job (`report-unhandled-
  failure`, `needs: [collect, diagnose, triage, act]`, `if: always()`) that
  inspects each job's `result` and, if any is `failure` or `cancelled`, posts
  a "could not inspect this run" verdict naming the failed job and linking
  its logs — to the lifecycle issue if one resolves, else the run summary.
  This preserves truthful, source-specific "could not inspect" reporting for
  the *existing* all-collectors-failed case (data-model.md, unchanged) while
  adding a second, broader catch-all for the "a job itself hard-failed"
  case FR-002/FR-007 also require. It is additive and does not change any
  existing job's detection/triage/guardrail logic, keeping
  `specs/015-pipeline-watchdog/` intact per this feature's own Assumptions.

## R2 — Where the safety net's report differs from the existing "could not inspect" path

**Decision**: Keep these as two distinct report variants, not one merged
message, because they carry different diagnostic information and cover
non-overlapping failure shapes:

| Variant | Trigger | Where it already lives | What's new |
|---|---|---|---|
| "Could not inspect — evidence unreadable" | `collect` job *succeeds* but all five evidence collectors fail (data-model.md, FR-005) | Already implemented (`Report "could not inspect" to lifecycle issue` step) | Unchanged |
| "Could not inspect — <job> failed" | Any job (`collect`/`diagnose`/`triage`/`act`) itself ends `failure`/`cancelled` | Does not exist today — this is the gap behind issue #96 | New `report-unhandled-failure` job (FR-002/FR-007) |

**Rationale**: Merging them into one code path would require the new safety
net to re-derive `evidence-available`/lifecycle-issue context from a job that
may itself have failed before producing those outputs — exactly the scenario
it must be robust to. Keeping the safety net independent (it re-resolves the
GitHub App token, lifecycle issue, and run URL itself, tolerating any of
those individual lookups failing too) is what makes it a true last-resort net
rather than another link in the same failure-prone chain.

**Alternatives considered**: Making every existing job's outputs
`if: always()`-safe so a single downstream job could read them uniformly —
rejected as much larger surface area to change (every job, every step) for
the same result the additive safety-net job achieves with a single new job
and zero changes to existing job logic.

## R3 — Verifying against the actual reported run

**Decision**: This plan does not assert the exact failing step of run
`30118703536` (the run linked from issue #96) as a certainty — it names the
most probable candidate steps from static analysis (R1) as the implement
stage's starting hypothesis, to be confirmed by pulling that run's job logs
(or, if the run has aged out of retention, a fresh reproduction) at the start
of implementation, per this spec's own "Reproducibility over a single run
link" assumption.

**Rationale**: Fetching that specific run's logs directly (`gh run view`,
`gh api .../actions/runs/.../jobs`, `gh run list`) was not available in the
sandboxed environment this plan was authored in — those specific `gh`
subcommands require an interactive approval this pipeline stage runs without.
Every other necessary fact (workflow structure, job dependency graph, error-
handling gaps) is verifiable directly from the checked-in workflow YAML,
which is sufficient to design the fix and its regression protection; only
pinpointing *which* of the several unguarded steps actually failed in that
one historical run requires log access the plan stage didn't have. This is
recorded here as a decision made without that clarification, per this
pipeline's standing instruction to proceed rather than block.

**Alternatives considered**: Blocking planning until log access is available
— rejected; the fix design (R1/R2) is correct regardless of which specific
unguarded step failed first, since the safety net catches all of them
uniformly, and the spec's own Assumptions already anticipate the original run
may not be available for verification.

## R4 — Regression protection scope (FR-008)

**Decision**: Two forms of regression protection, both additive:
1. The `report-unhandled-failure` safety-net job itself (R1) is the
   structural guard — it cannot be silently bypassed by a future unguarded
   step the same way today's gap can, because it watches *job-level*
   outcomes rather than needing every individual step pre-anticipated.
2. `docs/architecture.md`'s Stage 9 section gets the new job documented,
   so a future change to `watchdog.yml` that removes or narrows it is a
   visible documentation drift, not a silent regression.

**Alternatives considered**: A scheduled synthetic-failure smoke test (a
cron-triggered workflow that deliberately breaks a step and asserts a verdict
still posts) — considered for future hardening but out of scope here; this
spec's Assumptions keep the fix scoped to restoring
`specs/015-pipeline-watchdog/`'s already-specified behavior, and FR-025
(scheduled catch-up sweeps) is explicitly deferred beyond v1 in that spec.
The quickstart's manual fault-injection scenario (quickstart.md) is the
verification mechanism for this iteration.
