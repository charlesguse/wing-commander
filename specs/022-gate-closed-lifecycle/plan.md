# Implementation Plan: A Closed Lifecycle Is Inert — Gate Comment-/Label-Triggered Stages on Issue State

**Branch**: `022-gate-closed-lifecycle` | **Date**: 2026-07-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/022-gate-closed-lifecycle/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

A comment-/label-triggered stage today gates on *who* commented and *what*
the issue is, but never on whether the lifecycle issue is still **open** —
the observed defect (issue #109, post-mortem of findings #105/#106) is a
comment-triggered `clarify` run that fired on the very comment that closed
its lifecycle issue and undid teardown (resurrected a torn-down draft
branch, edited a closed PR, posted a callout on a closed issue, invented
clarification resolutions). Static reading of every workflow in
`.github/workflows/` (research.md R1) finds only **two** entry points are
actually reachable by a raw `issue_comment`/`issues.labeled` event today —
`wing-commander-2-clarify.yml` and `wing-commander-1-intake.yml` — plus one
PR-merge hand-off (`tasks-approved` in `wing-commander-4-tasks.yml`) that
FR-004 explicitly names alongside them; `finalize`/`implement` (converge)
have no comment trigger of their own but are chained by `workflow_call` and
also accept an `issue-number` input, so the same gate is added there
defensively (research.md R2).

The fix adds one new shared composite, `wing-commander-lifecycle-gate`,
that re-fetches the lifecycle issue's *current* state via `gh issue view`
(never trusting a cached event payload — consistent with this codebase's
existing "reusable workflow is event-agnostic" pattern) and is called as the
first billable step of every affected reusable workflow, before
`wing-commander-preflight`, before any checkout of a spec/draft branch, and
before any agent step. When the issue is closed, the calling job posts the
one permitted `wing-commander-callout` (`kind: info`) note and every
remaining step is skipped via `if: steps.lifecycle-gate.outputs.is-open ==
'true'`; nothing is checked out, committed, pushed, or dispatched. This
puts the gate at the trigger layer, not in a tool allowlist (FR-002),
uniformly across every entry point (FR-004), and leaves open-lifecycle
behavior byte-for-byte unchanged (FR-006).

Independently, the watchdog's denied-tool collector (`watchdog.yml`'s
`collect` job) is corrected: research (Claude Code SDK check) confirms the
terminal result record carries no `permission_denials`-shaped field today,
so FR-009's fallback path is the one that actually runs; the collector's jq
filter is fixed to count real denial occurrences instead of the
`group_by(tool) | select(length > 1)` step that silently drops
single-tool denials, and its per-denial `turn` field — which is actually a
raw array index into the interleaved SDK message stream, not a
conversation turn — is renamed to `record-index` and the count is labeled
as a non-authoritative fallback (FR-008–FR-010). The orphaned
`spec-draft/021-rebase-discover-stall` branch the zombie run resurrected
(FR-011) is identified (research.md R5) and flagged for maintainer/implement
-stage deletion, since branch deletion is destructive and out of scope for
this plan stage to perform.

## Technical Context

**Language/Version**: Bash (workflow `run:` steps, `ubuntu-latest` default shell) + GitHub Actions workflow YAML + `jq` for JSON evidence processing

**Primary Dependencies**: `gh` (GitHub CLI), `jq`, `actions/checkout@v4`, and this repo's own shared composites (`wing-commander-preflight`, `wing-commander-context`, `wing-commander-callout`) — all already in use by every affected workflow; one new composite (`wing-commander-lifecycle-gate`) is added, following the same style as the existing ones

**Storage**: N/A — state lives in GitHub Issues (open/closed), branches, and PRs; no database

**Testing**: No unit-test framework for workflow YAML in this repo (dogfooding per constitution I). The state gate is verified by re-triggering real comment/label events against a real closed lifecycle issue and reading the resulting run/comment (quickstart.md). The collector fix additionally gets a small deterministic fixture check (sample `claude-execution-output.json`-shaped arrays with known denial counts fed through the corrected `jq` filter), following the existing pattern of `.github/scripts/verify-watchdog-run.sh` — a plain bash/jq assertion script, not a language test framework

**Target Platform**: GitHub Actions, `ubuntu-latest` runners, this repository's own Actions environment (and any adopting repository that calls these reusable workflows — constitution VI)

**Project Type**: Single project — a GitHub Actions reusable-workflow pipeline component; no application `src/`/`tests/` split applies

**Performance Goals**: N/A beyond "no material latency added" — the new gate step is one `gh issue view` call (already a pattern every affected workflow uses elsewhere, e.g. `clarify.yml`'s "Fetch issue labels" step) plus, on the closed path only, one `gh issue comment` call; the collector fix is a `jq` filter change with no new network calls

**Constraints**: Constitution V (least privilege, untrusted content never instructions — the gate reads only `github.event.issue`-independent API state, never comment/label body text, so it cannot be steered by comment content); Constitution II (no new model tier — both changes are deterministic, no LLM call); FR-002 (the gate must live at the trigger, not be simulated by narrowing a tool allowlist — this plan adds no allowlist changes at all); FR-006 (zero behavior change on an open lifecycle)

**Scale/Scope**: Every comment-/label-triggered and issue-number-carrying `workflow_call` entry point in this repository's own pipeline (`clarify`, `intake`, `tasks` approved-mode, `finalize`, `implement`/converge) plus the watchdog's `collect` job's denied-tool collector; per constitution VI, the composite and workflow changes are repo-name-agnostic and apply equally to any adopting repository

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — the repo is its own first example | Fix flows through spec (#109) → plan → tasks → implement → converge like any other feature; this repo's own five gated stages are the worked example | PASS |
| II. Cost-conscious model tiering | No new agent step or model tier introduced anywhere; the gate and the collector fix are both pure deterministic bash/jq, no LLM call | PASS |
| III. Simple, GitHub-native interaction | The decline path still reports only to the lifecycle issue (one `kind: info` comment) — no new external surface, no dashboard | PASS |
| IV. Automation-first | Removes a case where automation silently did the *wrong* thing (acted on a closed lifecycle) without any human noticing until after the fact; the one permitted note keeps the decline legible without becoming a manual step | PASS |
| V. Security — untrusted content is never instructions (NON-NEGOTIABLE) | The gate reads `issue.state` from the GitHub API, never from comment/label body text — it cannot be spoofed by what a commenter writes. FR-002 explicitly keeps authorization at the trigger rather than in a tool allowlist, which this plan honors: no allowlist is broadened or tightened to simulate the gate | PASS |
| VI. Portability — the consuming repository owns its artifacts | New composite lives under `.github/actions/` in the pipeline repository like every existing one; no repository name/owner is hardcoded; the gate is applied inside the *reusable* workflows so every adopting repository's thin wrappers inherit it with no wrapper-side change required | PASS |

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/022-gate-closed-lifecycle/
├── plan.md                                # This file (/speckit-plan command output)
├── research.md                            # Phase 0 output (/speckit-plan command)
├── data-model.md                          # Phase 1 output (/speckit-plan command)
├── quickstart.md                          # Phase 1 output (/speckit-plan command)
├── contracts/                             # Phase 1 output (/speckit-plan command)
│   ├── wing-commander-lifecycle-gate.md   # New composite's input/output contract
│   ├── lifecycle-gate-points.md           # Per-entry-point audit/migration table (FR-004)
│   └── denied-tool-collector-delta.md     # Collector counting/labeling fix contract
└── tasks.md                               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no application `src/`/`tests/` split — it *is* a GitHub
Actions pipeline. The feature's changes are confined to:

```text
.github/actions/
└── wing-commander-lifecycle-gate/   # NEW composite — re-fetches issue state,
                                      # outputs is-open/state; no existing
                                      # composite is restructured
                                      # (wing-commander-preflight stays pure
                                      # shell/no-network per its own contract)

.github/workflows/
├── clarify.yml       # reusable · clarify — add gate step + if: guards
├── intake.yml         # reusable · intake — add gate step + if: guards
├── tasks.yml           # reusable · tasks — tasks-approved job: add gate
│                        # step (after spec-branch checkout, before dispatch)
├── finalize.yml        # reusable · finalize — add gate step (FR-004, defensive)
├── implement.yml       # reusable · implement/converge — add gate step per
│                        # cycle (FR-004, defensive)
├── watchdog.yml         # collect job — fix denied-tool jq filter (FR-008–FR-010)
├── wing-commander-1-intake.yml    # thin wrapper — not expected to change
├── wing-commander-2-clarify.yml   # thin wrapper — not expected to change
├── wing-commander-4-tasks.yml     # thin wrapper — not expected to change
├── wing-commander-6-finalize.yml  # thin wrapper — not expected to change
└── wing-commander-5-implement.yml # thin wrapper — not expected to change

docs/
└── architecture.md   # document the new lifecycle-gate step per stage and
                       # the collector's corrected field name

specs/015-pipeline-watchdog/   # unchanged as a contract; FR-010 supersedes
                                # only the `facts.turns` field's *name* in its
                                # data-model.md, documented as a deliberate,
                                # spec-022-sanctioned deviation (research.md R4)
specs/022-gate-closed-lifecycle/   # this feature's own spec-kit artifacts

(one-time, not a file change): deletion of the orphaned
origin/spec-draft/021-rebase-discover-stall branch (FR-011) — flagged for
the implement stage / a maintainer, not performed by this plan (research.md R5)
```

**Structure Decision**: Single project, no option-1/2/3 split applies. The
gate is one new composite action plus a small, mechanically-identical
insertion (one new step + `if:` guards on existing steps) repeated across
five reusable workflows — additive, not a restructuring. The collector fix
is confined to one existing `jq` filter in `watchdog.yml`. No thin wrapper
is expected to change, since the gate is event-agnostic and lives entirely
inside the reusable workflows the wrappers already call (consistent with
this codebase's existing D2 "event-agnostic reusable workflow" pattern —
research.md R3).

## Complexity Tracking

> Not applicable — Constitution Check has no violations to justify.
