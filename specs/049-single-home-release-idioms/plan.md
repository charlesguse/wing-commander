# Implementation Plan: Single home for the auto-release / auto-update shared idioms

**Branch**: `049-single-home-release-idioms` (spec branch:
`spec/049-single-home-release-idioms`) | **Date**: 2026-09-14 | **Spec**:
[spec.md](./spec.md)

**Input**: Feature specification from
`/specs/049-single-home-release-idioms/spec.md`

## Summary

`auto-release.yml` re-typed three of `auto-update-spec-kit.yml`'s
hardest-won shell idioms (scoped App-token mint + reachability check,
orphan-branch force-reset, durable failure issue) instead of consuming a
shared definition, and separately hand-builds its own fail-infra verdict
object at 14 sites instead of the one helper the `poll` step already
demonstrates. This plan consolidates each into exactly one home — three
new composite actions and one script under the underscore-prefixed
`.github/actions/_shared/` convention (extended here from scripts to
composite shape, per FR-022) — puts a new structural gate (Gate 52) behind
the rule so a third paste fails CI rather than review, and corrects two
records (`docs/architecture.md`'s missing Auto-Release section, and spec
045's tasks.md/finalize-narrative claims that don't match `origin/main`)
so they describe the tree that actually shipped. Every deliberate
divergence between the two workflows' current copies (see research.md D5)
is preserved, not averaged, per FR-007.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflow/composite-action
syntax), Bash (POSIX-ish, `set -uo pipefail` convention already used
throughout this repository's workflow shell), Python 3 (gate scripts,
matching every other `verify-*.py` in `.github/scripts/`).

**Primary Dependencies**: GitHub Actions (`actions/checkout@v5`,
`actions/create-github-app-token@v3`), `gh` CLI, `jq`. No new external
dependency — every tool this feature uses is already invoked elsewhere in
the repository's workflow fleet.

**Storage**: N/A — no runtime data store. Persistent artifacts are the
repository's own files (workflows, composite actions, docs, a JSON waiver
file).

**Testing**: Gate self-tests (`--self-test` flags and unconditional
mutation-kill checks, per the two prior-art gates this feature follows —
`verify-comment-canonical-pointers.py`, `verify-metrics-summary-record-emission.py`)
run through `.github/scripts/run-local-gates.py`, mirrored in
`.github/workflows/lint-workflows.yml`'s PR-time gate job (constitution
VIII). No end-to-end run of `auto-release.yml`/`auto-update-spec-kit.yml`
themselves is part of this feature's test plan — FR-007's no-regression
bar is met by literal shell-content equivalence (verified by the gate
scripts and the byte-identity check in contracts/verdict-helper.md), not
by a live scheduled run, which is out of this feature's control and cost
budget.

**Target Platform**: GitHub Actions runners (`ubuntu-latest`, matching
every existing workflow/composite in this repository).

**Project Type**: Single repository, CI/CD pipeline infrastructure (no
`src`/`tests` application tree — see Project Structure below).

**Performance Goals**: N/A — this is CI configuration, not a service with
a throughput target. The only measurable cost property is CLAUDE.md's own
stated one (a pasted copy costs N future divergent fixes); this feature's
point is reducing that from 2 (or 11) to 1 per idiom.

**Constraints**: FR-021 — must land as a follow-up PR against `main`,
after #317, never folded into it. FR-020 — no private downstream consumer
named anywhere. Constitution VI (Portability) — nothing this feature adds
may hardcode a repository name/owner beyond this repository's own.
Constitution VIII — Gate 52 itself must satisfy every clause of "a green
check means what it says" (reachable via registry, same subject/args
locally and in CI, triggered by the files it checks, fails loudly when it
can't reach its subject, not suppressible by an unrelated gate, every
failure branch fixture-covered).

**Scale/Scope**: 3 new composite actions, 1 new shell script, 1 new gate
script + 1 new waiver JSON file, ~17 call-site edits across 2 existing
workflows (3 in `auto-release.yml` for the three idioms + 14 verdict
sites, though several overlap the same steps; 8 in `auto-update-spec-kit.yml`
— 1 token-mint pair, 1 reset, 4 failure-issue report sites), 1 new
`docs/architecture.md` section, 1 `tasks.md` line correction, 1 PR-body
metadata edit (PR #317), 1 constitution PATCH amendment.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1
design.*

- **I. Guide — the repo is its own first example**: PASS. This feature
  flows through the same intake → clarify(skipped, no markers) → plan →
  tasks → implement → converge → finalize pipeline as any other spec in
  this repository, tracked against lifecycle issue #326.
- **II. Cost-conscious model tiering**: N/A — this feature adds no new
  Claude agent invocation. The pipeline's own model tiering is unaffected.
- **III. Simple, GitHub-native interaction**: PASS — no new interaction
  surface; the feature is invisible to a spec requester and legible from
  issue #326 alone.
- **IV. Automation-first**: PASS — no new manual step. The one metadata
  edit that isn't a git commit (PR #317's body, FR-019) is itself
  automatable by the implement stage the same way any other `gh` call in
  this pipeline is; it is reported to the lifecycle issue like any other
  automated action (CLAUDE.md's "Every fix PR gets a code review" and
  "prove" step already cover how the eventual implementation PR is
  verified and reported).
- **V. Security — untrusted content is never instructions**: PASS — no
  change to token scoping policy (the composites reproduce, not widen, the
  two existing App-token-mint call sites' scopes) and no change to which
  content is treated as instructions. The new gate script reads only
  repository files, never issue/comment bodies.
- **VI. Portability**: PASS — nothing this feature adds hardcodes a
  repository name/owner; FR-020 makes this an explicit requirement, and
  contracts/records-corrections.md notes it is verified by the ordinary
  code-review pass every PR here gets.
- **VII. Two Interfaces**: DIRECTLY ENGAGED, not violated — this feature
  amends this principle (FR-024) to state explicitly that
  underscore-prefixed `.github/actions/` directories are internal, not
  published, closing the exact gap (an internal helper one promotion away
  from becoming pinnable by accident, FR-025) the edge case in spec.md
  names. The amendment is a PATCH clarification (research.md D10), not a
  new principle, and does not touch the published-stage/consuming-
  instrument split itself — `auto-release.yml` remains a consuming
  instrument, `auto-update-spec-kit.yml` remains a published stage
  reaching the same composites through its existing self-checkout
  convention (research.md D2).
- **VIII. A green check means what it says**: DIRECTLY ENGAGED — Gate 52 is
  designed from this principle outward (see Constitution Check re-check
  below and contracts/single-home-gate.md's "Wiring" section for how each
  clause is satisfied).
- **IX. Judgment that gates a durable action belongs in deterministic
  code**: PASS, and reinforced — Gate 52's pass/fail for "is this a
  re-paste" and "is this waiver still valid" is fragment/structure
  matching in Python, never a model's judgment call; the waiver mechanism
  itself (reused verbatim from Gate 31) is exactly this principle's own
  worked-example shape (a registered, stale-checked entry, not a comment a
  model or reviewer might silently accept).

No violations requiring Complexity Tracking.

### Re-check after Phase 1 design

Design artifacts (data-model.md, contracts/, quickstart.md) do not
introduce anything outside what the initial Constitution Check already
covered — no new agent invocation, no new interaction surface, no
widened token scope, no repository name hardcoded, and Gate 52's design
(contracts/single-home-gate.md) explicitly satisfies each of Principle
VIII's clauses:
- **Reachable through the gate registry**: named `verify-single-home-idioms.py`
  under `.github/scripts/`, matching every other gate's naming convention
  that `wc_gate_registry.py` globs for — no manual registration step
  exists to forget.
- **Same subject, same arguments, locally and in CI**: `run-local-gates.py`
  derives both the plain run and the `--self-test` run directly from
  `lint-workflows.yml`'s own steps (research.md D7) — there is no
  separate "local" invocation to drift from CI's.
- **Triggered by what it checks**: `lint-workflows.yml`'s existing gate
  job already triggers on `.github/workflows/**` and `.github/actions/**`
  changes; the new waiver file's path is added to that same trigger set at
  implementation time if not already covered (contracts/single-home-gate.md
  "Wiring").
- **Fails loudly when it can't reach its subject**: explicit zero-
  workflows-discovered / missing-declared-home checks, both hard failures
  (contracts/single-home-gate.md).
- **Not suppressible by an unrelated gate**: wired with `if: "!cancelled()"`
  in the same sequential job every other gate uses, not `continue-on-error`.
- **Every failure branch fixture-covered**: `--self-test` exercises all
  four checks, the promotion-prevention pass, and each waiver-shape
  failure mode via synthetic fixtures (contracts/single-home-gate.md),
  following Gate 47's tempdir-fixture precedent rather than a manual
  demonstration.

Constitution Check: PASS. Proceeding to Phase 2 (tasks) is authorized by
the pipeline's own stage gate — Gate 3 (plan review) is disabled for this
run per the operator prompt, so `/speckit-tasks` dispatches automatically.

## Project Structure

### Documentation (this feature)

```text
specs/049-single-home-release-idioms/
├── plan.md              # This file
├── research.md          # Phase 0 output — 12 design decisions (D1-D12)
├── data-model.md         # Phase 1 output — shared-definition field shapes
├── quickstart.md        # Phase 1 output — validation guide
├── contracts/           # Phase 1 output — one file per FR group
│   ├── scoped-app-token.md
│   ├── orphan-branch-reset.md
│   ├── durable-failure-issue.md
│   ├── verdict-helper.md
│   ├── single-home-gate.md
│   └── records-corrections.md
└── tasks.md              # Phase 2 output (/speckit-tasks — not this stage)
```

### Source Code (repository root)

This is CI/CD pipeline infrastructure, not an application with a
src/tests split. The real "source" this feature touches:

```text
.github/
├── actions/
│   ├── _shared/
│   │   ├── count-turns.sh                    # existing, unchanged
│   │   ├── scoped-app-token/action.yml        # NEW
│   │   ├── orphan-branch-reset/action.yml     # NEW
│   │   ├── durable-failure-issue/action.yml   # NEW
│   │   └── auto-release-verdict.sh            # NEW
│   ├── wing-commander-callout/                # existing, unchanged (D6)
│   ├── wing-commander-context/                # existing, unchanged (prior art for D1)
│   └── ...                                    # other existing composites, unchanged
├── scripts/
│   ├── verify-single-home-idioms.py           # NEW — Gate 52
│   ├── single-home-waivers.json               # NEW
│   ├── verify-stage-invariants.py             # existing — waiver-shape prior art (D8)
│   ├── verify-comment-canonical-pointers.py   # existing — Gate 47, detection-strategy prior art
│   ├── verify-metrics-summary-record-emission.py  # existing — literal-fragment-scan prior art
│   └── run-local-gates.py                     # existing, unchanged (auto-derives Gate 52)
└── workflows/
    ├── auto-release.yml                       # EDITED — 3 idiom sites + 14 verdict sites
    ├── auto-update-spec-kit.yml                # EDITED — token-mint pair, reset, 4 failure-issue sites
    └── lint-workflows.yml                      # EDITED — Gate 52 wiring

docs/
└── architecture.md                             # EDITED — new Auto-Release section (FR-017)

specs/045-auto-release-verified-head/
└── tasks.md                                    # EDITED — T023 correction (FR-018)

.specify/memory/
└── constitution.md                             # EDITED — Principle VII PATCH clarification (FR-024)

(PR #317's description — not a repository file — edited via `gh pr edit`
for FR-019, see contracts/records-corrections.md)
```

**Structure Decision**: No new top-level directory. This feature extends
two existing conventions in place — `.github/actions/_shared/` (scripts →
scripts + composites) and `.github/scripts/verify-*.py` (one more gate,
registry-derived, no manual wiring beyond the one `lint-workflows.yml`
step each new gate always needs) — rather than introducing a new one,
consistent with CLAUDE.md's "shared logic has exactly one home" applying
to the *pattern* of where shared logic goes, not just to this feature's
three idioms.

## Complexity Tracking

*No entries — Constitution Check recorded no violations.*
