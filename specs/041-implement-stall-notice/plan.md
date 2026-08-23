# Implementation Plan: An Implement Run That Dies at Entry Still Marks the Record and Says So on the Issue

**Branch**: `041-implement-stall-notice` | **Date**: 2026-08-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/041-implement-stall-notice/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`implement.yml`'s `stalled` job (`:1492-1701`) is the pipeline's only chain-stop
notice today, and it is reachable for exactly one cause: the implement/converge
loop exhausting its retry budget while the `implement` job itself completes
with a *successful* conclusion (the loop swallows its own failure into an
output, `final-ok: 'false'`). Every other way the stage can stop before
publishing that outcome — the lifecycle-gate step failing outright, the
`Resolve and validate spec identity` / `Verify spec artifacts match the
dispatch` steps refusing a malformed hand-off, or the `verify-image-
prerequisites` job upstream failing so `implement` never starts — leaves
`stalled` skipped, because its `if:` (`needs.implement.outputs.final-ok ==
'false'`) carries no status-check function and GitHub's implicit `success()`
over the needs-closure suppresses it first. Five other gated stages (clarify,
finalize, intake, pr-conversation, tasks) have no equivalent job at all.

This plan splits the stage's possible entry-time stops into two kinds and
builds one shared mechanism for each, reused at all six gate call sites
(FR-017a):

1. **Refusal** — a step declines to proceed for a declared reason (missing
   credential, missing spec-kit skill, a malformed spec hand-off) and says so.
   Every refusal-shaped step in the fleet today (`wing-commander-preflight`'s
   `fail()` helper; `implement.yml`'s `Resolve and validate spec identity` and
   `Verify spec artifacts match the dispatch`, which already say "refusing"
   in their error text) gains a positive `refused`/`reason` output pair,
   written to `GITHUB_OUTPUT` *before* the step's own `exit 1` — a step's
   outputs are preserved by the runner regardless of the step's final exit
   code, this repository's only way to carry a signal out of a step that then
   fails (research.md D2). An `always()`-gated step, added immediately after
   each refusing step **inside the same job** (no cross-job propagation
   needed — the job ran, it did not skip), calls the *existing*
   `wing-commander-callout` composite with `kind: action`, reusing the exact
   mechanism the "closed lifecycle" and "unauthorized actor" notices already
   use. No record mark, no label change (FR-005).

2. **Abnormal termination** — the job that would have refused or succeeded
   never got that far: it failed outright, or a job it depends on failed so it
   never started. This is the case that needs a **survivor job** — one that
   runs even when its dependency is skipped or failed, per the `#224` idiom
   already established in this repository (`always() &&
   needs.<dep>.result == '<value>'`, contracts/runner-container-passthrough.md
   "Why this job must never skip"). `implement.yml`'s `stalled` job is widened
   to this shape and gains a second arm; the five other stages gain the same
   job, newly, as their "minimal bookkeeping" (FR-017b). A new composite,
   `wing-commander-chain-stop-notice`, encapsulates the three-effect sequence
   (mark `spec-meta.json` stalled, flip the `stage:*` label, post the notice)
   as one shared shape (FR-002, FR-017a) — including the case where the mark
   itself cannot be written (FR-011, FR-012's coverage requirement), and the
   case where no record exists yet to mark at all (`intake`, which runs
   before any `spec-meta.json` is written — folded into the *same*
   "record could not be updated" branch rather than a bespoke intake-only
   path, research.md D5). `implement`'s existing exhausted-retry arm is left
   completely untouched, in its current inline form — this plan does not
   migrate it into the new composite, trading a small amount of internal
   duplication for a hard guarantee against rewording it (Out of Scope).

Distinguishing the two at the survivor job requires knowing whether a refusal
happened in a job that may have failed — for that, and only that, the six
entry jobs each gain one new **job-level** output, `refusal-reason` (mapped
from whichever refusing step ran; empty when the job was skipped or failed
for any other reason). This is an internal wiring output between jobs of the
*same* workflow file, not a `workflow_call` output — it does not touch any
of the six stages' published contracts (FR-016; research.md D3 draws this
line explicitly).

Gate 15 (the existing job-suppression-shape check) is amended, not bypassed:
its `NON_SUCCESS_ARM` rule today matches only `needs.X.result == '...'`
shapes and would not have flagged `stalled`'s actual condition
(`needs.implement.outputs.final-ok == 'false'`) as unreadable — FR-015
requires this gap close without narrowing anything Gate 15 already catches.
A new **Gate 28** adds the executable coverage FR-012/FR-013/User-Story-4
require: driving the six survivor jobs' shipped `if:` conditions against
modelled `needs.*.result`/`needs.*.outputs.*` combinations neither Gate 15
(shape-only) nor `wc_shell_harness.py` (step-body-only) exercises today.

See [research.md](./research.md) for the full decision record — including
three decisions made without further clarification, listed there and
reported on the lifecycle issue — [data-model.md](./data-model.md) for the
per-stage identity-resolution table and the two notice-content shapes, and
[contracts/](./contracts/) for the new composite, the refusal-signal
contract, and the new gate's coverage contract.

## Technical Context

**Language/Version**: Bash (composite action `run:` steps, matching every
existing composite in this fleet), Python 3 (`.github/scripts/verify-*.py`,
matching every existing gate script) — no new language introduced.

**Primary Dependencies**: `gh` CLI, `jq`, `git` (already the sole dependencies
of the existing `stalled` job's steps this plan extends); `wc_shell_harness.py`
(existing, reused for Gate 28's step-body execution); a small new GitHub-
Actions-expression evaluator for Gate 28's job-level `if:`/`needs.*.result`
simulation, which no existing harness in this repository provides
(research.md D8 — the one genuinely new piece of test infrastructure this
plan introduces).

**Storage**: `spec-meta.json` on each spec's long-lived branch (existing
mechanism, existing schema — no field added or renamed). No new persisted
state.

**Testing**: New `.github/scripts/verify-chain-stop-notice.py`, wired into
`.github/workflows/lint-workflows.yml` as **Gate 28**. Amended
`.github/scripts/verify-gate-15.py` fixtures covering the output-based
non-success-arm shape Gate 15's rule did not previously detect. Both follow
this repository's established `verify-*.py` self-contained-script convention
(no shared test framework beyond `wc_shell_harness.py` and `wc_gate_registry.py`,
picked up automatically once wired into a `lint-workflows.yml` step per
`wc_gate_registry.py`'s filename-convention discovery — no manifest to edit).

**Target Platform**: GitHub Actions, `ubuntu-latest` runner (gate scripts) and
whatever runner/container each of the six stages already targets (the new
survivor job and the refusal-callout steps run in the same job/runner
contexts that already exist — no new runner requirement).

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: No latency added to any successful run (the new
survivor jobs and refusal-callout steps execute only on a failure/skip path
that today produces silence). A died-at-entry run's added cost is one
composite invocation (checkout + `jq` mark + `git push` + two `gh` calls) —
the same cost the existing exhausted-retry `stalled` job already pays today,
now paid on five more stages and one more implement arm.

**Constraints**:
- FR-016/SC-008: no `workflow_call` input, output, or secret of any of the
  six stages changes. The new `refusal-reason` job output is internal
  cross-job wiring within one workflow file, never surfaced as a
  `workflow_call` output (research.md D3).
- FR-004/FR-009/US3: the four currently-quiet paths (duplicate dispatch,
  closed lifecycle, successful cycle, cancelled run) must stay byte-for-byte
  quiet. The survivor job's `if:` is built to admit exactly the abnormal-
  termination shapes and nothing else (data-model.md); `!cancelled()`, not
  `always()`, is the status-check function (FR-009 — research.md D4 explains
  why this repository's one existing precedent, `always()` in watchdog's
  `report-unhandled-failure`, is not reused verbatim here).
- FR-006: at most one notice per run. The refusal-callout arm and the
  survivor job's abnormal-termination arm are constructed to be mutually
  exclusive by construction (data-model.md's condition table), not by a
  runtime dedup check.
- Out of Scope: the existing exhausted-retry notice's wording is not touched;
  the lifecycle gate's own retry/classification (spec 039/#188, already
  merged) is not touched; the watchdog is not touched.

**Scale/Scope**: One new composite action
(`.github/actions/wing-commander-chain-stop-notice/`); one refusal-signal
convention applied to three existing composite/inline steps
(`wing-commander-preflight`, `implement.yml`'s `Resolve and validate spec
identity`, `implement.yml`'s `Verify spec artifacts match the dispatch`) plus
whichever equivalent validation steps the other five stages carry (data-
model.md's per-stage table); one widened job (`implement.yml`'s `stalled`)
and five new minimal jobs (clarify, finalize, intake, pr-conversation,
tasks); one amended existing gate (Gate 15) and one new gate (Gate 28,
`.github/scripts/verify-chain-stop-notice.py`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #231 → this spec → this plan → tasks → implement), validated by the same gate-registry/shell-harness machinery the repository already checks itself with. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (planning-weight default). The feature adds no agent invocation of any kind — every new/changed step is deterministic bash, a composite action, and a Python gate script. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | The notice lands on the lifecycle issue the requester is already watching (US1/US2), through the same `gh issue comment`/label mechanism every other stage notice already uses (`wing-commander-callout` reused as-is for the refusal note). No new interaction surface. | ✅ Pass |
| IV. Automation-First | This is the defect this principle exists to catch: "any manual step that survives must be reported explicitly ... never silently assumed." A stalled or refused stage is now always reported; nothing about restart becomes automatic (Out of Scope), matching today's stall path. | ✅ Pass |
| V. Security — untrusted content is never instructions | No new untrusted-content path. The new composite reads only `gh`/`jq` output about the pipeline's own state (labels, `spec-meta.json`, run URLs) and the same declared `workflow_call` inputs every stage already trusts — never `github.event.*` body text. Refusal reason strings originate from this repository's own step logic (fixed messages naming a missing secret/file/skill), not from user input. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | The new composite lives under `.github/actions/**`, resolved via the established self-checkout snippet every other composite uses; it reads/writes only the calling repository's own `spec-meta.json` and issue. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | FR-016 is checked explicitly above: no `workflow_call` input/output/secret of any of the six published stages changes. The new composite is itself part of the published contract (a new file under `.github/actions/**`, resolved the same way every existing composite is) — its own `inputs:`/`outputs:` are the compatibility surface from this point forward, documented in contracts/wing-commander-chain-stop-notice.md. No stage-side ambient-state read is introduced. | ✅ Pass |
| VIII. A Green Check Means What It Says | This is the principle FR-012–FR-015 and User Story 4 restate at the spec level. Gate 28 is built to fail its own subject (drives the shipped `if:` conditions against modelled `needs.*` values, not the conditions' text alone), is wired into the registry `wc_gate_registry.py` already enforces, is triggered by changes to the six workflow files and the composite (`lint-workflows.yml`'s existing path triggers already cover `.github/workflows/**` and `.github/actions/**`), and every failure branch it ships (four required mutations, data-model.md) is exercised by a fixture in the same script. Gate 15's amendment is additive to what it already detects (FR-015), verified by keeping its existing fixture `CASES` and only adding to them. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/, quickstart.md) confirms the refusal signal is carried entirely by
step outputs already local to each job (no new ambient state, no new
`workflow_call` surface) and that the new composite's own `inputs:`/
`outputs:` are the only new compatibility surface this feature adds,
documented as such.

## Project Structure

### Documentation (this feature)

```text
specs/041-implement-stall-notice/
├── plan.md                                       # This file (/speckit-plan command output)
├── research.md                                   # Phase 0 output (/speckit-plan command)
├── data-model.md                                 # Phase 1 output (/speckit-plan command)
├── quickstart.md                                 # Phase 1 output (/speckit-plan command)
├── contracts/                                    # Phase 1 output (/speckit-plan command)
│   ├── wing-commander-chain-stop-notice.md       # new composite's I/O contract
│   ├── refusal-signal-contract.md                # the refused/reason output convention, and every step that gains it
│   └── chain-stop-gate-coverage.md               # Gate 15's amendment + new Gate 28's contract
├── checklists/
│   └── requirements.md                           # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                      # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src`/`tests` split. The real layout this
feature touches:

```text
.github/
├── actions/
│   ├── wing-commander-chain-stop-notice/    # NEW composite: mark spec-meta.json
│   │   └── action.yml                       #   stalled, flip stage:* labels,
│   │                                         #   post the "stage did not start"
│   │                                         #   notice. Tolerates an unwritable
│   │                                         #   record and a spec-dir-less
│   │                                         #   caller (intake) — both render
│   │                                         #   as "record could not be updated".
│   ├── wing-commander-preflight/
│   │   └── action.yml                       # + refused/reason outputs on fail()
│   └── wing-commander-callout/              # UNCHANGED — reused as-is for the
│       └── action.yml                       #   refusal note (kind: action)
├── scripts/
│   ├── wc_shell_harness.py                  # UNCHANGED — reused for Gate 28
│   ├── verify-gate-15.py                    # + fixtures for the output-based
│   │                                         #   non-success-arm shape
│   └── verify-chain-stop-notice.py          # NEW — Gate 28's script
└── workflows/
    ├── lint-workflows.yml                   # Gate 15 amended, + Gate 28
    ├── implement.yml                        # stalled job: existing exhausted-
    │                                         #   retry arm untouched; + abnormal-
    │                                         #   termination arm; + refusal
    │                                         #   outputs/callout on the two
    │                                         #   refusing steps already present
    ├── clarify.yml                          # + stalled job (new, minimal);
    │                                         #   + refusal outputs/callout
    ├── finalize.yml                         # + stalled job (new, minimal);
    │                                         #   + refusal outputs/callout
    ├── intake.yml                           # + stalled job (new, minimal;
    │                                         #   always the "no record yet"
    │                                         #   branch); + refusal outputs/callout
    ├── pr-conversation.yml                  # + stalled job (new, minimal;
    │                                         #   posts to the PR when identity
    │                                         #   could not be resolved);
    │                                         #   + refusal outputs/callout
    └── tasks.yml                            # + stalled job on both entry jobs
                                              #   (generate and approved);
                                              #   + refusal outputs/callout
```

**Structure Decision**: One new composite, applied uniformly at six call
sites via one widened job (implement) and five new minimal jobs, plus a
same-shaped refusal-callout addition inside each of the six entry jobs
themselves (not a separate job — the entry job ran, it only needs `always()`
on its own later step, per the Summary's mutual-exclusivity argument). No new
top-level directory, no change to any stage's declared `workflow_call`
surface, no change to the watchdog or the lifecycle-gate retry composite.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
