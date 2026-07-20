# Implementation Plan: Pipeline Watchdog — Run Validation & Triage

**Branch**: `spec/015-pipeline-watchdog` | **Date**: 2026-07-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/015-pipeline-watchdog/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Add a tenth pipeline stage, `watchdog.yml` (+ wrapper
`wing-commander-8-watchdog.yml`), that inspects a completed pipeline run
— any of the other nine stages, or itself — and works down a triage
ladder from report-only to autonomous fix. Mechanically, each run is:

1. **Collected** by deterministic bash/jq steps, one per FR-006 evidence
   source (execution-output artifacts, step summaries, annotations,
   `spec-meta.json` vs. expected stage, branch-vs-origin drift), into one
   normalized `signals.json` — no LLM sees raw untrusted content
   directly (FR-023).
2. **Diagnosed** by a single `claude-haiku-4-5`, read-only, structured-
   output step that turns signals into zero or more Findings, each
   citing its evidence (FR-002) and carrying a proposed problem class.
3. **Fingerprinted** deterministically (`sha256(class + normalized
   facts)`, never model-generated) and **deduplicated** against every
   open/closed GitHub issue carrying that fingerprint's marker, reusing
   `rebase.yml`'s existing marker-in-body convention (FR-012–FR-016).
4. **Triaged** to a rung by a deterministic gate, not model opinion: a
   `claude-sonnet-5` step may attempt a fix diff for known-remediable
   classes; the gate checks that diff against
   `.specify/memory/watchdog-guardrails.json`'s allowlist/paths/line-cap
   (FR-011) to decide rung 1 (auto-fix PR, no prior issue needed) vs.
   rung 2 (PR referencing an existing/just-filed pipeline-defect issue)
   vs. rung 3 (issue only); ties resolve toward the higher rung
   (FR-010).
5. **Reported** — every finding and every autonomous action is posted to
   the inspected run's own lifecycle issue (FR-022), never silently.

Because rung 1 still requires a human's merge click (constitution V is
NON-NEGOTIABLE on this point — see research.md's explicit
without-clarification decision), "autonomous" describes how quickly and
independently the watchdog diagnoses and proposes a fix, not a bypass of
human merge review. Self-inspection (FR-021, US4) needs no special case:
the wrapper's own `workflow_run` trigger names itself, guarded from
runaway recursion by a self-dispatch-depth check
(`vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP`, FR-018).

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow
definitions), `jq` for JSON — identical toolchain to every other pipeline
stage; no new language introduced.

**Primary Dependencies**: GitHub Actions, `gh` CLI (including `gh search
issues`, `gh run list`/`gh run view`, `gh api` for annotations/step
summaries), `jq`, `git`, `anthropics/claude-code-action@v1` (two agent
steps: diagnose, propose-fix — see research.md), the repo's own
`.github/actions/wing-commander-context`, `wing-commander-preflight`, and
`wing-commander-metrics-summary` composites, reached via the same
pipeline-repo self-checkout every other stage performs. No new external
service or SDK.

**Storage**: `.specify/memory/watchdog-guardrails.json` (new,
consuming-repo-owned per constitution VI, holds the rung-1 change-class
allowlist and line caps — research.md). GitHub issues themselves are the
durable dedup ledger, identified via a `<!-- wing-commander-watchdog:
fingerprint=<sha256> -->` marker in the issue body (no new database, no
new file per fingerprint). `specs/NNN-slug/spec-meta.json` is read (never
written by the watchdog itself) as one of the five evidence sources.
`vars.WING_COMMANDER_WATCHDOG_PAUSED` and
`vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` are repo variables, not
files, so a maintainer can change them without a PR (research.md).

**Testing**: No automated test suite exists for any pipeline stage in
this repository (confirmed: no `package.json`, no test directories,
static validation only). This stage is validated the same way — this
plan's `quickstart.md` scenarios exercise all four user stories and the
spec's edge cases against scratch runs/issues, cross-checked against
`lint-workflows.yml` (YAML/bash-syntax gate) and `release.yml`
(actionlint + interface-invariant greps) that already gate every
workflow file in this repo, including the new one.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), triggered
by `workflow_run` (repo-wide, keyed on the other nine wrappers' display
names plus its own) and `workflow_dispatch` (manual re-inspection of a
specific run, FR-025).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/` and `.github/actions/`, reusing the existing
composite actions. No frontend/backend split.

**Performance Goals**: SC-007 — median time from a run finishing to
findings appearing on the lifecycle issue under 10 minutes. Achieved by
the collectors being pure bash/jq (seconds, not minutes) and reserving
the two agent steps for, respectively, a cheap haiku-tier classification
that runs on every invocation and a sonnet-tier fix-proposal that only
runs when a known-remediable class is diagnosed — both bounded by
declared `--max-turns` per constitution II.

**Constraints**: Never trusts inspected content (transcripts, artifacts,
summaries, issue/comment bodies) as instructions — always framed and
handled as data (FR-023, constitution V). Never fabricates a finding
when evidence is missing/expired/unreadable — records "could not
inspect" instead (FR-005). Never escalates beyond what a finding
warrants, and resolves ambiguity toward the higher (more human-involved)
rung (FR-007, FR-010). Rung-1 writes are bounded by a crisp, deterministic
three-condition gate (allowlisted change-class, allowlisted paths, line
cap) computed against an actual diff, never a model's self-assessment
(FR-011). Self-dispatch is hard-capped (FR-018). A maintainer can pause
autonomous fixes at any time via a repo variable, with the watchdog
falling back to report-only while paused (FR-019). Every autonomous
action is recorded on the lifecycle issue (FR-020). Complements, never
duplicates, `implement.yml`'s existing stalled-detection and
`cleanup.yml`'s `mark-stalled` job (FR-024). Least-privilege
`--allowedTools` per agent step (diagnose is read-only; propose-fix is
scoped to `.github/workflows/**`, `.github/actions/**`, `docs/**`, no
`git push`/`gh` access); no web tools; only trusted refs are ever
checked out (never a fork PR head); the watchdog never approves or
merges anything — every write that reaches `main` is a PR awaiting a
human's own merge click (constitution V, research.md's rung-1 decision).

**Scale/Scope**: One new stage file (`watchdog.yml`), one new wrapper
(`wing-commander-8-watchdog.yml`), one new consuming-repo-owned config
file (`.specify/memory/watchdog-guardrails.json`), and (per research.md's
coexistence decision) a small read added to the existing lost-progress
collector's logic — no changes to any of the other eight workflow files'
own job definitions are required, unlike `specs/007-cleanup-stage/`'s
consolidation, because coexistence here is a signal-suppression check
inside the *new* stage, not a retirement of logic inside the *existing*
ones. Concurrent specs and concurrent watchdog runs across different
inspected runs proceed independently
(`concurrency: wing-commander-watchdog-<run-id>`, one concurrency group
per inspected run rather than per spec, since one spec's several stage
runs can each need independent watchdog inspection without serializing
against each other).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue
  #80 → this spec → this plan → tasks → implementation), and once live,
  its own first real inspection target will be one of this very spec's
  own pipeline runs (plan/tasks/implement) — a live worked example the
  moment it ships. **Pass.**
- **II. Cost-Conscious Model Tiering**: Diagnose runs on
  `claude-haiku-4-5` ("triage, classification" — constitution's own
  wording), matching every invocation's actual cost profile (most runs
  produce no finding at all). Propose-fix runs on `claude-sonnet-5`
  (implementation-weight work), invoked only for findings with a
  known-remediable class. Both declare `--max-turns`. No stage-wide
  "always run the expensive model" path exists. **Pass.**
- **III. Simple, GitHub-Native Interaction**: A maintainer sees findings
  and autonomous actions on the lifecycle issue they already watch
  (FR-022); rung-1/rung-2 fixes surface as ordinary pull requests; rung
  3 as an ordinary issue. No new dashboard, no new CLI — course
  correction is `vars.WING_COMMANDER_WATCHDOG_PAUSED` (a standard repo
  variable) or closing/commenting on the resulting issue/PR like any
  other GitHub object. **Pass.**
- **IV. Automation-First**: The watchdog itself automates a step
  (post-run triage) that today is entirely manual, per spec.md's own
  framing; the one surviving manual step for rung 1/2 — clicking merge
  on a PR — is reported explicitly (the PR itself, plus the lifecycle-
  issue comment), never silently assumed done. **Pass.**
- **V. Security (NON-NEGOTIABLE)**: All inspected content is treated as
  data, never instructions (FR-023) — the diagnose step's prompt frames
  `signals.json` and any raw evidence it reads as untrusted input, the
  same framing every comment-triggered stage already uses for issue
  bodies. Least-privilege `--allowedTools` per agent step (research.md).
  No web tools. Only trusted refs checked out — never a fork PR head, and
  the propose-fix step never touches a spec's own branch, only the
  pipeline repository's own workflow/action/doc files. **The watchdog
  never approves or merges to `main` at any rung** — this is the precise
  point research.md's "made without explicit clarification" decision
  exists to protect; rung 1 is deliberately *not* read as "direct commit,
  no PR," specifically because that reading would violate this
  NON-NEGOTIABLE principle. Auth via the same `wing-commander-bot` App
  token as every other stage, minted per-job by `wing-commander-context`.
  **Pass.**
- **VI. Portability**: The new `.specify/memory/watchdog-guardrails.json`
  is placed alongside `.specify/memory/constitution.md`, matching this
  principle's own enumerated locations for consuming-repo-owned content —
  no new top-level convention invented, and no path is hardcoded to
  Wing Commander itself. The stage resolves the repository it's running
  in the same way every other stage does (`${{ github.repository }}`,
  the composite self-checkout at `github.job_workflow_sha`). **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/015-pipeline-watchdog/
├── plan.md               # This file (/speckit-plan command output)
├── research.md            # Phase 0 output (/speckit-plan command)
├── data-model.md          # Phase 1 output (/speckit-plan command)
├── quickstart.md          # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   └── watchdog-workflow.md
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── watchdog.yml                  # NEW — reusable stage (workflow_call only), this feature's primary artifact
│   └── wing-commander-8-watchdog.yml  # NEW — thin wrapper: workflow_run (9 named workflows incl. itself) + workflow_dispatch
└── actions/
    ├── wing-commander-context/        # Reused unchanged (App token + label/spec resolution)
    ├── wing-commander-preflight/      # Reused unchanged (deterministic pre-agent fail-fast)
    └── wing-commander-metrics-summary/ # Reused unchanged (post-agent metrics block); watchdog's two
                                        # agent steps each get one of these, same as every other stage

.specify/
└── memory/
    └── watchdog-guardrails.json      # NEW — consuming-repo-owned FR-017 allowlist (research.md)

docs/
└── architecture.md                   # Gains a "Stage 9 — Watchdog" section documenting the shape
                                        # above (tasks-phase concern, not this plan, but the target
                                        # design this plan fixes)
```

**Structure Decision**: Single-project CI/CD feature, no `src/`/`tests/`
split, matching every prior stage's own footprint. The primary artifact
is the new reusable stage `watchdog.yml` (jobs: `collect` → `diagnose` →
`triage` → `act`, where `act` fans out to whichever of
create-PR/create-issue/comment/reopen the deterministic rung gate
selected) plus its wrapper. Unlike `specs/007-cleanup-stage/`, no
existing workflow file needs a job retired — coexistence with
`implement.yml`'s stalled job and `cleanup.yml`'s `mark-stalled` job is
achieved by a read *inside* the new stage's own collector (research.md),
not by changing those two files.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
