# Implementation Plan: A Failed `gh api` Read Never Becomes Data

**Branch**: `spec/091-gh-api-error-capture` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/091-gh-api-error-capture/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

On an HTTP error, `gh api ... --jq '<filter>'` still prints the raw JSON
error body to stdout while the human-readable line goes to stderr and the
filter is never applied — so `x="$(gh api ...)"` leaves `x` holding
`{"message":"Not Found",...}` on failure, not an empty string. #497 fixed
one site (auto-release's slug fallback); this feature closes the other two
gaps the spec names: every other command-substitution capture of a
covered `gh api` read across `.github/workflows/` and `.github/actions/`
(FR-001–FR-004), and the harness stubs that simulate `gh` for the gates
that execute those sites, which must reproduce the two-stream failure
shape so a regression fails the harness instead of passing it vacuously
(FR-009–FR-011, FR-015).

Scoping this plan against `main`, 32 command-substitution captures of
`gh api` exist today across 13 files (`.github/actions/wing-commander-
fold-commit/action.yml`, `.github/actions/wing-commander-metrics-persist/
action.yml`, `.github/workflows/auto-release.yml`, `auto-update-spec-
kit.yml`, `board-loop.yml`, `lint-workflows.yml`, `pr-conversation.yml`,
`tasks.yml`, `watchdog.yml`, `wing-commander-7-cleanup.yml`, `wing-
commander-watchdog-test.yml`, plus two more found by the same grep —
research.md's scoping note has the full list with line numbers). Reading
a sample of these during planning already turned up one real instance of
the defect this feature exists to close — `wing-commander-fold-commit/
action.yml:92`'s `bot_login="$(gh api user --jq .login 2>/dev/null ||
true)"` followed only by `[ -n "$bot_login" ] || bot_login="wing-
commander-bot[bot]"`, which treats the non-empty error JSON as a present
value rather than a failure — confirming the audit is not a formality.

The approach is three parts, one per user story:

1. **User Story 1 (audit + fix)**: hand-correct every unsafe site found
   among the 32, or annotate the deliberate ones, using the smallest
   change that makes the failure path explicit (FR-002/FR-004) — no
   gate exists yet to check this against, so it is a manual pass recorded
   site-by-site (FR-001).
2. **User Story 2 (the gate)**: a new PR-time gate,
   `verify-gh-api-error-capture.py`, follows Gate 28's own shape (raw-text
   scan + quote-aware tokenizer, `CASES`/`MUTATIONS` self-test, a
   `wc-gh-api-error-exempt: <reason>` marker matching Gates 18/28's
   existing exemption convention) to classify every capture as exiting,
   reassigning, opted-in, or unsafe, reading the covered-subcommand list
   (FR-013: `gh api` only, for now) from one new shared constant so
   widening it later is a one-line change.
3. **User Story 3 (harness conformance)**: a second new gate,
   `verify-gh-error-stub-conformance.py`, mechanically derives which
   existing harness-driven gates execute a shipped block containing a
   covered capture (reusing the User Story 2 detector against each
   harness's own extracted subject text — FR-015), and fails any of them
   whose `gh`-error simulation does not come from one new shared helper in
   `wc_shell_harness.py` rather than a hand-rolled literal (FR-009–FR-012)
   — the same "single home, not a second copy" enforcement shape Gate 47
   already applies to canonical prose, applied here to a canonical shell
   fragment.

## Technical Context

**Language/Version**: Python 3 (stdlib + PyYAML, matching every other
`.github/scripts/verify-*.py`), Bash for the shipped `run:` blocks under
audit and the harness fixtures that exercise them.

**Primary Dependencies**: `wc_shell_harness.py` (shared harness plumbing —
gains the FR-009/FR-010 single-home error-stub helper), `wc_gate_registry.py`
(unchanged — the new scripts are ordinary `verify-*.py` gates, discovered
by the existing mechanical convention, no registry edit needed). No new
third-party dependency.

**Storage**: N/A — every entity is read from the checked-out tree
(workflow/action YAML text, `.github/scripts/verify-*.py` source) at
gate-run time. No baseline or allowlist file (FR-014 forbids one).

**Testing**: Each new gate's own `--self-test` flag against in-source
`CASES`/`MUTATIONS` fixtures (Gate 28's shape — the closer precedent for a
static text-pattern detector than the fixture-dir shape other gates use),
invoked directly and via `python .github/scripts/run-local-gates.py`.
FR-007's regression list (including "the exact shape the #497 review
found") and FR-011's "gate now fails where before it passed" are both
proven this way, not by a manual demonstration (constitution VIII).

**Target Platform**: GitHub Actions `ubuntu-latest` runners (CI) and a
maintainer's own machine — both new gates are pure static text analysis
with no subprocess execution of the audited workflows themselves, so none
of `wc_shell_harness.py`'s Windows-bash-resolution concerns apply to them
directly; they apply only insofar as this feature edits `wc_shell_harness.py`
itself, which existing harness-driven gates already exercise cross-platform.

**Project Type**: CI tooling embedded in this repository's own pipeline —
not an application with its own `src/`/`tests/` split. The "source tree"
for this feature is `.github/scripts/`, `.github/workflows/lint-
workflows.yml`, and the 13 files under `.github/workflows/`/`.github/
actions/` the audit corrects or annotates.

**Performance Goals**: Both new gates are a static scan over `.github/
workflows/*.yml` and `.github/actions/**/action.yml` (under 60 files
total) plus, for the conformance gate, a scan of the `.github/scripts/
verify-*.py` gate population (~120 files) — sub-second each, not a
measurable addition to `run-local-gates.py`'s documented wall-clock
budget.

**Constraints**: FR-013 restricts the covered surface to `gh api` reads
only — the detector must not flag `gh issue view`, `gh pr list`, `gh run
view`, etc., even though several of the 13 files also capture those (e.g.
the lifecycle-gate diagnostic FR-003 already resolved as out of scope).
FR-014 requires every one of the 32 live sites to be corrected or
annotated before either gate is wired into `lint-workflows.yml`'s
`pull_request` job, so the gate runs clean from its first commit — wiring
the gate before the audit is complete would make Gate <N> red on `main`
from the moment it lands, which is itself the kind of check nobody trusts
(constitution VIII).

**Scale/Scope**: 32 capture sites across 13 files today (see above and
research.md); of the existing harness-driven gates
(`wc_gate_registry.gate_scripts()`'s `*/run-tests.sh` entries plus
harness-shaped `verify-*.py` scripts that stub `gh` via
`wc_shell_harness.run_step`), `verify-auto-release-specs-fallback.py` is
confirmed in scope for FR-015's retrofit set — it already stubs a covered
`gh api` capture's error arm twice, duplicating the JSON-body/stderr-line
literal within one file, which is exactly the "second copy" FR-010
exists to catch once the shared helper lands. The full FR-015 set is
derived mechanically at implementation time, not hand-counted here
(research.md D7) — a hand count in this plan would itself become a second,
driftable copy of what the gate computes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle VIII (A Green Check Means What It Says)** — this feature is
  a direct instance of the principle's own concern: User Story 3 exists
  because a harness stub that leaves stdout empty on a simulated `gh`
  error lets a shipped capture bug pass vacuously (exactly #497's "first
  stub" history, quoted in spec.md). Both new gates are reachable through
  the existing mechanical gate registry the moment their `run:` line is
  wired into `lint-workflows.yml`, run the same script locally and in CI,
  are triggered by edits to the paths they check (already covered by the
  existing `.github/workflows/**`/`.github/actions/**` path filters — no
  filter edit needed), fail loudly rather than pass vacuously when their
  subject is unreachable (an empty scan result because a glob resolved to
  nothing is a bug in the gate, not a clean bill), and carry a
  self-test exercising every failure branch via checked-in fixtures. PASS.
- **Principle IX (Judgment That Gates a Durable Action Belongs in
  Deterministic Code)** — both gates are plain Python static-analysis
  scripts; "does this failure path exit, reassign, or carry a marker" and
  "does this stub call the shared helper" are mechanical text questions
  with no model in the loop, matching FR-002's own deterministic
  definition of "safe." PASS.
- **Principle II (Cost-Conscious Model Tiering)** — this feature adds no
  new Claude/agent invocation of any kind; it is pure gate tooling and a
  hand audit performed once during implementation. N/A, no tension.
- **Constitution VII (Two Interfaces)** — the audit touches `run:` step
  bodies inside several published composite actions (`wing-commander-
  fold-commit`, `wing-commander-metrics-persist`, and others FR-015's
  derivation may add), but FR-004 requires every correction to leave
  successful-read behaviour unchanged, and none of the fixes this feature
  makes add, remove, or rename an `action.yml` input, output, or secret —
  the published contract's compatibility surface is untouched. PASS.
- **CLAUDE.md "Shared logic has exactly one home"** — FR-010/FR-012 are
  this rule applied to a jq-adjacent shell fragment (a `gh`-error stub
  case arm) rather than a `run:` block; the plan places it in
  `wc_shell_harness.py`, the existing shared home for exactly this class
  of harness plumbing, and gives the new conformance gate the job of
  keeping it the only copy — the same shape the CLAUDE.md worked example
  describes for the per-run cost line. PASS.

No violations. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/091-gh-api-error-capture/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── gh-api-capture-check-cli.md
│   ├── gh-error-stub-conformance-cli.md
│   └── shared-module-additions.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature ships no application code; it changes this repository's own
CI tooling tree and a set of shipped workflow/action `run:` blocks.
Concrete paths, not the generic template options:

```text
.github/
├── scripts/
│   ├── wc_gh_capture.py                      # NEW shared module — FR-013's
│   │                                          #   one covered-subcommand list,
│   │                                          #   the capture-site scanner
│   │                                          #   reused by both new gates
│   ├── wc_shell_harness.py                    # gains: FR-009/FR-010's single
│   │                                          #   gh-error-stub-arm helper,
│   │                                          #   FR-012's version comment
│   ├── verify-gh-api-error-capture.py         # NEW gate (User Story 2) —
│   │                                          #   FR-001/002/005/006/007/008/
│   │                                          #   013/014
│   ├── verify-gh-error-stub-conformance.py    # NEW gate (User Story 3) —
│   │                                          #   FR-009/010/011/012/015
│   └── verify-auto-release-specs-fallback.py  # existing harness — migrates
│                                              #   its own two STUB_GH error
│                                              #   arms onto the new shared
│                                              #   helper (first FR-015
│                                              #   retrofit, confirmed in
│                                              #   scope — see Scale/Scope)
├── actions/
│   └── wing-commander-fold-commit/action.yml  # audit fix example found
│                                              #   during planning (Scale/
│                                              #   Scope) — one of the 32
│                                              #   sites User Story 1 covers
└── workflows/
    └── lint-workflows.yml                     # + two new gates' run/
                                              #   self-test step pairs
```

Plus every other file among the 32-site inventory (research.md) that the
audit finds unsafe — the exact subset is a User Story 1 output, not
predicted here.

**Structure Decision**: Single project — this repository's own
`.github/scripts` + `.github/workflows` + `.github/actions` tree, reviewed
as the subject of a CI-tooling feature rather than as this feature's
delivery vehicle. No `src/`/`tests/` split applies.

## Complexity Tracking

*No violations — this section intentionally left without rows.*
