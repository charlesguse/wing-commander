# Implementation Plan: The Cost Line Names Its Own Run — Run-Stamped Cost Attribution

**Branch**: `spec/064-run-stamped-cost-attribution` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/064-run-stamped-cost-attribution/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Every cost-bearing comment the pipeline posts gains one invisible,
machine-readable stamp — an HTML comment carrying the metrics record key
(workflow run id, re-run attempt, job key, step index) — computed once, as
the very first, unconditional step of
`wing-commander-metrics-summary/action.yml`, and inherited by every
consumer of its `cost-line` output with no call-site change. The metrics
record key itself widens to include the re-run attempt number
(FR-014), composed once at emission and carried unchanged through the
persist-time job-id rewrite, so the stamp, the record, and the per-run
rollup line all name a run the same way. The watchdog's
`collect-cost-report` step partitions a lifecycle issue's comments into
three sets — `stamped_own` (believed regardless of the time window),
`stamped_foreign` (excluded regardless of the window), and `unstamped`
(the existing window heuristic, preserved as a fallback) — closing the
reported defect (two overlapping runs crediting each other's line) while
never manufacturing a false `cost-line-missing` against a comment posted
before this feature shipped. Two design problems drive most of this
plan's decisions, neither answered directly by spec.md: (1) FR-001
requires even the degraded "metrics unavailable" one-line fallback — which
lives outside the cost-line formatter's single home by CLAUDE.md's own
blessed exception — to carry a stamp; auditing the actual `if:` conditions
at all 12 call sites shows this fallback is only reachable while the
composite itself is running, so placing the stamp as the composite's
first, can't-fail step and exposing it as a standalone `stamp` output lets
the fallback reuse (not reconstruct) that value with one added line,
closing the requirement without a second formatter (research.md R2-R3);
(2) FR-009 requires the stamp to decide attribution even when the
inspected run's own time window is unresolvable, which means the
collector's existing `comments_checked` gate — today hard-requiring
`createdAt`/`updatedAt` alongside the issue and bot login — relaxes to
make the window an optional bound rather than a precondition, while
FR-002a requires the *opposite* narrowing when the run's own re-run
*attempt* number (not the window) is unresolvable: a same-run-id stamp
must not be trusted as stamp-backed in that case, demoting it to the
window fallback instead (research.md R5-R6). No new agent invocation, no
new workflow file, no new gate number — every change lands inside files
this pipeline already ships, following CLAUDE.md's "shared logic has
exactly one home" and this repository's existing gate-registry
convention.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML, `jq`, and
Python for the gate scripts this feature widens — identical toolchain to
the code it touches; no new language.

**Primary Dependencies**: `jq`, `gh` CLI (`gh run view` gains one field to
an existing call, no new call) — both already used inside
`wing-commander-metrics-summary/action.yml` and
`watchdog.yml`'s `collect-cost-report` step. No new external service, no
new composite action beyond the one new step inside an existing composite,
no new `claude-code-action` invocation.

**Storage**: No new storage location. The metrics record's durable store
(spec 043's `records.jsonl` on the metrics branch) gains one field per
record (`run_attempt`) and a widened `record_key`; nothing about where or
how it's written changes.

**Testing**: This repository's existing gate-registry convention — every
change lands inside a `verify-*.{py,sh}` script this repository already
runs (`verify-metrics-summary-record-emission.py`,
`verify-metrics-record-schema.py`, `verify-metrics-persist-retry.py`,
`verify-gate-19.py`, `verify-cost-report-collector.sh`, and the smaller
fixture-literal updates named in research.md R1/R9), each wired into
`lint-workflows.yml` and runnable locally via `run-local-gates.py`. One
new sibling case function (`case_run_stamp_has_exactly_one_home`) is added
to an existing gate script rather than a new gate file, matching
CLAUDE.md's own convention for widening a check ("add the single home
check to the nearest existing gate the same way"). No new gate number.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), unchanged
triggers — the 9 stage workflows already post their cost-bearing comment
where this feature adds a stamp; `watchdog.yml`'s existing `collect` job
already runs `collect-cost-report`.

**Project Type**: Single project — CI/CD automation under
`.github/workflows/` and `.github/actions/`, unchanged.

**Performance Goals**: Not latency-sensitive. One new unconditional bash
step (pure string interpolation, no external call) inside a composite
action that already runs; the collector's attribution logic changes from
one filter pass to a three-way partition over the same comment listing it
already fetches — no new `gh api` call in the collector beyond the one
field added to an existing `gh run view --json` invocation.

**Constraints**: FR-003/FR-013 (single home, documented once) bind the
stamp's implementation shape throughout — research.md R2/R3/R9 and
`contracts/run-stamp.md` exist specifically to keep the degraded fallback
path from becoming a second, drifting formatter. FR-014 binds every
composition site of the metrics record key to widen together in the same
change, including the gates that pin its shape (research.md R1). FR-009
and FR-002a bind the collector to two *opposite* relaxations at once (widen
what counts as "checked" when the window is missing; narrow what counts
as "stamp-backed" when the attempt is missing) — research.md R5/R6 and
`contracts/cost-attribution.md` are the mechanism that keeps these from
colliding.

**Scale/Scope**: Roughly a dozen files change at implementation time: two
composite actions (`wing-commander-metrics-summary`,
`wing-commander-metrics-persist`), one workflow
(`watchdog.yml`'s `run-meta` and `collect-cost-report` steps), the 12
call-site "Compute cost line" blocks across 9 stage workflows (one added
`env:` line and one changed fallback line each — mechanical, identical
edits, not independent logic), one shared test harness
(`wc_metrics_harness.py`), and roughly six existing gate scripts plus
their fixtures. `specs/046-watchdog-supervision-collectors`'s own
`data-model.md` documents the `cost-report` collector this feature
corrects inside; it is not edited by this plan (plan-stage edits are
confined to `specs/064-run-stamped-cost-attribution/`) — flagged here as
a candidate follow-up note for `/speckit-tasks` or the implementation
stage, not resolved now.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through intake (#491, routed from the board loop, originating issue #380) → this spec → this plan → tasks → implement, the same pipeline it instruments; its subject is that same pipeline's own cost supervision. | Pass |
| II. Cost-Conscious Model Tiering | No agent step, no model tier touched at all — this feature is entirely deterministic bash/jq inside existing composite and workflow steps. | Pass |
| III. Simple, GitHub-Native Interaction | No new interaction surface — the stamp is invisible by design (FR-004); the only visible change is a corrected `cost-line-missing` verdict on the lifecycle issue, exactly where cost-report findings already surface. | Pass |
| IV. Automation-First | No manual step added or removed; the stamp is produced automatically by the same composite call every stage already makes. | Pass |
| V. Security (NON-NEGOTIABLE) | The stamp is parsed as untrusted comment-body content, never as an instruction (research.md R7 — a malformed stamp degrades silently, never raises). FR-007's author-identity gate is explicitly preserved and, per spec.md's edge case, narrowed rather than weakened: a stamp is only believed on a comment the pipeline's own identities authored. No new write surface; the collector only reads. | Pass |
| VI. Portability | No new adoption step, no new required config; the stamp and the widened record key are internal implementation detail of a composite/workflow every adopter already runs. | Pass |
| VII. Two Interfaces | `wing-commander-metrics-summary` and `wing-commander-metrics-persist` are composite actions under the published contract — this feature widens their output shape (a new `run_attempt` record field, a new `stamp` output) additively, never removing or renaming an existing input/output/secret, which VII frames as "a deliberate act rather than a convenience": this plan records that act. `watchdog.yml` stays `workflow_call`-only; the one new `gh run view --json` field is read inside the already-existing, already-documented `vars.*`-adjacent exception this workflow carries for its own inspection logic (no second exception opened). | Pass |
| VIII. A Green Check Means What It Says | This is User Story 3's whole point: FR-012 requires the overlapping-runs case to become a checked-in scenario with each run's verdict asserted independently, and three named mutations (drop the stamp preference, invert it, drop the attempt from the matched key) must each independently fail the suite (research.md R9, `contracts/cost-attribution.md`'s coverage section, SC-005). | Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | Every decision this feature adds — which comment is "own," whether a stamp is stamp-backed or demoted to window-backed, whether a record_key is well-formed — is bash/jq/Python gate code, never a prompt. `diagnose` (the one agent step downstream of this collector) is unmodified; it still only reads the signal facts this feature widens by one key (`attribution`), the exact "descriptive fact, not a new judgment" carve-out this principle's own text allows. | Pass |
| X. Bounded Autonomy — The Pipeline Works Its Own Board | Not implicated — this feature does not touch the board loop, its routing, or its merge gates; it corrects a watchdog collector's attribution accuracy, which the board loop consumes as one input among many but does not itself define. | Pass |

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/064-run-stamped-cost-attribution/
├── plan.md               # This file (/speckit-plan command output)
├── research.md           # Phase 0 output (/speckit-plan command)
├── data-model.md          # Phase 1 output (/speckit-plan command)
├── quickstart.md          # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   ├── run-stamp.md
│   └── cost-attribution.md
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src`/`tests` split — it is a GitHub Actions
pipeline. This feature's concrete changes (all at implementation time,
none made by this plan):

```text
.github/
├── actions/
│   ├── wing-commander-metrics-summary/
│   │   └── action.yml                 # AMENDED — RECORD_KEY gains the
│   │                                    # run_attempt segment (R1); new
│   │                                    # unconditional first step
│   │                                    # `run-stamp` (R2); cost-line jq
│   │                                    # appends the stamp; new `stamp`
│   │                                    # output; run object gains
│   │                                    # run_attempt (contracts/run-stamp.md)
│   └── wing-commander-metrics-persist/
│       └── action.yml                 # AMENDED — the job-id rewrite's
│                                        # record_key interpolation carries
│                                        # run_attempt through unchanged (R1)
├── workflows/
│   ├── watchdog.yml                   # AMENDED — run-meta's `gh run view
│   │                                    # --json` gains `attempt`;
│   │                                    # collect-cost-report's
│   │                                    # COST_ATTRIBUTION_FILTER becomes
│   │                                    # the three-way partition
│   │                                    # (contracts/cost-attribution.md);
│   │                                    # COST_REPORT_FILTER's output
│   │                                    # gains `attribution`;
│   │                                    # comments_checked gating relaxes
│   │                                    # (R5)
│   ├── clarify.yml, cleanup.yml, finalize.yml, implement.yml,
│   │   intake.yml, plan.yml, pr-conversation.yml, rebase.yml,
│   │   tasks.yml                      # AMENDED — each "Compute cost
│   │                                    # line" block (12 occurrences
│   │                                    # total) gains one `env:` line
│   │                                    # (RUN_STAMP) and one changed
│   │                                    # fallback line (R3) — mechanical,
│   │                                    # identical edits
└── scripts/
    ├── wc_metrics_harness.py                       # AMENDED — record_key
    │                                                 # builders gain an
    │                                                 # attempt parameter
    ├── verify-metrics-summary-record-emission.py    # AMENDED — record_key
    │                                                 # mutation updated;
    │                                                 # new attempt-drop
    │                                                 # mutation; new
    │                                                 # case_run_stamp_has_
    │                                                 # exactly_one_home
    ├── verify-metrics-record-schema.py              # AMENDED — record_key
    │                                                 # shape regex,
    │                                                 # run_attempt field
    ├── verify-metrics-persist-retry.py              # AMENDED — want_key
    │                                                 # literals widened
    ├── verify-metrics-schema-version-tolerance.py   # AMENDED — fixture
    │                                                 # record_key literals
    ├── verify-turn-budget-collector.sh              # AMENDED — fixture
    │                                                 # record_key literals
    ├── verify-watchdog-no-record-on-clean-path.py   # AMENDED — fixture
    │                                                 # record_key literal
    ├── verify-gate-19.py                            # AMENDED —
    │                                                 # COST_SCENARIOS and
    │                                                 # COST_MUTATIONS
    │                                                 # extended
    │                                                 # (data-model.md's
    │                                                 # fixture table)
    ├── verify-cost-report-collector.sh              # AMENDED — new
    │                                                 # program-level
    │                                                 # fixtures for the
    │                                                 # widened jq programs
    └── fixtures/metrics-record-schema/*.json        # AMENDED — literal
                                                        # record_key/run
                                                        # shapes gain the
                                                        # attempt segment

specs/046-watchdog-supervision-collectors/data-model.md
    # NOT edited by this plan (out of scope per this run's constraints) —
    # flagged here as a candidate task for /speckit-tasks: its
    # `cost-report` claim-shape description predates this feature's
    # `attribution` fact.
```

**Structure Decision**: Every change lands inside a file the pipeline
already ships and consumes through its existing self-checkout path — no
new job, no new workflow, no new composite action, no new gate file.
Gate widening follows the existing `.github/scripts/verify-*.{py,sh}`
convention exactly, so `lint-workflows.yml`'s registry needs no new
registration line, only updated invocations of gates it already runs.

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
