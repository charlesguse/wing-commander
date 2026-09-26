# Implementation Plan: A never-unblocking merge gate is named

**Branch**: `070-blocked-gate-dry-run` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/070-blocked-gate-dry-run/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Spec 055's unattended auto-release verification still reports one condition
generically: a merge gate whose pull request is `mergeStateStatus: BLOCKED`
with no resolved check result (an empty `statusCheckRollup`, or every entry
still pending) is waited on forever, so a misconfigured or never-triggered
required check silently burns the entire 8100-second poll budget and ends as
the generic `fail-timeout` verdict instead of naming the stuck gate. This
plan closes that gap by (1) teaching the existing pure merge-decision script
to emit a new, distinct token — `blocked-pending` — for exactly this
condition, instead of collapsing it into the same `wait` token used for a
draft PR or a `mergeStateStatus` GitHub is still computing; and (2) adding a
second pure script that turns a per-gate elapsed-time count against a
20-minute allowance into `start` / `wait` / `stall` / `clear`, so the
`poll` step's existing bash loop — which already tracks per-gate failure
counts in plain associative arrays — can track "how long has this gate sat
blocked-pending" the same way, and emit a `fail-gate-stall` verdict naming
the gate, the PR, and "required checks never reported a result" once the
allowance is exhausted. No new verdict outcome is added (data-model.md);
this is a new *reason* within the existing `fail-gate-stall` outcome, so the
`report` job's three-way classification (`auto-release.yml` "Determine this
run's outcome" step) needs no change.

## Technical Context

**Language/Version**: Bash (`set -uo pipefail` idiom, GitHub Actions
`ubuntu-latest` runner shell) for the workflow step and the two
`.github/actions/_shared/*.sh` pure decision scripts; Python 3 (no test
framework — hand-rolled scenario lists + assertions, no pytest) for the
checked-in fixture harnesses under `.github/scripts/`.

**Primary Dependencies**: `gh` CLI (already invoked by the `poll` step),
`jq` (already required by both existing decision scripts), the repo's own
`wc_shell_harness.py` helper (`ensure_jq`, `resolve_bash`, `run_step`) that
the report-fixture gate already uses to execute a real workflow step's
script body outside of Actions.

**Storage**: N/A — all state is either GitHub PR/check-run data read live
via `gh pr list`, or in-memory bash state (associative arrays) scoped to one
`poll` step invocation, discarded when the attempt ends.

**Testing**: `.github/scripts/verify-auto-release-e2e-gate-decisions.py`
(Gate 66, `lint-workflows.yml:3637-3656`) — extended with new scenarios and
mutations for both the amended merge-decision script and the new
allowance-decision script. `.github/scripts/verify-auto-release-report.py`
(Gate 52, `lint-workflows.yml:3457-3474`) — extended with one more
`gate_stall()` fixture for the new reason's `observed` text. Both run via
`python .github/scripts/run-local-gates.py` per CLAUDE.md before push; no
new gate is registered (CLAUDE.md's single-home rule: one script per
decision surface, already established by spec 055).

**Target Platform**: GitHub Actions (`ubuntu-latest`), `.github/workflows/auto-release.yml`'s `verify-e2e` job, `poll` step (currently lines 750-1338).

**Project Type**: CI pipeline tooling — a single workflow step plus two
shared shell scripts and their Python fixture harnesses; no application
code, no frontend/backend split.

**Performance Goals**: N/A. The only timing requirement is functional: the
new allowance (20 minutes / 1200 seconds) must fit inside the existing
135-minute / 8100-second poll budget with the diagnosis reached and written
before the budget expires (FR-004, SC-001) — this is a correctness
constraint, not a throughput target.

**Constraints**:
- Must not change `auto-release-verdict.sh`'s six-field JSON shape or add a
  new `outcome` value (Assumptions: "the existing verdict vocabulary is
  sufficient").
- Must not change the generic-timeout code path (`auto-release.yml`
  lines 1083-1089) or the `report` job's three-way classification `case`
  (lines 1790-1794) — both already handle any `fail-gate-stall` correctly
  today (FR-007, FR-008).
- Must not reset a gate's allowance timer merely because the *shape* of the
  unresolved check result changes between observations (FR-005) — only
  merging or leaving the blocked-with-unresolved-checks state resets it.
- Must not let a failed read advance the allowance (FR-006) — the existing
  `gate_failures`/`MAX_GATE_FAILURES` bound already governs read failures,
  and the new timer logic must live entirely inside the success branch of
  that same read, so a failed read simply never touches it.
- This feature governs this repository's own release verification (the
  consuming instrument, Principle VII), not the published stage contract —
  no adopter-facing input, output, or secret changes shape as a result.

**Scale/Scope**: One workflow step (`auto-release.yml`'s `poll` step), one
amended shared script (`auto-release-e2e-merge-decision.sh`), one new
shared script (`auto-release-e2e-gate-allowance-decision.sh`), two extended
fixture files, one new `env:` constant.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Assessment |
|---|---|---|
| I. Guide — repo is its own first example | Yes | Built through this same pipeline (spec 070, issue #533); no bootstrap exception needed. |
| II. Cost-Conscious Model Tiering | No | No new Claude invocation is introduced; this is pure shell/Python. |
| III. Simple, GitHub-Native Interaction | Yes | No new interaction surface; the durable failure issue's body gains one reason string, same rendering path as the other four gate-stall reasons. |
| IV. Automation-First | N/A | No manual step is introduced or removed. |
| V. Security | N/A | No new credential, actor gate, or trust boundary; reuses the existing harness identity and `gh` calls already in scope. |
| VI. Portability | N/A | Nothing project-specific is bundled into Wing Commander's published surface; this lives entirely in this repository's own `auto-release.yml` and `_shared/` scripts. |
| VII. Two Interfaces | Yes | `auto-release.yml` is the consuming instrument, not a `workflow_call` published stage (spec 070 Assumptions confirms this explicitly) — no compatibility surface is touched. |
| VIII. A Green Check Means What It Says | Yes | Both new/changed decision branches get checked-in fixtures in the existing gate registry (Gate 66, Gate 52); no new gate needed, no existing gate's reach is narrowed. See Phase 1 gate-coverage design in data-model.md. |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | Yes | The "has this gate been blocked-pending too long" judgment is pushed into a new pure, deterministic script (mirroring D5/D6's rationale for the sibling merge-decision script) rather than left as prose or inline heuristic; see research.md D2. |
| X. Bounded Autonomy | N/A | Not a board-loop item; this is a spec-lifecycle feature. |

No violations. Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/070-blocked-gate-dry-run/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── gate-allowance-decision.md
├── checklists/
│   └── requirements.md
├── spec-meta.json
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── auto-release.yml               # `verify-e2e` job, `poll` step (~L750-1338):
│                                       # gains one new `env:` constant
│                                       # (GATE_BLOCKED_ALLOWANCE_SECONDS), one new
│                                       # per-gate state array (gate_blocked_since,
│                                       # parallel to the existing gate_failures/
│                                       # gate_last_failure at L868-869), and one new
│                                       # `case` arm alongside the existing
│                                       # conflicting/blocked/wrong-attempt/wrong-base
│                                       # arms (~L1009-1028) that calls the new
│                                       # allowance-decision script and either
│                                       # continues, records the timer start, or
│                                       # writes the new fail-gate-stall verdict.
│   └── lint-workflows.yml             # Gate 66 (~L3637-3656) and Gate 52
│                                       # (~L3457-3474) registrations: unchanged
│                                       # registration, extended fixture content.
├── actions/_shared/
│   ├── auto-release-e2e-merge-decision.sh   # AMENDED: the existing step 6
│   │                                         # (mergeStateStatus BLOCKED, still
│   │                                         # pending) prints a new token,
│   │                                         # `blocked-pending`, instead of `wait`.
│   │                                         # Every other branch (none,
│   │                                         # wrong-attempt, wrong-base, draft,
│   │                                         # conflicting, durably `blocked`,
│   │                                         # UNKNOWN/BEHIND `wait`, `merge`) is
│   │                                         # unchanged.
│   └── auto-release-e2e-gate-allowance-decision.sh   # NEW: pure script, takes the
│                                         # merge-decision token, a per-gate
│                                         # `blocked_since` value (or empty), the
│                                         # loop's current $SECONDS, and the
│                                         # allowance in seconds; prints one of
│                                         # `clear` / `start` / `wait` / `stall`.
└── scripts/
    ├── verify-auto-release-e2e-gate-decisions.py  # Gate 66: MERGE_SCENARIOS gains
    │                                     # the `blocked-pending` rename for the
    │                                     # three existing "BLOCKED, still pending"
    │                                     # scenarios; MERGE_MUTATIONS' matching
    │                                     # replacement text is updated to match;
    │                                     # a new ALLOWANCE_SCENARIOS list + 
    │                                     # run_allowance_suite() + 
    │                                     # ALLOWANCE_MUTATIONS exercise the new
    │                                     # script's four branches.
    └── verify-auto-release-report.py    # Gate 52: one new GATE_STALL_* fixture
                                          # (`gate_stall("<gate> PR merge",
                                          # "gh pr merge succeeds", "PR #<n>:
                                          # required checks never reported a
                                          # result")`) proving the rendering and
                                          # classification path, already generic
                                          # over the `observed` string, needs no
                                          # code change for the new reason.
```

**Structure Decision**: Single-project CI tooling change, entirely inside
the existing `auto-release.yml` / `_shared/` / `scripts/` layout spec 055
already established. No new directories, no new gate registration — this
extends two existing pure scripts and their two existing fixture harnesses,
per CLAUDE.md's "shared logic has exactly one home."

## Complexity Tracking

*No entries — the Constitution Check above found no violations requiring
justification.*
