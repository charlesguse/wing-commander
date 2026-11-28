# Implementation Plan: Post-agent full-suite verdict for implement cycles

**Branch**: `spec/133-post-agent-gate-verdict` | **Date**: 2026-11-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/133-post-agent-gate-verdict/spec.md`

## Summary

An implement cycle is judged by the full local gate suite *after* its agent
finishes, in a credential-free job, before the cycle may be recorded
converged. Approach (board loop's fix-agent → gate-suite-fix pattern, spec 095
boundary):

1. The `implement` job publishes the exact head its agent pushed and its
   tasks-only convergence reading (today's `converged`, renamed
   `tasks-converged`) as job outputs, plus the stall `handoff` flag.
2. A new job `gate-suite-implement-post` (`contents: read`, no App token,
   same runner/image as `gate-suite-implement-cycle`) runs only when
   `tasks-converged == 'true'` or `handoff == 'true'`. It reuses the
   `wing-commander-contained-gate-suite` composite under a new verdict site
   `implement-post`, with a suite budget below the job timeout (FR-007).
3. A new job `implement-dispatch` (holds the App token) `needs` both. It
   reads the verdict fail-closed with `wing-commander-gate-verdict`, computes
   the final `converged` (tasks-converged AND pass bound to the head; fail
   closed when the suite exists but could not run, FR-013), and performs the
   existing "Dispatch next step" logic. It is the only place `converged` is
   decided; the workflow_call output `converged`, the dispatch and the metrics
   record's convergence field all read it (FR-006).
4. On a stall hand-off the dispatch job waits for the post job (bounded by the
   suite budget) and posts the verdict as a marker issue comment on the
   lifecycle issue before dispatching finalize; finalize reads that comment
   and renders it in the final PR body. The finalize dispatch signature is
   unchanged (FR-014).
5. Agent guidance (implement prompt in `implement.yml` and the "Before
   pushing" section of CLAUDE.md addressing the implement agent) is changed to
   "run only the gates for files you changed, by name; the full suite runs
   after you" (FR-008). No changed-file selector (FR-009).

## Technical Context

**Language/Version**: GitHub Actions YAML (workflows + composite actions), Bash, jq, Python 3 (gate scripts, stdlib + PyYAML)

**Primary Dependencies**: existing composites `wing-commander-contained-gate-suite`, `wing-commander-gate-verdict`, `wing-commander-install-actionlint`; `wc_gate_verdict.py`, `wc_gate_suite_sites.py`; `run-local-gates.py`

**Storage**: verdict artifact `wc-gate-verdict-implement-post` (head-SHA-bound JSON); marker issue comment for finalize

**Testing**: `verify-*.py` gates with `--self-test` (new/extended), `python .github/scripts/run-local-gates.py`; post-merge proof by re-driving one implement run (`prove-after-merge`)

**Target Platform**: GitHub Actions runners, caller-supplied container image

**Project Type**: reusable-workflow pipeline (CI/CD infrastructure)

**Performance Goals**: no added full-suite run on non-converging cycles (SC-005); exactly one on converging / stall hand-off cycles

**Constraints**: post job holds no write credential (FR-002/SC-004); suite budget < job timeout (FR-007; cycle-start uses 25 min suite inside 30 min step, same shape); fail closed on any absent/unbound verdict (FR-004); finalize wrapper dispatch signature fixed (FR-014); one home for shared shell (CLAUDE.md)

**Scale/Scope**: one workflow (`implement.yml`) restructured, one finalize read path, 2–3 composites touched/added, ~4 gates extended, docs/reference.md, agent guidance

## Constitution Check

Checked against `.specify/memory/constitution.md` (read at plan time; no
principle text is quoted here). Outcome: **PASS, no justified violations.**

- Credential boundary (spec 095): post job is `contents: read`, no App token,
  checked by extending `verify-gate-suite-credential-free.py` — PASS.
- Fail-closed verdict reading: reuses `wc_gate_verdict.py` reader — PASS.
- Every composite input optional with a default (Constitution VII): new inputs
  default to today's behaviour — PASS.
- Adopter repositories without a suite keep converging on tasks alone — PASS.
- Changing agent guidance (CLAUDE.md, implement prompt) is a rules-change that
  the owner approves with the final PR (spec Assumptions) — flagged, not a
  violation.

Post-design re-check: unchanged, PASS.

## Project Structure

### Documentation (this feature)

```text
specs/133-post-agent-gate-verdict/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── post-agent-verdict.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
.github/workflows/implement.yml              # new jobs gate-suite-implement-post, implement-dispatch; implement outputs; prompt text
.github/workflows/finalize.yml               # read verdict marker comment; show in final PR body
.github/actions/wing-commander-gate-suite-prepare/   # NEW: shared branch-resolve + preflight (cycle and post call it)
.github/actions/wing-commander-contained-gate-suite/ # site list doc; optional exact-head input
.github/actions/wing-commander-gate-verdict/         # site list doc
.github/scripts/wc_gate_verdict.py           # add "implement-post" to SITES
.github/scripts/wc_gate_suite_sites.py       # SITES entry for implement-post
.github/scripts/verify-*.py                  # extend credential-free, preflight, gate-7, single-home gates; new verify-implement-post-verdict.py
docs/reference.md                            # post-agent gate job, budget, convergence effect (FR-012)
CLAUDE.md                                    # "Before pushing" wording for implement agent (owner-approved)
specs/133-post-agent-gate-verdict/contracts/ # live contract
```

**Structure Decision**: extend the existing implement workflow with two jobs
rather than add a workflow, keeping the stage's `workflow_call` interface
(outputs `converged` etc.) stable for callers.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|------|------------|--------------------------------------|
| New `implement-dispatch` job moving "Dispatch next step" out of `implement` | The App-token step that dispatches must run after the credential-free suite, and a job cannot wait on a later job | Running the suite inside `implement` would put agent-authored code beside the App token (breaks spec 095) |
