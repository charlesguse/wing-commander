# Implementation Plan: Watchdog Precision & Determinism Hardening

**Branch**: `spec/024-watchdog-precision-hardening` | **Date**: 2026-08-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/024-watchdog-precision-hardening/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

This feature is a retrospective-driven correction, not a new stage. It
closes five named gaps in `specs/015-pipeline-watchdog/spec.md` — no
precision requirement, no attribution invariant, a "stable" (not
deterministic) fingerprint, an unfalsifiable evidence-citation
requirement, and a self-inspection requirement contradicted by its own
shipped fix — plus a sixth, cross-cutting gap (nowhere is "gating
judgment belongs in deterministic code" written down), and a seventh
defect (a failed dedup lookup silently falls through to "file as new").
The deliverable is: (1) corrected/added requirements written directly
into `specs/015-pipeline-watchdog/{spec.md,data-model.md,contracts/
watchdog-workflow.md,quickstart.md}`; (2) a new governing principle in
`.specify/memory/constitution.md` recording the deterministic-judgment
lesson; (3) the `.github/workflows/watchdog.yml` code changes those
corrected requirements demand — attribution guards on the three
remaining collectors, a validity gate on cited evidence, a purely
signal-id-based fingerprint (dropping the model-fact fallback), a fourth
`unknown` dedup outcome with a bounded direct-read lookup, and removal of
rungs 1–2 (auto-fix, PR) and everything that exists solely to support
them; and (4) deletion of the stale `specs/023-reliable-diagnose-verdict/`
directory. Per FR-021, nothing about detection recall, dedup-and-reopen
behavior for genuinely distinct findings, loop-prevention, or coexistence
changes except where one of the seven named gaps requires it.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML, `jq`, and
the existing Python inline block that stamps deterministic signal ids —
identical toolchain to spec 015; no new language introduced.

**Primary Dependencies**: `gh` CLI, `jq`, `git`,
`anthropics/claude-code-action@v1` (the `diagnose` step only — the
`propose-fix` step is removed with rungs 1–2). One dependency-shaped
change: the dedup lookup moves from `gh search issues` (an
eventually-consistent index) to `gh issue list --label` (a bounded,
strongly-consistent direct read), per FR-020 — both are `gh` subcommands
already used elsewhere in this workflow, so no new tool is introduced.

**Storage**: `.specify/memory/watchdog-guardrails.json` is **deleted**
(FR-014 removes rung 1 and its allowlist entirely — this is not a content
edit). `specs/015-pipeline-watchdog/spec.md`, `data-model.md`,
`contracts/watchdog-workflow.md`, and `quickstart.md` are amended in
place (this feature's requirements are explicitly framed as "changes to
the watchdog's existing specification"). `.specify/memory/
constitution.md` gains one new principle (FR-012/FR-013). `specs/
023-reliable-diagnose-verdict/` is deleted outright (FR-017; git history
is the record). No new storage location is introduced — the existing
`🐕 · <class>` label already applied to every pipeline-defect issue
becomes the durable, queryable class attribute FR-020 requires for the
bounded dedup read, so no new label taxonomy is needed for that
requirement. A maintainer applying a `disposition:confirmed` /
`disposition:false-positive` label per filed finding — see research.md —
is the only new GitHub-native primitive this feature introduces, and it
is a label, not a file.

**Testing**: No automated test suite exists for any pipeline stage in
this repository (unchanged from spec 015). Validation continues to be
`quickstart.md` scenarios cross-checked against `lint-workflows.yml` and
`release.yml`. `lint-workflows.yml` Gate 17
(`.github/scripts/verify-watchdog-fix-commit.py`) is **removed**, not
merely left in place: its subject (the rung-1/2 commit-construction
steps) no longer exists once FR-014 lands, and Constitution VIII forbids
a gate outliving the subject it checks (a gate whose subject was deleted
would either be dead code or would vacuously "pass" having checked
nothing). Gate 5 (the denied-tool collector fixture) is explicitly
**not** touched here — FR-022 names "the collector fixture gate" as
tracked separately under issue #139.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), unchanged
triggers (`workflow_run` + `workflow_dispatch`).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/`, unchanged.

**Performance Goals**: FR-016 requires SC-007 (spec 015's never-measured
10-minute latency claim) to be "either measured or explicitly deferred
with the reason recorded." Decision (research.md): restate it as
measurable from data GitHub already retains — `gh run view --json
updatedAt` (run completion) against the `createdAt` of the watchdog's own
report comment on the lifecycle issue — rather than deferring it, since
no new telemetry is needed to compute it.

**Constraints**: FR-021 (scope boundary) — this feature MUST NOT change
detection recall, dedup-and-reopen behavior for genuinely distinct
findings, loop-prevention caps, or coexistence with existing
stalled/cleanup automation, except where a named gap above requires it.
Concretely: extending the attribution guard to the three remaining
collectors suppresses signals that were never attributable to begin
with — a precision fix, not a recall regression, because a genuinely
attributable problem still satisfies "executed AND owned the artifact."
Removing the fingerprint's model-fact fallback removes drift, not
matching power, because the primary (signal-id) path already covers
every finding whose evidence-signal ids survive validation, and FR-008/
FR-009 now guarantee every filed finding has non-empty, well-shaped
cited facts before it reaches fingerprinting.

**Scale/Scope**: No new workflow files. Touched: `.github/workflows/
watchdog.yml` (three collectors gain the attribution guard; a new
evidence-validity gate before fingerprinting; the fingerprint step drops
its fallback branch; the dedup-search step is replaced by a
label-scoped `gh issue list` read with a fourth `unknown` outcome; the
`triage` job's `Check fix-class eligibility`/`Propose fix`/`Rung gate`
steps and the `act` job's rung-1/rung-2 PR steps are deleted; the
self-dispatch-depth step's write-suppression logic collapses to a single
issue-only path); `.specify/memory/watchdog-guardrails.json` (deleted);
`.github/scripts/verify-watchdog-fix-commit.py` (deleted) and
`lint-workflows.yml` Gate 17 (deleted); `specs/015-pipeline-watchdog/
{spec.md,data-model.md,contracts/watchdog-workflow.md,quickstart.md}`
(amended); `.specify/memory/constitution.md` (one new principle);
`specs/023-reliable-diagnose-verdict/` (deleted).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue
  #140 → this spec → this plan → tasks → implementation), and its
  subject is the pipeline's own watchdog — the repository correcting its
  own worked example after ~200 real runs is as direct a demonstration of
  this principle as exists in this repo. **Pass.**
- **II. Cost-Conscious Model Tiering**: No model tier changes. `diagnose`
  stays `claude-opus-5` (unchanged, issue #124's carve-out). Removing
  `propose-fix` (`claude-sonnet-5`, rung 1/2 only) *reduces* the number
  of paid agent invocations per run — no new agent step is added.
  **Pass.**
- **III. Simple, GitHub-Native Interaction**: The precision criterion is
  computed from ordinary GitHub labels a maintainer applies to filed
  issues (research.md), not a new dashboard. Rung removal makes the
  watchdog's *entire* remediation surface a single, already-existing
  GitHub object (an issue) — simpler for a maintainer to reason about
  than the four-outcome ladder it replaces. **Pass.**
- **IV. Automation-First**: Removing rungs 1–2 trades an unexercised
  automation path (zero rung-1/2 firings across ~200 runs, per spec.md's
  Assumptions and `docs/architecture.md:750-752`) for a correctness
  property (precision) that the retrospective shows the pipeline
  actually needs; this is a deliberate, spec-sanctioned narrowing
  (FR-014), not an unreported manual step — every prior autonomous-fix
  code path this removes was already gated behind a human merge click,
  so no manual step newly appears. **Pass.**
- **V. Security (NON-NEGOTIABLE)**: Untrusted-content handling (FR-023
  of spec 015) is unchanged by this feature (FR-021 scope boundary).
  Removing `propose-fix` *shrinks* the write surface (no more
  bot-authored diffs to `.github/workflows/**`), reducing, not
  increasing, this feature's security-relevant footprint. **Pass.**
- **VI. Portability**: `.specify/memory/watchdog-guardrails.json`'s
  deletion and the constitution amendment both stay inside the
  consuming-repo-owned locations this principle already enumerates; no
  new top-level convention is invented. **Pass.**
- **VII. Two Interfaces**: `watchdog.yml` remains `workflow_call`-only
  with no new `github.event.*`/`vars.*` reads; the changes here are
  entirely inside the reusable stage's own deterministic job logic.
  This feature does, however, remove two published `workflow_call`
  inputs (`propose-fix-model`, `propose-fix-max-turns`), which this
  principle names a breaking change on its own terms regardless of
  whether any step still reads them. Resolution: both inputs are
  re-added with their pre-024 types/defaults, described as
  deprecated-and-ignored (accepted for v2 compatibility only, no
  step reads either, removal scheduled for the next major — issue
  #140), rather than dropped outright. **Pass**, on that basis.
- **VIII. A Green Check Means What It Says**: This principle is the
  direct justification for deleting Gate 17 alongside rungs 1–2
  (research.md) rather than leaving it checking a subject that no longer
  exists, and for FR-018–FR-020's `unknown` dedup outcome, which is
  itself an instance of this principle applied retroactively — the old
  "search failed ⇒ treat as new" behavior let a broken lookup report a
  false "nothing found" the same way the principle's own prior-art list
  names. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/024-watchdog-precision-hardening/
├── plan.md               # This file (/speckit-plan command output)
├── research.md            # Phase 0 output (/speckit-plan command)
├── data-model.md          # Phase 1 output (/speckit-plan command)
├── quickstart.md          # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   └── watchdog-spec-amendments-delta.md
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
specs/015-pipeline-watchdog/
├── spec.md                 # AMENDED — FR/SC renumbering per this feature's Requirements section
├── data-model.md           # AMENDED — Finding/Fingerprint/Dedup-outcome/Triage-decision entities
├── contracts/
│   └── watchdog-workflow.md  # AMENDED — job contract loses rung 1/2, dedup contract gains `unknown`
└── quickstart.md           # AMENDED — Scenarios 5-7 (rung 1/pause/boundary) retired; new scenarios added

.github/
├── workflows/
│   └── watchdog.yml         # AMENDED — collectors, evidence-validity gate, fingerprint, dedup, triage/act
└── scripts/
    └── verify-watchdog-fix-commit.py  # DELETED — Gate 17's fixture, subject removed with rungs 1-2

.specify/
└── memory/
    ├── watchdog-guardrails.json  # DELETED — rung-1 allowlist, no longer meaningful
    └── constitution.md           # AMENDED — one new principle (deterministic-judgment)

specs/023-reliable-diagnose-verdict/  # DELETED — stale, abandoned, FR-017
```

**Structure Decision**: Single-project CI/CD feature, matching spec 015's
own footprint — no `src/`/`tests/` split. Every code change lands inside
`watchdog.yml`'s existing `collect`/`diagnose`/`triage`/`act` jobs; no new
job is added and one job's scope (`triage`) shrinks (propose-fix and the
rung gate are removed, dedup and fingerprinting are hardened in place).
The `report-unhandled-failure` safety-net job (spec 020) is untouched.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
