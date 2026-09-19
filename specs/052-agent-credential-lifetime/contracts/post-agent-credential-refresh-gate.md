# Contract: Gate 68 — `verify-post-agent-credential-refresh.py`

**File**: `.github/scripts/verify-post-agent-credential-refresh.py`, wired
into `.github/workflows/lint-workflows.yml`'s existing PR-time job (a new
`run:` step naming the script — no registry file to hand-edit;
`wc_gate_registry.py`'s filename convention picks it up automatically, and
`verify-gate-wiring.py` confirms the wiring is complete in both
directions).

**Numbering**: the highest gate at plan time was Gate 66
(`verify-auto-release-e2e-gate-decisions.py`), so this gate provisionally
claimed Gate 67 — but #401 (`verify-auto-release-credential-step.py`)
landed first on the same base and took that number, so this gate is
**Gate 68**, matching this repository's own documented renumbering norm
(see the Gate 62–67 collision comments in `lint-workflows.yml`).

## Subject

The 8 workflow files FR-007 names, by literal path:
`.github/workflows/intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`,
`implement.yml`, `finalize.yml`, `pr-conversation.yml`,
`auto-update-spec-kit.yml` (scoped to its `e2e-stage` job only). Agent steps
are identified structurally — a step whose `uses:` resolves to
`anthropics/claude-code-action@*` (the same marker every existing gate that
locates an agent step already keys on) — not by a hardcoded step-id list,
so a stage's agent step being renamed does not silently blind the check.

## What it checks

1. **No stale credential reference** (FR-020 care point 1): for every job
   containing at least one agent step, every step positioned after the
   *first* agent step must not reference `steps.<any-id>.outputs.token` (or
   `steps.<any-id>.outputs.*token*` generally, to also catch
   `scratch-token`) directly — it must resolve its credential through
   `env.WC_BOT_TOKEN` or `env.WC_SCRATCH_TOKEN` instead. A step positioned
   *before* the first agent step is exempt (the raw output is still valid
   there, and the one caller that needs it — the initial checkout — is
   expected to use it, per contracts/wing-commander-context-relay.md).
2. **No un-refreshed second (or later) agent step** (FR-020 care point 2):
   for every agent step in a job after the first, a `wing-commander-context`
   (or, for the e2e arm, the scratch-token mint) invocation must appear
   between it and the previous agent step. Absence fails, naming the job
   and the un-refreshed agent step.
3. **No un-tolerated declared-observability step** (FR-021): every step
   whose name or in-place comment matches the "Report over-budget agent
   run" family (data-model.md's 12-row table, matched by a stable name
   pattern, not by line number) must carry `continue-on-error: true`.
4. **Loud failure on an unreachable subject** (FR-022, Constitution
   Principle VIII): if any of the 8 named files does not exist, or a named
   file's expected job (e.g. `e2e-stage` in `auto-update-spec-kit.yml`)
   cannot be located, or zero agent steps are found across all 8 files
   combined, the gate exits non-zero with a message naming which file/job
   it could not reach — never a silent pass over an empty result set.

## Mechanism

Static structural inspection via `yaml.safe_load` over each of the 8 files
(the same approach `verify-plan-tasks-cost-line.py` and
`verify-implement-stall-notice-unchanged.py` already use for their
subjects) — this gate's subject is step *ordering and reference shape*,
not runtime behaviour, so no `wc_shell_harness.py` execution pass is
needed. `bash -n` (an existing, separate PR-time gate) already proves every
`run:` block it touches is syntactically valid shell.

## Fixtures (FR-023 — every failure branch checked in)

Following `verify-plan-tasks-cost-line.py`'s `MUTATIONS`-over-the-live-tree
convention (`self_test()`, run as part of the script's own `--self-test`
invocation, itself wired as a step in `lint-workflows.yml`):

| Mutation | Expected result |
|---|---|
| Clean tree (no mutation) | PASS |
| Rewrite one post-agent step's credential reference back to `steps.ctx.outputs.token` | FAIL — names the workflow, job, and step (check 1) |
| Delete the refresh step between `implement.yml`'s `retry` and `progress` agent steps | FAIL — names `implement.yml`, the `implement` job, and `progress` (check 2) |
| Strip `continue-on-error: true` from `clarify.yml`'s canonical "Report over-budget agent run" step | FAIL — names `clarify.yml` and the step (check 3) |
| Point the subject list at a 9th, nonexistent workflow file | FAIL — "could not reach subject," not a pass over the other 8 (check 4) |
| Point the subject list at zero workflow files | FAIL — same, empty-result guard (check 4) |

Every mutation is applied to a `copy.deepcopy` of the real parsed tree, not
a checked-in synthetic YAML fixture file — consistent with research.md D6's
rationale (the real 8 files are the fixture; no second copy to keep in
sync).

## Local/CI parity (FR-022)

`run-local-gates.py` derives this gate's invocation from
`lint-workflows.yml`'s own `run:` block (`wc_gate_registry.pr_time_
invocations()`), so the local sweep runs the identical command CI runs —
no separate local-only argument set to drift, matching the parity failure
class Principle VIII and this gate's own precedent
(`verify-versioning-refs.py`'s `--self-test`-vs-`--remote origin` history)
warn against.

## Triggering (FR-022)

`lint-workflows.yml`'s `on.pull_request.paths` already includes
`.github/workflows/**` and `.github/actions/**` (the composite amendment in
contracts/wing-commander-context-relay.md lives under the latter) — no new
path entry is required for this gate's subject alone.
