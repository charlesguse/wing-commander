# Research: Post-agent full-suite verdict

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The decisions below are
plan-level choices made without clarification.

## D1: Where the verdict is decided

- **Decision**: new credential-free job `gate-suite-implement-post` plus a new
  App-token job `implement-dispatch` that reads the verdict and dispatches.
- **Rationale**: matches the board loop's fix → gate-suite-fix → publish split
  and spec 095; only way to run the suite after the agent without the token.
- **Alternatives**: run the suite inside `implement` (breaks credential
  boundary; the retry leg's in-job suite is an existing, tracked exemption);
  run it in finalize (finalize would then discover red after hand-off,
  contradicting FR-005).

## D2: Moving the dispatch out of `implement`

- **Decision**: move "Dispatch next step" and the convergence-dependent tail
  (stalled hand-off, `stage:stalled` label removal, metrics convergence field)
  into `implement-dispatch`; `implement` exports their inputs as job outputs
  (`tasks-converged`, `handoff`, `truncated`, `routed`, `reason`,
  `stall-comment`, `remaining`, `tier`, `head-sha`, `cycle-outcome`, cost
  line). Job outputs are masker-checked and size-limited; large text
  (`remaining`, `cycle-outcome`) travels as an artifact, as
  `implement-stall-diagnostics` already does.
- **Rationale**: a step in `implement` cannot read a job that needs it.
- **Alternative**: keep dispatch in `implement`, add a third job that
  re-dispatches on red — rejected: double dispatch and a window where finalize
  is already dispatched.
- **Risk**: metrics record emission currently lives in `implement`; the plan
  emits the convergence field from the dispatch job and
  `verify-metrics-summary-record-emission.py` must keep passing.

## D3: Head binding

- **Decision**: `implement` publishes `head-sha` (its final pushed commit,
  whichever leg pushed it). The post job gates `origin/<spec-branch>` via the
  composite's `head-ref`; the reader compares the verdict's head to
  `head-sha`, so a moved branch reads as absent (spec edge case).
- **Alternatives**: bundle artifact (implement does not produce one; the
  spec-branch checkout path already exists for cycle-start).

## D4: Fail closed when the suite exists but cannot run

- **Decision**: a shared composite `wing-commander-gate-suite-prepare` runs the
  branch resolution and preflight for both the cycle-start and post jobs and
  exports `script-exists`, `ready`, `missing`. The post job's `ready` is
  `false` with `script-exists == 'true'` → dispatch job records not converged
  naming `missing` (FR-013). `script-exists == 'false'` → converge on tasks.
- **Rationale**: the preflight `run:` block would otherwise be pasted a second
  time (CLAUDE.md "Shared logic has exactly one home"); add a single-home
  check to `verify-implement-gate-suite-preflight.py`.
- **Alternative**: degrade to skip like cycle-start — rejected by the owner
  (clarification 2026-11-26).

## D5: Delivering the stall hand-off verdict to finalize

- **Decision**: `implement-dispatch` posts a marker comment
  (`<!-- wing-commander:post-agent-verdict -->` with outcome, head, first
  failing gate fenced) before dispatching finalize; finalize reads the latest
  marker for the spec's lifecycle issue and renders it in the final PR body.
  If the post job is still running at the budget, the dispatch job posts
  "no verdict produced" and proceeds.
- **Rationale**: no change to the finalize dispatch inputs (FR-014); comment is
  durable and readable by owner. A spec-meta.json field was rejected: it needs
  a push by a job that holds the token on a branch the agent writes.
- **Alternative**: new workflow_dispatch input — forbidden by FR-014.

## D6: Waiting bounded by the suite budget

- **Decision**: the post job's own `timeout-minutes` (30) and suite budget (25)
  mirror cycle-start. `implement-dispatch` uses `needs`, so it waits for the
  job's end; a hung job is bounded by the timeout, and on the hand-off path
  `!cancelled()` plus the result lets it proceed with "no verdict".
- **Rationale**: no polling needed; `needs` gives the wait.

## D7: Agent guidance

- **Decision**: replace the "full suite, set Bash timeout to 600000" bullet and
  the "before pushing run the full suite" instruction with the by-name form
  (`python .github/scripts/run-local-gates.py <name>…`, existing filter),
  and state the verdict comes after. CLAUDE.md "Before pushing" is changed in
  the same PR; a gate checks the two do not contradict (FR-008).
- **Rationale**: owner decision; no selector (FR-009).

## D8: Verdict site and registries

- **Decision**: add site `implement-post` to `wc_gate_verdict.py` SITES, the
  verdict schema contract, `wc_gate_suite_sites.SITES` (reader
  `implement-dispatch`), and the composite descriptions. Gates 7, 62
  (job-name constants), credential-free and project-single-home tables get the
  new job.

## Implementation findings (cycle 1, T001)

Divergences from the plan found while reading `implement.yml` and the
composites:

- **Prepare composite scope.** The composite cannot hold the pipeline
  checkout (it is loaded from that checkout), so
  `wing-commander-gate-suite-prepare` holds only the branch resolve and the
  preflight; the pipeline ref/checkout and the actionlint install stay in the
  job. Consequence: when the pipeline checkout fails, the composite does not
  run, so `script-exists` is empty and the job reports the checkout as the
  missing prerequisite (it used to still report whether the repository had a
  suite). The implement job's `script-exists || 'true'` fallback is unchanged.
- **Exact-head input (T004).** No new input on the contained composite: it
  already gates `origin/<head-ref>` and the reader binds the verdict to
  `expected-head-sha`, so a branch that moved between the push and the post
  job reads as a `head_sha mismatch` failure (fail closed).
- **Job outputs are prose-free (#309).** `implement-dispatch` needs the
  remaining-work text, stall comment and cycle outcome that the `implement`
  job's dispatch step reads today as step outputs. Those are model-written
  prose and cannot travel as job outputs (`verify-job-outputs-prose-free.py`);
  moving the dispatch needs an artifact or a re-derivation from the pushed
  branch for them.
