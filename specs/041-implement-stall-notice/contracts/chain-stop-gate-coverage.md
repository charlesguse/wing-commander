# Contract: Gate 15 (amended) and Gate 28 (new)

## Gate 15 — amendment only

**File**: `.github/scripts/verify-gate-15.py`, exercising the "Gate 15" step
inline in `.github/workflows/lint-workflows.yml`.

**Change**: the `NON_SUCCESS_ARM` detection rule is broadened from matching
only `needs.<job>.result == '<value>'` comparisons to also matching
`needs.<job>.outputs.<name> == '<value>'` comparisons that sit in a job's
`if:` with no status-check function (`always|success|failure|cancelled`)
anywhere in the same expression. Every existing fixture in `CASES` is kept
byte-for-byte; new fixtures are appended, not inserted, so a diff shows this
as strictly additive.

**New fixtures required**:
1. A synthetic job whose `if:` is exactly `stalled`'s pre-fix condition
   (`needs.implement.outputs.final-ok == 'false'`, no status function) —
   MUST be flagged. This is the regression proof: the defect this whole
   feature exists to fix must be mechanically detectable, not just
   observed once and fixed by hand.
2. The same shape, now with `!cancelled() &&` prefixed — MUST NOT be
   flagged (the fixed shape is clean).
3. An existing-style `.result` comparison, unchanged, still flagged exactly
   as before the amendment — regression guard on the original rule.

**Verification**: Gate 15's own self-test already runs the extracted Python
against every `CASES` entry and asserts pass/fail plus specific substrings
in the error text (existing mechanism, unmodified) — the new fixtures slot
into that existing loop.

## Gate 28 — new gate

**File**: `.github/scripts/verify-chain-stop-notice.py`, wired into
`.github/workflows/lint-workflows.yml` as a new step, "Gate 28 — a stage
that dies at entry reaches the chain-stop notice, and nothing else does."

**Wiring**: picked up automatically by `wc_gate_registry.py`'s filename
convention (`verify-*.py` under `.github/scripts/`, invoked by a `run:` in
some `lint-workflows.yml` step) — no registry file to hand-edit (FR-014).
Gate 10 (existing, unmodified) already asserts this wiring is complete in
both directions.

**Mechanism** (research.md D8): a minimal evaluator for the expression
subset the seven survivor-job conditions actually use
(`!cancelled()`, `&&`, `||`, `==`, `!=`,
`needs.<job>.result`/`needs.<job>.outputs.<name>` substitution). For each of
the seven call sites (data-model.md's condition table):

1. Extract the job's `if:` string directly from the shipped workflow YAML
   (job-aware extension of `wc_shell_harness.py`'s existing step-lookup
   pattern — reads the job dict by id, not a step within it).
2. Evaluate it against a table of modelled `needs.*` combinations, each
   tagged with the expected boolean and the acceptance-scenario/FR it
   corresponds to:

| Modelled `needs.*` | Expected | Covers |
|---|---|---|
| entry job `result: success`, no refusal, no exhausted-retry flag | `false` | FR-004/US3 — a healthy run must not reach the notice |
| entry job `result: success`, `outputs.refusal-reason` non-empty | `false` | FR-005/FR-006 — a refusal already produced its own notice in-job |
| entry job `result: failure`, `outputs.refusal-reason` non-empty | `false` | same — a refusal that also fails the job must still not double-post |
| entry job `result: failure`, `outputs.refusal-reason` empty | `true` | FR-001/AC1 — the gate-failure/crash case |
| entry job `result: skipped` | `true` | FR-001/AC3 — the entry-level-dependency-failed case |
| upstream dependency `result: failure`, entry job `result: skipped` | `true` | same, upstream arm |
| run `cancelled` (job-level `result` irrelevant) | `false` | FR-009 — a cancelled run must not produce a notice |
| implement only: entry job `result: success`, `outputs.final-ok: 'false'`, `outputs.refusal-reason` empty | `true` | the pre-existing exhausted-retry case, still reachable after the widening |

3. Assert every row's actual evaluation matches its expected boolean, for
   all seven call sites.
4. Apply each of the four required mutations (data-model.md's mutation
   table) to a copy of the extracted condition string and re-run step 3,
   asserting at least one row now disagrees with its expected boolean for
   every mutation (FR-013) — following the `if mutated == original` guard
   `verify-stall-restart-runbook.py` already establishes, so a mutation that
   silently failed to apply cannot produce a false pass.

**What this gate does NOT do**: it does not execute the composite's own
shell (that is `wc_shell_harness.py`'s job, exercised separately for the new
composite's steps, following the same `run_step`/stubbed-`gh` pattern
`verify-stall-restart-runbook.py` established for the existing `stalled`
job). Gate 28 proves *reachability* of the notice path; step-body execution
proves the notice path, once reached, does the right thing. Splitting these
two concerns mirrors this repository's existing Gate 14 (executes shipped
shell) / Gate 15 (checks condition shape) split — Gate 28 is the executable
counterpart to Gate 15's static one, scoped to this feature's specific
conditions rather than every job in the fleet.
