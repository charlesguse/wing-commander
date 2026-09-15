# Implementation Plan: One read-only inspection policy for stage tool allowlists

**Branch**: `051-read-only-inspection-policy` | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/051-read-only-inspection-policy/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Nine `denied-tool` occurrences on #266 share one root cause: the per-stage
default tool lists in `specs/010-reusable-pipeline/contracts/stage-interfaces.md`
and the prose that tells an agent what to run have no owner-level policy for
what a read-only inspection is allowed to look like. This plan resolves that
by (1) writing the policy into the Gate 27 table itself as a named inspection
primitive set plus a compound/pipe/redirect rule, (2) extending
`wing-commander-tool-args`'s rendered `shell-commands` output so that rule
reaches every stage prompt from its one existing home instead of a
hand-pasted copy, (3) routing the two `gh api` reads to already-existing
non-`gh api` mechanisms (clarify already stages the comment body
deterministically; plan already holds `gh pr view --json`) and saying so in
the affected prompts, (4) scoping `CLAUDE.md`'s "Before pushing" gate-suite
instruction to the implement stage and human/local sessions, adding the
gate-suite run to implement's own agent step behind a prerequisite preflight
and an explicit timeout, (5) landing the deterministic leftovers (FR-011
through FR-013), and (6) extending Gate 27 and Gate 21 so a future stage or
prompt instruction that drifts from this policy fails CI instead of shipping
a tenth occurrence. No consumer-visible behavior changes beyond the
documented list edits (FR-017); no stage gains a write capability it does
not have today (FR-006, FR-008).

## Technical Context

**Language/Version**: Python 3 (gate scripts under `.github/scripts/`, run by GitHub Actions' `python3`), Bash (composite-action `run:` blocks), YAML (workflow/table edits) — the same stack every prior stage-interfaces/gate change in this repository uses. No new runtime is introduced.

**Primary Dependencies**: `wing-commander-tool-args` composite action (`.github/actions/wing-commander-tool-args/action.yml`); `.github/scripts/verify-stage-tool-lists.py` (Gate 27) and `.github/scripts/verify-tooling-statement.py` (Gate 21); `.github/scripts/wc_shell_harness.py` (shared by Gate-21-style shipped-script tests); `.github/scripts/run-local-gates.py` (the implement-stage self-check's subject).

**Storage**: N/A — this feature edits documentation (`stage-interfaces.md`, `CLAUDE.md`), a composite action's shell, workflow YAML `claude_args`/`prompt` blocks, and two gate scripts. No database, no runtime storage.

**Testing**: Gate 21's shipped-script harness pattern (`wc_shell_harness.run_step`) for the composite action's new/extended output; Gate 27's mutation-style self-test (`--self-test`) for the new policy-drift checks; `python .github/scripts/run-local-gates.py` as the PR-time regression suite this change must itself pass.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners, and any consumer-supplied `runner`/`container-image`), executing this repository's own reusable pipeline workflows.

**Project Type**: Single repository — a GitHub Actions pipeline and its supporting gate scripts (no frontend/backend split, no mobile target).

**Performance Goals**: N/A (not a latency/throughput feature). The one bounded-cost item is FR-009's gate-suite self-check: it must complete inside an explicit timeout (research.md D5) against a cycle whose own budget is far larger.

**Constraints**: FR-017 (byte-for-byte identical composed lists for a consumer who sets none of the four tool-list inputs — SC-005 of specs/026); Constitution VIII (every new/extended gate check needs a checked-in fixture for every failure branch it ships, reachable through the gate registry, same subject locally and in CI); Constitution IX (the "is this stage read-capable / is this command mandated" judgment that gates a table/gate outcome lives in the gate script, not left to a reviewer's prose reading).

**Scale/Scope**: 8 stage-interfaces.md rows gain the inspection primitive set or an exception note (intake, clarify, implement.cycle, implement.retry — plan.\*/tasks.\* already have it); 1 composite action gains policy prose in its rendered output; 2 gate scripts gain new checks with fixtures; 1 workflow (`implement.yml`) gains one preflight step and one gate-suite step; `CLAUDE.md` gains an audience-scoping sentence; 2 stage prompts (clarify, plan) gain one sentence each naming their `gh api` alternative; 9 recorded #266 occurrences each get a named disposition.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself worked through the pipeline (issue #338 → this spec → this plan → tasks → implement), consistent with the repo building its own capabilities through the pipeline it ships. PASS.
- **II. Cost-Conscious Model Tiering**: No new agent step is introduced; the one workflow change that adds runtime cost (FR-009's gate-suite self-check) adds no *agent* turns — it is a deterministic `run:` step the existing `implement.cycle`/`implement.retry` agent step is told about via the tooling statement, timed out independently of the agent's own turn budget. PASS.
- **III. Simple, GitHub-Native Interaction**: No change to how a requester interacts with the pipeline; #266 stays the visible thread and is closed with quoted evidence per SC-007. PASS.
- **IV. Automation-First**: No new manual step. FR-009a's preflight degrades to a step-summary note rather than surfacing a manual action. PASS.
- **V. Security — Untrusted Content Is Never Instructions**: FR-006/FR-008 are themselves security decisions — no stage gains `gh api` (which cannot be scoped to GET and sits under a token that can write issues in clarify/intake), and any future widening must be recorded in this same table and in `specs/011-security-policy`'s SECURITY.md. This feature widens no write surface, so SECURITY.md is unchanged. PASS, and the plan's research.md records the reasoning FR-006/FR-008 require.
- **VI. Portability**: All edits stay inside this repository's own published-stage/consuming-instrument split; nothing hardcodes a downstream adopter's identity. PASS.
- **VII. Two Interfaces**: The inspection primitive set and the compound/pipe/redirect rule are added to the *published* per-stage defaults (stage-interfaces.md, the composite's rendered output) — both are already part of the published contract surface FR-013/SC-006 of specs/026 committed to documenting. No new undeclared stage-side deviation is introduced. PASS.
- **VIII. A Green Check Means What It Says**: FR-014/FR-015/SC-003 require the new Gate 27 policy-drift checks and the extended Gate 21 mutation cases to ship with fixtures that prove each failure branch is reachable — planned in research.md D7 and reflected in data-model.md's entity list. PASS, contingent on tasks.md carrying the fixture work (tracked, not yet built — this is a plan gate, not an implementation gate).
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**: The "does this stage's list omit the inspection set without a recorded exception" and "does repository guidance mandate a command a stage cannot run" judgments (FR-015) are implemented as Gate 27 code reading the table and workflow literals — not left to a human or agent's reading of prose. PASS.

No violations requiring the Complexity Tracking table.

## Project Structure

### Documentation (this feature)

```text
specs/051-read-only-inspection-policy/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── inspection-policy.md
│   └── gate-extensions.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This is not an application with a src/tests split; it is a GitHub Actions
pipeline. The feature's real "source" is the existing tree below — every
listed path already exists and is edited in place, save for the two new
`contracts/*.md` files above, which are planning artifacts, not code the
pipeline runs.

```text
.github/
├── actions/
│   └── wing-commander-tool-args/action.yml   # extend the render (FR-002/FR-004)
├── scripts/
│   ├── verify-stage-tool-lists.py            # Gate 27 — new policy-drift checks (FR-014/FR-015)
│   └── verify-tooling-statement.py           # Gate 21 — new render cases/mutations (FR-014)
└── workflows/
    ├── intake.yml       # default-allowed-tools: inspection set + printenv (FR-003/FR-011/FR-012)
    ├── clarify.yml       # default-allowed-tools: inspection set; prompt: gh api route sentence (FR-003/FR-007)
    ├── plan.yml           # default-allowed-tools: drop gh auth status; prompt: gh api route sentence (FR-007/FR-013)
    ├── tasks.yml         # default-allowed-tools: drop gh auth status (FR-013)
    └── implement.yml     # default-allowed-tools: inspection set; new preflight + gate-suite step (FR-003/FR-009/FR-009a)

specs/010-reusable-pipeline/contracts/
└── stage-interfaces.md                        # the policy's one written home (FR-001) + updated table rows

CLAUDE.md                                       # "Before pushing" scoped by audience (FR-009b)
```

**Structure Decision**: No new source tree — every change lands in the
existing contract document, the existing composite action, the existing two
gate scripts, and the existing five stage workflows. This matches how every
prior `specs/0NN-*` change to this same table (026, 037, 044) has shipped:
the table and the gates that check it are the "source" for this kind of
cross-cutting policy, not a new module.

## Complexity Tracking

*No Constitution Check violations. Table intentionally omitted.*
