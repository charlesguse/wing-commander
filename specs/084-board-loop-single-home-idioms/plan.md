# Implementation Plan: Single-home the remaining board-loop idioms

**Branch**: `084-board-loop-single-home-idioms` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/084-board-loop-single-home-idioms/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Three idioms are pasted across `.github/workflows/board-loop.yml`. Two are
still duplicated and this feature consolidates them: the 17-site
board-item-marker write bootstrap becomes a `python3 -I`-compatible
command-line entrypoint on the existing `board_item_marker.py` module
(never a composite, per FR-005a's Gate-98 constraint), and the 2-site
PR-branch resolution becomes an internal composite,
`.github/actions/_shared/resolve-pr-branch/action.yml` (per FR-009, never
published). The third — the kill-switch/stop-request recheck — was already
extracted into `.github/actions/wing-commander-board-stop-check` before
this spec was drafted, **and research.md D1 finds its structural
single-home gate (`board-stop-check` in `verify-single-home-idioms.py`)
already exists too**, landed in commit `98ee260`, an ancestor of the
spec's own `e170077` triage baseline — so this feature's User Story 3 work
on that idiom is verification only. `verify-single-home-idioms.py` (Gate
60) gains two new checks — `marker-write` and `pr-branch` — extending its
existing `DECLARED_HOMES`/`ALL_CHECKS`/self-test structure rather than
adding a new gate script (FR-015), with detection patterns chosen
(research.md D5/D6) to avoid two pre-existing, conceptually-unrelated
false-positive sites in `pr-conversation.yml` without needing a waiver
(SC-008).

## Technical Context

**Language/Version**: Python 3 (gate scripts, `board_item_marker.py`),
Bash (workflow `run:` steps, the new composite's shell step) — matching
every other file in `.github/scripts`/`.github/actions`.

**Primary Dependencies**: PyYAML (`verify-single-home-idioms.py`'s
existing YAML parsing), the GitHub CLI (`gh`, for `gh pr view` inside the
new composite) — no new dependency introduced.

**Storage**: N/A — no persistent state; the waiver file
(`.github/scripts/single-home-waivers.json`) is reused unchanged.

**Testing**: `verify-single-home-idioms.py --self-test` (synthetic-tempdir
fixtures, the existing Gate 60 harness), `python
.github/scripts/run-local-gates.py` (full PR-time gate suite, including
Gate 98's own provenance self-test), plus manual byte-identity comparison
of the 17 marker-write call sites' old vs. new output (quickstart.md
step 4).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), matching
the rest of the board loop.

**Project Type**: Single project — this is a GitHub Actions workflow
repository; there is no frontend/backend split.

**Performance Goals**: N/A — this is a structural refactor of CI shell,
not a performance-sensitive path.

**Constraints**: Gate 98's provenance allowlist (`ALLOWED_PYTHON_ARGS_RE`,
`ALLOWED_SYS_PATH`, `WORKTREE_SCRIPTS_RE` in
`verify-board-loop-helper-provenance.py`) must continue to pass for the
fix/review/readiness jobs with zero source changes to Gate 98 itself
(research.md D2 confirms the chosen invocation spelling already satisfies
it). FR-016: no observable board-loop behavior change (same markers, same
refs checked out, same stop signals) except the one deliberate exception
FR-008 states (PR-branch resolution now fails loudly instead of silently
checking out an empty ref).

**Scale/Scope**: 17 marker-write call sites across 5 jobs, 2 PR-branch
call sites across 2 jobs, 1 already-extracted idiom needing verification
only, 2 new checks added to one existing gate script.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide — The Repo Is Its Own First Example**: PASS. This feature is
  itself specified, planned, and implemented through the pipeline
  (`specs/084-board-loop-single-home-idioms`, issue #607).
- **II. Cost-Conscious Model Tiering**: N/A to this plan directly — no new
  agent invocation is introduced; the board loop's existing model tiers
  are untouched.
- **III. Simple, GitHub-Native Interaction**: PASS. No new external
  surface; the lifecycle stays legible on issue #607.
- **IV. Automation-First**: PASS. No new manual step is introduced.
- **V. Security**: PASS. No change to trust boundaries, tool allowlists,
  or the App-vs-PAT rule. The new composite and CLI entrypoint run with
  the same tokens (`github.token`) the call sites already use.
- **VI. Portability**: PASS. All changes are within this repository's own
  `.github/` tree; nothing bundled from or resolved against Wing
  Commander externally.
- **VII. Two Interfaces**: PASS, and directly load-bearing — FR-009
  requires the new PR-branch composite live under `.github/actions/
  _shared/` (internal, underscore-prefixed) rather than as a published
  `wing-commander-*` action, matching this principle's own carve-out for
  underscore-prefixed directories. Gate 60's existing promotion-prevention
  check continues to enforce this with no change needed.
- **VIII. A Green Check Means What It Says**: PASS, and directly
  load-bearing — FR-012/FR-013 require the two new checks be reachable
  through the gate registry (inherited for free per research.md D7),
  triggered by the files they scan (existing path filters already cover
  them), and proven able to fail their own subject via a self-test fixture
  (contracts/single-home-gate-extension.md's self-test section).
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: PASS. The single-home checks are deterministic pattern scans,
  not a prompt instruction; the PR-branch composite's empty-branch refusal
  (FR-008) is deterministic shell, not a model judgment call.
- **X. Bounded Autonomy**: N/A — this feature is routed through the
  feature lifecycle (spec-shaped: it spans multiple stages and required
  the clarify stage's questions per the spec's own routing), not the
  board loop's fix-PR path.

No violations. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── board-loop.yml                        # 17 marker-write sites + 2 PR-branch sites → single-home call sites
├── actions/
│   ├── _shared/
│   │   └── resolve-pr-branch/                # NEW: internal composite (FR-006/FR-009)
│   │       └── action.yml
│   └── wing-commander-board-stop-check/      # UNCHANGED — already the declared home (research.md D1)
│       └── action.yml
└── scripts/
    ├── board_item_marker.py                  # gains a CLI entrypoint (FR-005a); write_marker() body unchanged
    ├── board_eligibility.py                   # UNCHANGED — BREACH_STEP/AWAITING_MERGE_STEP stay its one home
    ├── verify-single-home-idioms.py          # Gate 60 — gains marker-write and pr-branch checks (FR-015)
    └── single-home-waivers.json               # UNCHANGED — no new entries expected (SC-008)
```

**Structure Decision**: single project (this repository IS the GitHub
Actions workflow/gate tree; there is no separate application source or
test directory split). Every change lives under `.github/`, matching how
every other single-home consolidation in this repository
(`specs/049-single-home-release-idioms`, `specs/057-autonomous-board-loop`)
was structured.

## Complexity Tracking

*No Constitution Check violations — this section is empty.*
