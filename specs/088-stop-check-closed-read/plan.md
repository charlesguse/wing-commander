# Implementation Plan: An Honest Read-Failure Policy for board-stop-check's Closed Check

**Branch**: `spec/088-stop-check-closed-read` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/088-stop-check-closed-read/spec.md`

## Summary

`wing-commander-board-stop-check`'s `closed-check` step delegates to
`wing-commander-lifecycle-gate` under `continue-on-error: true`, and its
comment claims that tolerance "keeps" the fallback behaviour of the code it
replaced. Both halves are wrong: the replaced code failed the job on a
failed read (the same errexit-active semantics every `shell: bash` step
runs under), and `continue-on-error: true` is a real fail-open change that
shipped as an accident. This plan makes the read-failure policy explicit
and **fail-loud** (FR-002) by removing `continue-on-error: true`, and
resolves the ordering conflict that removal creates with FR-003 (the
kill-switch re-check and stop-request scan must still run, and must still
be able to stand down the run as paused, even when the closed-check read
fails totally) by **reordering the composite's two steps**: the kill-switch/
stop-request step moves first and no longer depends on `closed-check`'s
output; `closed-check` moves second, runs fail-loud, and its own failure
now fails the composite (and therefore the `prove` job) after — not
instead of — the pause logic has run. The composite's `paused` output
becomes an OR of the two steps' independent results rather than one step
reading the other's output through `env:`.

Because FR-002 removes the only tolerated failure on this path, FR-005
(no false `pipeline-defect` from a tolerated `closed-check` annotation on a
green `prove` run) is satisfied by construction — the two states (green job,
`closed-check` error annotation) become mutually exclusive — and needs no
change to `lifecycle-gate` or the watchdog (FR-006).

The same misreading of errexit produced four more false comments
(`board-loop.yml`, `metrics-persist.yml`, `implement.yml`,
`lint-workflows.yml`) asserting a `shell: bash` step "runs without `-e`."
This plan corrects all five sites (the `board-stop-check` comment via
FR-001's own rewrite), gives the corrected fact exactly one canonical
statement — the new gate script's own docstring, following this
repository's existing convention of a gate's "WHY THIS EXISTS" section
stating the fact it defends — and points every other site at it with a
`-- see <script>.py.` pointer that Gate 47
(`verify-comment-canonical-pointers.py`) validates for the four workflow-file
sources. The new gate (FR-009) scans both `.github/workflows/*.yml` and
`.github/actions/**/action.yml`, deliberately not repeating Gate 24's
narrow glob (FR-012) — the FR-001 violation this feature fixes lives in an
action file, so a gate that could not see action files could not have
caught the mistake it exists to prevent. Gate 24's own docstring is
corrected to record that boundary explicitly and to point at a follow-up
issue for widening it, filed during implementation rather than by this plan.

`verify-board-stop-check.py` (FR-013) gains structural assertions
(`closed-check` carries no `continue-on-error`, and precedes it in step
order the kill-switch step does not depend on it) plus extended shell-case
coverage of the reordered `check` step and the composite's new `paused`
output expression, covering every SC-007 branch.

## Technical Context

**Language/Version**: Bash (`set -uo pipefail`, GitHub Actions `shell: bash`
steps, which run errexit-active from the outer `bash --noprofile --norc -eo
pipefail {0}` invocation regardless of what the script's own `set` line
says), YAML (GitHub Actions workflow/composite-action syntax), Python 3
(gate scripts under `.github/scripts/`)

**Primary Dependencies**: GitHub Actions (composite actions, `workflow_call`
stages), `gh` CLI, `jq`, PyYAML (gate scripts), this repo's own
`wc_shell_harness.py` (synthetic-repo, real-bash step execution) and
`wc_gate_registry.py` (PR-time gate discovery, consumed by
`run-local-gates.py`)

**Storage**: N/A — state is git history, the composite's own step outputs,
and `GITHUB_OUTPUT`/workflow run annotations; no database

**Testing**: Deterministic Python gate scripts (`.github/scripts/verify-*.py`)
that extract shipped `run:` blocks and comment text and execute/scan them
against synthetic fixtures, run locally via `python
.github/scripts/run-local-gates.py` and in CI via `lint-workflows.yml`

**Target Platform**: GitHub Actions runners (`ubuntu-latest`), Linux bash

**Project Type**: CI/CD pipeline (GitHub Actions reusable workflows +
composite actions) — not a library/service/app

**Performance Goals**: N/A — one extra `gh issue view` retry-hardened read
per `prove` run (already paid today); no throughput target

**Constraints**: `wing-commander-board-stop-check`'s published `paused`
output name and shape (`"true"`/`"false"`) MUST NOT change (Constitution
VII); `lifecycle-gate/action.yml` and `watchdog.yml` MUST NOT change
(FR-005 is satisfied by construction, FR-006 forbids a filtering remedy);
the `gh run cancel` stderr interpolation at `action.yml:171` MUST be left
alone (FR-011, sequenced with spec 087/#621); Gate 24's glob MUST NOT widen
in this feature (FR-012 records the boundary only); the four already-safe
"no `-e`" sites get comment-only corrections, not logic changes (FR-010,
already re-checked in spec.md's Observed Facts — each is safe under
correct errexit semantics)

**Scale/Scope**: One composite action's two-step reorder plus a new output
expression (`wing-commander-board-stop-check/action.yml`), five comment
corrections (four workflow files, one composite), one new gate script + its
`lint-workflows.yml` registration + self-test, one extension to
`verify-board-stop-check.py`, one documentation-only correction to
`verify-gate-24.py`'s docstring, and one follow-up issue filed during
implementation (Gate 24 widening, FR-012)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: N/A trigger — this is a bug fix to an already-published
  composite action, not a new capability; the fix itself ships through the
  pipeline (this spec, issue #623). **Pass.**
- **II. Cost-Conscious Model Tiering**: No agent invocation is added,
  changed, or removed by this feature — every change is deterministic
  YAML/bash/Python. **Pass, N/A.**
- **III. Simple, GitHub-Native Interaction**: FR-004's visibility
  requirement (naming the issue and the policy's consequence in the run
  itself) keeps the `prove` job's outcome legible without reading source;
  the plan/tasks/implement progression posts status to lifecycle issue
  #623 as usual. **Pass.**
- **IV. Automation-First**: No new manual step is introduced; the fix
  removes an accidental silent fail-open, it does not add one. **Pass.**
- **V. Security**: No change to trust boundaries, tool allowlists, or
  checkout refs. The composite still resolves through self-checkout and
  uses the same two tokens (`token`, `cancel-token`) for the same calls.
  **Pass.**
- **VI. Portability**: Every changed file lives under this repository's own
  `.github/actions/`, `.github/workflows/`, or `.github/scripts/`; nothing
  is bundled from or resolved outside the consuming repository's checkout.
  **Pass.**
- **VII. Two Interfaces**: `wing-commander-board-stop-check` is a published
  composite (resolved through self-checkout by every board-loop job). This
  feature changes its internal step order and how `paused` is computed, but
  not the composite's declared inputs, outputs, or their names/shapes — the
  `paused` output stays `"true"`/`"false"`. This is a behavior *correction*
  (fail-open was never the intended contract — FR-002's clarification
  answer says so explicitly) inside an unchanged signature, not a surface
  widening. **Pass.**
- **VIII. A Green Check Means What It Says**: This feature's own thesis.
  FR-009's new gate must be reachable through the registry, run the
  *shipped* comment text (not a copy), fail loudly rather than pass
  vacuously when it can't reach its subject, and carry mutation coverage
  proving it can fail. FR-012 records — rather than silently leaves — the
  one gate (24) that cannot see this feature's own primary fix site.
  **Pass by design.**
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: The read-failure policy (fail-loud vs. fail-open) is encoded as
  an `if:`/`continue-on-error:` structure in the composite's own YAML and
  bash, never left to an agent's judgment. **Pass.**
- **X. Bounded Autonomy**: `wing-commander-board-stop-check` is one of the
  board loop's own kill-switch/stop-request mechanisms (Principle X: "every
  durable action the loop takes stands behind deterministic code... the
  kill switch is clear"). This feature directly strengthens that guarantee
  for the `prove` job's close-or-redrive durable action: an undetermined
  issue state now stops the job rather than silently falling through.
  **Pass, and reinforces X.**

No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/088-stop-check-closed-read/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   ├── board-stop-check-composite.md   # Phase 1 output — the reordered
│   │                                     # step/output contract
│   └── errexit-claim-gate.md           # Phase 1 output — the new gate's
│                                         # scanning contract
└── tasks.md              # Phase 2 output (/speckit-tasks — not produced here)
```

### Source Code (repository root)

This is a CI/CD pipeline repository, not an application; there is no `src/`.
The feature's real "source" is GitHub Actions workflow and composite-action
YAML plus Python gate scripts:

```text
.github/actions/
└── wing-commander-board-stop-check/
    └── action.yml          # Reorder: kill-switch/stop-request step first
                              # (drops its ISSUE_IS_OPEN dependency),
                              # closed-check second (continue-on-error
                              # removed), new failure-visibility step third,
                              # composite `paused` output becomes an OR
                              # expression (FR-001, FR-002, FR-003, FR-004)

.github/workflows/
├── board-loop.yml          # Comment correction only (~line 1653, FR-007)
├── metrics-persist.yml     # Comment correction only (~line 348, FR-007)
├── implement.yml           # Comment correction only (current location
│                             # ~line 3013 — see research.md D9 on the
│                             # spec's now-stale 2785 citation; FR-007)
└── lint-workflows.yml      # Comment correction (~line 1921, FR-007) +
                              # new "Gate <N> — ..." registration and
                              # self-test (FR-009)

.github/scripts/
├── verify-errexit-claim-comments.py   # NEW — FR-009's gate; its own
│                                         # docstring is the FR-008
│                                         # canonical statement
├── verify-board-stop-check.py          # Extended: structural assertions on
│                                         # the reordered composite, extended
│                                         # SHELL_CASES, new paused-expression
│                                         # coverage (FR-013, SC-007)
└── verify-gate-24.py                   # Docstring-only correction: records
                                          # the `.github/workflows/*.yml`-only
                                          # scope and points at the widening
                                          # follow-up issue (FR-012)
```

**Structure Decision**: Single-project CI pipeline layout already
established by this repository (`.github/workflows/`, `.github/actions/`,
`.github/scripts/`); this feature edits one composite action, four
workflow comments, one gate-registration workflow, and three script files
in place, and adds one new script. No new top-level directory, no new
composite front door beyond the one already published
(`wing-commander-board-stop-check`).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. (No table needed.)
