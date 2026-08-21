# Implementation Plan: A Turn-Exhausted Implement Cycle Is Carried Forward, Not Redone from Cold

**Branch**: `040-truncated-cycle-carry-forward` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/040-truncated-cycle-carry-forward/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`.github/workflows/implement.yml`'s "Read back cycle outcome" step
(lines 878–926) today collapses a turn-exhausted cycle (`error_max_turns`,
already classified `verdict=exhausted` by the existing
`wing-commander-agent-verdict` composite it runs *after*, lines 798–804)
into the same `ok=false` bucket as a genuine crash — triggering an
escalated redo of the same iteration from a cold context on
`inputs.escalation-model` (the "Implement and converge (retry at
escalation model)" step, lines 957–1077), discarding whatever the
truncated cycle already pushed. This plan rewires that one step (plus its
retry-path mirror and the downstream consolidation/dispatch steps) to read
the verdict composite's already-computed `exhausted` value, test the
branch for positive evidence of progress, and — only when both hold —
classify the cycle **truncated**: `ok=true` (so the existing retry gate,
`steps.outcome.outputs.ok == 'false'`, and the existing `stalled` job gate,
`needs.implement.outputs.final-ok == 'false'`, both stop firing for it
*without either condition's text changing*), `converged` forced `false`
without ever running the converge-commit-absence scan, and the next
iteration dispatched at the same tier via the loop's existing
`self-workflow` re-dispatch.

**Classification** (research.md D1/D2): `truncated` is a new step output,
not a fourth `ok`/`converged` state — it collapses onto the existing
`ok=true` "advance" path so every downstream `if:` that already reads
`ok`/`final-ok` needs no edit (FR-017's "no existing path may be widened"
holds by construction, not by review). Truncated requires three positive
conditions together (FR-002): `verdict=="exhausted"`; `spec-meta.json`
advanced to `(implement, N)`; and progress (below). Any one failing keeps
today's failed path untouched.

**Progress test** (research.md D3): two arms, either sufficient (FR-004) —
a higher checked-task count in `tasks.md` between `BASE_SHA` and the
branch tip (Arm A), or any changed file outside the spec directory
(Arm B). The lifecycle-record advance (`spec-meta.json`, inside the spec
directory, not `tasks.md`) satisfies neither arm by construction, so
FR-004a's exclusion needs no separate SHA-identification logic — a cycle
whose only landed change is its own bookkeeping commit fails both arms and
is correctly classified failed.

**Convergence** (research.md D4): forced `false` on the truncated path by
*skipping* the existing converge-commit scan entirely, not by running it
and overwriting a `true` result afterward — R1's blocking risk (spec.md)
gets no intermediate `converged=true` value for a future edit to
accidentally ship past.

**Retry classified the same way** (research.md D7, FR-016): a new "Record
retry base SHA" step captures the branch tip immediately before the retry
runs, so a truncated retry's own progress test is measured against where
the *retry* started (after the primary's partial work), not the original
`base-sha` — otherwise a retry that made zero further progress would
inherit the primary's progress and be wrongly carried forward instead of
escalating (there is nowhere further to escalate to at that tier — S5).

**Counter and reporting** (research.md D5/D6): a new `spec-meta.json`
field, `truncated_count`, written deterministically (not by the agent —
D5's rationale: a truncated agent cannot reliably report on its own
truncation) by a new "Record truncated-cycle count" step, incremented on
`truncated`, reset to 0 on any completed *or* failed cycle (FR-011,
including across a stall-then-manual-restart boundary). "Dispatch next
step" (lines 1422–1485), already the deterministic step composing every
other lifecycle-issue outcome message, gains two new branches — truncated
below cap, truncated at cap — ahead of its existing `CONVERGED != true`
branches, so a truncated cycle is never worded as "failed" or as an
unexplained non-convergence (FR-013, FR-015), and the at-cap case states
the last cycle ran out of turns instead of printing the empty
remaining-work list a truncated cycle's missing convergence pass would
otherwise produce (FR-014).

**Coverage** (research.md D8): a new
`.github/scripts/verify-truncated-cycle-carry-forward.py`, following
`verify-stall-restart-runbook.py`'s (Gate 14) real-git-repo-plus-bare-
remote shape — the shape this feature's own commit/push side effect (the
counter write) needs proven for real, not the transcript-only shape
Gate 22 uses for the verdict composite itself (already proven, reused
here only as a trusted stubbed input). Wired into
`.github/workflows/lint-workflows.yml` as **Gate 26** (next unused —
confirmed against every `Gate N —` occurrence in the file, highest in use
today is Gate 25 from specs/039-lifecycle-gate-retry), with six scenarios
and five required mutations (FR-019) plus a reflexive presence check
(FR-020).

See [research.md](./research.md) for the full decision record,
[data-model.md](./data-model.md) for the concrete shapes, and
[contracts/](./contracts/) for `implement.yml`'s updated internal-behavior
contract and the new coverage script's contract.

## Technical Context

**Language/Version**: Bash (the `run:` steps rewritten/added in
`implement.yml`), Python 3 (`.github/scripts/verify-truncated-cycle-
carry-forward.py`, matching every existing `verify-*.py` gate script) —
no new language introduced.

**Primary Dependencies**: `jq`, `git` (already the sole dependencies of
every step this feature touches), `wc_shell_harness.py` (existing, reused
unmodified — its `find_step`/`run_step`/`parse_github_output` API already
covers what the new coverage needs), the existing
`wing-commander-agent-verdict` composite (consumed as an already-computed
upstream output, not modified).

**Storage**: `spec-meta.json` on each spec's persistent branch gains one
new field, `truncated_count` (data-model.md). No other persisted state;
every other new value (step outputs) lives only for the duration of the
`implement` job.

**Testing**: New `.github/scripts/verify-truncated-cycle-carry-forward.py`,
wired into `.github/workflows/lint-workflows.yml` as Gate 26, executing
`implement.yml`'s real `run:` step text against synthetic git history in a
real repo with a local bare remote (research.md D8). Covers: truncated
with progress via either arm (US1, US2, FR-004, FR-005), no-progress
escalation (US3, FR-004), the retry path classified the same way (US4,
FR-016), the consecutive-truncation counter's increment/reset (US5,
FR-011), the at-cap and below-cap reporting text (FR-013/FR-014/FR-015),
an unaffected ordinary failure and an unaffected normal successful cycle
(FR-017), and the five required regression mutations (FR-019) plus the
gate's own reflexive wiring check (FR-020).

**Target Platform**: GitHub Actions `workflow_call` stage, `ubuntu-latest`
runner, dispatched by `wing-commander-5-implement.yml` exactly as today.

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: No added latency on any non-`exhausted`-verdict
cycle (FR-017) — those paths read one new env var
(`steps.cycle-verdict.outputs.verdict`, already computed) and take the
identical branch they do today. A truncated cycle's own added cost is one
new git commit+push (the counter write) and a handful of `git log`/`git
diff --name-only` reads already within the job's existing `git fetch`
scope — no new network calls beyond what "Read back cycle outcome"
already makes.

**Constraints**:
- `implement.yml`'s declared `workflow_call` inputs/outputs do not change
  (FR-021) — no calling wrapper needs an edit.
- No turn budget, turn-budget ceiling, or default iteration cap changes
  (FR-022) — this feature changes only what happens when a budget is
  exhausted.
- Every existing gate condition text (`steps.outcome.outputs.ok ==
  'false'` on the retry steps, `needs.implement.outputs.final-ok ==
  'false'` on the `stalled` job) is unchanged — truncated collapses onto
  `ok=true` specifically so these do not need editing (research.md D2).
- The progress test must never treat the lifecycle-record advance itself
  as evidence of progress (FR-004a) — satisfied by the two arms' own
  scope (research.md D3), not by excluding a specific commit SHA.
- Coverage must independently kill five distinct regressions (FR-019),
  not merely exercise the happy path.

**Scale/Scope**: One file changed with new steps and rewired existing
steps (`.github/workflows/implement.yml`: "Read back cycle outcome",
"Read back retry outcome", "Consolidate final outcome", "Dispatch next
step" rewired in place; "Record retry base SHA", "Record truncated-cycle
count" newly added), one new file added
(`.github/scripts/verify-truncated-cycle-carry-forward.py`), one new gate
step added to `.github/workflows/lint-workflows.yml` (Gate 26). Zero edits
to `wing-commander-5-implement.yml`, to any other calling wrapper, to the
`wing-commander-agent-verdict` composite, or to any other composite
action.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #179 → this spec → this plan → tasks → implement), validated by the same shell-harness/gate-registry machinery (`wc_shell_harness.py`, `wc_gate_registry.py`) the repository already runs on itself. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (`plan.yml`'s planning-weight default). The feature adds no new agent invocation — every new/rewired step is deterministic bash reading an already-computed upstream output; it changes *when* the existing escalation-tier agent invocation fires, never adds one. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | No new interaction surface. The lifecycle issue still carries every status this feature reports (US5, FR-013) — a maintainer reads the same issue thread they already do, with more accurate wording, not a new dashboard. | ✅ Pass |
| IV. Automation-First | A truncated cycle with progress now proceeds fully automatically (no human restart, S5/US4) where today it can dead-end at `stalled`. A truncated cycle with no progress still escalates automatically, exactly as today. Every new state (`truncated_count`) is reported explicitly to the lifecycle issue, never silently tracked (FR-011, FR-012). | ✅ Pass |
| V. Security — untrusted content is never instructions | No change to what any step trusts: `spec-meta.json`, `tasks.md` checkbox counts, and file-change lists are read from the pipeline's own git history on its own branch, never from issue/comment text or `github.event.*`. No new tool grant, no new secret. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | Unaffected — `implement.yml` and `lint-workflows.yml` already live under `.github/**`, resolved from the pipeline repository's own checkout; this feature adds no new resolution path. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | `implement.yml`'s published `workflow_call` contract (inputs, outputs, required access) is explicitly unchanged (FR-021, contracts/implement-cycle-outcome.md) — this is an internal-behavior change to the published contract's implementation, not a surface change. No new stage-side ambient-state read (`spec-meta.json` is already stage-owned state, not `vars.*`/`github.event.*`). No deviation to register. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design
(data-model.md, contracts/, quickstart.md) confirms every new field lives
either in a step output (ephemeral, job-scoped) or in `spec-meta.json`
(already the stage's own lifecycle state, not a new external surface), and
introduces no new untrusted-input path — the progress test reads only
this repository's own commit history on the spec's own branch.

## Project Structure

### Documentation (this feature)

```text
specs/040-truncated-cycle-carry-forward/
├── plan.md                                   # This file (/speckit-plan command output)
├── research.md                               # Phase 0 output (/speckit-plan command)
├── data-model.md                             # Phase 1 output (/speckit-plan command)
├── quickstart.md                             # Phase 1 output (/speckit-plan command)
├── contracts/                                # Phase 1 output (/speckit-plan command)
│   ├── implement-cycle-outcome.md            # updated implement.yml internal-behavior contract (delta)
│   └── truncated-cycle-coverage.md           # new coverage script's contract
├── checklists/
│   └── requirements.md                       # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                  # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src`/`tests` split. The real layout this
feature touches:

```text
.github/
├── workflows/
│   ├── implement.yml                 # "Read back cycle outcome" (878-926) and
│   │                                  #   "Read back retry outcome" (1146-1196)
│   │                                  #   rewired: read the verdict composite's
│   │                                  #   already-computed `exhausted` value, run
│   │                                  #   the two-arm progress test, force
│   │                                  #   converged=false on truncation.
│   │                                  #   "Consolidate final outcome" (1201-1230)
│   │                                  #   gains a `truncated` passthrough.
│   │                                  #   "Dispatch next step" (1422-1485) gains
│   │                                  #   truncated-below-cap / truncated-at-cap
│   │                                  #   report branches. NEW: "Record retry
│   │                                  #   base SHA" (before the retry step),
│   │                                  #   "Record truncated-cycle count" (after
│   │                                  #   consolidation). Retry/stalled gate
│   │                                  #   CONDITIONS unchanged text throughout.
│   └── lint-workflows.yml            # + Gate 26 — "a turn-exhausted cycle is
│                                      #   classified truncated only with positive
│                                      #   evidence, and carried forward without
│                                      #   ever reporting converged"
└── scripts/
    ├── wc_shell_harness.py           # UNCHANGED — reused as-is
    ├── verify-stall-restart-runbook.py  # prior art for the real-git-repo +
    │                                  #   bare-remote shape (read only)
    ├── verify-agent-verdict.py       # prior art for exhausted/failed/healthy
    │                                  #   verdict fixtures (read only)
    └── verify-truncated-cycle-carry-forward.py  # NEW — Gate 26's script

.github/actions/
└── wing-commander-agent-verdict/     # UNCHANGED — consumed as-is; its
    └── action.yml                    #   `verdict=exhausted` output is this
                                       #   feature's positive-identification
                                       #   source (FR-003), not re-derived
```

**Structure Decision**: No new top-level directory, no new composite
action, no edit to `wing-commander-5-implement.yml` or any other calling
wrapper, no edit to `wing-commander-agent-verdict`. The entire change is:
several steps of one existing workflow file rewired/added in place, one
new verification script, and one new gate step registering that script —
matching the spec's own framing (a narrow, positively-gated
reclassification of one outcome, not a general retry-avoidance framework).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
